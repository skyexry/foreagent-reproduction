"""Leave-task/leave-repeat calibration, sealed prediction, then target scoring."""
import argparse
from collections import defaultdict
import gzip
import hashlib
import json
from pathlib import Path
import random
import statistics
import sys
import time

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT))
from reproduction.clean_ranking_v1.run import evaluate, percentile

PROTOCOL_SHA='682c0eb60e6466cbe2cb3f67681b3a161f4eb86e6b0dcab5ddacc19931733e76'


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path,value):path.write_text(json.dumps(value,sort_keys=True,indent=2,allow_nan=False)+'\n')


def read_lines(path):
    if path.suffix=='.gz':
        with gzip.open(path,'rt') as f:return [json.loads(x) for x in f]
    return [json.loads(x) for x in path.read_text().splitlines()]


def fit(data,source_banks,training_tasks):
    task_gains={task:statistics.fmean(data[bank][task]['C']['regret']-data[bank][task]['L']['regret']
               for bank in source_banks) for task in sorted(training_tasks)}
    mean=statistics.fmean(task_gains.values())
    loo={task:statistics.fmean(g for t,g in task_gains.items() if t!=task) for task in task_gains}
    enabled=mean>=.01 and all(g>0 for g in loo.values())
    return dict(source_banks=source_banks,training_tasks=sorted(training_tasks),
        training_task_gains=task_gains,training_mean_gain=mean,delete_one_training_task_gain=loo,
        min_delete_one_training_gain=min(loo.values()),enabled_L=enabled,treatment='L' if enabled else 'C')


def summarize(data):
    tasks=sorted(data);metrics=('regret','best_hit','unique_reads','cache_reads','budget_denials')
    macro={arm:{key:statistics.fmean(data[t][arm][key] for t in tasks) for key in metrics} for arm in ('C','L','K')}
    contrasts={}
    for name,(left,right) in {'C_minus_K':('C','K'),'L_minus_K':('L','K'),'C_minus_L':('C','L')}.items():
        contrasts[name]={}
        for key in ('regret','best_hit'):
            gain=[(data[t][left][key]-data[t][right][key])*(1 if key=='regret' else -1) for t in tasks]
            rng=random.Random(20261108093)
            draws=[statistics.fmean(rng.choices(gain,k=len(gain))) for _ in range(10000)]
            contrasts[name][key]=dict(gain=statistics.fmean(gain),ci95=[percentile(draws,.025),percentile(draws,.975)],
                positive_tasks=sum(g>1e-12 for g in gain),negative_tasks=sum(g < -1e-12 for g in gain),
                equal_tasks=sum(abs(g)<=1e-12 for g in gain),
                leave_one_task_out={task:statistics.fmean(g for t,g in zip(tasks,gain) if t!=task) for task in tasks})
    return dict(tasks=len(tasks),macro=macro,contrasts=contrasts,
        inference='descriptive paired task bootstrap of fixed out-of-fold predictions; overlapping calibration/training folds are dependent; no refitting inside bootstrap')


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--output',type=Path,required=True)
    ap.add_argument('--transfer-run',type=Path);args=ap.parse_args()
    out=args.output.resolve();assert not out.exists();out.mkdir(parents=True);start=time.monotonic()
    here=Path(__file__).resolve().parent;assert sha(here/'protocol.json')==PROTOCOL_SHA
    (out/'protocol.snapshot.json').write_bytes((here/'protocol.json').read_bytes())
    (out/'experiment.snapshot.py').write_bytes(Path(__file__).read_bytes())
    discovery=here.parent/'c0-final-selection/run-002'
    data=json.loads((discovery/'per_task.json').read_text())['by_bank']
    decisions=read_lines(discovery/'decisions.sealed.jsonl.gz')
    lookup={(r['bank'],r['job_id']):r for r in decisions}
    inputs={str((discovery/name).relative_to(ROOT)):sha(discovery/name) for name in ['per_task.json','decisions.sealed.jsonl.gz','selection_seal.json']}
    all_tasks=sorted(data['DS']);gpt=sorted(b for b in data if b!='DS')
    plans=[]
    for bank in ['DS']+gpt:
        plans.append(dict(analysis='discovery_leave_task_and_GPT_repeat',target_bank=bank,target_tasks=all_tasks,
            source_banks=['DS'] if bank=='DS' else [b for b in gpt if b!=bank],calibration_tasks=all_tasks,
            chronology='four archives used to design this protocol; discovery only'))
    common=[]
    if args.transfer_run:
        transfer=args.transfer_run.resolve()
        other=json.loads((transfer/'per_task.json').read_text())['available_new_banks']
        ds0=sorted(other);assert len(ds0)==2
        common=sorted(set.intersection(*(set(other[b]) for b in ds0)))
        assert len(common)>=3
        for bank in ds0:
            data[bank]=other[bank]
            for analysis,sources,training in [
                ('DS0_cross_repeat_common_tasks',[b for b in ds0 if b!=bank],common),
                ('DS1_to_DS0_direct_temperature_transfer',['DS'],all_tasks)]:
                plans.append(dict(analysis=analysis,target_bank=bank,target_tasks=common,
                    source_banks=sources,calibration_tasks=training,
                    chronology='temperature-0 additional comparison fixed before outcomes; common target tasks; DS1 direct transfer is a distinct preplanned sensitivity'))
        for row in read_lines(transfer/'decisions.sealed.jsonl.gz'):
            if row['bank'] in ds0:lookup[(row['bank'],row['job_id'])]=row
        for name in ['per_task.json','decisions.sealed.jsonl.gz','selection_seal.json']:
            p=transfer/name
            if p.exists():inputs[str(p.relative_to(ROOT))]=sha(p)
    calibration=[];prediction=[];fit_cache={}
    for plan in plans:
        for task in plan['target_tasks']:
            training=[t for t in plan['calibration_tasks'] if t!=task]
            fitted=fit(data,plan['source_banks'],training)
            assert task not in fitted['training_tasks']
            if plan['target_bank'] in gpt:assert plan['target_bank'] not in fitted['source_banks']
            fold=dict(analysis=plan['analysis'],target_bank=plan['target_bank'],target_task=task,**fitted)
            calibration.append(fold);fit_cache[(plan['analysis'],plan['target_bank'],task)]=fold
        for (bank,job_id),row in lookup.items():
            if bank!=plan['target_bank'] or row['task'] not in plan['target_tasks']:continue
            fold=fit_cache[(plan['analysis'],bank,row['task'])]
            prediction.append(dict(analysis=plan['analysis'],bank=bank,task=row['task'],job_id=job_id,
                treatment=fold['treatment'],selected={'C':row['selected']['C'],'L':row['selected']['L'],
                    'K':row['selected'][fold['treatment']]},
                source_selection_trace_sha256=row['selection_trace_sha256'],stats=row['stats']))
    write(out/'plans.json',dict(plans=plans,DS0_common_tasks=common,common_task_count=len(common),
        DS1_transfer_training='all available DS1 tasks except target task (25 of 26); target scoring on common DS0 tasks',
        unknown_judge_configuration='default C until calibrated',policy='training mean C-L >= .01 and every delete-one-training-task mean > 0'))
    write(out/'calibration.json',calibration)
    pred=out/'predictions.sealed.jsonl.gz'
    pred.write_bytes(gzip.compress(''.join(json.dumps(r,sort_keys=True)+'\n' for r in prediction).encode(),mtime=0))
    write(out/'selection_seal.json',dict(inputs=inputs,protocol_sha256=PROTOCOL_SHA,script_sha256=sha(Path(__file__)),
        calibration_sha256=sha(out/'calibration.json'),predictions_sha256=sha(pred),folds=len(calibration),
        predictions=len(prediction),target_score_labels_loaded=False,
        separation='calibration uses explicitly allowed source-bank/non-target-task C/L outcomes; target prediction selects sealed C or L IDs; target labels joined only after both outputs sealed'))
    print(json.dumps(dict(stage='calibration_and_predictions_sealed',folds=len(calibration),predictions=len(prediction))),flush=True)
    labels=json.loads((ROOT/'experiments/clean-ranking-v1/prepared/evaluation_labels.json').read_text())
    jobs={j['job_id']:j for line in (ROOT/'experiments/clean-ranking-v1/prepared/jobs.jsonl').read_text().splitlines() if (j:=json.loads(line))}
    episodes=[];grouped=defaultdict(list)
    for row in prediction:
        job=jobs[row['job_id']];utility=labels[row['task']];metrics={}
        for arm,selected in row['selected'].items():
            score=evaluate(job['ids'],selected,utility)
            score.update({k:row['stats'][k] for k in ['cache_reads','budget_denials']})
            score['unique_reads']=row['stats']['unique_feedback_reads']
            metrics[arm]=score;grouped[(row['analysis'],row['bank'],row['task'],arm)].append(score)
        episodes.append({k:row[k] for k in ['analysis','bank','task','job_id','treatment']}|dict(metrics=metrics))
    per_task={};summaries={};switches={}
    for plan in plans:
        key=plan['analysis']+'::'+plan['target_bank']
        values={task:{arm:{metric:statistics.fmean(r[metric] for r in grouped[(plan['analysis'],plan['target_bank'],task,arm)])
            for metric in ['regret','best_hit','unique_reads','cache_reads','budget_denials']} for arm in ['C','L','K']}
            for task in plan['target_tasks']}
        per_task[key]=values;summaries[key]=summarize(values)
        folds=[f for f in calibration if (f['analysis'],f['target_bank'])==(plan['analysis'],plan['target_bank'])]
        ep=[e for e in episodes if (e['analysis'],e['bank'])==(plan['analysis'],plan['target_bank'])]
        switches[key]=dict(tasks=len(folds),enabled_L_tasks=sum(f['enabled_L'] for f in folds),
            episodes=len(ep),enabled_L_episodes=sum(e['treatment']=='L' for e in ep),
            enabled_tasks=[f['target_task'] for f in folds if f['enabled_L']],
            training_task_counts=sorted(set(len(f['training_tasks']) for f in folds)),
            training_source_bank_counts=sorted(set(len(f['source_banks']) for f in folds)))
    # Family summaries remain secondary and accompany every configuration above.
    for analysis,family in [('discovery_leave_task_and_GPT_repeat',gpt)]+([
            ('DS0_cross_repeat_common_tasks',ds0),('DS1_to_DS0_direct_temperature_transfer',ds0)] if args.transfer_run else []):
        relevant=[per_task[analysis+'::'+b] for b in family]
        tasks=sorted(set.intersection(*(set(d) for d in relevant)))
        pooled={t:{arm:{m:statistics.fmean(d[t][arm][m] for d in relevant) for m in ['regret','best_hit','unique_reads','cache_reads','budget_denials']}
                   for arm in ['C','L','K']} for t in tasks}
        key=analysis+'::task_first_pooled';per_task[key]=pooled;summaries[key]=summarize(pooled)
    criteria=dict(stage='waiting_for_temperature0' if not args.transfer_run else 'temperature0_evaluated',
        development_discovery='DS1 and GPT3 designed after C/L signs; out-of-fold computations describe discovery data',
        new_temperature0='different archived predictions preregistered; same development tasks')
    if args.transfer_run:
        gains=[summaries['DS0_cross_repeat_common_tasks::'+b]['contrasts']['C_minus_K']['regret']['gain'] for b in ds0]
        pooled=summaries['DS0_cross_repeat_common_tasks::task_first_pooled']['contrasts']['C_minus_K']['regret']['gain']
        enabled=[switches['DS0_cross_repeat_common_tasks::'+b]['enabled_L_tasks'] for b in ds0]
        criteria.update(DS0_individual_gains=gains,DS0_pooled_gain=pooled,DS0_enabled_task_counts=enabled,
            cross_repeat_gate_enables_both=all(x>0 for x in enabled),both_banks_benefit=all(x>0 for x in gains),
            common_task_macro_ge_01=pooled>=.01)
        criteria['research_priority_pass']=criteria['cross_repeat_gate_enables_both'] and criteria['both_banks_benefit'] and criteria['common_task_macro_ge_01']
        criteria['decision']='calibration_gated_selector_research_priority' if criteria['research_priority_pass'] else 'configuration_specific_DS1_signal_remains'
    (out/'per_episode.jsonl').write_text(''.join(json.dumps(r,sort_keys=True)+'\n' for r in episodes))
    write(out/'per_task.json',per_task)
    write(out/'summary.json',dict(status='passed',summaries=summaries,switches=switches,criteria=criteria,
        inference='fixed heldout predictions only; overlapping training/calibration tasks induce dependence; task bootstrap intervals are descriptive; same-task repeats supply no new task confirmation',
        wall_seconds=time.monotonic()-start,new_model_calls=0,training_runs=0,GPU_runs=0))
    write(out/'hashes.json',{p.name:sha(p) for p in out.iterdir() if p.is_file() and p.name!='hashes.json'})
    for key,value in switches.items():print(json.dumps(dict(configuration=key,switches=value,
        gain_vs_C=summaries[key]['contrasts']['C_minus_K']['regret'],gain_vs_L=summaries[key]['contrasts']['L_minus_K']['regret'])),flush=True)
    print(json.dumps(dict(criteria=criteria,wall_seconds=time.monotonic()-start)),flush=True)


if __name__=='__main__':main()
