"""Runnable control policy, not a proposed research improvement."""
import itertools
import random

_rng = None


def decide(observation):
    global _rng
    if _rng is None:
        _rng = random.Random(observation['seed'])
    seen = {tuple(sorted((r['a'], r['b']))) for r in observation['feedback']}
    remaining = sorted(tuple(sorted(pair)) for pair in itertools.combinations(observation['candidates'], 2)
                       if tuple(sorted(pair)) not in seen)
    if not remaining or observation['remaining_budget'] == 0:
        return {'action':'stop'}
    return {'action':'compare', 'pair':list(_rng.choice(remaining))}
