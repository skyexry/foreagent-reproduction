"""One explicitly authorized retry of each failed coverage pair; preserve first attempts."""
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import ssl
import subprocess

import certifi
import run_coverage as runner

FIRST = runner.OUTPUT
OUTPUT = FIRST / 'retry-attempt-002'


def now():
    return datetime.now(timezone.utc).isoformat()


def main():
    first = json.loads((FIRST / 'summary.json').read_text())
    assert first['inflight_pairs'] == 0 and first['pending_pairs'] == 0
    failed = [r for r in first['results'] if r['error'] is not None]
    if OUTPUT.exists():
        raise SystemExit('Retry directory already exists; refusing duplicate paid calls.')
    manifest = json.loads((runner.DATA / 'manifest.json').read_text())
    prepared = {i['index']: i for i in runner.prepare(manifest)}
    items = [prepared[r['index']] for r in failed]
    for item in items:
        original = json.loads((FIRST / f'pair-{item["index"]:03d}.json').read_text())['request']
        assert {k:v for k,v in item['payload'].items() if k != 'stream'} == {k:v for k,v in original.items() if k != 'stream'}
    OUTPUT.mkdir()
    runner.OUTPUT = OUTPUT
    source = Path(__file__).read_bytes()
    (OUTPUT / 'retry_coverage.py.snapshot').write_bytes(source)
    (OUTPUT / 'run_coverage.py.snapshot').write_bytes((runner.ROOT / 'run_coverage.py').read_bytes())
    metadata = {'run_id': 'coverage-20261021-retry-002', 'started_at_utc': now(),
                'first_attempt_directory': str(FIRST), 'retry_indices': [i['index'] for i in items],
                'workers': 4, 'max_attempts_this_stage_per_pair': 1, 'automatic_retries': 0,
                'budget_limit_cny': None, 'authorization': 'User authorized retrying failed pairs after first round and removed concern about the 20 CNY cap.',
                'generation_settings': 'Exactly equal to each original request; transport uses stream=True.',
                'selection_rule': 'Use attempt-001 if valid; otherwise use valid attempt-002. Preserve both and report first-round metrics separately.',
                'script_sha256': hashlib.sha256(source).hexdigest(),
                'commit_at_launch': subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
                'script_snapshot_is_authoritative': True}
    runner.write_json(OUTPUT / 'started.json', metadata)
    key = (Path.home()/'.config/foreagent/siliconflow.key').read_text().strip()
    context = ssl.create_default_context(cafile=certifi.where())
    results = []

    def call(item):
        started = now()
        runner.write_json(OUTPUT / f'request-{item["index"]:03d}.json',
                          {'index': item['index'], 'attempt_id': 2, 'started_at_utc': started, 'request': item['payload']})
        result = runner.call_one(item, key, context)
        return result, started, now()

    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = [pool.submit(call, item) for item in items]
        for future in as_completed(futures):
            result, started, ended = future.result()
            results.append(result)
            saved = json.loads((OUTPUT / f'pair-{result["index"]:03d}.json').read_text())
            with (OUTPUT / 'attempts.jsonl').open('a') as log:
                log.write(json.dumps({'run_id': metadata['run_id'], 'pair_id': f'{result["task"]}/group-{result["source_group_index"]}',
                    'attempt_id': 2, 'is_retry': True, 'started_at_utc': started, 'ended_at_utc': ended, **saved}, ensure_ascii=False)+'\n')
            adopted = {r['index']: r for r in first['results']}
            for r in results:
                if r['error'] is None: adopted[r['index']] = r
            valid = [r for r in adopted.values() if r['error'] is None]
            correct = sum(r['correct'] for r in valid)
            summary = {**metadata, 'completed_retries': len(results), 'selected_retries': len(items),
                       'valid_retries': sum(r['error'] is None for r in results),
                       'combined_valid': len(valid), 'combined_correct': correct,
                       'valid_output_rate': len(valid)/246, 'accuracy_valid_only': correct/len(valid) if valid else None,
                       'accuracy_full_sample': correct/246, 'first_round_valid': first['valid_pairs'], 'first_round_correct': first['correct'],
                       'retry_known_cost_cny': sum(r['estimated_cost_cny'] for r in results if r['estimated_cost_cny'] is not None),
                       'retry_unknown_cost_calls': sum(r['estimated_cost_cny'] is None for r in results),
                       'first_round_known_cost_cny': first['estimated_cost_cny'], 'results': results}
            runner.write_json(OUTPUT / 'summary.json', summary)
            print(f'Retries {len(results)}/{len(items)}; valid={summary["valid_retries"]}; combined={correct}/{len(valid)}', flush=True)
    print('Retry stage finished; original attempt files unchanged.', flush=True)


if __name__ == '__main__':
    main()
