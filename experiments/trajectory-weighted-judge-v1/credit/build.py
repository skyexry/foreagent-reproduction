"""Task-local full-DS1 credit expansion; preserves the original 52-job check.

Run from any directory: python3 -B <this file> --output <new directory>.
Only the opposite direction is rerun after exact saved baseline verification.
Output tasks/*.json is the sole weight input for task-isolated fitting.
"""
import argparse
from collections import Counter, defaultdict
import gzip
import hashlib
import json
import math
from pathlib import Path
import random
import statistics
import sys
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT))
from reproduction.clean_ranking_v1.loader import load_world
from reproduction.clean_ranking_v1.run import evaluate, select

SEED = 20261108


def load(path):
    return json.loads(path.read_bytes())


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def dump(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2,
                               allow_nan=False) + '\n')


def exposure(n):
    return '0' if n == 0 else '1' if n == 1 else '2-3' if n < 4 else '4+'


def distribution(weights):
    values = sorted(weights)
    def quantile(q):
        x = (len(values)-1)*q
        lo, hi = math.floor(x), math.ceil(x)
        return values[lo] + (values[hi]-values[lo])*(x-lo)
    return dict(min=values[0], p25=quantile(.25), median=quantile(.5),
                p75=quantile(.75), p95=quantile(.95), max=values[-1],
                mean=statistics.fmean(values),
                effective_sample_size=sum(values)**2/sum(x*x for x in values))


def task_build(task, jobs, original, bank, paths, utility, world, old_rows):
    code = {i: (ROOT/path).read_text() for i, path in paths.items()}
    occurrences = []
    baseline_checks = 0
    comparisons = 0
    with_branch = []
    for job in jobs:
        job_code = {i: code[i] for i in job['ids']}
        saved = original[job['job_id']]
        selected, trace, stats = select(world, job, bank, job_code, 'corrected_tournament', .7)
        assert (selected, trace, stats) == (saved['selected'], saved['trace'], saved['stats'])
        assert len({'|'.join(sorted((r['a'], r['b']))) for r in trace}) == len(trace)
        baseline_checks += 1
        base_regret = evaluate(job['ids'], selected, utility)['regret']
        span = max(utility[i] for i in job_code) - min(utility[i] for i in job_code)
        for turn, event in enumerate(trace):
            a, b = event['a'], event['b']
            if event['winner'] is None or utility[a] == utility[b]:
                continue
            right, wrong = sorted((a, b), key=utility.get, reverse=True)
            pair = '|'.join(sorted((a, b)))
            assert pair in bank
            opposite = wrong if event['winner'] == right else right
            entry = bank[pair]
            changed = dict(entry, predicted_best_index=entry['order'].index(opposite))
            supplied = {**bank, pair: changed}
            picked, path, counts = select(world, job, supplied, job_code, 'corrected_tournament', .7)
            assert path[:turn] == trace[:turn]
            assert path[turn] == {**event, 'winner': opposite}
            opposite_regret = evaluate(job['ids'], picked, utility)['regret']
            outcomes = ({'right': base_regret, 'wrong': opposite_regret}
                        if event['winner'] == right else
                        {'right': opposite_regret, 'wrong': base_regret})
            row = dict(task=task, job=job['job_id'], pair=pair, repeat=job['repeat'],
                       gap=(utility[right]-utility[wrong])/span,
                       delta=outcomes['wrong']-outcomes['right'], **outcomes)
            occurrences.append(row)
            comparisons += 1
            with_branch.append(dict(job=job['job_id'], turn=turn, pair=pair,
                                    forced=opposite, selected=picked, trace=path, stats=counts))
    sample = [r for r in occurrences if r['job'].split(':')[-2] == '0']
    assert sample == old_rows
    grouped = defaultdict(list)
    for row in occurrences:
        grouped[row['pair']].append(row)
    pairs = {}
    for pair in sorted(bank):
        a, b = pair.split('|')
        assert a in utility and b in utility and utility[a] != utility[b]
        rows = grouped.get(pair, [])
        delta = statistics.fmean(r['delta'] for r in rows) if rows else 0.
        gap = statistics.fmean(r['gap'] for r in rows) if rows else 0.
        pairs[pair] = dict(winner=max((a, b), key=utility.get), n=len(rows), mean_delta=delta, mean_gap=gap,
                           terminal=1.+max(0., delta), gap=1.+gap)
    # Independent deterministic RNG per task and stratum: unrelated files do not
    # affect this task's shuffle or the training-only partition.
    for group in ('0', '1', '2-3', '4+'):
        keys = [p for p, v in pairs.items() if exposure(v['n']) == group]
        increments = [pairs[p]['terminal']-1. for p in keys]
        random.Random(f'{SEED}:{task}:{group}').shuffle(increments)
        for pair, increment in zip(keys, increments):
            pairs[pair]['shuffled'] = 1.+increment
        assert sorted(pairs[p]['terminal'] for p in keys) == sorted(pairs[p]['shuffled'] for p in keys)
    # Seed-repeat disagreements describe overlap-context variability on this
    # development corpus; this is an exploratory diagnostic, not replication.
    by_pool_pair = defaultdict(dict)
    for row in occurrences:
        by_pool_pair[(row['job'].rsplit(':', 1)[0], row['pair'])][row['repeat']] = row['delta']
    matched = [v for v in by_pool_pair.values() if set(v) == {0, 1}]
    differing = [v for v in matched if abs(v[0]-v[1]) > 1e-12]
    info = dict(task=task, jobs=baseline_checks, branch_reruns=comparisons,
                original_52_rows_verified=len(sample), eligible_pairs=len(pairs),
                exposed_pairs=len(grouped), positive_mean_delta_pairs=sum(v['mean_delta']>0 for v in pairs.values()),
                negative_mean_delta_pairs=sum(v['mean_delta']<0 for v in pairs.values()),
                terminal_nonzero_increment_pairs=sum(v['terminal']>1 for v in pairs.values()),
                exposure_classes=dict(Counter(exposure(v['n']) for v in pairs.values())),
                occurrence_signs=dict(Counter('positive' if r['delta']>1e-12 else 'negative' if r['delta']< -1e-12 else 'zero' for r in occurrences)),
                raw_weights={arm:distribution([v[arm] for v in pairs.values()]) for arm in ('terminal','gap','shuffled')},
                exploratory_repeat_seed=dict(matched_pool_pairs=len(matched), differing=len(differing),
                    mean_absolute_difference=statistics.fmean(abs(v[0]-v[1]) for v in matched) if matched else None))
    return pairs, occurrences, with_branch, info


def run(output):
    start = time.monotonic()
    output.mkdir(parents=True, exist_ok=False)
    for name in ('tasks', 'rows', 'branches'):
        (output/name).mkdir()
    prepared = ROOT/'experiments/clean-ranking-v1/prepared'
    protocol = ROOT/'experiments/trajectory-weighted-judge-v1/protocol.json'
    for path, expected in load(protocol)['inputs'].items():
        assert digest(ROOT/path) == expected, path
    archive = ROOT/'experiments/clean-ranking-v1/results/decisions.jsonl.gz'
    with gzip.open(archive, 'rt') as stream:
        original = {r['job_id']:r for r in map(json.loads, stream) if r['method']=='corrected_tournament'}
    jobs = list(map(json.loads, (prepared/'jobs.jsonl').read_text().splitlines()))
    assert len(jobs) == 850
    bank, paths, labels = [load(prepared/name) for name in ('feedback.json','code_files.json','evaluation_labels.json')]
    prior = ROOT/'experiments/c0-judge-credit-check/run_1/rows.jsonl'
    old = list(map(json.loads, prior.read_text().splitlines()))
    world = load_world()
    infos, hashes = [], {}
    for task in sorted(bank):
        pairs, rows, branches, info = task_build(task, [j for j in jobs if j['task']==task],
            original, bank[task], paths[task], labels[task], world, [r for r in old if r['task']==task])
        dump(output/'tasks'/f'{task}.json', pairs)
        (output/'rows'/f'{task}.jsonl').write_text(''.join(json.dumps(r, sort_keys=True)+'\n' for r in rows))
        with gzip.GzipFile(filename=str(output/'branches'/f'{task}.jsonl.gz'), mode='wb', mtime=0) as stream:
            stream.write(''.join(json.dumps(r, sort_keys=True)+'\n' for r in branches).encode())
        infos.append(info)
        hashes[task] = digest(output/'tasks'/f'{task}.json')
        print(json.dumps(info), flush=True)
    summary = dict(tasks=len(infos), jobs=sum(i['jobs'] for i in infos),
        branch_reruns=sum(i['branch_reruns'] for i in infos),
        original_52_rows_verified=sum(i['original_52_rows_verified'] for i in infos),
        eligible_pairs=sum(i['eligible_pairs'] for i in infos), exposed_pairs=sum(i['exposed_pairs'] for i in infos),
        terminal_nonzero_increment_pairs=sum(i['terminal_nonzero_increment_pairs'] for i in infos),
        per_task=infos, shuffle_seed=SEED, shuffle_key='seed:task:exposure_class',
        fitting_normalization='Trainer divides raw arm weights by the retained training task mean; each training task receives equal total weight.',
        training_partition_rule='Trainer loads tasks/<task>.json only for training tasks; this summary is audit-only.',
        paid_calls=0, gpu=0, candidate_executions=0, model_fits=0,
        elapsed_seconds=time.monotonic()-start)
    dump(output/'summary.json', summary)
    receipt = dict(status='passed', exact_baseline_jobs=850, exact_old_rows=len(old),
        old_rows_sha256=digest(prior), task_weight_sha256=hashes,
        source_sha256={str(p.relative_to(ROOT)):digest(p) for p in
                      (Path(__file__), protocol, archive, prior,
                       ROOT/'experiments/c0-judge-credit-check/check.py',
                       prepared/'feedback.json', prepared/'code_files.json',
                       prepared/'evaluation_labels.json', prepared/'jobs.jsonl')},
        summary_sha256=digest(output/'summary.json'))
    assert summary['original_52_rows_verified'] == len(old) == 306
    dump(output/'receipt.json', receipt)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    run(parser.parse_args().output)
