"""Fetch pinned public inputs or verify/import an independently supplied attachment."""
import argparse
import concurrent.futures
import gzip
import hashlib
import json
from pathlib import Path
import shutil
import ssl
import tempfile
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]

def sha(data):
    return hashlib.sha256(data).hexdigest()

def verify(entry, path):
    data = gzip.decompress(path.read_bytes()) if entry['encoding'] == 'gzip' else path.read_bytes()
    assert len(data) == entry['bytes'] and sha(data) == entry['sha256'], entry['target']

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--group', choices=['corpus', 'historical', 'pairwise-inputs'], action='append')
    parser.add_argument('--local-root', type=Path, help='Explicit verified local cache, using repository-relative data/ layout')
    parser.add_argument('--layout', choices=['repository', 'historical'], default='repository')
    parser.add_argument('--check-only', action='store_true')
    parser.add_argument('--limit', type=int, help='Download smoke check only; omit for complete groups')
    parser.add_argument('--attachment', choices=['pairwise'])
    parser.add_argument('--archive', type=Path)
    args = parser.parse_args()
    if args.attachment:
        assert args.archive, '--archive is required'
        info = next(x for x in json.loads((ROOT/'provenance/attachments.json').read_text()) if x['id'] == args.attachment)
        assert sha(args.archive.read_bytes()) == info['sha256'], 'Attachment checksum mismatch'
        with zipfile.ZipFile(args.archive) as archive:
            for item in archive.infolist():
                target = (ROOT/item.filename).resolve()
                assert target.is_relative_to(ROOT/'outputs/coverage-20261021'), item.filename
            archive.extractall(ROOT)
        print(json.dumps({'attachment': args.attachment, 'sha256': info['sha256'], 'files': len(archive.infolist())}))
        return
    groups = args.group or ['corpus', 'historical']
    entries = [e for e in json.loads((ROOT/'provenance/data_manifest.json').read_text())['files'] if e['group'] in groups]
    if args.limit:
        entries = entries[:args.limit]
    try:
        import certifi
        context = ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        context = ssl.create_default_context()
    def fetch(e):
        dst = ROOT/e['target']
        if dst.exists():
            verify(e, dst)
            return
        assert not args.check_only, f'Missing: {e["target"]}'
        dst.parent.mkdir(parents=True, exist_ok=True)
        # All candidates are validated before the atomic replace.
        with tempfile.NamedTemporaryFile(dir=dst.parent, suffix='.part', delete=False) as stream:
            temp = Path(stream.name)
        try:
            if args.local_root:
                relative = e['target'] if args.layout == 'repository' else e['target'].removeprefix('data/historical/')
                shutil.copyfile(args.local_root/relative, temp)
            else:
                with urllib.request.urlopen(e['url'], context=context, timeout=180) as response:
                    data = response.read()
                if e['encoding'] == 'gzip':
                    data = gzip.compress(data, mtime=0)
                temp.write_bytes(data)
            verify(e, temp)
            temp.replace(dst)
        finally:
            temp.unlink(missing_ok=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(fetch, entries))
    print(json.dumps({'groups': groups, 'verified_files': len(entries), 'complete_group': args.limit is None}))

if __name__ == '__main__':
    main()
