"""Reparse saved API responses, reconstruct adoption and compare frozen metrics."""
import json
import os
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import report_coverage_retry as report
from run_coverage import prompt

def main():
    out = Path(os.environ['FOREAGENT_RUN_DIR'])
    (out/'experiments').mkdir(parents=True, exist_ok=True)
    shutil.copyfile(ROOT/'experiments/coverage_author_reference.json', out/'experiments/coverage_author_reference.json')
    report.ROOT = out
    report.OUTPUT = ROOT/'outputs/coverage-20261021'
    report.main()
    actual = json.loads((out/'experiments/coverage_retry_results.json').read_text())
    expected = json.loads((ROOT/'experiments/coverage_retry_results.json').read_text())
    assert actual == expected, 'Adoption or summary changed'
    manifest = json.loads((ROOT/'experiments/coverage_manifest.json').read_text())
    reparsed = 0
    for row in actual['adopted_results']:
        group = manifest['groups'][row['index']]
        assert (row['task'], row['source_group_index'], row['best_index']) == (group['task'], group['source_group_index'], group['best_index'])
        folder = report.OUTPUT/('retry-attempt-002' if row['adopted_attempt'] == 2 else '')
        record = json.loads((folder/f'pair-{row["index"]:03d}.json').read_text())
        assert record['result']['parsed'] == row['parsed']
        choice = record['response']['choices'][0]; message = choice['message']
        combined = (message.get('reasoning_content') or '') + '\n' + (message.get('content') or '')
        parsed = prompt.parse_response(combined, 2)
        assert parsed == row['parsed'] and choice['finish_reason'] == 'stop'
        assert row['correct'] == int(parsed['predicted_best_index'] == group['best_index'])
        reparsed += 1
    check = dict(reparsed_adopted_responses=reparsed, historical_api_calls=actual['total_calls'],
                 new_api_calls=0, correct=actual['combined']['correct'], denominator=actual['selected_pairs'],
                 expected_summary='exact match')
    (out/'verification.json').write_text(json.dumps(check, indent=2)+'\n')
    print(json.dumps(check))

if __name__ == '__main__':
    main()
