"""R8 structure, failure handling, canonical cache orientation and task pooling."""
import unittest
from types import SimpleNamespace
from reproduction.round08.data import normalize_prediction, parse_table
from reproduction.round08.run import load_canonical, saved_response_query, run_tournament, task_means
from reproduction.round06.run import METRICS

A, B, C = ['solution_'+x+'.py' for x in ['AAAA', 'BBBB', 'CCCC']]


def group(a=A, b=B):
    return dict(paths=[a, b])


def row(a='AAAA.py', b='BBBB.py', index=0, confidence=.8):
    return dict(solutions=[dict(path=a), dict(path=b)], prediction=dict(best_index=index, confidence=confidence))


class Round08Tests(unittest.TestCase):
    def test_identity_join_uses_files_or_unique_short_suffix(self):
        table, count = parse_table({'results': [row()]}, [group()])
        self.assertEqual(table[tuple(sorted((A, B)))]['winner'], A)
        self.assertEqual(count['pairs'], 1)
        table2, _ = parse_table({'results': [row(A, B)]}, [group()])
        self.assertEqual(table, table2)

    def test_missing_confidence_and_invalid_winner_are_distinct(self):
        a = normalize_prediction({'best_index': 1}, A, B)
        self.assertEqual((a['winner'], a['confidence']), (B, .5))
        b = normalize_prediction({'best_index': None, 'confidence': .9}, A, B)
        self.assertIsNone(b['winner']); self.assertEqual(b['confidence'], 0.)
        self.assertTrue(b['invalid_winner'])

    def test_nonfinite_and_out_of_range_confidence_fail_structure(self):
        for value in [-.1, 1.1, float('nan'), float('inf')]:
            with self.assertRaises(AssertionError):
                normalize_prediction({'best_index': 0, 'confidence': value}, A, B)

    def test_duplicate_or_missing_pair_fails_original_gate(self):
        with self.assertRaises(AssertionError):
            parse_table({'results': [row(), row()]}, [group()])
        with self.assertRaises(AssertionError):
            parse_table({'results': [row()]}, [group(), group(A, C)])

    def test_recovered_failure_restores_only_its_original_pair(self):
        rec = dict(paths_order=[A, C], candidate_pair=sorted([A, C]), group_index=1,
                   parsed={'error': 'recorded original API failure'},
                   normalized=dict(winner=None, confidence=0., confidence_fallback=True, invalid_winner=True))
        table, count = parse_table({'results': [row()]}, [group(), group(A, C)], [rec])
        self.assertEqual(count['raw_recovered_records'], 1)
        self.assertEqual(count['pairs'], 2)
        self.assertIsNone(table[tuple(sorted((A, C)))]['winner'])
        self.assertEqual(table[tuple(sorted((A, C)))]['confidence'], 0.)

    def test_recovery_cannot_overwrite_an_existing_judgment(self):
        rec = dict(paths_order=[A, B], candidate_pair=sorted([A, B]), group_index=0,
                   parsed={'error': 'recorded failure'},
                   normalized=dict(winner=None, confidence=0., confidence_fallback=True, invalid_winner=True))
        with self.assertRaises(AssertionError):
            parse_table({'results': [row()]}, [group()], [rec])

    def test_saved_feedback_orientation_and_canonical_reverse_cache(self):
        mod = load_canonical(); calls = []
        mod.WorldModel._comparison_cache.clear()
        mod.query = saved_response_query({tuple(sorted((A, B))): dict(winner=A, confidence=.9)}, calls)
        wm = mod.WorldModel('toy', '', config=mod.WorldModelConfig(confidence_threshold=.7, max_concurrent_requests=1))
        a, b = [SimpleNamespace(id=x, code=x) for x in [A, B]]
        self.assertEqual(wm.predict_pairwise(a, b).winner_idx, 0)
        self.assertEqual(wm.predict_pairwise(b, a).winner_idx, 1)
        self.assertEqual(len(calls), 1)

    def test_invalid_model_feedback_is_cached_as_zero_confidence(self):
        mod = load_canonical()
        table = {tuple(sorted((A, B))): dict(winner=None, confidence=0.)}
        _, _, trace, feedback = run_tournament(mod, [A, B], table, 1, 'toy')
        self.assertEqual(len(feedback), 1)
        self.assertEqual(len(trace), 10)
        self.assertTrue(all(not e['valid'] and e['confidence'] == 0 for e in trace))

    def test_pooling_keeps_feedback_runs_inside_tasks(self):
        runs = ['one', 'two', 'three']; tasks = ['easy', 'hard']; accum = {}
        for ri, run in enumerate(runs):
            for ti, task in enumerate(tasks):
                value = ri/10+ti/2
                accum[run, task] = [{kind: {m: value for m in METRICS} for kind in ['tournament', 'r6', 'r7']}]*300
        per_run, pooled_tasks, pooled = task_means(accum, {'feedback_runs': runs}, tasks)
        self.assertEqual(len(pooled_tasks), 2)
        self.assertEqual(len(per_run), 3)
        self.assertAlmostEqual(pooled['r7']['normalized_regret'], .35)


if __name__ == '__main__':
    unittest.main()
