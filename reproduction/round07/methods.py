"""R7 changes only the second ordering key within the R6 highest-rate group."""
from reproduction.round06.methods import win_rate_select


def evidence_tiebreak_select(candidates, feedback):
    top, stats, graph = win_rate_select(candidates, feedback)
    support = {x: stats[x]['wins'] + stats[x]['losses'] for x in top}
    maximum = max(support.values())
    selected = [x for x in top if support[x] == maximum]
    return selected, stats, {**graph, 'selected_isolated': sum(support[x] == 0 for x in selected)}
