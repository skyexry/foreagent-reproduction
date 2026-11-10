"""Measure shortlist loss and evaluate a score-blind, task-held-out embedding reranker."""
import argparse
from collections import Counter, defaultdict
from functools import lru_cache
import gzip
import hashlib
from itertools import combinations
import json
from math import comb
from pathlib import Path
import random
from statistics import fmean
import sys

import numpy as np
from scipy.stats import rankdata

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
PREP=ROOT/'experiments/clean-ranking-v1/prepared'
TRAIN=ROOT/'experiments/trajectory-weighted-judge-v1'
sys.path.insert(0,str(TRAIN/'train'))
from data import load_codes


def save(path, obj):
    path.write_text(json.dumps(obj,indent=2,sort_keys=True,allow_nan=False)+'\n')


@lru_cache(maxsize=8192)
def top_subsets(ranks, k):
    """Uniform choice within the group crossing the k-th slot, lower ranks first."""
    threshold=sorted(ranks)[k-1]
    fixed=tuple(i for i,r in enumerate(ranks) if r<threshold)
    at=[i for i,r in enumerate(ranks) if r==threshold]
    return tuple(fixed+more for more in combinations(at,k-len(fixed)))


def slot_weights(values, slot):
    """Probability of each program occupying the given true slot (0-based)."""
    target=sorted(values,reverse=True)[slot]
    count=values.count(target)
    return [1/count if v==target else 0 for v in values]


def diag(ranks, utility):
    n=len(ranks)
    if n<4:
        return {}
    r=tuple(ranks); hi=max(utility); span=hi-min(utility)
    truth1,truth2=slot_weights(utility,0),slot_weights(utility,1)
    true_ranks=tuple(-x for x in utility)
    truth_masks=[sum(1<<i for i in pair) for pair in top_subsets(true_ranks,2)]
    shorts=top_subsets(r,3)
    both_out=[]; gap=[]
    for subset in shorts:
        mask=sum(1<<i for i in subset)
        both_out.append(fmean(float(mask & m == 0) for m in truth_masks))
        gap.append((hi-max(utility[i] for i in subset))/span if span else 0.)
    out={'both_out':fmean(both_out),'oracle_top3_regret':fmean(gap)}
    for k in (3,4):
        if n<=k:continue
        probs=[]; definite=[]
        for x in r:
            better=sum(z<x for z in r)
            probs.append(1-min(1,max(0,(k-better)/r.count(x))))
            definite.append(float(better>=k))
        for title,w in [('first',truth1),('second',truth2)]:
            out[f'{title}_{k+1}plus']=sum(p*t for p,t in zip(probs,w))
            out[f'{title}_certain_{k+1}plus']=sum(p*t for p,t in zip(definite,w))
    return out


def utility_metrics(ranks,u):
    picked=[i for i,x in enumerate(ranks) if x==min(ranks)]
    hi=max(u); span=hi-min(u)
    return dict(regret=fmean((hi-u[i])/span if span else 0. for i in picked),
                hit=fmean(float(u[i]==hi) for i in picked))


def record_scores(rows, labels, arms):
    # Reduce seeds, pools and GPT archives within task before task averaging.
    cells=defaultdict(lambda:defaultdict(list))
    for r in rows:
        u=[labels[r['task']][i] for i in r['ids']]
        for a in arms:
            metrics=utility_metrics(r[a],u)
            if a in ('c0','fusion'):
                metrics.update(diag(r[a],u))
            for k,v in metrics.items():
                cells['DS' if r['bank']=='DS' else 'GPT',r['task']][f'{a}_{k}'].append(v)
    return {f:{t:{m:fmean(obs) for m,obs in cell.items()} for (fam,t),cell in cells.items() if fam==f}
            for f in ('DS','GPT')}


def summarize(per_task):
    summary={}
    for fam,tasks in per_task.items():
        keys=sorted(set().union(*(d.keys() for d in tasks.values())))
        summary[fam]={k:fmean(d[k] for d in tasks.values() if k in d) for k in keys}
    return summary


def intervals(diffs):
    x=np.asarray(diffs,dtype=float)
    rng=np.random.default_rng(20261110)
    boot=x[rng.integers(0,len(x),size=(10000,len(x)))].mean(axis=1)
    return dict(gain=float(x.mean()),ci95=np.quantile(boot,[.025,.975]).tolist(),
                tasks_better=int((x>1e-12).sum()),tasks_worse=int((x< -1e-12).sum()),
                tasks_tied=int((abs(x)<=1e-12).sum()),leave_one_task_out_gain_range=[
                    float((x.sum()-x.max())/(len(x)-1)),float((x.sum()-x.min())/(len(x)-1))])


def retrieve(held, reference_scores, codes, vectors):
    """Access to a held-out fold's evaluation scores is structurally excluded."""
    assert held not in reference_scores and set(reference_scores)==set(codes)-{held}
    test=sorted(codes[held])
    blocked={codes[held][i]['ast_sha256'] for i in test}
    query=np.stack([vectors[held][i] for i in test])
    by_query=defaultdict(list)
    for t,us in sorted(reference_scores.items()):
        train=[i for i in sorted(us) if codes[t][i]['ast_sha256'] not in blocked]
        if not train:continue
        # Collapse identical syntax trees within this reference task before building percentiles.
        reps={}
        for i in train:reps.setdefault(codes[t][i]['ast_sha256'],i)
        train=list(reps.values())
        p=(rankdata([us[i] for i in train])-1)/(len(train)-1) if len(train)>1 else np.array([.5])
        perm=p.tolist();random.Random('embedding-rerank-v1|'+held+'|'+t).shuffle(perm)
        library=np.stack([vectors[t][i] for i in train])
        sim=query@library.T
        for row,q in enumerate(test):
            j=int(np.argmax(sim[row]))
            by_query[q].append((float(sim[row,j]),t,train[j],float(p[j]),perm[j]))
    predictions={}
    for i,matches in by_query.items():
        best=sorted(matches,key=lambda x:(-x[0],x[1],x[2]))[:3]
        assert len(best)==3 and len({x[1] for x in best})==3
        predictions[i]=dict(score=round(fmean(x[3] for x in best),12),shuffled=round(fmean(x[4] for x in best),12),
                            neighbors=[[x[1],x[2]] for x in best])
    return predictions


def main(out):
    out.mkdir(exist_ok=False)
    rr=[json.loads(l) for l in gzip.open(HERE/'ranks.jsonl.gz','rt')]
    labels=json.loads((PREP/'evaluation_labels.json').read_text())
    for r in rr:r['c0']=r.pop('ranks')
    c=record_scores(rr,labels,['c0'])
    s=summarize(c)
    ds=c['DS']; gate_tasks=sum(d.get('c0_first_certain_4plus',0)>0 or d.get('c0_second_certain_4plus',0)>0 for d in ds.values())
    counts=Counter(len(r['ids']) for r in rr if r['bank']=='DS')
    study=dict(baseline=s,ds_job_size=dict(counts),eligible_jobs=sum(v for k,v in counts.items() if k>=4),
               eligible_tasks=sum('c0_first_4plus' in d for d in ds.values()),tasks_with_guaranteed_misses=gate_tasks,
               gate=gate_tasks>=2 and s['DS']['c0_oracle_top3_regret']>.01)
    save(out/'summary.json',study)
    if not study['gate']:
        save(out/'per_task.json',c);return
    emb=TRAIN/'representation/run_1/embeddings.npz'
    assert hashlib.sha256(emb.read_bytes()).hexdigest()==json.loads((emb.parent/'receipt.json').read_text())['feature_sha256']
    codes=load_codes();vec=defaultdict(dict)
    with np.load(emb,allow_pickle=False) as items:
        for key,v in zip(items['code_keys'],items['code']):
            t,i=key.split('|');vec[t][i]=v.astype(float)/np.linalg.norm(v.astype(float))
    predictions={}
    for held in sorted(codes):
        reference={t:labels[t] for t in codes if t!=held}
        predictions[held]=retrieve(held,reference,codes,vec)
    save(out/'neighbors.json',predictions)
    for r in rr:
        p=predictions[r['task']]; rranks=rankdata([-p[i]['score'] for i in r['ids']]); cranks=rankdata(r['c0'])
        r['embedding']=rranks.tolist()
        r['fusion']=(cranks+rranks).tolist()
        r['shuffled_fusion']=(cranks+rankdata([-p[i]['shuffled'] for i in r['ids']])).tolist()
    (out/'decisions.jsonl.gz').write_bytes(gzip.compress(''.join(json.dumps(r)+'\n' for r in rr).encode(),mtime=0))
    per=record_scores(rr,labels,['c0','fusion','embedding','shuffled_fusion']); save(out/'per_task.json',per)
    study['metrics']=summarize(per);study['comparisons']={}
    for fam,d in per.items():
        study['comparisons'][fam]={}
        for baseline,arm in [('c0','fusion'),('c0','embedding'),('c0','shuffled_fusion'),('shuffled_fusion','fusion')]:
            study['comparisons'][fam][baseline+'_vs_'+arm]=intervals([v[baseline+'_regret']-v[arm+'_regret'] for _,v in sorted(d.items())])
    study['advance']=all(study['comparisons'][k]['c0_vs_fusion']['gain']>=.01 and
                         study['comparisons'][k]['c0_vs_fusion']['ci95'][0]>0 for k in ('DS','GPT'))
    save(out/'summary.json',study)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('output',type=Path)
    main(p.parse_args().output)
