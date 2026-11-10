"""CPU-only paired GPT-bank replay of the frozen valid-coverage policy."""
import argparse
from collections import defaultdict
import gzip
import hashlib
import itertools
import json
from pathlib import Path
import random
import statistics
import sys
import time

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT))
from reproduction.clean_ranking_v1.ranking import allocate, top_set
from reproduction.clean_ranking_v1.run import evaluate, percentile
from reproduction.research_env_v1.core import Episode, public_feedback


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path,obj):
    path.write_text(json.dumps(obj,sort_keys=True,indent=2,allow_nan=False)+'\n')


def compare(task_metrics, key):
    tasks=sorted(task_metrics)
    deltas=[task_metrics[t]['coverage_random'][key]-task_metrics[t]['valid_coverage_v1'][key]
            for t in tasks]
    if key=='best_hit':
        deltas=[-x for x in deltas]
    rng=random.Random(20261108093)
    samples=[statistics.fmean(rng.choices(deltas,k=len(deltas))) for _ in range(10000)]
    leave={t:statistics.fmean(d for i,d in enumerate(deltas) if tasks[i]!=t) for t in tasks}
    return dict(gain=statistics.fmean(deltas),ci95=[percentile(samples,.025),percentile(samples,.975)],
        tasks_positive=sum(d>1e-12 for d in deltas),tasks_negative=sum(d < -1e-12 for d in deltas),
        tasks_equal=sum(abs(d)<=1e-12 for d in deltas),leave_one_task_out=leave,
        leave_one_min=min(leave.values()),leave_one_max=max(leave.values()),
        leave_one_all_positive=all(v>0 for v in leave.values()))


def independent_policy(job,bank):
    rng=random.Random(job['seed']); chain=list(job['ids']);rng.shuffle(chain)
    chain=[tuple(sorted(p)) for p in zip(chain,chain[1:])]
    seen=set();trace=[]
    while len(trace)<job['budget']:
        remaining=sorted(tuple(sorted(p)) for p in itertools.combinations(job['ids'],2)
                         if tuple(sorted(p)) not in seen)
        if len(trace)<len(chain):
            edge=chain[len(trace)]
        else:
            vd=dict.fromkeys(job['ids'],0);qd=dict.fromkeys(job['ids'],0)
            for row in trace:
                for endpoint in (row['a'],row['b']):
                    qd[endpoint]+=1;vd[endpoint]+=int(row['valid'])
            rng.shuffle(remaining)
            edge=max(remaining,key=lambda p:(sum(vd[i]==0 for i in p),-min(vd[i] for i in p),
                        -sum(vd[i] for i in p),-sum(qd[i] for i in p)))
        seen.add(edge);trace.append(public_feedback(bank,*edge,.7))
    return trace


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--output',type=Path,required=True)
    args=ap.parse_args();out=args.output.resolve();assert not out.exists();out.mkdir(parents=True)
    start=time.monotonic()
    base=ROOT/'experiments/selection-frontier-02/banks'
    manifest=json.loads((base/'manifest.json').read_text())
    protocol=json.loads((ROOT/'experiments/selection-frontier-02/protocol.json').read_text())
    for p,d in protocol['frozen_sha256'].items():assert sha(ROOT/p)==d
    policy=ROOT/'research/policies/valid_coverage_v1.py';source=policy.read_text()
    jobs=[json.loads(x) for x in (ROOT/'experiments/clean-ranking-v1/prepared/jobs.jsonl').read_text().splitlines()]
    old_path=ROOT/'experiments/selection-frontier-01/d1/run_1/projected_full_traces.jsonl'
    old={r['job_id']:r['trace'] for line in old_path.read_text().splitlines()
         if (r:=json.loads(line))['method']=='coverage_random'}
    rows=[];checks=defaultdict(int)
    for run,meta in manifest['banks'].items():
        path=ROOT/meta['path'];assert sha(path)==meta['sha256']
        bank=json.loads(gzip.decompress(path.read_bytes()))
        for job in jobs:
            assert time.monotonic()-start < 600
            query=lambda a,b:public_feedback(bank[job['task']],a,b,.7)['winner']
            selected,random_trace=allocate(job['ids'],query,job['budget'],job['seed'],'coverage_random')
            trace=[public_feedback(bank[job['task']],a,b,.7) for a,b,_ in random_trace]
            assert [(r['a'],r['b']) for r in trace]==[(r['a'],r['b']) for r in old[job['job_id']]]
            rows.append(dict(bank=run,job_id=job['job_id'],task=job['task'],method='coverage_random',
                             selected=selected,trace=trace))
            namespace={};exec(compile(source,str(policy),'exec'),namespace)
            env=Episode(job,bank[job['task']],.7)
            while len(env.observed)<job['budget']:
                assert env.act(namespace['decide'](env.observation()))
            actual=env.trace
            assert actual==[{**r,'cached':False} for r in independent_policy(job,bank[job['task']])]
            chain_n=len(job['ids'])-1
            assert [(r['a'],r['b']) for r in actual[:chain_n]]==[(r['a'],r['b']) for r in trace[:chain_n]]
            checks['matched_random_schedule_episodes']+=1
            checks['matched_chain_episodes']+=1
            checks['independent_policy_trace_matches']+=1
            rows.append(dict(bank=run,job_id=job['job_id'],task=job['task'],method='valid_coverage_v1',
                             selected=env.selected(),trace=actual))
    assert len(rows)==5100 and len(jobs)==850
    decision_path=out/'decisions.sealed.jsonl.gz'
    decision_path.write_bytes(gzip.compress(''.join(json.dumps(r,sort_keys=True)+'\n' for r in rows).encode(),mtime=0))
    seal=dict(decisions_sha256=sha(decision_path),selection_evaluations=len(rows),labels_loaded=False,
        policy_sha256=sha(policy),script_sha256=sha(Path(__file__)),
        baseline_schedule_sha256=sha(old_path),bank_manifest_sha256=sha(base/'manifest.json'),
        frozen_inputs=protocol['frozen_sha256'],checks=dict(checks))
    write(out/'selection_seal.json',seal)
    # Labels are first opened after all selections and traces have been sealed.
    labels=json.loads((ROOT/'experiments/clean-ranking-v1/prepared/evaluation_labels.json').read_text())
    by_job={j['job_id']:j for j in jobs};grouped=defaultdict(list);episodes=[]
    metrics=('regret','best_hit','unique_reads','valid_edges','zero_valid_degree_candidates')
    for row in rows:
        job=by_job[row['job_id']];utility=labels[job['task']]
        result=evaluate(job['ids'],row['selected'],utility)
        best=max(utility[i] for i in job['ids']);worst=min(utility[i] for i in job['ids'])
        expected_regret=(best-statistics.fmean(utility[i] for i in row['selected']))/(best-worst) if best>worst else 0.
        assert abs(expected_regret-result['regret'])<1e-10
        assert result['best_hit']==sum(utility[i]==best for i in row['selected'])/len(row['selected'])
        vd=dict.fromkeys(job['ids'],0)
        for edge in row['trace']:
            if edge['valid']:
                vd[edge['a']]+=1;vd[edge['b']]+=1
        result.update(unique_reads=len(row['trace']),valid_edges=sum(e['valid'] for e in row['trace']),
                      zero_valid_degree_candidates=sum(v==0 for v in vd.values()))
        grouped[(row['bank'],row['task'],row['method'])].append(result)
        episodes.append({k:row[k] for k in ['bank','job_id','task','method']}|dict(metrics=result))
    runs=sorted(manifest['banks']);tasks=sorted(labels);methods=('coverage_random','valid_coverage_v1')
    per_task={run:{task:{method:{metric:statistics.fmean(r[metric] for r in grouped[(run,task,method)])
               for metric in metrics} for method in methods} for task in tasks} for run in runs}
    pooled={task:{method:{metric:statistics.fmean(per_task[run][task][method][metric] for run in runs)
             for metric in metrics} for method in methods} for task in tasks}
    all_summaries={}
    for name,data in list(per_task.items())+[('GPT_task_first_pooled',pooled)]:
        all_summaries[name]=dict(macro={method:{metric:statistics.fmean(data[t][method][metric] for t in tasks)
            for metric in metrics} for method in methods},
            comparisons={metric:compare(data,metric) for metric in ['regret','best_hit']})
    (out/'per_episode.jsonl').write_text(''.join(json.dumps(r,sort_keys=True)+'\n' for r in episodes))
    write(out/'per_task.json',dict(by_bank=per_task,GPT_task_first_pooled=pooled))
    write(out/'summary.json',dict(status='passed',version='frontier-02-GPT-allocation-replay-v1',
        jobs_per_arm_per_bank=850,banks=3,tasks=26,selection_evaluations=5100,
        confidence_gate=.7,aggregation='frozen top_set: win fraction, valid degree, uniform ties',
        selection_seal_sha256=sha(out/'selection_seal.json'),summaries=all_summaries,
        wall_seconds=time.monotonic()-start,new_model_calls=0,candidate_training_runs=0))
    write(out/'hashes.json',{p.name:sha(p) for p in out.iterdir() if p.is_file() and p.name!='hashes.json'})
    print(json.dumps(all_summaries))


if __name__=='__main__':main()
