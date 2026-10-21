"""Prepare up to ten predetermined pairs for each of the 26 official tasks."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import random
import shutil
import subprocess

from prepare_smoke import ROOT, REVISION, UPSTREAM

DATA = ROOT / 'data' / 'coverage'
SEED = 20261021


def download(relative):
    target = DATA / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.exists():
        previous = ROOT / 'data' / 'smoke' / relative
        if previous.exists():
            shutil.copyfile(previous, target)
        else:
            temp = target.with_suffix(target.suffix + '.part')
            subprocess.run(['curl', '-LfsS', '--retry', '2', '--max-time', '120',
                            f'https://huggingface.co/datasets/zjunlp/PredictBeforeExecute/resolve/{REVISION}/{relative}',
                            '-o', str(temp)], check=True)
            temp.replace(target)
    if not target.stat().st_size or target.read_bytes().startswith(b'version https://git-lfs'):
        raise ValueError(f'Missing data: {relative}')
    return target


def prepare_task(task):
    relative = f'solutions_subset_50/{task}/ground_truth/groups_{task}_n2.json'
    groups = json.loads(download(relative).read_text())
    # Task-specific deterministic seed avoids dependence on download completion order.
    rng = random.Random(f'{SEED}:{task}')
    indices = sorted(rng.sample(range(len(groups)), min(10, len(groups))))
    selected = []
    files = {relative,
             f'tasks/description/description_{task.replace("-", "_")}.md',
             f'tasks/data_analysis/result/da_result_{task}.txt'}
    for index, group in enumerate(groups):
        if len(group['paths']) != 2 or group['best_index'] not in (0, 1):
            raise ValueError(f'Invalid group: {task}/{index}')
        scores = group['scores']
        expected = (min if group['is_lower_better'] else max)(range(2), key=lambda i: scores[i])
        if expected != group['best_index'] or scores[0] == scores[1]:
            raise ValueError(f'Label/score mismatch: {task}/{index}')
    for index in indices:
        group = groups[index]
        paths = [f'solutions_subset_50/{task}/code/{Path(p).name}' for p in group['paths']]
        files.update(paths)
        selected.append({'task': task, 'source_group_index': index, **group, 'paths': paths})
    for relative in sorted(files):
        download(relative)
    print(f'{task}: total={len(groups)}, selected={len(selected)}', flush=True)
    return {'task': task, 'available_pairs': len(groups), 'selected_pairs': len(selected)}, selected, files


def main():
    tasks_path = download('tasks/task_name_subset.txt')
    tasks = tasks_path.read_text().splitlines()
    if len(tasks) != 26 or len(set(tasks)) != 26:
        raise ValueError('Expected 26 distinct tasks')
    with ThreadPoolExecutor(max_workers=8) as pool:
        prepared = list(pool.map(prepare_task, tasks))
    files = {'tasks/task_name_subset.txt'}
    for _, _, paths in prepared:
        files.update(paths)
    manifest = {'upstream_commit': UPSTREAM, 'dataset_revision': REVISION, 'seed': SEED,
                'sampling': 'random.Random(f"{seed}:{task}").sample, at most 10 pairs per task; original order retained',
                'tasks': [item[0] for item in prepared],
                'groups': [group for item in prepared for group in item[1]],
                'sha256': {p: hashlib.sha256((DATA / p).read_bytes()).hexdigest() for p in sorted(files)}}
    (DATA / 'manifest.json').write_text(json.dumps(manifest, indent=2))
    (ROOT / 'experiments' / 'coverage_manifest.json').write_text(json.dumps(manifest, indent=2))
    print('READY', len(tasks), 'tasks;', sum(t['available_pairs'] for t in manifest['tasks']),
          'available pairs;', len(manifest['groups']), 'selected pairs;', len(files), 'files')


if __name__ == '__main__':
    main()
