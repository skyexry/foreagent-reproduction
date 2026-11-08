"""Restore checksum-pinned research inputs from the versioned Release archive.

Download with the authenticated GitHub CLI, then supply --archive. Existing files
are verified first and kept. --check-only verifies the complete restored layout.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import tempfile
import zipfile

ROOT=Path(__file__).resolve().parents[1]


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def restore(root,archive=None,check_only=False):
    root=Path(root).resolve()
    entries=json.loads((root/'research/protected_manifest.json').read_text())['sha256']
    targets={}
    for name,expected in entries.items():
        path=root/name
        if Path(name).is_absolute() or not path.resolve().is_relative_to(root) or path.is_symlink():
            raise ValueError('Unexpected input path: '+name)
        if path.exists() and sha(path.read_bytes())!=expected:
            raise ValueError('Existing file differs; preserved for review: '+name)
        targets[name]=path
    if check_only:
        missing=[name for name,path in targets.items() if not path.is_file()]
        if missing:
            raise ValueError('Missing protected inputs: '+str(len(missing)))
        return dict(status='verified',protected_files=len(entries),restored=0)
    if archive is None:
        raise ValueError('Supply --archive or --check-only')
    info=json.loads((root/'research/input_bundle.json').read_text())
    archive=Path(archive)
    if sha(archive.read_bytes())!=info['sha256']:
        raise ValueError('Archive SHA-256 mismatch')
    if sha((root/'research/protected_manifest.json').read_bytes())!=info['protected_manifest_sha256']:
        raise ValueError('Archive/environment version mismatch')
    restored=0
    with zipfile.ZipFile(archive) as bundle:
        names=bundle.namelist()
        if len(names)!=len(set(names)) or set(names)!=set(entries):
            raise ValueError('Archive file population differs from pinned manifest')
        # Validate all entries before creating any destination files.
        for name,expected in entries.items():
            item=bundle.getinfo(name)
            if (item.external_attr>>16)&0o170000==0o120000 or sha(bundle.read(name))!=expected:
                raise ValueError('Archive entry mismatch: '+name)
        for name,path in targets.items():
            if path.exists():
                continue
            path.parent.mkdir(parents=True,exist_ok=True)
            with tempfile.NamedTemporaryFile(dir=path.parent,prefix='.restore-',delete=False) as stream:
                temporary=Path(stream.name)
                stream.write(bundle.read(name))
            try:
                # Atomic create without replacing a concurrent existing file.
                os.link(temporary,path)
            finally:
                temporary.unlink()
            restored+=1
    restore(root,check_only=True)
    return dict(status='verified',protected_files=len(entries),restored=restored)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    mode=parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--archive',type=Path)
    mode.add_argument('--check-only',action='store_true')
    args=parser.parse_args()
    print(json.dumps(restore(ROOT,args.archive,args.check_only),indent=2))


if __name__=='__main__':
    main()
