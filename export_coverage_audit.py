"""Export recoverable coverage evidence without modifying logs or making API calls."""
import argparse
import time
from collections import Counter
from datetime import datetime, timezone
import hashlib
import inspect
import json
import re
import subprocess

from prepare_coverage import ROOT, DATA
from run_coverage import OUTPUT, prepare, write_json
from vendor.foreagent import prompt


def sha(data):
    return hashlib.sha256(data).hexdigest()


def token_fields(usage):
    u = usage or {}
    cached = u.get('prompt_cache_hit_tokens')
    if cached is None:
        cached = (u.get('prompt_tokens_details') or {}).get('cached_tokens')
    return {'input': u.get('prompt_tokens'), 'output': u.get('completion_tokens'),
            'total': u.get('total_tokens'), 'reasoning': (u.get('completion_tokens_details') or {}).get('reasoning_tokens'),
            'cached_input': cached, 'cache_miss_input': u.get('prompt_cache_miss_tokens')}


def aggregate_tokens(results):
    values = [token_fields(r.get('usage')) for r in results]
    return {k: {'known_sum': sum(v[k] for v in values if v[k] is not None) if any(v[k] is not None for v in values) else None,
                'reported_calls': sum(v[k] is not None for v in values),
                'missing_calls': sum(v[k] is None for v in values)} for k in token_fields(None)}


def main():
    destination = OUTPUT / 'audit'
    destination.mkdir(exist_ok=True)
    manifest = json.loads((DATA / 'manifest.json').read_text())
    metadata = json.loads((OUTPUT / 'started.json').read_text())
    prepared = {i['index']: i for i in prepare(manifest)}  # Also verifies all input hashes.
    now = datetime.now(timezone.utc).isoformat()
    run_id = OUTPUT.name
    pairs = []
    for index, group in enumerate(manifest['groups']):
        task = group['task']
        desc = f'tasks/description/description_{task.replace("-", "_")}.md'
        da = f'tasks/data_analysis/result/da_result_{task}.txt'
        source = (DATA / desc).read_text()
        match = re.search(r'(?m)^#{2,3} Evaluation\s*\n', source)
        assert match, task
        # Preserve the source's metric wording; do not infer a metric from score values.
        evaluation = re.split(r'(?m)^#{1,3} ', source[match.end():], maxsplit=1)[0].strip()
        candidates = [{'slot': slot, 'model_index': n, 'candidate_id': path.rsplit('/', 1)[-1],
                       'path': path, 'sha256': manifest['sha256'][path], 'true_score': group['scores'][n]}
                      for n, (slot, path) in enumerate(zip(('A', 'B'), group['paths']))]
        assert group['scores'][0] != group['scores'][1]
        assert group['best_index'] == (min if group['is_lower_better'] else max)(range(2), key=lambda n: group['scores'][n])
        pairs.append({'pair_id': f'{task}/group-{group["source_group_index"]}', 'index': index,
                      'task_id': task, 'source_group_index': group['source_group_index'], 'candidates': candidates,
                      'description': {'path': desc, 'sha256': manifest['sha256'][desc]},
                      'data_report': {'path': da, 'sha256': manifest['sha256'][da]},
                      'metric_definition_verbatim': evaluation, 'metric_source': desc,
                      'is_lower_better': group['is_lower_better'], 'true_winner': ('A', 'B')[group['best_index']]})
    occurrences = Counter(c['path'] for p in pairs for c in p['candidates'])
    write_json(destination / 'pairs_manifest.json', {
        'run_id': run_id, 'data_root': str(DATA), 'dataset': 'zjunlp/PredictBeforeExecute',
        'revision': manifest['dataset_revision'], 'seed': manifest['seed'], 'sampling': manifest['sampling'],
        'without_replacement_within_task': True, 'candidate_order': 'Original order; A=0, B=1; no swap.',
        'exclusions': 'No additional exclusions from author solutions_subset_50 ground_truth groups. Invalid labels, missing inputs, or exact ties abort preparation, not silently exclude pairs. Upstream curation not independently reconstructed.',
        'candidate_reuse_allowed': True, 'candidate_occurrences': dict(occurrences),
        'selected_pairs': len(pairs), 'tasks': manifest['tasks'], 'pairs': pairs,
        'all_input_sha256': manifest['sha256']})
    attempts = []
    for file in sorted(OUTPUT.glob('pair-*.json')):
        record = json.loads(file.read_text())
        result = record['result']; index = result['index']; pair = pairs[index]
        request = record['request']
        expected = dict(prepared[index]['payload']); expected['stream'] = request['stream']
        assert request == expected, f'Actual payload differs from reconstruction: {index}'
        assert (result['task'], result['source_group_index'], result['best_index']) == (
            pair['task_id'], pair['source_group_index'], manifest['groups'][index]['best_index'])
        valid = result['error'] is None
        if valid:
            assert result['finish_reason'] == 'stop'
            assert result['correct'] == int(result['parsed']['predicted_best_index'] == result['best_index'])
        attempt_id = f'{run_id}/{pair["pair_id"]}/attempt-001'
        body = record['response']
        choice = (body or {}).get('choices', [{}])[0]
        # Reparse only for audit classification; do not change the adopted result.
        observed = None
        if body:
            message = choice.get('message', {})
            try:
                observed = prompt.parse_response('\n\n'.join(x for x in [message.get('reasoning_content'), message.get('content')] if x), 2)
            except (ValueError, TypeError, KeyError, IndexError):
                pass
        error = result['error']
        status = ('valid' if valid else 'timeout' if error == 'TimeoutError' else
                  'output_truncated' if choice.get('finish_reason') == 'length' else
                  'api_or_network_error' if result['transport_error'] else 'invalid_output')
        attempts.append({'run_id': run_id, 'pair_id': pair['pair_id'], 'task_id': pair['task_id'],
            'index': index, 'attempt_id': attempt_id, 'is_retry': False,
            'adopted_attempt_id': attempt_id if valid else None, 'status': status, 'error_type_recorded': error,
            'error_message': None, 'http_status_recorded': result.get('http_status'),
            'started_at_utc': None, 'ended_at_utc': None, 'elapsed_seconds': result['seconds'],
            'timestamp_missing_reason': 'Original runner saved elapsed time but no explicit wall-clock timestamps; filesystem times are not substituted.',
            'provider_created': (body or {}).get('created'), 'request': request,
            'raw_response': body, 'response_representation': 'assembled_SSE_message_and_usage' if request['stream'] else 'parsed_HTTP_JSON',
            'original_wire_bytes_saved': False, 'finish_reason': choice.get('finish_reason'),
            'parsed_output_adopted': result['parsed'], 'parsed_output_recovered': observed,
            'choice_adopted': ('A', 'B')[result['parsed']['predicted_best_index']] if valid else None,
            'usage_raw': result['usage'], 'tokens': token_fields(result['usage']),
            'estimated_cost_cny': result['estimated_cost_cny'], 'budget_charge_cny': result['budget_charge_cny'],
            'source_record': str(file.relative_to(OUTPUT)), 'source_sha256': sha(file.read_bytes())})
    temp = destination / 'attempts.jsonl.tmp'
    temp.write_text(''.join(json.dumps(a, ensure_ascii=False) + '\n' for a in attempts))
    temp.replace(destination / 'attempts.jsonl')
    snapshot_files = ['run_coverage.py', 'run_smoke.py', 'prepare_coverage.py', 'vendor/foreagent/prompt.py', 'vendor/foreagent/eval.py', 'requirements-smoke.txt', 'export_coverage_audit.py', 'report_coverage.py']
    snapshots = {}
    head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    for name in snapshot_files:
        content = (ROOT / name).read_bytes(); digest = sha(content)
        target = destination / 'code' / digest / name
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists(): target.write_bytes(content)
        committed_result = subprocess.run(['git', 'show', f'{head}:{name}'], cwd=ROOT, capture_output=True)
        committed = committed_result.stdout if committed_result.returncode == 0 else None
        snapshots[name] = {'path': str(target.relative_to(destination)), 'sha256': digest, 'matches_current_commit': content == committed}
    dispatched = {json.loads(p.read_text())['index'] for p in OUTPUT.glob('request-*.json')}
    completed = {a['index'] for a in attempts}
    assert completed <= dispatched
    config = {'run_id': run_id, 'run_date_from_directory': '2026-10-21', 'started_at_utc': None,
        'audit_exported_at_utc': now, 'recorded_settings': metadata, 'provider': 'SiliconFlow',
        'endpoint': 'https://api.siliconflow.cn/v1/chat/completions', 'dataset': 'zjunlp/PredictBeforeExecute',
        'data_root': str(DATA), 'subset': 'solutions_subset_50; tasks/task_name_subset.txt; 26 tasks, 246 selected pairs',
        'dataset_download_time': None, 'enable_thinking': True,
        'unspecified_parameters': {k: 'provider default / unknown' for k in ['top_p', 'top_k', 'seed', 'frequency_penalty', 'presence_penalty', 'server_model_snapshot']},
        'prompt': {'system': prompt.BENCH_SYSTEM_PROMPT_COT, 'user_template_python': inspect.getsource(prompt.build_user_prompt),
                   'complete_implementation': snapshots['vendor/foreagent/prompt.py'], 'allow_cot': True, 'prompt_boost': True,
                   'input_order': 'Task description, data analysis, instructions and candidate code in original 0/1 order; exact requests are in attempts.jsonl.',
                   'truncation': 'None in client; full code is read. Server-side behavior unknown.',
                   'confidence': 'Optional in the original prompt, unchanged. Raw response preserved; no confidence inferred from prose.'},
        'execution': {'socket_timeout_seconds': 300, 'total_wall_time_limit_seconds': None, 'automatic_retries': 0,
                      'resume_policy': 'Only undispatched pairs; completed failures are not retried.', 'phases': metadata['transport_history']},
        'implementation': {'commit_at_export': head, 'snapshots_captured_at_utc': now, 'files': snapshots,
                           'launch_commit_not_recorded': True, 'early_nonstream_and_single_stream_launch_snapshots': None,
                           'limitation': 'Current snapshots are captured during the run, not retroactively asserted as launch snapshots for earlier phases.'},
        'scoring_rules': str(ROOT / 'experiments/coverage_scoring.md'),
        'source_manifest_sha256': sha((DATA / 'manifest.json').read_bytes()),
        'snapshot_counts': {'selected': len(pairs), 'terminal_attempts_exported': len(attempts),
                            'dispatched_without_terminal_record': sorted(dispatched - completed),
                            'undispatched': sorted(set(range(len(pairs))) - dispatched)},
        'missing_data_policy': 'Null means not recorded/unknown, never zero. Failed partial streams, HTTP error bodies/headers and original SSE frames were not saved.',
        'cost_policy': 'Known usage estimate only; runner assumes no cache discount if cached token count is missing. Unknown usage retains budget allowance, not asserted actual cost. Reasoning tokens are included in output tokens.',
        'aggregate_tokens': aggregate_tokens([json.loads((OUTPUT / a['source_record']).read_text())['result'] for a in attempts])}
    write_json(destination / 'run_config.json', config)
    print(json.dumps({'audit': str(destination), **config['snapshot_counts']}, ensure_ascii=False))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--follow', action='store_true', help='Refresh audit until this existing batch stops; then export the report. No API calls.')
    args = parser.parse_args()
    last_completed = None
    while True:
        summary = json.loads((OUTPUT / 'summary.json').read_text())
        if summary['completed_pairs'] != last_completed:
            main()
            last_completed = summary['completed_pairs']
        if not args.follow:
            break
        if summary['inflight_pairs'] == 0 and (summary['pending_pairs'] == 0 or summary['stop_reason']):
            from report_coverage import main as report
            report()
            break
        time.sleep(30)
