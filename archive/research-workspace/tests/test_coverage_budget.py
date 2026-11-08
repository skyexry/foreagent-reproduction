"""Verify spending and error-stop behavior without real API requests."""
import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import run_coverage as runner


class CoverageBudgetTests(unittest.TestCase):
    def exercise(self, fail_first, resume=False):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            data, output = root / 'data', root / 'output'
            data.mkdir()
            (data / 'manifest.json').write_text(json.dumps({
                'upstream_commit': 'test', 'dataset_revision': 'test',
                'tasks': [{'task': 'test', 'selected_pairs': 8, 'available_pairs': 8}],
            }))
            key_path = root / '.config/foreagent/siliconflow.key'
            key_path.parent.mkdir(parents=True)
            key_path.write_text('fake-test-key')
            items = [{'index': i, 'source': {'task': 'test'}, 'input_bytes': 10,
                      'allowance_cny': 3.0} for i in range(8)]
            calls = []

            def fake_call(item, key, context):
                calls.append(item['index'])
                failed = fail_first and item['index'] == 0
                result = {'index': item['index'], 'task': 'test',
                        'error': 'simulated' if failed else None, 'correct': 0,
                        'estimated_cost_cny': 2.0, 'budget_charge_cny': 2.0,
                        'transport_error': failed}
                runner.write_json(output / f'pair-{item["index"]:03d}.json', {'result': result})
                return result

            with (patch.object(runner, 'DATA', data), patch.object(runner, 'OUTPUT', output),
                  patch.object(runner, 'BUDGET', 10.0), patch.object(runner, 'PRIOR_SPEND', 1.0),
                  patch.object(runner, 'prepare', return_value=items),
                  patch.object(runner, 'call_one', side_effect=fake_call),
                  patch('pathlib.Path.home', return_value=root),
                  patch('sys.argv', ['run_coverage.py', '--run', '--workers', '2']),
                  contextlib.redirect_stdout(io.StringIO())):
                runner.main()
                if resume:
                    with patch('sys.argv', ['run_coverage.py', '--run', '--resume', '--workers', '2']):
                        runner.main()
            return calls, json.loads((output / 'summary.json').read_text())

    def test_budget_reserves_inflight_cost(self):
        calls, summary = self.exercise(False)
        self.assertEqual(len(calls), 4)
        self.assertLessEqual(summary['budget_accounted_cny_including_prior'], 10)
        self.assertEqual(summary['stop_reason'], 'budget_reservation_limit')

    def test_api_failure_stops_new_calls(self):
        calls, summary = self.exercise(True)
        self.assertLessEqual(len(calls), 2)
        self.assertLessEqual(summary['budget_accounted_cny_including_prior'], 10)
        self.assertEqual(summary['stop_reason'], 'API_or_network_error_no_new_calls')

    def test_resume_skips_successes_and_failed_requests(self):
        calls, summary = self.exercise(True, resume=True)
        self.assertEqual(sorted(calls), [0, 1, 2, 3])
        self.assertEqual(len(calls), len(set(calls)))
        self.assertLessEqual(summary['budget_accounted_cny_including_prior'], 10)

    def test_stream_collects_final_usage_without_choices(self):
        events = [
            {'choices': [{'delta': {'reasoning_content': 'reason'}, 'finish_reason': None}]},
            {'choices': [{'delta': {'content': '{"predicted_best_index": 1}'}, 'finish_reason': 'stop'}]},
            {'choices': [], 'usage': {'prompt_tokens': 10, 'completion_tokens': 5, 'total_tokens': 15}},
        ]
        lines = [b': heartbeat\n'] + [b'data: ' + json.dumps(e).encode() + b'\n' for e in events] + [b'data: [DONE]\n']
        result = runner.read_stream(lines)
        self.assertEqual(result['usage']['total_tokens'], 15)
        self.assertEqual(result['choices'][0]['message']['reasoning_content'], 'reason')
        self.assertEqual(result['choices'][0]['finish_reason'], 'stop')

    def test_incomplete_stream_is_rejected(self):
        with self.assertRaises(ValueError):
            runner.read_stream([b'data: {"choices": []}\n'])


if __name__ == '__main__':
    unittest.main()
