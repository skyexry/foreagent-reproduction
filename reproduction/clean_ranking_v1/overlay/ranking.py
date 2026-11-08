"""Decision-sensitive comparison allocation; only revealed feedback enters selection."""
from fractions import Fraction
import itertools
import random


def top_set(ids, feedback):
    wins = dict.fromkeys(ids, 0)
    degree = dict.fromkeys(ids, 0)
    for a, b, winner in feedback:
        if winner is None:
            continue
        degree[a] += 1
        degree[b] += 1
        wins[winner] += 1
    keys = {i: (Fraction(wins[i], degree[i]) if degree[i] else Fraction(1, 2), degree[i])
            for i in ids}
    best = max(keys.values())
    return [i for i in ids if keys[i] == best]


def choose_active(ids, remaining, feedback, rng):
    """Maximize TV between selections after the two hypothetical valid outcomes.

    This is a sensitivity heuristic; it is not a confidence interval or a
    probabilistic guarantee under correlated, adaptively selected opponents.
    """
    current = set(top_set(ids, feedback))
    degree = dict.fromkeys(ids, 0)
    for a, b, winner in feedback:
        if winner is not None:
            degree[a] += 1
            degree[b] += 1
    edges = list(remaining)
    rng.shuffle(edges)
    def priority(edge):
        a, b = edge
        left = set(top_set(ids, feedback + [(a, b, a)]))
        right = set(top_set(ids, feedback + [(a, b, b)]))
        sensitivity = Fraction(1) - Fraction(len(left & right), max(len(left), len(right)))
        return sensitivity, int(a in current or b in current), -(degree[a] + degree[b])
    return max(edges, key=priority)


def allocate(ids, query, budget, seed, policy):
    rng = random.Random(seed)
    if not ids:
        return [], []
    if len(set(ids)) != len(ids):
        raise ValueError('Candidate identities must be unique')
    edges = [tuple(sorted(e)) for e in itertools.combinations(ids, 2)]
    remaining = set(edges)
    feedback = []
    if policy in ('coverage_random', 'coverage_decision_sensitive'):
        chain = list(ids)
        rng.shuffle(chain)
        initial = [tuple(sorted((a, b))) for a, b in zip(chain, chain[1:])]
    elif policy == 'random_pairs':
        initial = []
    else:
        raise ValueError('Unknown comparison policy: ' + policy)
    for step in range(min(budget, len(edges))):
        if step < len(initial):
            edge = initial[step]
        elif policy == 'coverage_decision_sensitive':
            edge = choose_active(ids, sorted(remaining), feedback, rng)
        else:
            edge = rng.choice(sorted(remaining))
        remaining.remove(edge)
        winner = query(*edge)
        if winner not in (None, *edge):
            raise ValueError('Feedback winner outside queried pair')
        feedback.append((*edge, winner))
    return top_set(ids, feedback), feedback


def rank_candidates(world_model, candidates):
    """Optional live integration; default original tournament stays unchanged."""
    nodes = {n.id: n for n in candidates}
    ids = list(nodes)
    comparisons = []
    def query(a, b):
        result = world_model.predict_pairwise(nodes[a], nodes[b], len(comparisons)+1)
        comparisons.append(result)
        return (a, b)[result.winner_idx] if result.is_valid else None
    top, _ = allocate(ids, query, world_model.config.comparison_budget,
                      world_model.config.selection_seed, world_model.config.selection_policy)
    order = top + [i for i in ids if i not in top]
    meta = {i: {'rank': 0 if i in top else 1, 'round': len(comparisons)} for i in ids}
    return [nodes[i] for i in order], comparisons, meta
