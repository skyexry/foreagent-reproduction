"""ID alignment and malformed-input checks for the independent online audit scorer."""
import copy
import math
import unittest

from scripts.verify_online_baseline import PREDICTIONS, score_by_id


class OnlineScoreTests(unittest.TestCase):
    def setUp(self):
        self.pred = [{'id_seqpos': k, **{c: str(v) for c in PREDICTIONS}}
                     for k, v in [('a', 1), ('b', 3), ('c', 100)]]
        self.answers = [{'id_seqpos': k, 'keep': keep, **{c: '0' for c in PREDICTIONS}}
                        for k, keep in [('a', 'True'), ('b', 'True'), ('c', 'False')]]

    def test_mask_three_targets_and_row_order(self):
        expected = math.sqrt(5)
        for ps, ys in [(self.pred, self.answers), (self.pred[::-1], self.answers),
                       (self.pred, self.answers[::-1])]:
            result = score_by_id(ps, ys)
            self.assertAlmostEqual(result['score'], expected)
            self.assertEqual(result['scored_rows'], 2)

    def test_duplicate_missing_and_unknown_ids_rejected(self):
        bad = [self.pred[:-1], [self.pred[0], self.pred[0], self.pred[2]]]
        unknown = copy.deepcopy(self.pred)
        unknown[0]['id_seqpos'] = 'unknown'
        for ps in bad+[unknown]:
            with self.assertRaises(ValueError):
                score_by_id(ps, self.answers)

    def test_nonfinite_predictions_rejected(self):
        for value in ('nan', 'inf', '-inf'):
            ps = copy.deepcopy(self.pred)
            ps[0]['reactivity'] = value
            with self.assertRaises(ValueError):
                score_by_id(ps, self.answers)

    def test_missing_columns_rejected(self):
        ps = copy.deepcopy(self.pred)
        del ps[0]['deg_50C']
        with self.assertRaises(KeyError):
            score_by_id(ps, self.answers)

    def test_invalid_and_empty_masks_rejected(self):
        for flag in ('yes', 'False'):
            ys = copy.deepcopy(self.answers)
            for row in ys:
                row['keep'] = flag
            with self.assertRaises(ValueError):
                score_by_id(self.pred, ys)


if __name__ == '__main__':
    unittest.main()
