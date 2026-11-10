"""Separate audits for allowed calibration labels and sealed target predictions."""
import argparse
from collections import defaultdict
import copy
import gzip
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import random
import statistics
import sys

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT))


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def close(a,b):assert abs(a-b)<1e-11,(a,b)


def dump(path,obj):path.write_text(json.dumps(obj,sort_keys=True,indent=2)+'\n')


def lines(path):
    with gzip.open(path,'rt') as f:return [json.loads(x) for x in f]


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--run',type=Path,required=True)
    args=ap.parse_args();run=args.run.resolve();here=Path(__file__).resolve().parent
    manifest=json.loads((run/'hashes.json').read_text())
    for p,d in manifest.items():assert sha(run/p)==d,p
    seal=json.loads((run/'selection_seal.json').read_text())
    for p,d in seal['inputs'].items():assert sha(ROOT/p)==d,p
    assert sha(run/'calibration.json')==seal['calibration_sha256']
    assert sha(run/'predictions.sealed.jsonl.gz')==seal['predictions_sha256']
    assert sha(run/'experiment.snapshot.py')==seal['script_sha256']
    plans=json.loads((run/'plans.json').read_text());cal=json.loads((run/'calibration.json').read_text())
    data={};source_rows={}
    for p in seal['inputs']:
        path=ROOT/p
        if path.name=='per_task.json':
            raw=json.loads(path.read_text())
            data.update(raw['by_bank'] if 'by_bank' in raw else raw['available_new_banks'])
        if path.name=='decisions.sealed.jsonl.gz':
            for row in lines(path):source_rows[(row['bank'],row['job_id'])]=row
    lookup={(p['analysis'],p['target_bank']):p for p in plans['plans']}
    spec=importlib.util.spec_from_file_location('snapshot_calibration',run/'experiment.snapshot.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    fit_checks=defaultdict(int)
    folds={}
    for row in cal:
        plan=lookup[(row['analysis'],row['target_bank'])];task=row['target_task']
        expected_tasks=sorted(t for t in plan['calibration_tasks'] if t!=task)
        expected_sources=plan['source_banks']
        assert row['training_tasks']==expected_tasks and row['source_banks']==expected_sources
        assert task not in expected_tasks
        if row['analysis']=='discovery_leave_task_and_GPT_repeat' and row['target_bank']!='DS':
            assert row['target_bank'] not in expected_sources and len(expected_sources)==2
        if row['analysis']=='DS0_cross_repeat_common_tasks':
            assert row['target_bank'] not in expected_sources and len(expected_sources)==1 and len(expected_tasks)==9
        values={t:statistics.fmean(data[b][t]['C']['regret']-data[b][t]['L']['regret'] for b in expected_sources)
                for t in expected_tasks}
        for t,value in values.items():close(row['training_task_gains'][t],value)
        expected=statistics.fmean(values.values());close(expected,row['training_mean_gain'])
        removed={t:statistics.fmean(g for name,g in values.items() if name!=t) for t in values}
        for t,gain in removed.items():close(row['delete_one_training_task_gain'][t],gain)
        decision=expected>=.01 and all(g>0 for g in removed.values())
        assert decision==row['enabled_L'] and row['treatment']==('L' if decision else 'C')
        # Adversarially alter every excluded target-task outcome, plus the entire
        # held-out target repeat where protocol requires whole-repeat exclusion.
        changed=copy.deepcopy(data)
        for b,tasks in changed.items():
            if task in tasks:
                tasks[task]['C']['regret']=1e9;tasks[task]['L']['regret']=-1e9
        if row['target_bank'] not in expected_sources:
            for scores in changed[row['target_bank']].values():
                scores['C']['regret']=-1e12;scores['L']['regret']=1e12
        assert module.fit(data,expected_sources,expected_tasks)==module.fit(changed,expected_sources,expected_tasks)
        folds[(row['analysis'],row['target_bank'],task)]=row
        fit_checks['target_task_excluded']+=1
        fit_checks['source_banks_and_training_tasks_match_plan']+=1
        fit_checks['fit_and_delete_one_rule_independent']+=1
        fit_checks['excluded_label_and_repeat_perturbation_invariant']+=1
    cal_result=dict(status='passed',folds=len(cal),checks=dict(fit_checks),verifier_sha256=sha(Path(__file__)),
        scope='calibration audit uses only allowed source-bank/non-target-task outcomes and independently checks bit; target-task and heldout-repeat adversarial perturbations leave fitted output exactly unchanged')
    dump(run/'calibration_verification.json',cal_result)
    prediction=lines(run/'predictions.sealed.jsonl.gz')
    labels=json.loads((ROOT/'experiments/clean-ranking-v1/prepared/evaluation_labels.json').read_text())
    jobs={j['job_id']:j for line in (ROOT/'experiments/clean-ranking-v1/prepared/jobs.jsonl').read_text().splitlines() if (j:=json.loads(line))}
    episodes={(r['analysis'],r['bank'],r['job_id']):r for line in (run/'per_episode.jsonl').read_text().splitlines() if (r:=json.loads(line))}
    grouped=defaultdict(list);checks=defaultdict(int)
    for row in prediction:
        fold=folds[(row['analysis'],row['bank'],row['task'])]
        source=source_rows[(row['bank'],row['job_id'])]
        assert row['treatment']==fold['treatment']
        assert row['selected']['C']==source['selected']['C'] and row['selected']['L']==source['selected']['L']
        assert row['selected']['K']==source['selected'][fold['treatment']]
        assert row['stats']==source['stats']
        assert row['source_selection_trace_sha256']==source['selection_trace_sha256']
        job=jobs[row['job_id']];utility=labels[row['task']]
        high=max(utility[i] for i in job['ids']);low=min(utility[i] for i in job['ids'])
        for arm,selected in row['selected'].items():
            regret=statistics.fmean((high-utility[i])/(high-low) if high>low else 0. for i in selected)
            hit=sum(utility[i]==high for i in selected)/len(selected)
            recorded=episodes[(row['analysis'],row['bank'],row['job_id'])]['metrics'][arm]
            close(regret,recorded['regret']);close(hit,recorded['best_hit'])
            close(recorded['unique_reads'],source['stats']['unique_feedback_reads'])
            key=row['analysis']+'::'+row['bank']
            grouped[(key,row['task'],arm)].append(dict(regret=regret,best_hit=hit,
                unique_reads=source['stats']['unique_feedback_reads'],cache_reads=source['stats']['cache_reads'],budget_denials=source['stats']['budget_denials']))
            checks['scores_independent']+=1
        checks['predictions_match_calibration_and_sealed_C_L']+=1
    task_result=json.loads((run/'per_task.json').read_text());summary=json.loads((run/'summary.json').read_text())
    for config,values in task_result.items():
        tasks=sorted(values)
        if not config.endswith('::task_first_pooled'):
            for task in tasks:
                for arm in ('C','L','K'):
                    for metric in ('regret','best_hit','unique_reads','cache_reads','budget_denials'):
                        close(values[task][arm][metric],statistics.fmean(r[metric] for r in grouped[(config,task,arm)]))
        else:
            analysis=config.split('::')[0]
            configs=[k for k in task_result if k.startswith(analysis+'::') and not k.endswith('::task_first_pooled')]
            if analysis=='discovery_leave_task_and_GPT_repeat':configs=[k for k in configs if not k.endswith('::DS')]
            for task in tasks:
                for arm in ('C','L','K'):
                    for metric in ('regret','best_hit','unique_reads','cache_reads','budget_denials'):
                        close(values[task][arm][metric],statistics.fmean(task_result[k][task][arm][metric] for k in configs))
        target=summary['summaries'][config]
        for arm in ('C','L','K'):
            for metric in ('regret','best_hit','unique_reads','cache_reads','budget_denials'):
                close(target['macro'][arm][metric],statistics.fmean(values[t][arm][metric] for t in tasks))
        for name,(a,b) in {'C_minus_K':('C','K'),'L_minus_K':('L','K'),'C_minus_L':('C','L')}.items():
            for metric in ('regret','best_hit'):
                delta=[(values[t][a][metric]-values[t][b][metric])*(1 if metric=='regret' else -1) for t in tasks]
                result=target['contrasts'][name][metric];close(result['gain'],statistics.fmean(delta))
                rng=random.Random(20261108093)
                draws=sorted(statistics.fmean(delta[math.floor(rng.random()*len(delta))] for _ in delta) for _ in range(10000))
                for q,reported in zip((.025,.975),result['ci95']):
                    x=(len(draws)-1)*q;i=int(x);f=x-i
                    close(reported,draws[i]*(1-f)+draws[min(i+1,len(draws)-1)]*f)
                checks['paired_fixed_prediction_CI_independent']+=1
    pred_result=dict(status='passed',predictions=len(prediction),checks=dict(checks),verifier_sha256=sha(Path(__file__)),
        scope='target selections independently checked against calibration bit and source C/L; direct label scoring; per-task/pooled metrics and fixed-prediction descriptive bootstrap rechecked')
    dump(run/'prediction_verification.json',pred_result)
    print(json.dumps(dict(calibration=cal_result,prediction=pred_result)))


if __name__=='__main__':main()
