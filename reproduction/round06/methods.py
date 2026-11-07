"""Label-free R6 aggregation: one vote per accepted unordered pair."""
from fractions import Fraction
import math


def unique_feedback(candidates, comparisons, threshold=0.7):
    assert type(threshold) in (int, float) and 0 < threshold <= 1
    ids = set(candidates)
    assert len(ids) == len(candidates) and ids
    observed = {}
    for c in comparisons:
        a, b = c['a'], c['b']
        assert a in ids and b in ids and a != b
        confidence = c['confidence']
        assert type(confidence) in (int, float) and math.isfinite(confidence) and 0 <= confidence <= 1
        assert isinstance(c['valid'], bool) and c['valid'] == (confidence >= threshold)
        winner = c['winner']
        assert winner in (a, b) if c['valid'] else winner is None
        key = tuple(sorted((a, b)))
        row = dict(a=key[0], b=key[1], winner=winner,
                   confidence=confidence, valid=c['valid'])
        if key in observed:
            assert observed[key] == row, 'Conflicting repeated feedback'
        else:
            observed[key] = row
    return list(observed.values())


def win_rate_select(candidates, feedback, *, threshold=0.7):
    """Input contains only IDs and queried feedback; real scores stay external."""
    unique = unique_feedback(candidates, feedback, threshold)
    wins = dict.fromkeys(candidates, 0)
    losses = dict.fromkeys(candidates, 0)
    neighbors = {x: set() for x in candidates}
    for edge in unique:
        if edge['valid']:
            a, b, winner = edge['a'], edge['b'], edge['winner']
            loser = b if winner == a else a
            wins[winner] += 1
            losses[loser] += 1
            neighbors[a].add(b)
            neighbors[b].add(a)
    scores = {x: Fraction(wins[x], wins[x] + losses[x])
              if wins[x] + losses[x] else Fraction(1, 2) for x in candidates}
    maximum = max(scores.values())
    selected = [x for x in candidates if scores[x] == maximum]
    statistics = {x: dict(wins=wins[x], losses=losses[x],
                          numerator=scores[x].numerator, denominator=scores[x].denominator)
                  for x in candidates}
    unvisited = set(candidates)
    components = 0
    while unvisited:
        components += 1
        stack = [unvisited.pop()]
        while stack:
            for y in neighbors[stack.pop()]:
                if y in unvisited:
                    unvisited.remove(y)
                    stack.append(y)
    isolated = [x for x in candidates if not neighbors[x]]
    graph = dict(unique_feedback=len(unique), valid_unique_edges=sum(e['valid'] for e in unique),
                 isolated_candidates=len(isolated), components=components,
                 all_uninformative=not any(e['valid'] for e in unique),
                 selected_isolated=sum(x in isolated for x in selected))
    return selected, statistics, graph
