"""R6 semantic controls: deduplication, missing evidence and exact ties."""
import unittest
from reproduction.round06.methods import unique_feedback, win_rate_select


def edge(a, b, winner, confidence=.8):
    return dict(a=a, b=b, winner=winner if confidence >= .7 else None,
                confidence=confidence, valid=confidence >= .7)


class Round06Tests(unittest.TestCase):
    def test_transitive_wins_and_reversed_duplicate_count_once(self):
        rows = [edge('A', 'B', 'A'), edge('B', 'A', 'A'),
                edge('A', 'C', 'A'), edge('B', 'C', 'B')]
        top, stats, graph = win_rate_select(list('ABC'), rows)
        self.assertEqual(top, ['A'])
        self.assertEqual(stats['A']['wins'], 2)
        self.assertEqual(graph['unique_feedback'], 3)
        self.assertEqual(graph['components'], 1)

    def test_boundary_and_zero_degree_neutral_value(self):
        top, stats, graph = win_rate_select(list('ABC'), [edge('A', 'B', 'A', .7)])
        self.assertEqual(top, ['A'])
        self.assertEqual((stats['C']['numerator'], stats['C']['denominator']), (1, 2))
        self.assertEqual(graph['isolated_candidates'], 1)
        self.assertEqual(graph['components'], 2)

    def test_low_confidence_does_not_vote_or_disclose_winner(self):
        top, stats, graph = win_rate_select(list('ABC'), [edge('A', 'B', 'A', .6999)])
        self.assertEqual(top, list('ABC'))
        self.assertTrue(graph['all_uninformative'])
        self.assertEqual(sum(s['wins'] for s in stats.values()), 0)
        self.assertEqual(graph['unique_feedback'], 1)

    def test_cycle_and_isolated_node_remain_exactly_tied(self):
        top, stats, graph = win_rate_select(list('ABCD'), [edge('A', 'B', 'A'),
                      edge('B', 'C', 'B'), edge('C', 'A', 'C')])
        self.assertEqual(top, list('ABCD'))
        self.assertEqual(graph['selected_isolated'], 1)
        self.assertTrue(all((s['numerator'], s['denominator']) == (1, 2) for s in stats.values()))

    def test_equal_rational_scores_with_different_degrees(self):
        rows = [edge('A', 'C', 'A'), edge('A', 'D', 'D'),
                edge('B', 'C', 'B'), edge('B', 'D', 'B'),
                edge('B', 'E', 'E'), edge('B', 'F', 'F')]
        _, stats, _ = win_rate_select(list('ABCDEF'), rows)
        self.assertEqual((stats['A']['numerator'], stats['A']['denominator']), (1, 2))
        self.assertEqual((stats['B']['numerator'], stats['B']['denominator']), (1, 2))

    def test_feedback_order_and_candidate_permutation_preserve_top_set(self):
        rows = [edge('A', 'B', 'A'), edge('B', 'C', 'B')]
        a = win_rate_select(list('ABC'), rows)[0]
        b = win_rate_select(list('CBA'), rows[::-1])[0]
        self.assertEqual(set(a), set(b))

    def test_conflicting_cache_feedback_is_rejected(self):
        with self.assertRaises(AssertionError):
            unique_feedback(list('AB'), [edge('A', 'B', 'A'), edge('B', 'A', 'B')])

    def test_out_of_pool_identity_and_invalid_winner_are_rejected(self):
        for row in [edge('A', 'C', 'A'), edge('A', 'B', 'Z')]:
            with self.assertRaises(AssertionError):
                unique_feedback(list('AB'), [row])

    def test_empty_feedback_and_equal_true_scores_scoring(self):
        from reproduction.round06.run import score_selection
        top, _, graph = win_rate_select(list('AB'), [])
        m = score_selection(list('AB'), top, {'A': 1., 'B': 1.})
        self.assertEqual(m['uniform_tie_best_hit'], 1.)
        self.assertEqual(m['normalized_regret'], 0.)
        self.assertEqual(m['selected_percentile'], .5)
        self.assertEqual(graph['components'], 2)


if __name__ == '__main__':
    unittest.main()
