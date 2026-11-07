"""Score a frozen pool replay independently, including flat utilities and ties."""
import json
import math
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def scores(values, selected):
    lo, hi = min(values), max(values)
    # Each selected candidate gets one point per worse opponent, half per tied opponent.
    percentile = statistics.mean(
        (sum((v > other) + 0.5 * (v == other) for other in values) - 0.5) / (len(values) - 1)
        for v in selected
    )
    return (sum(v == hi for v in selected) / len(selected),
            (hi - statistics.mean(selected)) / (hi - lo) if hi > lo else 0.0,
            percentile)


def audit(folder):
    if not __debug__:
        raise RuntimeError("Use normal Python with assertions enabled")
    assert scores([1, 1, 1], [1]) == (1, 0, .5)
    assert scores([0, 2, 2], [2]) == (1, 0, .75)
    assert scores([0, 2, 2], [0, 2]) == (.5, .5, .375)
    protocol = json.loads((ROOT/'experiments/corpus26-v2/protocol.json').read_text())
    expected = {(t['task'], p['pool_id'], i): (p['candidate_order'], seed)
                for t in protocol['tasks'] for p in t['pools'] for i, seed in enumerate(p['replay_seeds'])}
    utilities = {}
    for t in protocol['tasks']:
        task = t['task']
        groups = json.loads((ROOT/f'data/coverage/solutions_subset_50/{task}/ground_truth/groups_{task}_n2.json').read_text())
        utilities[task] = {Path(name).name: (-raw if g['is_lower_better'] else raw)
                           for g in groups for name, raw in zip(g['paths'], g['scores'], strict=True)}
    seen = set()
    ties = 0
    with (folder/'runs.jsonl').open() as stream:
        for line in stream:
            row = json.loads(line)
            key = (row['task'], row['pool_id'], row['repeat'])
            assert key not in seen and (row['candidate_order'], row['seed']) == expected[key]
            seen.add(key)
            u = utilities[row['task']]
            values = [u[i] for i in row['candidate_order']]
            ties += len(set(values)) < len(values)
            result = scores(values, [u[i] for i in row['top_group']])
            for name, value in zip(('uniform_tie_best_hit', 'normalized_regret', 'selected_percentile'), result, strict=True):
                assert math.isclose(row['metrics'][name], value, abs_tol=1e-12), (key, name)
    assert seen == expected.keys()
    return {'scenarios': len(seen), 'pools_with_ties_counted_per_replay': ties}


if __name__ == '__main__':
    print(json.dumps(audit(Path(sys.argv[1]))))
