"""Fixed-graph comparison of sparse ranking rules. Run with python3 -B."""
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

BASE = ROOT / 'experiments/clean-ranking-v1'
METHODS = ('legacy', 'hard_shrink', 'hard_colley', 'soft_shrink', 'soft_colley')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    if path.suffix == '.gz':
        with gzip.open(path, 'rt') as stream:
            return json.load(stream)
    return json.loads(path.read_bytes())


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n')


def top(scores, degree):
    tied = np.flatnonzero(np.abs(scores - scores.max()) <= 1e-12)
    return tied[degree[tied] == degree[tied].max()].tolist()


def rank(ids, edges, bank):
    n = len(ids)
    index = {ident: i for i, ident in enumerate(ids)}
    parsed = []
    reported = []
    for a, b in edges:
        record = bank['|'.join(sorted((a, b)))]
        win, conf = response_values(record)
        winner = record['order'][win] if win is not None else None
        if winner is not None:
            assert winner in (a, b)
            parsed.append((index[winner], index[b if winner == a else a], conf))
        reported.append((a, b, winner if conf >= .7 else None))
    selected = {'legacy': top_set(ids, reported)}
    for setting in ('hard', 'soft'):
        weights = np.zeros((n, n))
        for w, l, c in parsed:
            weights[w, l] += float(c >= .7) if setting == 'hard' else max(0., 2*c-1)
        both = weights + weights.T
        degree = np.count_nonzero(both, axis=1)
        total = both.sum(axis=1)
        wins = weights.sum(axis=1)
        shrink = (1+wins)/(2+total)
        matrix = np.diag(2+total) - both
        rhs = 1 + wins-total/2
        adjusted = np.linalg.solve(matrix, rhs)
        assert np.max(np.abs(matrix @ adjusted - rhs)) < 1e-10
        for name, scores in [('shrink', shrink), ('colley', adjusted)]:
            selected[setting+'_'+name] = [ids[i] for i in top(scores, degree)]
    return selected


def describe(values, tasks, draws):
    x = np.array(values)
    return dict(gain=float(x.mean()), ci95=np.quantile(x[draws].mean(axis=1), [.025,.975]).tolist(),
                min_leave_one=float(((x.sum()-x)/(len(tasks)-1)).min()),
                tasks_improve=int(np.sum(x > 1e-12)), task_gain=dict(zip(tasks, values)))


def main(out, ds_only):
    out.mkdir(parents=True, exist_ok=False)
    start = time.monotonic()
    shutil.copyfile(__file__, out/'experiment.snapshot.py')
    protocol = read(HERE.parent/'protocol.json')
    assert sha(HERE/'protocol.json') == '49fefc4dff7e96454d46180ffb4af2ca554a2fb9e95ae1f04f41fb265f7434be'
    assert all(sha(ROOT/f) == h for f,h in protocol['frozen_sha256'].items())
    banks = {'DS': BASE/'prepared/feedback.json'}
    if not ds_only:
        files = sorted((HERE.parent/'banks').glob('gpt*.json.gz'))
        assert len(files) == 3, files
        banks.update({f.name[:-8]:f for f in files})
    jobs = {j['job_id']:j for j in map(json.loads, (BASE/'prepared/jobs.jsonl').read_text().splitlines())}
    schedules = defaultdict(dict)
    with gzip.open(BASE/'results/decisions.jsonl.gz', 'rt') as stream:
        for row in map(json.loads, stream):
            schedules[row['method']][row['job_id']] = [(e['a'],e['b']) for e in row['trace']]
    predictions = out/'sealed.jsonl.gz'
    with gzip.open(predictions,'xt') as stream:
        for name,path in banks.items():
            bank = read(path)
            for schedule in ('coverage_random','random_pairs','corrected_tournament'):
                if name != 'DS' and schedule != 'coverage_random':
                    continue
                for key,job in jobs.items():
                    edges = schedules[schedule][key]
                    assert len(edges) == len({tuple(sorted(e)) for e in edges}) <= job['budget']
                    selected = rank(job['ids'],edges,bank[job['task']])
                    stream.write(json.dumps([name,schedule,key,len(edges),selected])+'\n')
    write(out/'seal.json',dict(hash=sha(predictions), banks={k:sha(v) for k,v in banks.items()},
                               protocol=sha(HERE/'protocol.json'), script=sha(Path(__file__))))
    labels = read(BASE/'prepared/evaluation_labels.json')
    saved = {}
    with gzip.open(BASE/'results/decisions.jsonl.gz','rt') as stream:
        for row in map(json.loads,stream):
            saved[row['method'],row['job_id']] = row['selected']
    grouped = defaultdict(list)
    with gzip.open(predictions,'rt') as stream:
        for name,schedule,key,reads,selected in map(json.loads,stream):
            job = jobs[key]; task = job['task']
            if name=='DS' and schedule!='corrected_tournament':
                assert set(selected['legacy']) == set(saved[schedule,key])
            selected['actual_c0'] = saved['corrected_tournament',key]
            for method,ids in selected.items():
                s = evaluate(job['ids'],ids,labels[task])
                grouped[name,schedule,method,task].append([s['regret'],s['best_hit']])
    means={k:np.mean(v,axis=0).tolist() for k,v in grouped.items()}
    tasks=sorted(labels)
    assert len(tasks)==26 and len(jobs)==850
    rng=random.Random(20261108093)
    draws=np.array([rng.choices(range(len(tasks)),k=len(tasks)) for _ in range(10000)])
    contrasts=[('hard_shrink','hard_colley'),('legacy','hard_colley'),('hard_colley','soft_colley'),
               ('legacy','soft_colley'),('soft_shrink','soft_colley'),('hard_shrink','soft_shrink'),
               ('actual_c0','hard_colley'),('actual_c0','soft_colley')]
    results={}
    for group in list(banks)+([] if ds_only else ['GPT_pooled']):
        names=[group] if group!='GPT_pooled' else [k for k in banks if k!='DS']
        for schedule in sorted(schedules):
            if (names[0],schedule,'legacy',tasks[0]) not in means:
                continue
            def metric(m,t,idx):
                return statistics.fmean(means[b,schedule,m,t][idx] for b in names)
            rows={m:dict(regret=statistics.fmean(metric(m,t,0) for t in tasks),
                         hit=statistics.fmean(metric(m,t,1) for t in tasks)) for m in METHODS}
            gains={}
            for old,new in contrasts:
                if old=='actual_c0' and group!='DS':
                    continue
                gains[new+'_over_'+old]=describe([metric(old,t,0)-metric(new,t,0) for t in tasks],tasks,draws)
            gains['interaction']=describe([(metric('soft_shrink',t,0)-metric('soft_colley',t,0))-
                                          (metric('hard_shrink',t,0)-metric('hard_colley',t,0)) for t in tasks],tasks,draws)
            results[group+'/'+schedule]={'means':rows,'gains':gains}
    write(out/'final_info.json',dict(results=results,seconds=time.monotonic()-start,paid_calls=0,training=0))


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--ds-only',action='store_true')
    args=parser.parse_args()
    main(args.out,args.ds_only)
