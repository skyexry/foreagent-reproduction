"""Download a fixed 10-pair smoke subset; never execute candidate code."""
import hashlib
import json
from pathlib import Path
import random
import subprocess

REVISION = '6b322cb88bdbcb2b2d3897ec7d0ded94a5bb2d06'
UPSTREAM = 'c4d52cf99bd870d830b456ac7c0684aec1aef375'
TASKS = ['leaf-classification', 'detecting-insults-in-social-commentary']
ROOT = Path(__file__).resolve().parent
DATA = ROOT / 'data' / 'smoke'


def download(relative):
    target = DATA / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.exists():
        temp = target.with_suffix(target.suffix + '.part')
        subprocess.run(['curl', '-LfsS', '--max-time', '120',
                        f'https://huggingface.co/datasets/zjunlp/PredictBeforeExecute/resolve/{REVISION}/{relative}',
                        '-o', str(temp)], check=True)
        temp.replace(target)
    assert target.stat().st_size > 0
    assert not target.read_bytes().startswith(b'version https://git-lfs')
    return target


def main():
    selected = []
    rng = random.Random(20261021)
    for task in TASKS:
        path = download(f'solutions_subset_50/{task}/ground_truth/groups_{task}_n2.json')
        groups = json.loads(path.read_text())
        key = task.replace('-', '_')
        download(f'tasks/description/description_{key}.md')
        download(f'tasks/data_analysis/result/da_result_{task}.txt')
        for index in sorted(rng.sample(range(len(groups)), 5)):
            group = groups[index]
            assert len(group['paths']) == 2 and group['best_index'] in (0, 1)
            scores = group['scores']
            expected = (min if group['is_lower_better'] else max)(range(2), key=lambda i: scores[i])
            assert expected == group['best_index'] and scores[0] != scores[1]
            paths = []
            for original in group['paths']:
                relative = f'solutions_subset_50/{task}/code/{Path(original).name}'
                download(relative)
                paths.append(relative)
            selected.append({'task': task, 'source_group_index': index, **group, 'paths': paths})
        print(task, 'source pairs:', len(groups), 'selected: 5', flush=True)
    manifest = {'upstream_commit': UPSTREAM, 'dataset_revision': REVISION, 'seed': 20261021,
                'groups': selected, 'sha256': {str(p.relative_to(DATA)): hashlib.sha256(p.read_bytes()).hexdigest()
                                            for p in DATA.rglob('*') if p.is_file() and p.name != 'manifest.json'}}
    (DATA / 'manifest.json').write_text(json.dumps(manifest, indent=2))
    print('Ready:', len(selected), 'pairs;', len(manifest['sha256']), 'files')


if __name__ == '__main__':
    main()
