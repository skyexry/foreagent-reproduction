"""Semantic checks of the single R7 tie-break change."""
import unittest
from reproduction.round06.methods import win_rate_select
from reproduction.round07.methods import evidence_tiebreak_select


def edge(a, b, winner, confidence=.8):
    return dict(a=a, b=b, winner=winner if confidence >= .7 else None,
                confidence=confidence, valid=confidence >= .7)


class Round07Tests(unittest.TestCase):
    def test_equal_perfect_rates_favor_more_valid_unique_evidence(self):
        ids = list('ABXYZW')
        rows = [edge('A', 'X', 'A'), edge('B', 'Y', 'B'), edge('B', 'Z', 'B'), edge('B', 'W', 'B')]
        self.assertEqual(win_rate_select(ids, rows)[0], ['A', 'B'])
        self.assertEqual(evidence_tiebreak_select(ids, rows)[0], ['B'])

    def test_support_never_overrides_a_higher_rate(self):
        ids = list('ABXYZ')
        rows = [edge('A', 'X', 'A'), edge('B', 'Y', 'B'), edge('B', 'Z', 'B'), edge('A', 'B', 'A')]
        self.assertEqual(evidence_tiebreak_select(ids, rows)[0], ['A'])

    def test_equal_support_keeps_ties(self):
        self.assertEqual(evidence_tiebreak_select(list('ABXY'),
                         [edge('A', 'X', 'A'), edge('B', 'Y', 'B')])[0], ['A', 'B'])

    def test_repeated_cache_reads_and_low_confidence_do_not_add_support(self):
        ids = list('ABXYZ')
        rows = [edge('A', 'X', 'A'), edge('X', 'A', 'A'), edge('B', 'Y', 'B'), edge('B', 'Z', 'B', .6)]
        self.assertEqual(evidence_tiebreak_select(ids, rows)[0], ['A', 'B'])

    def test_no_valid_feedback_preserves_all_candidates(self):
        ids = list('ABC')
        selected, _, graph = evidence_tiebreak_select(ids, [edge('A', 'B', 'A', .6)])
        self.assertEqual(selected, ids)
        self.assertEqual(graph['selected_isolated'], 3)

    def test_cycle_removes_only_lower_support_isolated_tie(self):
        ids = list('ABCD')
        rows = [edge('A', 'B', 'A'), edge('B', 'C', 'B'), edge('C', 'A', 'C')]
        selected, stats, graph = evidence_tiebreak_select(ids, rows)
        self.assertEqual(selected, list('ABC'))
        self.assertEqual(graph['selected_isolated'], 0)
        self.assertEqual(stats, win_rate_select(ids, rows)[1])

    def test_permutations_preserve_set_and_remaining_display_order(self):
        ids = list('ABXY'); rows = [edge('A', 'X', 'A'), edge('B', 'Y', 'B')]
        a = evidence_tiebreak_select(ids, rows)[0]
        b = evidence_tiebreak_select(ids[::-1], rows[::-1])[0]
        self.assertEqual(set(a), set(b))
        self.assertEqual(b, ['B', 'A'])


if __name__ == '__main__':
    unittest.main()
