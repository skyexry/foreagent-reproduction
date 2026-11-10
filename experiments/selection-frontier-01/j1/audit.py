#!/usr/bin/env python3
"""Independent J1 audit: rebuild directly from frozen files, with no experiment imports."""
from collections import Counter, defaultdict
from datetime import datetime, timezone
from fractions import Fraction
import gzip
import hashlib
import json
import math
from pathlib import Path
import random
import statistics
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
OUT = HERE / 'run_2'
START = time.monotonic()


def read(path):
    return json.loads(Path(path).read_text())


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def same(a, b):
    assert math.isclose(a, b, abs_tol=1e-12, rel_tol=1e-12), (a, b)


protocol = read(ROOT / 'experiments/selection-frontier-01/protocol.json')
assert digest(ROOT / 'experiments/selection-frontier-01/protocol.json') == 'fbd9f027a7f2afdce09b24927825df21f8714e864ba1c996e1e0a2a010fe1100'
for name, expected in protocol['frozen_sha256'].items():
    assert digest(ROOT / name) == expected
manifest = read(OUT / 'output_sha256.json')
for name, expected in manifest.items():
    assert digest(OUT / name) == expected, name
assert digest(HERE / 'experiment.py') == digest(OUT / 'experiment.snapshot.py')
assert (OUT / 'failure.log').read_text() == ''
final, summary = read(OUT / 'final_info.json'), read(OUT / 'summary.json')
assert final['status'] == 'success' and final['results'] == summary
assert final['elapsed_wall_seconds'] < 600
assert final['new_api_calls'] == final['candidate_training'] == final['gpu'] == 0
jobs = [json.loads(line) for line in (ROOT / 'experiments/clean-ranking-v1/prepared/jobs.jsonl').read_text().splitlines()]
labels = read(ROOT / 'experiments/clean-ranking-v1/prepared/evaluation_labels.json')
with gzip.open(ROOT / 'experiments/clean-ranking-v1/results/decisions.jsonl.gz', 'rt') as stream:
    saved = [json.loads(line) for line in stream]
saved = {r['job_id']: r for r in saved if r['method'] == 'coverage_random'}
episodes = [json.loads(line) for line in (OUT / 'per_episode.jsonl').read_text().splitlines()]
edges = [json.loads(line) for line in (OUT / 'per_edge.jsonl').read_text().splitlines()]
assert len(episodes) == len(saved) == len(jobs) == 850
by_task, tallies, edge_cursor = defaultdict(list), Counter(), 0
first_cases = {}
for job, episode in zip(jobs, episodes):
    assert episode['job_id'] == job['job_id']
    source, utility, ids = saved[job['job_id']], labels[job['task']], job['ids']
    traces, selections, metrics = {}, {}, {}
    trace = source['trace']
    assert len(trace) == min(job['budget'], math.comb(len(ids), 2))
    rng = random.Random(job['seed'])
    chain = list(ids)
    rng.shuffle(chain)
    remaining = set(tuple(sorted((a, b))) for index, a in enumerate(ids) for b in ids[index+1:])
    initial = [tuple(sorted(pair)) for pair in zip(chain, chain[1:])]
    for step, event in enumerate(trace):
        pair = initial[step] if step < len(initial) else rng.choice(sorted(remaining))
        remaining.remove(pair)
        assert pair == (event['a'], event['b'])
        a, b, winner = event['a'], event['b'], event['winner']
        strict_error = winner is not None and utility[winner] < max(utility[a], utility[b])
        corrected = (a if utility[a] > utility[b] else b) if strict_error else winner
        expected = edges[edge_cursor]
        edge_cursor += 1
        assert expected['job_id'] == job['job_id'] and expected['step'] == step + 1
        assert (expected['a'], expected['b'], expected['original_winner'], expected['corrected_winner']) == (a, b, winner, corrected)
        assert expected['confidence'] == event['confidence']
        assert expected['source_group_index'] == event['source_group_index']
        assert expected['strict_error_corrected'] == strict_error
        assert expected['true_tie'] == (utility[a] == utility[b])
        assert expected['utility_a'] == utility[a] and expected['utility_b'] == utility[b]
        assert expected['unique_read_cost_each_arm'] == 1
        tallies['queries'] += 1
        tallies['valid'] += winner is not None
        tallies['abstained'] += winner is None
        tallies['strict_error'] += strict_error
        tallies['true_ties'] += utility[a] == utility[b]
        for arm, value in [('original', winner), ('corrected', corrected)]:
            traces.setdefault(arm, []).append((a, b, value))
    for arm, feedback in traces.items():
        wins, degree = Counter(), Counter()
        for a, b, winner in feedback:
            if winner is not None:
                degree.update((a, b))
                wins[winner] += 1
        key = {i: (Fraction(wins[i], degree[i]) if degree[i] else Fraction(1, 2), degree[i]) for i in ids}
        best_key = max(key.values())
        selected = [i for i in ids if key[i] == best_key]
        assert selected == episode[arm + '_selected']
        if arm == 'original':
            assert selected == source['selected']
        hi, lo = max(utility[i] for i in ids), min(utility[i] for i in ids)
        regret = statistics.fmean((hi-utility[i])/(hi-lo) if hi != lo else 0. for i in selected)
        hit = statistics.fmean(float(utility[i] == hi) for i in selected)
        same(regret, episode[arm]['regret'])
        same(hit, episode[arm]['best_hit'])
        assert episode[arm]['unique_feedback_reads'] == len(trace)
        metrics[arm] = (regret, hit)
    gain = metrics['original'][0] - metrics['corrected'][0]
    same(gain, episode['regret_gain'])
    status = 'improved' if gain > 1e-12 else 'worsened' if gain < -1e-12 else 'equal'
    assert status == episode['outcome']
    first_cases.setdefault(status, job['job_id'])
    tallies[status] += 1
    by_task[job['task']].append(metrics)
assert edge_cursor == len(edges) == 11004
assert len(by_task) == 26
tasks = read(OUT / 'per_task.json')
task_metrics = {}
for task in sorted(by_task):
    task_metrics[task] = {arm: [statistics.fmean(m[arm][k] for m in by_task[task]) for k in (0, 1)] for arm in ('original', 'corrected')}
    saved_task = next(t for t in tasks if t['task'] == task)
    for arm in ('original', 'corrected'):
        same(task_metrics[task][arm][0], saved_task[arm]['regret'])
        same(task_metrics[task][arm][1], saved_task[arm]['best_hit'])
for arm in ('original', 'corrected'):
    for key, index in [('regret', 0), ('best_hit', 1)]:
        same(statistics.fmean(t[arm][index] for t in task_metrics.values()), summary['macro'][arm][key])
for field, values in [
    ('primary_regret_gain_original_minus_corrected', [t['original'][0] - t['corrected'][0] for t in task_metrics.values()]),
    ('paired_best_hit_gain_corrected_minus_original', [t['corrected'][1] - t['original'][1] for t in task_metrics.values()]),
    ('corrected_residual_regret', [t['corrected'][0] for t in task_metrics.values()])]:
    same(statistics.fmean(values), summary[field]['mean'])
    rng = random.Random(protocol['fixed']['bootstrap_seed'])
    samples = sorted(statistics.fmean(rng.choices(values, k=len(values))) for _ in range(10000))
    limits = []
    for probability in (.025, .975):
        position = (len(samples) - 1) * probability
        lo, hi = math.floor(position), math.ceil(position)
        limits.append(samples[lo] + (samples[hi] - samples[lo]) * (position - lo))
    for actual, expected in zip(limits, summary[field]['task_cluster_percentile_95']):
        same(actual, expected)
cases = read(OUT / 'predefined_cases.json')
for category, first in first_cases.items():
    assert cases[category]['episode']['job_id'] == first
for key in ('queries', 'valid', 'abstained', 'improved', 'equal', 'worsened'):
    assert tallies[key] == summary['counts'][key]
assert tallies['strict_error'] == summary['counts']['valid_strict_error']
assert tallies['true_ties'] == summary['counts']['true_ties_all_queried'] == 0
receipt = {'status': 'passed', 'audit_utc': datetime.now(timezone.utc).isoformat(),
           'audit_seconds': time.monotonic() - START, 'audit_script_sha256': digest(Path(__file__)),
           'run_2_output_manifest_sha256': digest(OUT / 'output_sha256.json'),
           'frozen_input_hashes_verified': len(protocol['frozen_sha256']) + 1,
           'output_hashes_verified': len(manifest), 'episodes_independently_rebuilt': 850,
           'edges_checked': edge_cursor, 'tasks_independently_rebuilt': 26,
           'bootstrap_endpoint_95_intervals_rebuilt': 3, 'first_predefined_cases_checked': first_cases,
           'source': 'Frozen raw decisions, jobs and labels; independent script imports no experiment or reproduction modules.',
           'counts': dict(tallies)}
(HERE / 'audit.json').write_text(json.dumps(receipt, indent=2) + '\n')
print(json.dumps(receipt, indent=2))
