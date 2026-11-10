#!/usr/bin/env python3
"""Independent arithmetic verification plus blocked-label selector replay."""
from collections import Counter, defaultdict
import gzip
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import random
import shutil
import sys
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0,str(ROOT))
sys.dont_write_bytecode = True


def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def load(p): return json.loads(Path(p).read_text())
def dump(p,x): Path(p).write_text(json.dumps(x,indent=2,ensure_ascii=False)+'\n')
def near(a,b): assert math.isclose(a,b,abs_tol=1e-12,rel_tol=1e-12),(a,b)


def main():
    out = Path(sys.argv[1]).resolve()
    dest = out/('verification_'+sys.argv[2])
    assert not dest.exists()
    dest.mkdir()
    shutil.copyfile(__file__,dest/'verify.snapshot.py')
    start = time.monotonic()
    summary = load(out/'summary.json')
    for relative,h in load(out/'output_sha256.json').items():assert sha(out/relative)==h,relative
    for relative,h in load(out/'input_sha256.json').items():
        if relative == 'protocol.json':p=HERE.parent/'protocol.json'
        else:p=ROOT/relative
        assert sha(p)==h,relative
    # Execute the snapshotted selection routine with execution-label file access blocked.
    spec=importlib.util.spec_from_file_location('factorial_snapshot',out/'experiment.snapshot.py')
    experiment=importlib.util.module_from_spec(spec);spec.loader.exec_module(experiment)
    # Snapshot module resolves HERE/ROOT from its directory; bind the original roots.
    experiment.HERE,experiment.ROOT=HERE,ROOT
    jobs=[json.loads(s) for s in (ROOT/'experiments/clean-ranking-v1/prepared/jobs.jsonl').read_text().splitlines()]
    banks={'DeepSeek':load(ROOT/'experiments/clean-ranking-v1/prepared/feedback.json')}
    manifest=load(HERE.parent/'banks/manifest.json')
    for name in summary['banks']:
        if name!='DeepSeek':
            with gzip.open(ROOT/manifest['banks'][name]['path'],'rt') as f:banks[name]=json.load(f)
    old={}
    with gzip.open(ROOT/'experiments/clean-ranking-v1/results/decisions.jsonl.gz','rt') as f:
        for line in f:
            row=json.loads(line)
            old[(row['job_id'],row['method'])]={k:row[k] for k in ('selected','trace','stats')}
            # Poison historical metric fields to prove selection ignores them.
            old[(row['job_id'],row['method'])]['metrics']={'regret':1e99,'best_hit':-1e99}
    blocked=ROOT/'experiments/clean-ranking-v1/prepared/evaluation_labels.json'
    original_open=Path.open
    attempts=[]
    def guarded_open(self,*a,**kw):
        if self.resolve()==blocked:
            attempts.append(str(self))
            raise AssertionError('Execution label read in selection phase')
        return original_open(self,*a,**kw)
    Path.open=guarded_open
    try:reselected,_=experiment.select_phase(dest,jobs,old,banks)
    finally:Path.open=original_open
    assert not attempts
    assert sha(dest/'selections.sealed.jsonl')==sha(out/'selections.sealed.jsonl')
    # Independent evaluator: integer cross-products, no frozen choose or score calls.
    labels=load(blocked)
    byid={j['job_id']:j for j in jobs}
    episodes={}
    task_lists=defaultdict(list)
    for row in reselected:
        job=byid[row['job_id']];ids=job['ids'];w,d=Counter(),Counter()
        for a,b,v,c in row['trace']:
            if v is not None:w[v]+=1;d[a]+=1;d[b]+=1
        if row['arm']!='actual_C0':
            smooth=row['arm'].endswith('smooth')
            nums={i:(w[i]+1,d[i]+2) if smooth else (w[i],d[i]) if d[i] else (1,2) for i in ids}
            sel=[]
            for i in ids:
                if all(nums[i][0]*nums[j][1]>nums[j][0]*nums[i][1] or
                       (nums[i][0]*nums[j][1]==nums[j][0]*nums[i][1] and d[i]>=d[j]) for j in ids):sel.append(i)
            assert sel==row['selected']
        vals=labels[row['task']];hi=max(vals[i] for i in ids);lo=min(vals[i] for i in ids)
        regret=0 if hi==lo else sum((hi-vals[i])/(hi-lo) for i in row['selected'])/len(row['selected'])
        hit=sum(vals[i]==hi for i in row['selected'])/len(row['selected'])
        key=(row['bank'],row['schedule'],row['arm'],row['task'])
        task_lists[key].append((regret,hit))
        episodes[(row['bank'],row['schedule'],row['arm'],row['job_id'])]=(regret,hit)
    for line in (out/'per_episode.jsonl').read_text().splitlines():
        row=json.loads(line);regret,hit=episodes[(row['bank'],row['schedule'],row['arm'],row['job_id'])]
        near(regret,row['metrics']['regret']);near(hit,row['metrics']['best_hit'])
    taskmean={k:(math.fsum(x[0] for x in rows)/len(rows),math.fsum(x[1] for x in rows)/len(rows)) for k,rows in task_lists.items()}
    gpt=[n for n in banks if n!='DeepSeek']
    if gpt:
        for task in sorted(labels):
            for arm in experiment.ARMS:
                rows=[taskmean[(n,'coverage_random',arm,task)] for n in gpt]
                taskmean[('GPT_task_first_mean','coverage_random',arm,task)]=tuple(math.fsum(r[m] for r in rows)/3 for m in (0,1))
    for row in load(out/'per_task.json'):
        vals=taskmean[(row['bank'],row['schedule'],row['arm'],row['task'])]
        near(vals[0],row['metrics']['regret']);near(vals[1],row['metrics']['best_hit'])
    for row in summary['macro']:
        vals=[taskmean[(row['bank'],row['schedule'],row['arm'],task)] for task in sorted(labels)]
        near(math.fsum(x[0] for x in vals)/26,row['metrics']['regret'])
        near(math.fsum(x[1] for x in vals)/26,row['metrics']['best_hit'])
    for name,row in summary['contrasts'].items():
        if 'baseline' in row:
            left,right=tuple(row['baseline']),tuple(row['intervention'])
            delta=[taskmean[(*left,t)][0]-taskmean[(*right,t)][0] for t in sorted(labels)]
        else:
            bank=name.split('/')[0]
            delta=[]
            for t in sorted(labels):
                a={arm:taskmean[(bank,'coverage_random',arm,t)][0] for arm in experiment.ARMS}
                delta.append(a['g50_raw']-a['g50_smooth']-a['g70_raw']+a['g70_smooth'])
        near(math.fsum(delta)/26,row['regret_gain']['mean'])
        rng=random.Random(20261108093)
        samples=sorted(math.fsum(delta[int(rng.random()*26)] for _ in range(26))/26 for _ in range(10000))
        bounds=[]
        for q in (.025,.975):
            pos=9999*q;l=int(pos);h=min(l+1,9999)
            bounds.append(samples[l]*(h-pos)+samples[h]*(pos-l) if l!=h else samples[l])
        for a,b in zip(bounds,row['regret_gain']['task_cluster_percentile_95']):near(a,b)
        loo=[(math.fsum(delta)-v)/25 for v in delta]
        near(min(loo),row['regret_gain']['leave_one_min']);near(max(loo),row['regret_gain']['leave_one_max'])
    receipt={'status':'passed','selection_replayed_with_label_file_reads_denied':len(reselected),
             'label_access_attempts':attempts,'poisoned_historical_metrics_selection_sha_matches':True,
             'independent_episode_scores':len(episodes),'independent_task_metrics':len(taskmean),
             'macro_rows':len(summary['macro']),'independent_task_bootstrap_and_leave_one_contrasts':len(summary['contrasts']),
             'hashes_verified':'all saved output hashes and bound input hashes',
             'elapsed_seconds':time.monotonic()-start,'summary_sha256':sha(out/'summary.json'),
             'verification_script_sha256':sha(__file__)}
    dump(dest/'receipt.json',receipt)
    dump(dest/'output_sha256.json',{str(p.relative_to(dest)):sha(p) for p in sorted(dest.rglob('*')) if p.is_file() and p.name!='output_sha256.json'})
    print(json.dumps(receipt,indent=2))


if __name__=='__main__':main()
