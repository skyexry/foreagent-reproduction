"""Prepare the verified official Cactus archive with the frozen author preparer."""
from pathlib import Path
import hashlib
import json
import runpy
import shutil
import sys
import zipfile

import pandas as pd
import yaml

BASE = Path('/root/autodl-tmp/foreagent/cactus-20261115')
SOURCE = Path('/root/autodl-tmp/foreagent/preflight/upstream/mle-bench')
sys.path.insert(0, str(SOURCE))
COMP = SOURCE / 'mlebench/competitions/aerial-cactus-identification'


def digest(path, algorithm='md5'):
    return hashlib.file_digest(path.open('rb'), algorithm).hexdigest()


def main():
    expected = yaml.safe_load((COMP / 'checksums.yaml').read_text())
    archive = BASE / 'data-source/aerial-cactus-identification.zip'
    assert digest(archive) == expected['zip']
    prepared = BASE / 'data-source/prepared'
    raw = BASE / 'data-source/raw'
    public, private = prepared / 'public', prepared / 'private'
    assert not prepared.exists(), prepared
    for path in (raw, public, private):
        path.mkdir(parents=True)
    private.chmod(0o700)
    with zipfile.ZipFile(archive) as zipped:
        assert set(zipped.namelist()) == {'train.csv', 'train.zip', 'test.zip', 'sample_submission.csv'}
        zipped.extractall(raw)
    runpy.run_path(str(COMP / 'prepare.py'))['prepare'](raw, public, private)
    for visibility in ('public', 'private'):
        for name, wanted in expected[visibility].items():
            assert digest(prepared / visibility / name) == wanted, name
    shutil.copyfile(COMP / 'description.md', public / 'description.md')
    shutil.copyfile(BASE / 'data-source/da_result_aerial-cactus-identification.txt', public / 'da_report.txt')
    train, test = pd.read_csv(public / 'train.csv'), pd.read_csv(private / 'test.csv')
    assert len(train) == 14175 and len(test) == 3325
    assert set(train.id).isdisjoint(test.id)
    for subset, frame in [('train', train), ('test', test)]:
        with zipfile.ZipFile(public / (subset + '.zip')) as zipped:
            names = {Path(n).name for n in zipped.namelist() if not n.endswith('/')}
            assert names == set(frame.id)
    assert not (BASE / 'task').exists()
    shutil.copytree(public, BASE / 'task')
    receipt = {'status': 'prepared with unchanged author prepare.py', 'train_rows': len(train),
               'heldout_rows': len(test), 'md5': expected,
               'public_files': {p.name: digest(p, 'sha256') for p in public.iterdir() if p.is_file()},
               'private_path': str(private / 'test.csv')}
    (BASE / 'data-verification.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print(json.dumps(receipt, indent=2))


if __name__ == '__main__':
    main()
