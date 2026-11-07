"""Materialize the pinned leaderboard objects in a local checkout of the author code."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
from pathlib import Path
import sys
import ssl
import certifi
from urllib.request import urlopen
from urllib.error import URLError
import subprocess

root = Path(sys.argv[1]).resolve()
context = ssl.create_default_context(cafile=certifi.where())
commit = 'c4d52cf99bd870d830b456ac7c0684aec1aef375'


def fetch(path):
    relative = path.relative_to(root).as_posix()
    pointer = subprocess.check_output(['git', '-C', str(root), 'show', f'{commit}:{relative}']).decode().splitlines()
    digest = pointer[1].removeprefix('oid sha256:')
    size = int(pointer[2].removeprefix('size '))
    if path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest() == digest:
        return True
    if path.exists() and path.read_text(errors='replace').splitlines() != pointer:
        raise ValueError(f'Unexpected local leaderboard contents: {relative}')
    urls = [f'https://media.githubusercontent.com/media/zjunlp/predict-before-execute/{commit}/{relative}',
            'https://media.githubusercontent.com/media/openai/mle-bench/main/' + relative.removeprefix('mle-bench/')]
    for url in urls:
        try:
            with urlopen(url, context=context, timeout=15) as response:
                data = response.read(size + 1)
        except (URLError, TimeoutError):
            continue
        if len(data) == size and hashlib.sha256(data).hexdigest() == digest:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
            return True
    print('Unavailable:', relative, flush=True)
    return False


tracked = subprocess.check_output(['git', '-C', str(root), 'ls-tree', '-r', '--name-only', commit], text=True)
paths = [root/name for name in tracked.splitlines()
         if name.startswith('mle-bench/mlebench/competitions/') and name.endswith('/leaderboard.csv')]
if len(paths) != 30:
    raise RuntimeError('Expected 30 pinned leaderboard paths')
with ThreadPoolExecutor(max_workers=5) as pool:
    verified = sum(pool.map(fetch, paths))
print(f'{verified}/{len(paths)} leaderboard objects verified')
sys.exit(0 if verified == len(paths) and paths else 1)
