"""Verify the baseline's exact code, protocol, result and report fingerprints."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def main():
    manifest = json.loads((ROOT/'BASELINE_FREEZE.json').read_text())
    for name, expected in manifest['files'].items():
        assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest() == expected, name
    print(json.dumps({'freeze_id': manifest['freeze_id'], 'verified_files': len(manifest['files'])}))

if __name__ == '__main__':
    main()
