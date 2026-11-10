"""selection-frontier-02 preregistered valid-edge coverage allocation.

Same seeded chain as coverage_random; then prioritize zero-valid-degree
endpoints, minimum valid degree, total valid degree, and queried degree.
The host keeps the frozen aggregator and budget. Only observed edges enter.
"""
import itertools
import random

_rng = None
_chain = None


def priority(edge, valid_degree, queried_degree):
    a, b = edge
    return (int(valid_degree[a] == 0) + int(valid_degree[b] == 0),
            -min(valid_degree[a], valid_degree[b]),
            -(valid_degree[a] + valid_degree[b]),
            -(queried_degree[a] + queried_degree[b]))


def decide(observation):
    global _rng, _chain
    ids = observation['candidates']
    if _rng is None:
        _rng = random.Random(observation['seed'])
        chain = list(ids)
        _rng.shuffle(chain)
        _chain = [tuple(sorted(pair)) for pair in zip(chain, chain[1:])]
    feedback = observation['feedback']
    seen = {tuple(sorted((r['a'], r['b']))) for r in feedback}
    remaining = sorted(tuple(sorted(pair)) for pair in itertools.combinations(ids, 2)
                       if tuple(sorted(pair)) not in seen)
    if observation['remaining_budget'] == 0 or not remaining:
        return {'action': 'stop'}
    if len(feedback) < len(_chain):
        edge = _chain[len(feedback)]
    else:
        valid_degree, queried_degree = dict.fromkeys(ids, 0), dict.fromkeys(ids, 0)
        for row in feedback:
            for endpoint in (row['a'], row['b']):
                queried_degree[endpoint] += 1
                valid_degree[endpoint] += int(row['valid'])
        # Sort before shuffle makes tie randomization reproducible and label-free.
        _rng.shuffle(remaining)
        edge = max(remaining, key=lambda pair: priority(pair, valid_degree, queried_degree))
    return {'action': 'compare', 'pair': list(edge)}
