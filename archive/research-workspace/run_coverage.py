"""Budgeted parallel evaluation of the fixed 26-task coverage sample."""
import argparse
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
import hashlib
import http.client
import json
from pathlib import Path
import platform
import ssl
import time
import urllib.error
import urllib.request

import certifi
from prepare_coverage import ROOT, DATA
from run_smoke import MODEL, INPUT_PRICE, OUTPUT_PRICE, CACHE_PRICE, THINKING_BUDGET, MAX_TOKENS
from vendor.foreagent import prompt
from vendor.foreagent.eval import accuracy_n2

OUTPUT = ROOT / 'outputs' / 'coverage-20261021'
PRIOR_SPEND = 0.43  # Round up the previous smoke evaluation and initial API test.
BUDGET = 20.0


def write_json(path, value):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2))
    temporary.replace(path)


def prepare(manifest):
    for relative, digest in manifest['sha256'].items():
        if hashlib.sha256((DATA / relative).read_bytes()).hexdigest() != digest:
            raise ValueError(f'Input checksum mismatch: {relative}')
    by_task = {}
    for index, source in enumerate(manifest['groups']):
        group = {**source, 'paths': [str(DATA / p) for p in source['paths']]}
        resources = prompt.load_task_resources(source['task'], tasks_root=str(DATA / 'tasks'))
        if not resources['task_desc'] or not resources['data_analysis']:
            raise ValueError(f'Missing task resources: {source["task"]}')
        user = prompt.build_user_prompt(source['task'], group, str(DATA), tasks_root=str(DATA / 'tasks'),
                                        allow_cot=True, prompt_boost=True)
        if '# Could not read file:' in user:
            raise ValueError('Missing candidate code')
        messages = [{'role': 'system', 'content': prompt.BENCH_SYSTEM_PROMPT_COT}, {'role': 'user', 'content': user}]
        payload = {'model': MODEL, 'messages': messages, 'temperature': 1.0,
                   'enable_thinking': True, 'thinking_budget': THINKING_BUDGET,
                   'max_tokens': MAX_TOKENS, 'stream': True}
        input_bytes = sum(len(m['content'].encode()) for m in messages)
        allowance = ((input_bytes + 2048) * INPUT_PRICE + (THINKING_BUDGET + MAX_TOKENS) * OUTPUT_PRICE) / 1e6
        item = {'index': index, 'source': source, 'payload': payload,
                'input_bytes': input_bytes, 'allowance_cny': allowance}
        by_task.setdefault(source['task'], []).append(item)
    # Round-robin tasks so a budget stop does not concentrate on the first few tasks.
    return [items[round_index] for round_index in range(10) for items in by_task.values() if round_index < len(items)]


def read_stream(response, progress=None):
    """Collect SSE content and final usage without waiting silently for the full answer."""
    message = {'role': 'assistant', 'content': '', 'reasoning_content': ''}
    body = {'choices': [{'index': 0, 'message': message, 'finish_reason': None}], 'usage': None}
    ended = False
    last_progress = 0.0
    for line in response:
        if not line.startswith(b'data:'):
            continue
        data = line[5:].strip()
        if data == b'[DONE]':
            ended = True
            break
        chunk = json.loads(data)
        for name in ('id', 'model', 'created', 'system_fingerprint'):
            if name in chunk:
                body[name] = chunk[name]
        if chunk.get('usage'):
            body['usage'] = chunk['usage']
        for choice in chunk.get('choices', []):
            delta = choice.get('delta', {})
            for field in ('content', 'reasoning_content'):
                message[field] += delta.get(field) or ''
            if choice.get('finish_reason'):
                body['choices'][0]['finish_reason'] = choice['finish_reason']
        now = time.monotonic()
        if progress is not None and now - last_progress >= 30:
            progress(len(message['reasoning_content']), len(message['content']))
            last_progress = now
    if not ended or body['usage'] is None:
        raise ValueError('Incomplete stream or missing usage')
    return body


def call_one(item, key, context):
    source = item['source']
    began = time.monotonic()
    result = {'index': item['index'], 'task': source['task'], 'source_group_index': source['source_group_index'],
              'best_index': source['best_index'], 'parsed': {}, 'correct': 0, 'error': None,
              'reasoning_present': False, 'finish_reason': None, 'usage': None,
              'estimated_cost_cny': None, 'budget_charge_cny': item['allowance_cny'], 'transport_error': False}
    body = None
    try:
        request = urllib.request.Request('https://api.siliconflow.cn/v1/chat/completions',
            data=json.dumps(item['payload']).encode(),
            headers={'Authorization': f'Bearer {key}', 'Content-Type': 'application/json'})
        with urllib.request.urlopen(request, context=context, timeout=300) as response:
            def progress(reasoning_chars, answer_chars):
                write_json(OUTPUT / f'progress-{item["index"]:03d}.json',
                           {'index': item['index'], 'seconds': time.monotonic() - began,
                            'reasoning_chars': reasoning_chars, 'answer_chars': answer_chars})
            body = read_stream(response, progress=progress)
        usage = body['usage']
        cached = usage.get('prompt_cache_hit_tokens', usage.get('prompt_tokens_details', {}).get('cached_tokens', 0))
        cost = ((usage['prompt_tokens'] - cached) * INPUT_PRICE + cached * CACHE_PRICE + usage['completion_tokens'] * OUTPUT_PRICE) / 1e6
        result.update(usage=usage, estimated_cost_cny=cost, budget_charge_cny=cost)
        choice = body['choices'][0]
        message = choice['message']
        result.update(finish_reason=choice['finish_reason'], reasoning_present=bool(message.get('reasoning_content')))
        combined = '\n\n'.join(x for x in [message.get('reasoning_content'), message.get('content')] if x)
        parsed = prompt.parse_response(combined, 2)
        if parsed.get('predicted_best_index') not in (0, 1):
            raise ValueError('Predicted index outside 0/1')
        if choice['finish_reason'] != 'stop':
            raise ValueError('Response did not finish normally')
        result.update(parsed=parsed, correct=accuracy_n2(parsed['predicted_best_index'], source['best_index']))
    except (urllib.error.URLError, TimeoutError, ConnectionError, http.client.HTTPException, ssl.SSLError) as exc:
        result.update(error=type(exc).__name__, http_status=getattr(exc, 'code', None), transport_error=True)
    except (ValueError, TypeError, KeyError, IndexError) as exc:
        result.update(error=type(exc).__name__ + ': invalid API output')
        # Unknown usage remains conservatively charged at the request allowance.
        if result['usage'] is None:
            result['transport_error'] = True
    result['seconds'] = time.monotonic() - began
    write_json(OUTPUT / f'pair-{item["index"]:03d}.json', {'result': result, 'request': item['payload'], 'response': body})
    return result


def summarize(metadata, results, pending, inflight, elapsed, stop_reason):
    task_rows = []
    for task in metadata['tasks']:
        records = [r for r in results if r['task'] == task['task']]
        task_rows.append({**task, 'completed': len(records), 'valid': sum(r['error'] is None for r in records),
                          'correct': sum(r['correct'] for r in records)})
    return {**metadata, 'completed_pairs': len(results), 'valid_pairs': sum(r['error'] is None for r in results),
            'correct': sum(r['correct'] for r in results), 'pending_pairs': pending, 'inflight_pairs': inflight,
            'estimated_cost_cny': sum(r['estimated_cost_cny'] or 0 for r in results),
            'budget_accounted_cny_including_prior': PRIOR_SPEND + sum(r['budget_charge_cny'] for r in results),
            'elapsed_seconds': elapsed, 'stop_reason': stop_reason, 'per_task': task_rows,
            'results': sorted(results, key=lambda r: r['index'])}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', action='store_true', help='Make paid API calls')
    parser.add_argument('--workers', type=int, default=16)
    parser.add_argument('--resume', action='store_true', help='Continue undispatched pairs only; never retry recorded requests')
    parser.add_argument('--max-new-calls', type=int, help='Stop after this many new requests, for transport validation')
    args = parser.parse_args()
    if not 1 <= args.workers <= 16:
        raise SystemExit('Use 1–16 workers')
    if args.max_new_calls is not None and args.max_new_calls < 1:
        raise SystemExit('--max-new-calls must be positive')
    manifest = json.loads((DATA / 'manifest.json').read_text())
    prepared = prepare(manifest)
    print(f'Validated {len(prepared)} pairs across {len(manifest["tasks"])} tasks; input bytes={sum(x["input_bytes"] for x in prepared):,}', flush=True)
    print(f'Worst-case total ¥{sum(x["allowance_cny"] for x in prepared):.2f}; execution uses actual spend + reserved in-flight allowances, cap ¥20 including ¥0.43 prior spend.', flush=True)
    if not args.run:
        return
    OUTPUT.mkdir(parents=True, exist_ok=True)
    existing = (OUTPUT / 'started.json').exists() or any(OUTPUT.glob('pair-*.json'))
    if existing and not args.resume:
        raise SystemExit('Existing run found: inspect records before any further paid calls.')
    if args.resume and not existing:
        raise SystemExit('No existing run to resume')
    metadata = {'model': MODEL, 'python': platform.python_version(), 'upstream_commit': manifest['upstream_commit'],
                'dataset_revision': manifest['dataset_revision'], 'manifest_sha256': hashlib.sha256((DATA / 'manifest.json').read_bytes()).hexdigest(),
                'temperature': 1.0, 'thinking_budget': THINKING_BUDGET, 'max_tokens': MAX_TOKENS,
                'allow_cot': True, 'prompt_boost': True, 'retries': 0, 'workers': args.workers,
                'budget_cny': BUDGET, 'prior_spend_allowance_cny': PRIOR_SPEND, 'requested_pairs': len(prepared),
                'pricing_url': 'https://www.siliconflow.cn/pricing',
                'rates_per_million_cny': {'input': INPUT_PRICE, 'output': OUTPUT_PRICE, 'cached_input': CACHE_PRICE},
                'tasks': manifest['tasks'], 'stream': True}
    results, previous_elapsed = [], 0.0
    if args.resume:
        previous = json.loads((OUTPUT / 'summary.json').read_text())
        if previous['inflight_pairs']:
            raise SystemExit('Previous run has unfinished in-flight calls; do not resume yet')
        for field in ('manifest_sha256', 'model', 'temperature', 'thinking_budget', 'max_tokens', 'budget_cny'):
            if previous[field] != metadata[field]:
                raise SystemExit(f'Resume configuration mismatch: {field}')
        results = [json.loads(p.read_text())['result'] for p in sorted(OUTPUT.glob('pair-*.json'))]
        recorded = {r['index'] for r in results}
        dispatched = {json.loads(p.read_text())['index'] for p in OUTPUT.glob('request-*.json')}
        if dispatched != recorded or len(results) != previous['completed_pairs']:
            raise SystemExit('Dispatched requests lack final records; inspect before resuming')
        prepared = [item for item in prepared if item['index'] not in recorded]
        previous_elapsed = previous['elapsed_seconds']
        metadata['transport_history'] = previous.get('transport_history', [
            {'stream': previous.get('stream', False), 'workers': previous['workers']}]) + [
            {'stream': True, 'workers': args.workers, 'resumed_after_pairs': len(results)}]
        write_json(OUTPUT / f'pause-after-{len(results):03d}.json', previous)
    write_json(OUTPUT / 'started.json', metadata)
    key = (Path.home() / '.config/foreagent/siliconflow.key').read_text().strip()
    context = ssl.create_default_context(cafile=certifi.where())
    pending, active = list(prepared), {}
    spent, reserved, stop_reason = PRIOR_SPEND + sum(r['budget_charge_cny'] for r in results), 0.0, None
    started = time.monotonic()
    new_calls = 0
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        while pending or active:
            while pending and len(active) < args.workers and stop_reason is None:
                if args.max_new_calls is not None and new_calls >= args.max_new_calls:
                    stop_reason = 'call_limit'
                    break
                item = pending[0]
                if spent + reserved + item['allowance_cny'] > BUDGET:
                    break
                pending.pop(0)
                reserved += item['allowance_cny']
                new_calls += 1
                write_json(OUTPUT / f'request-{item["index"]:03d}.json',
                           {'index': item['index'], 'task': item['source']['task'], 'allowance_cny': item['allowance_cny'], 'status': 'dispatched'})
                active[pool.submit(call_one, item, key, context)] = item
            if not active:
                if pending and stop_reason is None:
                    stop_reason = 'budget_reservation_limit'
                break
            done, _ = wait(active, timeout=30, return_when=FIRST_COMPLETED)
            for future in done:
                item = active.pop(future)
                result = future.result()
                reserved -= item['allowance_cny']
                spent += result['budget_charge_cny']
                results.append(result)
                if result['transport_error']:
                    stop_reason = 'API_or_network_error_no_new_calls'
                if spent + reserved > BUDGET:
                    stop_reason = 'observed_charge_exceeded_reservation'
                print(f'{len(results)}/{metadata["requested_pairs"]} completed; correct={sum(r["correct"] for r in results)}; errors={sum(r["error"] is not None for r in results)}; cost+prior=¥{spent:.4f}; active={len(active)}; stop={stop_reason}', flush=True)
            summary = summarize(metadata, results, len(pending), len(active), previous_elapsed + time.monotonic() - started, stop_reason)
            write_json(OUTPUT / 'summary.json', summary)
    summary = summarize(metadata, results, len(pending), 0, previous_elapsed + time.monotonic() - started, stop_reason)
    write_json(OUTPUT / 'summary.json', summary)
    print('FINAL', json.dumps({k: summary[k] for k in ['completed_pairs', 'valid_pairs', 'correct', 'pending_pairs', 'estimated_cost_cny', 'stop_reason']}), flush=True)


if __name__ == '__main__':
    main()
