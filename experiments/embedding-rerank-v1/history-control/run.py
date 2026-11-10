"""One-step paired simulation of which prior execution scores the ranker can see."""
import argparse
from collections import defaultdict
import gzip
import hashlib
import json
from pathlib import Path
import random
import sys

import numpy as np
from scipy.stats import rankdata
DIR=Path(__file__).resolve().parent
sys.path.insert(0,str(DIR.parent))
from study import PREP, ROOT, TRAIN, load_codes, intervals, save, utility_metrics
sys.path.insert(0,str(ROOT))
from reproduction.clean_ranking_v1.correctness import response_values


def history_score(chosen, vectors, reference):
    assert set(chosen)==set(reference)
    vals=(rankdata([reference[i] for i in chosen])-1)/(len(chosen)-1)
    near=np.argsort(-vectors,axis=1,kind='stable')[:,:3]
    return np.round(vals[near].mean(axis=1),12)


def main(out):
    if out.exists():raise FileExistsError(out)
    labels=json.loads((PREP/'evaluation_labels.json').read_text())
    codes=load_codes()
    sim={}; idx={}
    with np.load(TRAIN/'representation/run_1/embeddings.npz',allow_pickle=False) as e:
        keys=e['code_keys'].tolist()
        for t,ns in codes.items():
            ids=sorted(ns);v=e['code'][[keys.index(t+'|'+i) for i in ids]].astype(float)
            v/=np.linalg.norm(v,axis=1,keepdims=True)
            sim[t]=v@v.T;idx[t]={i:j for j,i in enumerate(ids)}
    manifest=json.loads((ROOT/'experiments/selection-frontier-02/banks/manifest.json').read_text())
    sources={'DS':PREP/'feedback.json',**{k:ROOT/v['path'] for k,v in manifest['banks'].items()}}
    data=[json.loads(s) for s in gzip.open(DIR.parent/'ranks.jsonl.gz','rt')]
    grouped=defaultdict(lambda:defaultdict(list)); eligible=set(); sizes={}; offered=defaultdict(int); missing=defaultdict(int)
    for bank,path in sources.items():
        archive=json.loads(gzip.decompress(path.read_bytes()) if path.suffix=='.gz' else path.read_bytes())
        for r in (r for r in data if r['bank']==bank):
            t,ids=r['task'],r['ids'];base=rankdata(r['ranks']);queryix=[idx[t][i] for i in ids]
            seen={codes[t][i]['ast_sha256'] for i in ids};lib=[]
            for i,source in sorted(codes[t].items()):
                h=source['ast_sha256']
                if h not in seen:lib.append(i);seen.add(h)
            n=min(len(lib)//2,10);sizes[r['job']]=n
            # Both selections are sealed before the shared test utilities are scored.
            for seed in range(5):
                arms={'c0':base,'random_history':base,'judge_history':base}
                if n>=3:
                    eligible.add(t)
                    rng=random.Random(f"advisor-history-v1|{t}|{r['job'].rsplit(':',1)[0]}|{seed}")
                    order=rng.sample(lib,2*n); rand=[]; chosen=[]
                    for a,b in zip(order[::2],order[1::2]):
                        coin=rng.choice((a,b));rand.append(coin)
                        fb=archive[t].get('|'.join(sorted((a,b))))
                        offered[bank]+=1
                        missing[bank]+=int(fb is None)
                        win,conf=response_values(fb) if fb is not None else (None,0.)
                        chosen.append(fb['order'][win] if win is not None and conf>=.7 else coin)
                    for arm,hist in [('random_history',rand),('judge_history',chosen)]:
                        assert not set(ids).intersection(hist) and len(set(hist))==n
                        revealed={i:labels[t][i] for i in hist}
                        memory=history_score(hist,sim[t][np.ix_(queryix,[idx[t][i] for i in hist])],revealed)
                        arms[arm]=base+rankdata(-memory)
                group=grouped['DS' if bank=='DS' else 'GPT',t]
                truth=[labels[t][i] for i in ids]
                for arm,rank in arms.items():group[arm].append(utility_metrics(rank,truth)['regret'])
    per={f:{t:{a:float(np.mean(l)) for a,l in scores.items()} for (fam,t),scores in grouped.items() if fam==f} for f in ('DS','GPT')}
    reports={}
    for fam,tasks in per.items():
        reports[fam]={}
        for name,ts in [('all',list(tasks)),('eligible',[t for t in tasks if t in eligible])]:
            reports[fam][name]={'regret':{a:float(np.mean([tasks[t][a] for t in ts])) for a in next(iter(tasks.values()))},
                                'judge_history_gain_vs_random':intervals([tasks[t]['random_history']-tasks[t]['judge_history'] for t in ts]),
                                'judge_history_gain_vs_c0':intervals([tasks[t]['c0']-tasks[t]['judge_history'] for t in ts])}
    save(out,dict(eligible_tasks=len(eligible),eligible_jobs=sum(n>=3 for n in sizes.values()),seeds=5,historical_pairs_offered=dict(offered),missing_votes=dict(missing),per_task=per,summary=reports))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('output',type=Path);main(p.parse_args().output)
