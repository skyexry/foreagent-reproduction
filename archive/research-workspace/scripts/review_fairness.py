"""Paired single-choice comparison over the preregistered common gate grid."""
import json
import math
import os
from pathlib import Path
import statistics
import sys
from concurrent.futures import ProcessPoolExecutor

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from reproduction.round06.run import bootstrap, load_task, score_selection
from reproduction.round06.methods import win_rate_select
from reproduction.round07.methods import evidence_tiebreak_select
from reproduction.round08.run import load_canonical, run_tournament
from audit_baseline_scores import scores
from review_preflight import preflight

GATES = (.5, .6, .7, .8, .9, 1.)
METHODS = ('tournament', 'r6', 'r7')
METRICS = ('hit', 'regret', 'queries')
E = ROOT/'experiments/icml-review'


def replay(task):
    module = load_canonical()
    name = task['task']
    utility, table = load_task(name, task['source'])
    assert len(task['pools']) == 100 and len({p['pool_id'] for p in task['pools']}) == 100
    result = {}
    for gate in GATES:
        by_method = {m: [] for m in METHODS}
        for pool in task['pools']:
            ids = pool['candidate_order']
            assert len(set(ids)) == len(ids) == task['pool_size'] and len(pool['replay_seeds']) == 3
            for seed in pool['replay_seeds']:
                top, _, _, edges = run_tournament(module, ids, table, seed, name, threshold=gate)
                r6, stats6, _ = win_rate_select(ids, edges, threshold=gate)
                r7, stats7, _ = evidence_tiebreak_select(ids, edges, threshold=gate)
                assert stats6 == stats7 and set(r7) <= set(r6)
                for method, chosen in zip(METHODS, (top, r6, r7), strict=True):
                    metrics = score_selection(ids, chosen, utility)
                    hit, regret, pct = scores([utility[i] for i in ids], [utility[i] for i in chosen])
                    for v,k in zip((hit,regret,pct),('uniform_tie_best_hit','normalized_regret','selected_percentile'),strict=True):
                        assert math.isclose(metrics[k],v,abs_tol=1e-12)
                    by_method[method].append((hit,regret,len(edges)))
        result[str(gate)] = {m:dict(zip(METRICS,map(statistics.mean,zip(*rows)),strict=True)) for m,rows in by_method.items()}
        assert all(len(rows)==300 for rows in by_method.values())
    return name,result


def summarize(data):
    split = json.loads((ROOT/'experiments/environment-audit/calibration.json').read_text())
    dev, val = split['development_tasks'],split['validation_tasks']
    assert not set(dev)&set(val) and set(data)==set(dev+val) and len(dev)==18 and len(val)==8
    def avg(tasks,m,g):
        return {k:statistics.mean(data[t][str(g)][m][k] for t in tasks) for k in METRICS}
    def qualifies(row, ref):
        return row['hit']>=ref['hit'] and row['queries']<=ref['queries']
    dev_ref=avg(dev,'tournament',.7)
    val_ref=avg(val,'tournament',.7)
    tuned={}
    for m in METHODS:
        trials={g:avg(dev,m,g) for g in GATES}
        feasible=[g for g,x in trials.items() if qualifies(x,dev_ref)]
        if not feasible:
            tuned[m]={'eligible':False}
            continue
        best=min(feasible,key=lambda g:(trials[g]['regret'],abs(g-.7),g))
        v=avg(val,m,best)
        tuned[m]=dict(gate=best,development=trials[best],validation=v,validation_constraints=qualifies(v,val_ref))
    grid={}
    for g in GATES:
        row={m:avg(dev+val,m,g) for m in METHODS}
        delta=[data[t][str(g)]['r7']['regret']-data[t][str(g)]['r6']['regret'] for t in sorted(data)]
        row['paired_r7_minus_r6_regret_ci']=bootstrap(delta,dict(replicates=10000,seed=2026110709))
        grid[str(g)]=row
    for m,r,arm in [('tournament',6,'control'),('r6',6,'treatment'),('r7',7,'treatment')]:
        saved=json.loads((ROOT/f'experiments/round-0{r}/summary.json').read_text())
        ref=saved['macro'][arm]
        for key, col in [('hit','uniform_tie_best_hit'),('regret','normalized_regret')]:
            assert abs(grid['0.7'][m][key]-ref[col])<1e-12
            for task in saved['per_task']:
                assert abs(data[task['task']]['0.7'][m][key]-task[arm][col])<1e-12
    return dict(grid=grid,tuned=tuned,validation_reference=val_ref,per_task=data)


if __name__=='__main__':
    if not __debug__ or os.environ.get('PYTHONHASHSEED')!='0':
        raise SystemExit('Normal Python and PYTHONHASHSEED=0 are required.')
    preflight()
    tasks=json.loads((ROOT/'experiments/corpus26-v2/protocol.json').read_text())['tasks']
    dest=Path(sys.argv[1])
    if dest.exists():
        raise SystemExit('Choose a fresh output file')
    with ProcessPoolExecutor(4) as pool:
        result=summarize(dict(pool.map(replay,tasks)))
    dest.write_text(json.dumps(result,indent=2)+'\n')
