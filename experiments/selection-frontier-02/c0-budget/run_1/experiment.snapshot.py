"""Rerun the actual tournament with the single-elimination unique-read cap."""
import argparse
import collections
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
from reproduction.clean_ranking_v1.loader import load_world
from reproduction.clean_ranking_v1.run import select, evaluate


def read(path):
    return json.loads(path.read_bytes())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def summarize(tasks):
    names=sorted(tasks)
    x=np.array([np.mean(tasks[t],axis=0) for t in names])
    rng=random.Random(20261108093)
    draws=np.array([rng.choices(range(len(names)),k=len(names)) for _ in range(10000)])
    limits=np.quantile(x[draws].mean(axis=1),[.025,.975],axis=0)
    return {key:{'mean':v,'ci':limits[:,i].tolist()} for i,(key,v) in enumerate(zip(
        ['regret_deterioration','read_savings','hit_change','short_regret','full_regret','short_reads','full_reads'],x.mean(axis=0)))}


def run(out):
    start=time.monotonic()
    out.mkdir(parents=True,exist_ok=False)
    shutil.copyfile(__file__,out/'experiment.snapshot.py')
    assert sha(HERE/'protocol.json')=='b0b5c42bee398871a01839adee3bed559c3057229b6b01514c39a6ccdf746e06'
    base=ROOT/'experiments/clean-ranking-v1/prepared'
    jobs={j['job_id']:j for j in map(json.loads,(base/'jobs.jsonl').open())}
    sources=read(base/'code_files.json')
    code={t:{i:(ROOT/f).read_text() for i,f in items.items()} for t,items in sources.items()}
    metadata={'DS':{'path':str((base/'feedback.json').relative_to(ROOT)),
                    'sha256':read(HERE.parent/'protocol.json')['frozen_sha256'][str((base/'feedback.json').relative_to(ROOT))]}}
    for manifest in ['banks/manifest.json','deepseek-transfer/banks_1/manifest.json']:
        metadata.update(read(HERE.parent/manifest)['banks'])
    full={}
    for f in ['c0-final-selection/run-002/decisions.sealed.jsonl.gz','deepseek-transfer/run_1/decisions.sealed.jsonl.gz']:
        with gzip.open(HERE.parent/f,'rt') as stream:
            for r in map(json.loads,stream):
                full[r['bank'], r['job_id']] = r
    module=load_world()
    sealed=out/'selections.jsonl.gz'
    with gzip.open(sealed,'xt') as stream:
        for name,entry in metadata.items():
            path=ROOT/entry['path']; assert sha(path)==entry['sha256']
            bank=json.loads(gzip.decompress(path.read_bytes())) if path.suffix=='.gz' else read(path)
            for key,job in jobs.items():
                if job['task'] not in bank:
                    continue
                fullrow=full[name,key]
                reduced={**job,'budget':min(job['budget'],len(job['ids'])-1)}
                contents={i:code[job['task']][i] for i in job['ids']}
                picked,trace,stats=select(module,reduced,bank[job['task']],contents,'corrected_tournament',.7)
                assert trace==fullrow['trace'][:len(trace)] and len(trace)<=reduced['budget']
                stream.write(json.dumps([name,key,picked,fullrow['selected']['C'],len(trace),len(fullrow['trace'])])+'\n')
    (out/'seal.json').write_text(json.dumps({'hash':sha(sealed),'script':sha(Path(__file__))})+'\n')
    labels=read(base/'evaluation_labels.json')
    per=collections.defaultdict(lambda:collections.defaultdict(list))
    with gzip.open(sealed,'rt') as stream:
        for name,key,short,all_ids,sc,fc in map(json.loads,stream):
            job=jobs[key];t=job['task']
            x=evaluate(job['ids'],short,labels[t]); y=evaluate(job['ids'],all_ids,labels[t])
            v=[x['regret']-y['regret'],fc-sc,x['best_hit']-y['best_hit'],x['regret'],y['regret'],sc,fc]
            per[name][t].append(v)
            if name.startswith('gpt'):
                per['GPT_pooled'][t].append(v)
    summary={name:summarize(by_task) for name,by_task in per.items()}
    (out/'per_task.json').write_text(json.dumps({n:{t:np.mean(v,axis=0).tolist() for t,v in b.items()} for n,b in per.items()},indent=2)+'\n')
    (out/'final_info.json').write_text(json.dumps({'banks':summary,'seconds':time.monotonic()-start,'registered':sha(HERE/'protocol.json'),
        'new_paid_calls':0,'candidate_training':0,'n_selections':len(full)},indent=2,allow_nan=False)+'\n')


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--out',type=Path,required=True)
    run(parser.parse_args().out)
