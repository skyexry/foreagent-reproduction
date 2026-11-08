"""Verify the published manifest before executing any assertion-based baseline checks."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
MANIFEST_DIGEST = '25929f530088b895f8e0093f4ede6703c8925807ebd493ca004de6675149981d'


def preflight(root=ROOT):
    if not __debug__:
        raise RuntimeError('Baseline verification requires assertions enabled')
    data = (root/'BASELINE_FREEZE.json').read_bytes()
    if hashlib.sha256(data).hexdigest() != MANIFEST_DIGEST:
        raise ValueError('Manifest differs from published fd55d93')
    files = json.loads(data)['files']
    for name, digest in files.items():
        if hashlib.sha256((root/name).read_bytes()).hexdigest() != digest:
            raise ValueError(f'Frozen file mismatch: {name}')
    return len(files)


if __name__ == '__main__':
    print(f'Checked {preflight()} files against release manifest', flush=True)
    if len(sys.argv)>1:
        subprocess.run([sys.executable, str(ROOT/'scripts/reproduce.py'), *sys.argv[1:]], check=True)
        if sys.argv[1] in ('all', 'corpus'):
            from audit_baseline_scores import audit
            for variant in ('original', 'cache-fixed'):
                print(variant, audit(ROOT/'runs/corpus'/variant))
