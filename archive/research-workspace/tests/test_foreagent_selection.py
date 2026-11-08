"""Behavior checks using local fake feedback; no API or candidate execution."""
from concurrent.futures import ThreadPoolExecutor
import json
import random
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from foreagent_selection import CacheFixedWorldModel, pinned
from replay_foreagent_selection import FeedbackBackend, load_tasks, run_one, score_selection


class SelectionTests(unittest.TestCase):
    def setUp(self):
        self.a = SimpleNamespace(id='A', code='code-A')
        self.b = SimpleNamespace(id='B', code='code-B')
        self.calls = []

    def fake_query(self, **kwargs):
        self.calls.append(kwargs['user_message'])
        return json.dumps(dict(predicted_best_index=0, confidence=0.8))

    def model(self, cls=CacheFixedWorldModel):
        return cls('task', 'report', config=pinned.WorldModelConfig(confidence_threshold=0.7))

    def test_reversal_preserves_winner_loser_round_and_first_prompt(self):
        wm = self.model()
        with patch.object(pinned, 'query', self.fake_query):
            ab = wm.predict_pairwise(self.a, self.b, 1)
            ba = wm.predict_pairwise(self.b, self.a, 3)
            again = wm.predict_pairwise(self.a, self.b, 4)
        self.assertEqual(len(self.calls), 1)
        self.assertLess(self.calls[0].index(self.a.code), self.calls[0].index(self.b.code))
        self.assertEqual((ab.winner_idx, ab.loser_idx, ab.round_num), (0, 1, 1))
        self.assertEqual((ba.winner_idx, ba.loser_idx, ba.round_num), (1, 0, 3))
        self.assertEqual((again.winner_idx, again.loser_idx, again.round_num), (0, 1, 4))
        self.assertEqual(ba.confidence, ab.confidence)

    def test_original_retains_known_direction_bug(self):
        wm = self.model(pinned.WorldModel)
        wm._comparison_cache = {}
        with patch.object(pinned, 'query', self.fake_query):
            self.assertEqual(wm.predict_pairwise(self.a, self.b).winner_idx, 0)
            self.assertEqual(wm.predict_pairwise(self.b, self.a).winner_idx, 0)
        self.assertEqual(len(self.calls), 1)

    def test_low_confidence_and_missing_confidence_stay_inconclusive(self):
        for payload in ('{"predicted_best_index": 0, "confidence": 0.6}', '{"predicted_best_index": 0}'):
            wm = self.model()
            with patch.object(pinned, 'query', return_value=payload) as query:
                ab = wm.predict_pairwise(self.a, self.b)
                ba = wm.predict_pairwise(self.b, self.a)
            self.assertEqual(query.call_count, 1)
            self.assertFalse(ab.is_valid)
            self.assertIsNone(ba.winner_idx)
            self.assertIsNone(ba.loser_idx)
            self.assertEqual(ba.confidence, ab.confidence)

    def test_instances_do_not_share_task_feedback(self):
        first, second = self.model(), self.model()
        with patch.object(pinned, 'query', self.fake_query):
            first.predict_pairwise(self.a, self.b)
            second.predict_pairwise(self.b, self.a)
        self.assertEqual(len(self.calls), 2)

    def test_concurrent_reversed_queries_use_one_feedback(self):
        wm = self.model()
        with patch.object(pinned, 'query', self.fake_query):
            with ThreadPoolExecutor(max_workers=2) as executor:
                ab = executor.submit(wm.predict_pairwise, self.a, self.b)
                ba = executor.submit(wm.predict_pairwise, self.b, self.a)
                ab, ba = ab.result(), ba.result()
        self.assertEqual(len(self.calls), 1)
        self.assertEqual((self.a.id, self.b.id)[ab.winner_idx], (self.b.id, self.a.id)[ba.winner_idx])

    def test_high_confidence_tournament_uses_nine_feedbacks(self):
        wm = self.model()
        nodes = [SimpleNamespace(id=str(i), code=f'candidate-{i}') for i in range(10)]
        with patch.object(pinned, 'query', self.fake_query):
            ranked, comparisons, ranks = wm.tournament_rank(nodes)
        self.assertEqual(len(self.calls), 9)
        self.assertEqual(len(comparisons), 9)
        self.assertEqual(sum(r['rank'] == 0 for r in ranks.values()), 1)
        self.assertEqual(len(ranked), 10)

    def test_low_confidence_safety_exit_and_tie(self):
        wm = self.model()
        with patch.object(pinned, 'query', return_value='{"predicted_best_index": 0, "confidence": 0.6}') as query:
            ranked, comparisons, ranks = wm.tournament_rank([self.a, self.b])
        self.assertEqual(query.call_count, 1)
        self.assertEqual(len(comparisons), 10)
        self.assertEqual(max(r['round'] for r in ranks.values()), 5)
        self.assertEqual([ranks[n.id]['rank'] for n in ranked], [0, 0])

    def test_original_cache_prevents_fresh_judgment_without_replay(self):
        # Direct original prompt/parser/batch/tournament. The backend would
        # become confident on its second call, if the cache allowed a call.
        class NeverHitCache(dict):
            def __contains__(self, key):
                return False

        for cache_enabled in (True, False):
            wm = self.model(pinned.WorldModel)
            wm._comparison_cache = {} if cache_enabled else NeverHitCache()
            responses = [json.dumps(dict(predicted_best_index=0, confidence=c))
                         for c in (0.6, 0.9, 0.9)]
            with patch.object(pinned, 'query', side_effect=responses) as query:
                ranked, comparisons, ranks = wm.tournament_rank([self.a, self.b])
            if cache_enabled:
                self.assertEqual(query.call_count, 1)
                self.assertEqual(len(comparisons), 10)
                self.assertEqual(max(c.round_num for c in comparisons), 5)
                self.assertTrue(all(c.confidence == 0.6 for c in comparisons))
                self.assertEqual([ranks[n.id]['rank'] for n in ranked], [0, 0])
            else:
                self.assertEqual(query.call_count, 3)
                self.assertEqual(len(comparisons), 3)
                self.assertEqual(max(c.round_num for c in comparisons), 2)

    def test_metric_direction_and_tied_best(self):
        for lower, scores in ((True, {'A': 1, 'B': 1, 'C': 3}),
                              (False, {'A': 3, 'B': 3, 'C': 1})):
            m = score_selection('C', ['A', 'C'], list(scores), scores, lower)
            self.assertEqual(m['top1_hit'], 0)
            self.assertEqual(m['rank_regret'], 1)
            self.assertEqual(m['uniform_top_hit'], 0.5)
            self.assertAlmostEqual(m['random_hit'], 2 / 3)

    def test_real_feedback_replay_is_deterministic_and_cache_fixed(self):
        tasks, _, _ = load_tasks()
        task = tasks[0]
        order = random.Random(20261107).sample(task['ids'], 10)
        a = run_one('cache_fixed', order, 'test', task['feedback'], task['scores'], task['lower'])
        b = run_one('cache_fixed', order, 'test', task['feedback'], task['scores'], task['lower'])
        self.assertEqual(a, b)
        self.assertEqual(a['metrics']['cache_identity_errors'], 0)
        self.assertEqual(a['metrics']['attempts'], a['metrics']['cache_hits'] + a['metrics']['unique_feedback'])

    def test_replay_matches_original_threaded_tournament_control_flow(self):
        tasks, _, _ = load_tasks()
        task = tasks[0]
        order = random.Random(20261107).sample(task['ids'], 10)
        for kind, cls in (('original', pinned.WorldModel), ('cache_fixed', CacheFixedWorldModel)):
            expected = run_one(kind, order, 'parity', task['feedback'], task['scores'], task['lower'])
            backend = FeedbackBackend(task['feedback'])
            wm = cls('task', '', config=pinned.WorldModelConfig(confidence_threshold=0.7, max_concurrent_requests=1))
            wm._comparison_cache = {}
            with (patch.object(pinned, 'query', backend.query),
                  patch.object(pinned, 'build_pairwise_prompt', lambda **kw: (kw['code_a'], kw['code_b'])),
                  patch.object(pinned, 'random', random.Random('parity'))):
                ranked, comparisons, ranks = wm.tournament_rank([SimpleNamespace(id=c, code=c) for c in order])
            self.assertEqual([n.id for n in ranked], expected['ranked'])
            self.assertEqual(ranks, expected['ranks'])
            self.assertEqual(len(comparisons), expected['metrics']['attempts'])
            self.assertEqual(backend.calls, expected['metrics']['unique_feedback'])


if __name__ == '__main__':
    unittest.main()
