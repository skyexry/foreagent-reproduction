"""Independent tie check by enumerating shortlist membership and neighbor label lookups."""
from collections import Counter, defaultdict
import gzip
from itertools import combinations
import json
from pathlib import Path
from statistics import fmean
import numpy as np

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
out=HERE/'run-001'
s=json.loads((out/'summary.json').read_text())
rows=list(map(json.loads,gzip.open(out/'decisions.jsonl.gz','rt')))
per=json.loads((out/'per_task.json').read_text())
gt=json.loads((ROOT/'experiments/clean-ranking-v1/prepared/evaluation_labels.json').read_text())
neighbors=json.loads((out/'neighbors.json').read_text())
import sys
sys.path.insert(0,str(ROOT/'experiments/trajectory-weighted-judge-v1/train'))
from data import load_codes
codes=load_codes()
checked=0
for task,items in neighbors.items():
    blocked={n['ast_sha256'] for n in codes[task].values()};rp={}
    for other,pool in sorted(codes.items()):
        if other==task:continue
        seen=set(blocked);allowed=[]
        for i in sorted(pool):
            h=pool[i]['ast_sha256']
            if h not in seen:allowed.append(i);seen.add(h)
        for i in allowed:
            x=gt[other][i];scores=[gt[other][j] for j in allowed]
            rp[other,i]=(sum(v<x for v in scores)+.5*(sum(v==x for v in scores)-1))/(len(scores)-1) if len(scores)>1 else .5
    for i,pred in items.items():
        assert all(t!=task and codes[t][j]['ast_sha256'] not in blocked for t,j in pred['neighbors'])
        assert abs(fmean(rp[t,j] for t,j in pred['neighbors'])-pred['score'])<1e-11
        checked+=1
assert checked==877
acc=defaultdict(lambda:defaultdict(list))
for row in rows:
    task=row['task']; u=[gt[task][i] for i in row['ids']]; fam='DS' if row['bank']=='DS' else 'GPT'
    for arm in ('c0','fusion','embedding','shuffled_fusion'):
        r=row[arm];chosen=[i for i,x in enumerate(r) if x==min(r)]
        loss=(max(u)-fmean(u[i] for i in chosen))/(max(u)-min(u)) if max(u)>min(u) else 0
        acc[fam,task][arm+'_regret'].append(loss)
    if len(u)<4:continue
    # A subset is a possible top 3 iff no excluded candidate outranks any included candidate.
    r=row['c0']; groups=[z for z in combinations(range(len(u)),3)
                           if max(r[i] for i in z)<=min(r[i] for i in range(len(u)) if i not in z)]
    for slot,name in [(0,'first'),(1,'second')]:
        tied=[i for i,v in enumerate(u) if v==sorted(u,reverse=True)[slot]]
        prob=fmean(sum(i not in z for i in tied)/len(tied) for z in groups)
        acc[fam,task]['c0_'+name+'_4plus'].append(prob)
for (fam,t),m in acc.items():
    for k,values in m.items():assert abs(fmean(values)-per[fam][t][k])<1e-12,(fam,t,k)
assert abs(s['metrics']['DS']['c0_regret']-.26416156273452185)<1e-12
assert len(rows)==3400 and len({r['job'] for r in rows})==850
print('Verified 877 out-of-task neighbor predictions, 3400 decisions, four arms and exact top-3 membership frequencies.')
