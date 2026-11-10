"""Run the fixed 10-pair subset with upstream prompts, parser and accuracy metric."""
import argparse
import hashlib
import json
from pathlib import Path
import platform
import ssl
import time
import urllib.error
import urllib.request

import certifi
from vendor.foreagent import prompt
from vendor.foreagent.eval import accuracy_n2
from prepare_smoke import DATA, ROOT

MODEL = 'Pro/deepseek-ai/DeepSeek-V3.2'
# SiliconFlow pricing page checked 2026-10-21, CNY per million tokens.
INPUT_PRICE, OUTPUT_PRICE, CACHE_PRICE = 4.0, 6.0, 0.4
THINKING_BUDGET, MAX_TOKENS = 32768, 8192


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', action='store_true', help='Make paid API calls; default is dry-run')
    args = parser.parse_args()
    manifest = json.loads((DATA / 'manifest.json').read_text())
    for relative, digest in manifest['sha256'].items():
        assert hashlib.sha256((DATA / relative).read_bytes()).hexdigest() == digest, relative
    prepared = []
    for source in manifest['groups']:
        group = {**source, 'paths': [str(DATA / p) for p in source['paths']]}
        resources = prompt.load_task_resources(source['task'], tasks_root=str(DATA / 'tasks'))
        assert resources['task_desc'] and resources['data_analysis']
        user = prompt.build_user_prompt(source['task'], group, str(DATA), tasks_root=str(DATA / 'tasks'),
                                        allow_cot=True, prompt_boost=True)
        assert '# Could not read file:' not in user
        messages = [{'role': 'system', 'content': prompt.BENCH_SYSTEM_PROMPT_COT},
                    {'role': 'user', 'content': user}]
        payload = {'model': MODEL, 'messages': messages, 'temperature': 1.0,
                   'enable_thinking': True, 'thinking_budget': THINKING_BUDGET,
                   'max_tokens': MAX_TOKENS, 'stream': False}
        # UTF-8 byte count is a deliberately conservative input-token allowance.
        input_allowance = sum(len(m['content'].encode()) for m in messages) + 2048
        upper_cost = (input_allowance * INPUT_PRICE + (THINKING_BUDGET + MAX_TOKENS) * OUTPUT_PRICE) / 1e6
        prepared.append((source, payload, upper_cost))
    total_allowance = sum(x[2] for x in prepared)
    assert len(prepared) == 10 and total_allowance < 20
    print(f'Validated 10 pairs, full prompt inputs present; conservative allowance ¥{total_allowance:.4f}', flush=True)
    if not args.run:
        return

    output = ROOT / 'outputs' / 'smoke-20261021'
    output.mkdir(parents=True, exist_ok=True)
    # No automatic retries or implicit resume: avoid accidental duplicate charges.
    if any(output.glob('pair-*.json')) or (output / 'started.json').exists():
        raise SystemExit('Existing run found; inspect it before issuing more requests.')
    metadata = {'model': MODEL, 'python': platform.python_version(), 'upstream_commit': manifest['upstream_commit'],
                'dataset_revision': manifest['dataset_revision'], 'temperature': 1.0,
                'thinking_budget': THINKING_BUDGET, 'max_tokens': MAX_TOKENS,
                'allow_cot': True, 'prompt_boost': True, 'retries': 0, 'budget_cny': 20,
                'conservative_allowance_cny': total_allowance, 'pricing_url': 'https://www.siliconflow.cn/pricing',
                'rates_per_million_cny': {'input': INPUT_PRICE, 'output': OUTPUT_PRICE, 'cached_input': CACHE_PRICE}}
    (output / 'started.json').write_text(json.dumps(metadata, indent=2))
    key = (Path.home() / '.config/foreagent/siliconflow.key').read_text().strip()
    context = ssl.create_default_context(cafile=certifi.where())
    results = []
    start = time.monotonic()
    for index, (source, payload, allowance) in enumerate(prepared):
        request = urllib.request.Request('https://api.siliconflow.cn/v1/chat/completions',
            data=json.dumps(payload).encode(), headers={'Authorization': f'Bearer {key}', 'Content-Type': 'application/json'})
        print(f'Calling {index + 1}/10: {source["task"]} group {source["source_group_index"]}', flush=True)
        began = time.monotonic()
        try:
            with urllib.request.urlopen(request, context=context, timeout=300) as response:
                body = json.load(response)
        except (urllib.error.URLError, TimeoutError) as exc:
            # Do not print response/request headers or credentials.
            failure = {'index': index, 'error_type': type(exc).__name__, 'http_status': getattr(exc, 'code', None)}
            (output / 'failure.json').write_text(json.dumps(failure, indent=2))
            print('Stopped on API/network error:', failure, flush=True)
            break
        choice = body['choices'][0]
        message = choice['message']
        combined = '\n\n'.join(x for x in [message.get('reasoning_content'), message.get('content')] if x)
        parsed, error = {}, None
        try:
            parsed = prompt.parse_response(combined, 2)
            if parsed.get('predicted_best_index') not in (0, 1):
                raise ValueError('Predicted index is outside 0/1')
            if choice['finish_reason'] != 'stop':
                raise ValueError('Response did not finish normally')
        except (ValueError, TypeError, KeyError) as exc:
            error = str(exc)
        usage = body['usage']
        cached = usage.get('prompt_cache_hit_tokens', usage.get('prompt_tokens_details', {}).get('cached_tokens', 0))
        cost = ((usage['prompt_tokens'] - cached) * INPUT_PRICE + cached * CACHE_PRICE + usage['completion_tokens'] * OUTPUT_PRICE) / 1e6
        record = {'index': index, 'task': source['task'], 'source_group_index': source['source_group_index'],
                  'best_index': source['best_index'], 'parsed': parsed, 'error': error,
                  'correct': accuracy_n2(parsed['predicted_best_index'], source['best_index']) if not error else 0,
                  'reasoning_present': bool(message.get('reasoning_content')), 'finish_reason': choice['finish_reason'],
                  'usage': usage, 'estimated_cost_cny': cost, 'seconds': time.monotonic() - began}
        # Preserve exact inputs and raw API response locally for audit, never the key.
        (output / f'pair-{index:02d}.json').write_text(json.dumps({'result': record, 'request': payload, 'response': body}, ensure_ascii=False, indent=2))
        results.append(record)
        print(f'Completed {index + 1}/10: correct={record["correct"]}, parse_error={error}, tokens={usage["total_tokens"]}, estimated ¥{cost:.4f}', flush=True)
    summary = {**metadata, 'requested_pairs': 10, 'completed_pairs': len(results),
               'valid_pairs': sum(r['error'] is None for r in results),
               'correct': sum(r['correct'] for r in results),
               'accuracy_on_completed_counting_invalid_as_wrong': sum(r['correct'] for r in results) / len(results) if results else None,
               'estimated_cost_cny': sum(r['estimated_cost_cny'] for r in results),
               'elapsed_seconds': time.monotonic() - start, 'results': results}
    (output / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    print('SUMMARY', json.dumps({k: summary[k] for k in ['completed_pairs', 'valid_pairs', 'correct', 'estimated_cost_cny', 'elapsed_seconds']}), flush=True)


if __name__ == '__main__':
    main()
