"""Match fixed coverage pairs to one released author run; no LLM calls."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import subprocess

from prepare_coverage import ROOT, REVISION

RUN = 'deepseek-reasoner_1p0_pboost_cot_20251209_164656'


def match_task(task, selected):
    relative = f'solutions_subset_50/{task}/report/alignment_{task}_n2_data-both_{RUN}.json'
    target = ROOT / 'data' / 'author_reference' / f'{task}.json'
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.exists():
        temp = target.with_suffix('.part')
        fetched = subprocess.run(['curl', '-LfsS', '--retry', '2', '--max-time', '120',
                                 f'https://huggingface.co/datasets/zjunlp/PredictBeforeExecute/resolve/{REVISION}/{relative}',
                                 '-o', str(temp)], capture_output=True)
        if fetched.returncode:
            return {'task': task, 'source_path': relative, 'error': f'download exit {fetched.returncode}', 'matches': []}
        temp.replace(target)
    rows = json.loads(target.read_text())['results']
    matches = []
    for group in selected:
        names = [Path(p).stem[-4:] + '.py' for p in group['paths']]
        found = [r for r in rows if [s['path'] for s in r['solutions']] == names
                 and [s['score'] for s in r['solutions']] == group['scores']]
        entry = {'source_group_index': group['source_group_index'], 'task': task,
                 'best_index': group['best_index'], 'match_count': len(found)}
        if len(found) == 1 and found[0]['groundtruth']['best_index'] == group['best_index']:
            predicted = found[0]['prediction'].get('best_index')
            if predicted in (0, 1):
                entry.update(author_prediction=predicted, author_correct=int(predicted == group['best_index']))
            else:
                entry['error'] = 'invalid author prediction'
        else:
            entry['error'] = 'non-unique match or label mismatch'
        matches.append(entry)
    print(task, 'matched', sum('author_prediction' in r for r in matches), '/', len(selected), flush=True)
    return {'task': task, 'source_path': relative, 'sha256': hashlib.sha256(target.read_bytes()).hexdigest(),
            'author_source_records': len(rows), 'matches': matches}


def main():
    manifest = json.loads((ROOT / 'experiments/coverage_manifest.json').read_text())
    tasks = [t['task'] for t in manifest['tasks']]
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = [pool.submit(match_task, t, [g for g in manifest['groups'] if g['task'] == t]) for t in tasks]
        records = [f.result() for f in futures]
    result = {'dataset_revision': REVISION, 'author_run': RUN,
              'note': 'One released run, not the paper three-run average; sampling fixed before lookup.',
              'tasks': records}
    (ROOT / 'experiments/coverage_author_reference.json').write_text(json.dumps(result, ensure_ascii=False, indent=2))
    matches = [m for r in records for m in r['matches'] if 'author_prediction' in m]
    print('TOTAL matched', len(matches), 'author correct', sum(m['author_correct'] for m in matches))


if __name__ == '__main__':
    main()
