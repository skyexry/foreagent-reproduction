"""Actual C0 paths, then preregistered C/H/L/T final selection on revealed edges."""
import argparse
from collections import Counter, defaultdict
from fractions import Fraction
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
from reproduction.clean_ranking_v1.correctness import response_values
from reproduction.clean_ranking_v1.loader import load_world
from reproduction.clean_ranking_v1.ranking import top_set
from reproduction.clean_ranking_v1.run import evaluate, percentile, select

PROTOCOL_SHA='85355f6e117dd6770e28ea813df2bbbc6715d7ea0bb87835ad51b144395744c2'
ARMS=('C','H','L','T')
CONTRASTS={'C_minus_L':('C','L'),'C_minus_H':('C','H'),
           'H_minus_L':('H','L'),'L_minus_T':('L','T'),'C_minus_T':('C','T')}


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def objsha(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def write(path,obj):
    path.write_text(json.dumps(obj,indent=2,sort_keys=True,allow_nan=False)+'\n')


def feedback_edges(trace,bank,threshold):
    feedback=[]
    for edge in trace:
        item=bank['|'.join(sorted((edge['a'],edge['b'])))]
        index,confidence=response_values(item)
        winner=item['order'][index] if index is not None and confidence>=threshold else None
        feedback.append((edge['a'],edge['b'],winner))
    return feedback


def ranks(ids,feedback):
    wins=dict.fromkeys(ids,0);degree=dict.fromkeys(ids,0)
    for a,b,winner in feedback:
        if winner is not None:
            wins[winner]+=1;degree[a]+=1;degree[b]+=1
    return {i:(Fraction(wins[i],degree[i]) if degree[i] else Fraction(1,2),degree[i]) for i in ids}


def independent_top(ids,feedback,allowed=None):
    # Independent integer cross-products verify the legacy ratio/degree ranking.
    wins=dict.fromkeys(ids,0);degree=dict.fromkeys(ids,0)
    for a,b,winner in feedback:
        if winner is not None:
            degree[a]+=1;degree[b]+=1;wins[winner]+=1
    allowed=ids if allowed is None else allowed
    def better(a,b):
        an,ad=(wins[a],degree[a]) if degree[a] else (1,2)
        bn,bd=(wins[b],degree[b]) if degree[b] else (1,2)
        difference=an*bd-bn*ad
        return 1 if difference>0 else -1 if difference<0 else (degree[a]>degree[b])-(degree[a]<degree[b])
    best=allowed[0]
    for i in allowed[1:]:
        if better(i,best)>0:best=i
    return [i for i in allowed if better(i,best)==0]


def summary(data):
    tasks=sorted(data)
    macro={arm:{metric:statistics.fmean(data[t][arm][metric] for t in tasks)
                for metric in data[tasks[0]][arm]} for arm in ARMS}
    contrasts={}
    for name,(left,right) in CONTRASTS.items():
        contrasts[name]={}
        for metric in ('regret','best_hit'):
            deltas=[(data[t][left][metric]-data[t][right][metric])*(1 if metric=='regret' else -1) for t in tasks]
            rng=random.Random(20261108093)
            samples=[statistics.fmean(rng.choices(deltas,k=len(deltas))) for _ in range(10000)]
            loo={task:statistics.fmean(d for t,d in zip(tasks,deltas) if t!=task) for task in tasks}
            contrasts[name][metric]=dict(gain=statistics.fmean(deltas),ci95=[percentile(samples,.025),percentile(samples,.975)],
                tasks_improved=sum(d>1e-12 for d in deltas),tasks_unchanged=sum(abs(d)<=1e-12 for d in deltas),
                tasks_worsened=sum(d < -1e-12 for d in deltas),leave_one_task_out=loo,
                leave_one_min=min(loo.values()),leave_one_max=max(loo.values()),
                every_leave_one_positive=all(v>0 for v in loo.values()))
    return dict(tasks=len(tasks),macro=macro,contrasts=contrasts)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();out=args.output.resolve();assert not out.exists();out.mkdir(parents=True)
    start=time.monotonic();here=Path(__file__).resolve().parent
    assert sha(here/'protocol.json')==PROTOCOL_SHA
    (out/'protocol.snapshot.json').write_bytes((here/'protocol.json').read_bytes())
    (out/'experiment.snapshot.py').write_bytes(Path(__file__).read_bytes())
    write(out/'sensitivity_supplement.json',dict(stage='before any selection or score loading in this run',
        authorization='Parent clarified protocol D wording before execution; diagnostic only, no new pass criterion.',
        pool_size_groups=['n=10','n<10'],other_groups=['actual C0 singleton','actual C0 tied top','L selection equals C','L selection changes C'],
        full_26_task_analysis='primary and unchanged',bootstrap_seed=20261108093,bootstrap_draws=10000))
    frozen=json.loads((here.parent/'protocol.json').read_text())['frozen_sha256']
    for name,digest in frozen.items():assert sha(ROOT/name)==digest,name
    prepared=ROOT/'experiments/clean-ranking-v1/prepared'
    jobs=[json.loads(line) for line in (prepared/'jobs.jsonl').read_text().splitlines()]
    assert len(jobs)==850
    paths=json.loads((prepared/'code_files.json').read_text())
    code={t:{i:(ROOT/p).read_text() for i,p in d.items()} for t,d in paths.items()}
    for task,files in paths.items():
        for cid,path in files.items():assert sha(ROOT/path)[:20]==cid
    banks={'DS':json.loads((prepared/'feedback.json').read_text())}
    bm=json.loads((here.parent/'banks/manifest.json').read_text())
    for run,meta in bm['banks'].items():
        path=ROOT/meta['path'];assert sha(path)==meta['sha256']
        banks[run]=json.loads(gzip.decompress(path.read_bytes()))
    with gzip.open(ROOT/'experiments/clean-ranking-v1/results/decisions.jsonl.gz','rt') as f:
        saved={r['job_id']:r for line in f if (r:=json.loads(line))['method']=='corrected_tournament'}
    # Only saved selection/trace/ledger fields are accessed before score loading.
    module=load_world();rows=[];bank_checks={}
    for bank_name,bank in banks.items():
        check=Counter()
        for job in jobs:
            assert time.monotonic()-start<600
            task=job['task'];contents={i:code[task][i] for i in job['ids']}
            selected,trace,stats=select(module,job,bank[task],contents,'corrected_tournament',.7)
            assert len({tuple(sorted((r['a'],r['b']))) for r in trace})==len(trace)
            assert len(trace)<=job['budget'] and len(trace)==stats['unique_feedback_reads']
            # Re-run the same terminal procedure with only actually revealed bank rows.
            restricted={'|'.join(sorted((r['a'],r['b']))):bank[task]['|'.join(sorted((r['a'],r['b'])))] for r in trace}
            replayed,replay_trace,replay_stats=select(module,job,restricted,contents,'corrected_tournament',.7)
            assert (selected,trace,stats)==(replayed,replay_trace,replay_stats)
            check['terminal_replay_exact']+=1
            if bank_name=='DS':
                old=saved[job['job_id']]
                assert selected==old['selected'] and trace==old['trace'] and stats==old['stats']
                check['frozen_DS_selected_trace_ledger_exact']+=1
            high=feedback_edges(trace,bank[task],.7)
            low=feedback_edges(trace,bank[task],.5)
            assert [r[2] for r in high]==[r['winner'] for r in trace]
            keys=ranks(job['ids'],low);best=max(keys[i] for i in selected)
            chosen={'C':selected,'H':top_set(job['ids'],high),'L':top_set(job['ids'],low),
                    'T':[i for i in selected if keys[i]==best]}
            assert chosen['H']==independent_top(job['ids'],high)
            assert chosen['L']==independent_top(job['ids'],low)
            assert chosen['T']==independent_top(job['ids'],low,selected)
            if all(keys[i][1]==0 for i in selected):assert chosen['T']==selected
            check['alternative_selection_independent_integer_check']+=1
            record=dict(bank=bank_name,job_id=job['job_id'],task=task,n=len(job['ids']),
                selected=chosen,trace=trace,stats=stats,low_evidence=[list(x) for x in low],
                unique_reads=len(trace),high_valid_edges=sum(w is not None for a,b,w in high),
                low_valid_edges=sum(w is not None for a,b,w in low),C0_tied=len(selected)>1,
                L_changes_selection=set(chosen['L'])!=set(selected))
            record['selection_trace_sha256']=objsha(record)
            rows.append(record)
        bank_checks[bank_name]=dict(check)
        print(json.dumps(dict(stage='selection_sealed_in_memory',bank=bank_name,jobs=850,checks=dict(check))),flush=True)
    decision=out/'decisions.sealed.jsonl.gz'
    decision.write_bytes(gzip.compress(''.join(json.dumps(r,sort_keys=True)+'\n' for r in rows).encode(),mtime=0))
    inputs=dict(frozen,**{'experiments/selection-frontier-02/c0-final-selection/protocol.json':PROTOCOL_SHA,
        'experiments/selection-frontier-02/banks/manifest.json':sha(here.parent/'banks/manifest.json')})
    inputs.update({meta['path']:meta['sha256'] for meta in bm['banks'].values()})
    write(out/'selection_seal.json',dict(decisions_sha256=sha(decision),protocol_sha256=PROTOCOL_SHA,
        script_sha256=sha(Path(__file__)),jobs_per_bank=850,banks=4,selection_arms=4,selection_evaluations=13600,
        score_labels_loaded=False,inputs=inputs,bank_checks=bank_checks,
        policy='unmodified frozen C0 actual adaptive tournament; final C/H/L/T reaggregation of revealed unique edges'))
    print(json.dumps(dict(stage='all_selection_sealed',decisions_sha256=sha(decision))),flush=True)
    # First score-label access occurs after all four bank schedules/selections are sealed.
    labels=json.loads((prepared/'evaluation_labels.json').read_text())
    tasks=sorted(labels);grouped=defaultdict(list);by_job={j['job_id']:j for j in jobs};episodes=[]
    mechanism=defaultdict(lambda:defaultdict(list));subgroup=defaultdict(lambda:defaultdict(list))
    for row in rows:
        task=row['task'];bank=row['bank'];job=by_job[row['job_id']];utility=labels[task]
        metrics={}
        for arm in ARMS:
            s=row['selected'][arm];scored=evaluate(job['ids'],s,utility)
            best=max(utility[i] for i in job['ids']);worst=min(utility[i] for i in job['ids'])
            alternative=(best-statistics.fmean(utility[i] for i in s))/(best-worst) if best>worst else 0.
            assert abs(scored['regret']-alternative)<1e-10
            scored.update(unique_reads=row['unique_reads'],cache_reads=row['stats']['cache_reads'],
                budget_denials=row['stats']['budget_denials'],selected_size=len(s))
            metrics[arm]=scored;grouped[(bank,task,arm)].append(scored)
        if bank=='DS':
            for key in ('regret','best_hit'):assert abs(metrics['C'][key]-saved[row['job_id']]['metrics'][key])<1e-12
        gain=metrics['C']['regret']-metrics['L']['regret']
        assert abs(gain-((metrics['C']['regret']-metrics['H']['regret'])+(metrics['H']['regret']-metrics['L']['regret'])))<1e-12
        best_ids={i for i in job['ids'] if utility[i]==max(utility.values() if False else (utility[j] for j in job['ids']))}
        vd07=dict.fromkeys(job['ids'],0);vd05=dict.fromkeys(job['ids'],0)
        new_correct=[];old_correct=[];new_ties=old_ties=0
        for threshold,vd,target in ((.7,vd07,old_correct),(.5,vd05,new_correct)):
            for a,b,winner in feedback_edges(row['trace'],banks[bank][task],threshold):
                if winner is not None:
                    vd[a]+=1;vd[b]+=1
                    if threshold==.5:
                        item=banks[bank][task]['|'.join(sorted((a,b)))];_,conf=response_values(item)
                        if conf>=.7:continue
                    if utility[a]!=utility[b]:target.append(utility[winner]==max(utility[a],utility[b]))
                    elif threshold==.5:new_ties+=1
                    else:old_ties+=1
        episode=dict(bank=bank,task=task,job_id=row['job_id'],n=row['n'],C0_tied=row['C0_tied'],
            L_changes_selection=row['L_changes_selection'],L_selection_relation=(
                'unchanged' if set(row['selected']['L'])==set(row['selected']['C']) else
                'subset_of_C' if set(row['selected']['L'])<set(row['selected']['C']) else
                'disjoint_from_C' if not set(row['selected']['L'])&set(row['selected']['C']) else 'partial_overlap_C'),
            metrics=metrics,primary_gain=gain,
            mechanism=dict(high_valid_edges=row['high_valid_edges'],low_valid_edges=row['low_valid_edges'],
                added_valid_edges=row['low_valid_edges']-row['high_valid_edges'],
                best_zero_high=sum(vd07[i]==0 for i in best_ids)/len(best_ids),
                best_zero_low=sum(vd05[i]==0 for i in best_ids)/len(best_ids),
                high_strict_accuracy=sum(old_correct)/len(old_correct) if old_correct else None,
                added_strict_accuracy=sum(new_correct)/len(new_correct) if new_correct else None,
                high_strict_correct=sum(old_correct),high_strict_total=len(old_correct),
                added_strict_correct=sum(new_correct),added_strict_total=len(new_correct),
                high_score_ties=old_ties,added_score_ties=new_ties))
        episodes.append(episode)
        for group in [('n=10' if row['n']==10 else 'n<10'),
                      ('C0_tied' if row['C0_tied'] else 'C0_singleton'),
                      ('L_changes' if row['L_changes_selection'] else 'L_unchanged'),
                      ('improved' if gain>1e-12 else 'worsened' if gain < -1e-12 else 'unchanged')]:
            subgroup[(bank,group)][task].append(episode)
        for key,value in episode['mechanism'].items():
            if value is not None:mechanism[(bank,task)][key].append(value)
    metric_names=('regret','best_hit','unique_reads','cache_reads','budget_denials','selected_size')
    per_task={bank:{task:{arm:{k:statistics.fmean(r[k] for r in grouped[(bank,task,arm)])
              for k in metric_names} for arm in ARMS} for task in tasks} for bank in banks}
    gpt=[b for b in banks if b!='DS']
    pooled={task:{arm:{k:statistics.fmean(per_task[b][task][arm][k] for b in gpt)
                      for k in metric_names} for arm in ARMS} for task in tasks}
    all_summaries={bank:summary(data) for bank,data in per_task.items()}
    all_summaries['GPT_task_first_pooled']=summary(pooled)
    for bank,value in all_summaries.items():
        print(json.dumps(dict(stage='scored',bank=bank,macro=value['macro'],primary=value['contrasts']['C_minus_L']['regret'])),flush=True)
    group_summary={}
    for bank in banks:
        bank_groups={}
        relations=Counter(e['L_selection_relation'] for e in episodes if e['bank']==bank)
        for (b,group),values in subgroup.items():
            if b!=bank:continue
            task_gains={task:statistics.fmean(e['primary_gain'] for e in es) for task,es in values.items()}
            # Fixed full-analysis denominator makes subgroup contributions additive.
            task_counts={task:len(grouped[(bank,task,'C')]) for task in tasks}
            contribution=sum(sum(e['primary_gain'] for e in es)/task_counts[task]/26 for task,es in values.items())
            bank_groups[group]=dict(episodes=sum(map(len,values.values())),tasks=len(values),
                conditional_task_macro_gain=statistics.fmean(task_gains.values()),
                full_task_macro_contribution=contribution,per_task_gain=task_gains)
        group_summary[bank]=dict(groups=bank_groups,L_selection_relations=dict(relations))
        assert abs(sum(bank_groups[g]['full_task_macro_contribution'] for g in ['n=10','n<10'])-
                   all_summaries[bank]['contrasts']['C_minus_L']['regret']['gain'])<1e-12
    mechanism_out={}
    for bank in banks:
        data={task:{key:statistics.fmean(vals) for key,vals in mechanism[(bank,task)].items()} for task in tasks}
        keys=sorted({k for d in data.values() for k in d})
        macro={k:statistics.fmean(d[k] for d in data.values() if k in d) for k in keys}
        selected=[e for e in episodes if e['bank']==bank]
        strict={}
        for prefix in ('high','added'):
            correct=sum(e['mechanism'][prefix+'_strict_correct'] for e in selected)
            total=sum(e['mechanism'][prefix+'_strict_total'] for e in selected)
            strict[prefix]=dict(correct=correct,total=total,accuracy=correct/total if total else None)
        mechanism_out[bank]=dict(task_macro=macro,per_task=data,micro_strict_direction_accuracy=strict)
    ds=all_summaries['DS']['contrasts']['C_minus_L']['regret']
    gpt_gains=[all_summaries[b]['contrasts']['C_minus_L']['regret']['gain'] for b in gpt]
    pooled_result=all_summaries['GPT_task_first_pooled']['contrasts']['C_minus_L']['regret']
    criteria=dict(DS_gain_ge_01=ds['gain']>=.01,DS_all_leave_one_positive=ds['every_leave_one_positive'],
        GPT_pooled_positive=pooled_result['gain']>0,GPT_at_least_2_individual_positive=sum(g>0 for g in gpt_gains)>=2,
        GPT_individual_gains=gpt_gains,GPT_pooled_interval_excludes_zero=pooled_result['ci95'][0]>0)
    criteria['research_priority_pass']=all(criteria[k] for k in ['DS_gain_ge_01','DS_all_leave_one_positive','GPT_pooled_positive','GPT_at_least_2_individual_positive'])
    criteria['decision']='research_priority_only_development_scope' if criteria['research_priority_pass'] else 'no_overall_promotion'
    (out/'per_episode.jsonl').write_text(''.join(json.dumps(e,sort_keys=True)+'\n' for e in episodes))
    write(out/'per_task.json',dict(by_bank=per_task,GPT_task_first_pooled=pooled))
    write(out/'subgroups.json',group_summary)
    write(out/'mechanisms.json',mechanism_out)
    result=dict(status='passed',id='c0-final-selection-03',protocol_sha256=PROTOCOL_SHA,
        jobs_per_bank=850,banks=4,tasks=26,selection_arms=4,selection_evaluations=13600,
        summaries=all_summaries,criteria=criteria,checks=bank_checks,selection_seal_sha256=sha(out/'selection_seal.json'),
        scope='26 previously inspected development tasks; DS discovery and 3 repeated archived GPT feedback records; fixed same-bank actual C0 paths only; fresh-task confirmation remains separate.',
        wall_seconds=time.monotonic()-start,new_model_calls=0,new_training_runs=0,new_GPU_rentals=0)
    write(out/'summary.json',result)
    write(out/'hashes.json',{p.name:sha(p) for p in out.iterdir() if p.is_file() and p.name!='hashes.json'})
    print(json.dumps(dict(stage='complete',criteria=criteria,wall_seconds=result['wall_seconds'])),flush=True)


if __name__=='__main__':main()
