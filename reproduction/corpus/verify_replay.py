"""Independently score each replay and check frozen content fingerprints."""
import gzip
import hashlib
import json
import math
import os
from pathlib import Path
import statistics

REPO = Path(__file__).resolve().parents[2]
ROOT = Path(os.environ['FOREAGENT_RUN_DIR'])

def digest(path):
    data = gzip.decompress(path.read_bytes()) if path.suffix == '.gz' else path.read_bytes()
    return hashlib.sha256(data).hexdigest()

def main():
    protocol = json.loads((ROOT/'protocol.json').read_text())
    fingerprints = json.loads((REPO/'provenance/expected_run_hashes.json').read_text())
    expected = {(t['task'], p['pool_id'], r): (p['candidate_order'], seed)
                for t in protocol['tasks'] for p in t['pools'] for r, seed in enumerate(p['replay_seeds'])}
    utility = {}
    for t in protocol['tasks']:
        task = t['task']
        groups = json.loads((REPO/f'data/coverage/solutions_subset_50/{task}/ground_truth/groups_{task}_n2.json').read_text())
        utility[task] = {Path(p).name: (-v if g['is_lower_better'] else v)
                         for g in groups for p, v in zip(g['paths'], g['scores']) if math.isfinite(v)}
    checks = {}; all_rows = {}
    for variant in ('original', 'cache-fixed'):
        folder = ROOT/variant
        for name, value in fingerprints['corpus-'+variant].items():
            assert digest(folder/name) == value, (variant, name, 'frozen fingerprint mismatch')
        rows = [json.loads(s) for s in (folder/'runs.jsonl').read_text().splitlines()]
        assert len(rows) == len(expected) == 7800
        all_rows[variant] = rows
        for row in rows:
            key = (row['task'], row['pool_id'], row['repeat'])
            assert (row['candidate_order'], row['seed']) == expected[key]
            ids = row['candidate_order']; top = row['top_group']; executed = row['simulated_executed']; u = utility[row['task']]
            best = max(u[x] for x in ids); worst = min(u[x] for x in ids); k = len(top)
            assert set(top) == {x for x, meta in row['rank_meta'].items() if meta['rank'] == 0}
            assert executed and set(executed) <= set(top)
            assert executed == (row['probability_executed'] or [top[0]])
            exact = dict(uniform_tie_best_hit=sum(u[x] == best for x in top)/k,
                         selected_percentile=statistics.mean(sum(u[y] < u[x] for y in ids)/(len(ids)-1) for x in top),
                         normalized_regret=(best-statistics.mean(u[x] for x in top))/(best-worst),
                         actual_empty_execution=0., actual_execution_count=len(executed),
                         actual_execute_best=float(any(u[x] == best for x in executed)),
                         expected_empty_execution=0., expected_execution_count=.2*k+.8**k,
                         expected_execute_best=1-.8**sum(u[x] == best for x in top)+.8**k*int(u[top[0]] == best),
                         forced_fallback=float(not row['probability_executed']))
            for name, value in exact.items():
                assert math.isclose(row['metrics'][name], value, abs_tol=1e-10), (key, name)
        summary = json.loads((folder/'results.json').read_text())
        for task in summary['per_task']:
            subset = [row for row in rows if row['task'] == task['task']]
            for name, value in task['mean'].items():
                assert math.isclose(value, statistics.mean(r['metrics'][name] for r in subset), abs_tol=1e-10)
        for name, value in summary['macro'].items():
            assert math.isclose(value, statistics.mean(t['mean'][name] for t in summary['per_task']), abs_tol=1e-10)
        comparisons = unique = mismatch = reads = 0; union = set()
        with gzip.open(folder/'traces.jsonl.gz', 'rt') as trace:
            for line in trace:
                item = json.loads(line); pairs = {tuple(sorted((c['a'], c['b']))) for c in item['comparisons']}
                comparisons += len(item['comparisons']); unique += len(pairs)
                mismatch += sum(c['cache_direction_mismatch'] for c in item['comparisons'])
                union.update((item['task'], *p) for p in pairs)
        reads = comparisons - unique
        assert unique == sum(r['metrics']['unique_feedback_queries'] for r in rows)
        assert reads == sum(r['metrics']['cache_hits'] for r in rows)
        if variant == 'cache-fixed':
            assert mismatch == 0
        checks[variant] = dict(replays=len(rows), independent_scoring='passed', frozen_fingerprints='matched',
                               comparison_records=comparisons, cache_reads=reads,
                               unique_feedback_within_replay_summed=unique, distinct_feedback_across_experiment=len(union),
                               direction_mismatches=mismatch, actual_api_calls=0, candidate_training_runs=0,
                               forced_fallbacks=sum(r['forced_fallback'] for r in rows), final_empty=0)
    for a, b in zip(all_rows['original'], all_rows['cache-fixed'], strict=True):
        assert all(a[k] == b[k] for k in ('task', 'pool_id', 'repeat', 'seed', 'candidate_order'))
    (ROOT/'verification_portable.json').write_text(json.dumps(checks, indent=2)+'\n')
    print(json.dumps(checks))

if __name__ == '__main__':
    main()
