"""Check the collected phase-one files and optionally their original local sources."""
import argparse
import hashlib
import json
import os
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check-originals', action='store_true')
    args = parser.parse_args()
    root = Path(__file__).resolve().parent
    manifest = json.loads((root/'SOURCES.json').read_text())
    checked = 0
    for entry in manifest['files']:
        file = root/entry['path']
        if entry['type'] == 'symlink':
            if not file.is_symlink() or os.readlink(file) != entry['copied_link_target']:
                raise ValueError('Link differs: '+entry['path'])
            if not file.resolve().is_relative_to(root) or not file.is_file():
                raise ValueError('Input link is outside archive or missing: '+entry['path'])
            if args.check_originals and os.readlink(entry['source']) != entry['original_link_target']:
                raise ValueError('Original link differs: '+entry['source'])
        else:
            data = file.read_bytes()
            if len(data) != entry['bytes'] or hashlib.sha256(data).hexdigest() != entry['sha256']:
                raise ValueError('Copy differs: '+entry['path'])
            if args.check_originals and entry['source']:
                raw = Path(entry['source']).read_bytes()
                if len(raw) != entry['bytes'] or hashlib.sha256(raw).hexdigest() != entry['sha256']:
                    raise ValueError('Original differs: '+entry['source'])
        checked += 1
    print(json.dumps({'status':'passed','entries':checked,'original_sources_checked':args.check_originals}))


if __name__ == '__main__':
    main()
