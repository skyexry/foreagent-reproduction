"""Budget-matched revisit versus expand comparison using two archived judges."""
import argparse
from collections import defaultdict
import gzip
import hashlib
import json
from pathlib import Path
import random
import shutil
import statistics
import sys
import time

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT))
from reproduction.clean_ranking_v1.correctness import response_values
from reproduction.clean_ranking_v1.ranking import top_set
from reproduction.clean_ranking_v1.run import evaluate


def read(path):
    return json.loads(path.read_bytes())


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def winner(table, task, edge):
    record = table[task]['|'.join(sorted(edge))]
    idx, confidence = response_values(record)
    return record['order'][idx] if idx is not None and confidence >= .7 else None


def decision(job, edges, primary, backup):
    ids = job['ids']
    split = len(ids)-1
    results = [winner(primary,job['task'],edge) for edge in edges]
    revisit = [i for i in range(split) if results[i] is None][:len(edges)-split]
    keep = len(edges)-len(revisit)
    sham = results[:keep]
    recovered = list(sham)
    for i in revisit:
        recovered[i] = winner(backup,job['task'],edges[i])
    assert keep+len(revisit) == len(edges) == job['budget']
    choices = {}
    for arm,outcomes in [('new',results),('sham',sham),('backup',recovered)]:
        choices[arm] = top_set(ids,[(a,b,y) for (a,b),y in zip(edges,outcomes)])
    return choices, len(revisit), sum(recovered[i] is not None for i in revisit)


def run(out):
    out.mkdir(exist_ok=False,parents=True)
    start = time.monotonic()
    shutil.copyfile(__file__,out/'experiment.snapshot.py')
    assert digest(HERE/'protocol.json')=='643f00dae2dda5825121b12cca0ca5c6671d92c179c0e331d73c9a68d910b517'
    for f,h in read(HERE.parent/'protocol.json')['frozen_sha256'].items():
        assert digest(ROOT/f)==h
    base=ROOT/'experiments/clean-ranking-v1'
    bank={'DS':read(base/'prepared/feedback.json')}
    for name,meta in read(HERE.parent/'banks/manifest.json')['banks'].items():
        path=ROOT/meta['path']
        assert digest(path)==meta['sha256']
        with gzip.open(path,'rt') as stream:
            bank[name]=json.load(stream)
    jobs={j['job_id']:j for j in map(json.loads,(base/'prepared/jobs.jsonl').open())}
    schedule={}
    with gzip.open(base/'results/decisions.jsonl.gz','rt') as stream:
        for row in map(json.loads,stream):
            if row['method']=='coverage_random':
                schedule[row['job_id']]=[(e['a'],e['b']) for e in row['trace']]
    assert len(jobs)==len(schedule)==850 and len(bank)==4
    sealed=out/'selections.jsonl.gz'
    with gzip.open(sealed,'xt') as stream:
        for gpt in sorted(set(bank)-{'DS'}):
            for first,second in [('DS',gpt),(gpt,'DS')]:
                for key,j in jobs.items():
                    choices,k,valid=decision(j,schedule[key],bank[first],bank[second])
                    stream.write(json.dumps([first,second,key,choices,k,valid])+'\n')
    (out/'seal.json').write_text(json.dumps({'sha256':digest(sealed),'script':digest(Path(__file__))},indent=2)+'\n')
    labels=read(base/'prepared/evaluation_labels.json')
    saved={}
    with gzip.open(base/'results/decisions.jsonl.gz','rt') as stream:
        for row in map(json.loads,stream):
            if row['method']=='coverage_random':
                saved[row['job_id']]=row['selected']
    c0_path=HERE.parent/'c0-final-selection/run-001/summary.json'
    c0=read(c0_path)['summaries'] if c0_path.exists() else {}
    values=defaultdict(list)
    with gzip.open(sealed,'rt') as stream:
        for first,second,key,choices,k,valid in map(json.loads,stream):
            job=jobs[key];task=job['task']
            if first=='DS':
                assert set(choices['new'])==set(saved[key])
            group='DS_first' if first=='DS' else 'GPT_first'
            for arm,ids in choices.items():
                score=evaluate(job['ids'],ids,labels[task])
                for name in [first+'+'+second,group]:
                    values[name,task,arm].append([score['regret'],score['best_hit'],k,valid,job['budget']])
    tasks=sorted(labels)
    rng=random.Random(20261108093)
    draws=np.array([rng.choices(range(len(tasks)),k=len(tasks)) for _ in range(10000)])
    results={}
    for name in sorted({k[0] for k in values}):
        arms={a:np.stack([np.mean(values[name,t,a],axis=0) for t in tasks]) for a in choices}
        record={'means':{a:dict(zip(['regret','hit','planned_revisits','rescued','total_calls'],v.mean(axis=0))) for a,v in arms.items()}}
        for old,new in [('new','backup'),('new','sham'),('sham','backup')]:
            dif=arms[old][:,0]-arms[new][:,0]
            record[new+'_over_'+old]=dict(gain=float(dif.mean()),ci95=np.quantile(dif[draws].mean(axis=1),[.025,.975]).tolist(),
                                           min_leave_one=float(((dif.sum()-dif)/(len(tasks)-1)).min()),per_task=dict(zip(tasks,dif)))
        results[name]=record
    payload={'comparisons':results,'c0_reference_source':str(c0_path.relative_to(ROOT)) if c0 else None,
             'seconds':time.monotonic()-start,'forecast':'Research comparator; sham uses identical nominal costs for attribution.',
             'new_api_calls':0,'candidate_executions':0}
    (out/'final_info.json').write_text(json.dumps(payload,indent=2,allow_nan=False)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--out',required=True,type=Path)
    run(p.parse_args().out)
