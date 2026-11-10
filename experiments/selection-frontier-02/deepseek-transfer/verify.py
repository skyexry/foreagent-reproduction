#!/usr/bin/env python3
"""Standalone DS0 direction/selection/score/task-bootstrap verification."""
from collections import defaultdict
from fractions import Fraction
import gzip
import hashlib
import json
import math
from pathlib import Path
import random
import shutil
import sys
import time

HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
OUT=HERE/sys.argv[1];DEST=OUT/('verification_'+sys.argv[2]);assert not DEST.exists();DEST.mkdir()
shutil.copyfile(__file__,DEST/'verify.snapshot.py')
start=time.monotonic();checks=defaultdict(int)
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
load=lambda p:json.loads(Path(p).read_text())
def close(a,b):assert math.isclose(a,b,abs_tol=1e-11,rel_tol=1e-11),(a,b)
for p,h in load(OUT/'hashes.json').items():assert sha(OUT/p)==h,p
for p,h in load(OUT/'input_sha256.json').items():assert sha(ROOT/p)==h,p
seal=load(OUT/'selection_seal.json');assert sha(OUT/'decisions.sealed.jsonl.gz')==seal['decisions_sha256']
assert not seal['blocked_label_access_attempts']
manifest=load(HERE/'banks_1/manifest.json')
banks={}
for n,m in manifest['banks'].items():banks[n]=json.loads(gzip.decompress((ROOT/m['path']).read_bytes()))
jobs={j['job_id']:j for line in (ROOT/'experiments/clean-ranking-v1/prepared/jobs.jsonl').read_text().splitlines() if (j:=json.loads(line))}
labels=load(ROOT/'experiments/clean-ranking-v1/prepared/evaluation_labels.json')
episodes={(r['bank'],r['job_id']):r for line in (OUT/'per_episode.jsonl').read_text().splitlines() if (r:=json.loads(line))}
grouped=defaultdict(list)
def top(ids,edges,allowed):
    wins=dict.fromkeys(ids,0);degree=dict.fromkeys(ids,0)
    for a,b,w in edges:
        if w is None:continue
        wins[w]+=1;degree[a]+=1;degree[b]+=1
    keys={i:(Fraction(wins[i],degree[i]) if degree[i] else Fraction(1,2),degree[i]) for i in ids}
    best=max(keys[i] for i in allowed)
    return [i for i in allowed if keys[i]==best]
with gzip.open(OUT/'decisions.sealed.jsonl.gz','rt') as f:
    for line in f:
        row=json.loads(line);plain={k:v for k,v in row.items() if k!='selection_trace_sha256'}
        assert hashlib.sha256(json.dumps(plain,sort_keys=True,separators=(',',':')).encode()).hexdigest()==row['selection_trace_sha256']
        job=jobs[row['job_id']];task=job['task'];bank=banks[row['bank']][task];high=[];low=[]
        seen=set()
        for e in row['trace']:
            a,b=e['a'],e['b'];pair='|'.join(sorted((a,b)));assert pair not in seen;seen.add(pair)
            item=bank[pair];index=item['predicted_best_index']
            if type(index) is str and index in ('0','1'):index=int(index)
            if type(index) is not int or index not in (0,1):index=None
            try:
                raw=item.get('confidence',.5);assert type(raw) is not bool
                conf=float(raw);assert math.isfinite(conf) and 0<=conf<=1
            except (AssertionError,ValueError,TypeError):conf=0.;index=None
            winner=item['order'][index] if index is not None and conf>=.7 else None
            assert e['winner']==winner;close(e['confidence'],conf)
            high.append((a,b,winner));low.append((a,b,item['order'][index] if index is not None and conf>=.5 else None))
            checks['source_edge_directions']+=1
        assert len(seen)==row['stats']['unique_feedback_reads']<=job['budget']
        assert row['low_evidence']==[list(x) for x in low]
        assert row['selected']['H']==top(job['ids'],high,job['ids'])
        assert row['selected']['L']==top(job['ids'],low,job['ids'])
        assert row['selected']['T']==top(job['ids'],low,row['selected']['C'])
        checks['alternative_selection_sets']+=3
        utility=labels[task];hi=max(utility[i] for i in job['ids']);lo=min(utility[i] for i in job['ids'])
        for arm,selection in row['selected'].items():
            regret=0 if hi==lo else sum((hi-utility[i])/(hi-lo) for i in selection)/len(selection)
            hit=sum(utility[i]==hi for i in selection)/len(selection)
            target=episodes[(row['bank'],row['job_id'])]['metrics'][arm]
            close(regret,target['regret']);close(hit,target['best_hit']);close(target['unique_reads'],len(seen))
            grouped[(row['bank'],task,arm)].append((regret,hit))
            checks['independent_scores']+=1
new_data={n:{t:{a:{m:math.fsum(x[k] for x in grouped[(n,t,a)])/len(grouped[(n,t,a)])
          for k,m in enumerate(('regret','best_hit'))} for a in ('C','H','L','T')} for t in sorted(banks[n])} for n in banks}
reported=load(OUT/'per_task.json');prior=load(HERE.parent/'c0-final-selection/run-002/per_task.json')['by_bank']
for n,data in new_data.items():
    for t in data:
        for a in data[t]:
            for m,v in data[t][a].items():close(v,reported['available_new_banks'][n][t][a][m]);checks['task_metrics']+=1
common=manifest['common_tasks'];assert len(common)==10
for n,data in reported['matched_common_all_banks'].items():
    if n=='DS0_task_first_pooled':sources=new_data;names=list(new_data)
    elif n=='GPT_task_first_pooled':sources=prior;names=[b for b in prior if b!='DS']
    else:sources={**prior,**new_data};names=[n]
    for t in common:
        for a in ('C','H','L','T'):
            for m in ('regret','best_hit'):
                expected=math.fsum(sources[b][t][a][m] for b in names)/len(names)
                close(expected,data[t][a][m]);checks['matched_common_task_metrics']+=1


def quantile(samples,q):
    x=(len(samples)-1)*q;l=int(x);h=min(l+1,len(samples)-1);f=x-l
    return samples[l]*(1-f)+samples[h]*f


def inference(values,tasks,target):
    n=len(values);close(math.fsum(values)/n,target['gain'])
    rng=random.Random(20261108093)
    samples=sorted(math.fsum(values[int(rng.random()*n)] for _ in range(n))/n for _ in range(10000))
    for q,v in zip((.025,.975),target['ci95']):close(quantile(samples,q),v)
    for i,t in enumerate(tasks):close((math.fsum(values)-values[i])/(n-1),target['leave_one_task_out'][t])
    checks['independent_bootstrap_leave_one_contrasts']+=1


summary=load(OUT/'summary.json')
contrast={'C_minus_L':('C','L'),'C_minus_H':('C','H'),'H_minus_L':('H','L'),'L_minus_T':('L','T'),'C_minus_T':('C','T')}
for group,all_data in [('available_summaries',reported['available_new_banks']),('matched_common_summaries',reported['matched_common_all_banks'])]:
    for n,data in all_data.items():
        tasks=sorted(data);s=summary[group][n]
        for a in ('C','H','L','T'):
            for m in ('regret','best_hit'):close(math.fsum(data[t][a][m] for t in tasks)/len(tasks),s['macro'][a][m])
        for name,(a,b) in contrast.items():
            for m in ('regret','best_hit'):
                values=[(data[t][a][m]-data[t][b][m])*(1 if m=='regret' else -1) for t in tasks]
                inference(values,tasks,s['contrasts'][name][m])
for name,target in summary['judge_setting_actual_C0_gains'].items():
    if name.endswith('_available_tasks'):
        bank=name.removesuffix('_available_tasks');data=reported['available_new_banks'][bank]
    else:
        bank=name.removesuffix('_common_tasks');data=reported['matched_common_all_banks'][bank]
    tasks=sorted(data);values=[prior['DS'][t]['C']['regret']-data[t]['C']['regret'] for t in tasks]
    inference(values,tasks,target)
result={'status':'passed','checks':dict(checks),'summary_sha256':sha(OUT/'summary.json'),
        'execution':'standalone parser, Fraction selector, direct utility formulas, random-index bootstrap; main selection phase label-file block separately recorded',
        'elapsed_seconds':time.monotonic()-start,'script_sha256':sha(__file__)}
(DEST/'receipt.json').write_text(json.dumps(result,indent=2)+'\n')
(DEST/'hashes.json').write_text(json.dumps({p.name:sha(p) for p in DEST.iterdir() if p.is_file() and p.name!='hashes.json'},indent=2)+'\n')
print(json.dumps(result,indent=2))
