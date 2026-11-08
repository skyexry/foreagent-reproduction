"""Verify Git materials or restore and verify the complete saved run attachment."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import zipfile


def file_hash(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def restore_records(root, manifest, archive, asset):
    """Restore only manifest-listed records; preserve differing existing files."""
    if archive.stat().st_size != asset['bytes'] or file_hash(archive) != asset['sha256']:
        raise ValueError('Attachment SHA-256 or byte count differs')
    expected = {e['path']: e for e in manifest['files'] if e['path'].startswith('records/')}
    with zipfile.ZipFile(archive) as bundle:
        members = bundle.infolist()
        if len(members) != len(expected) or {m.filename for m in members} != expected.keys():
            raise ValueError('Attachment entries differ from the frozen record manifest')
        # Validate every entry before writing any files.
        for member in members:
            e = expected[member.filename]
            destination = root/e['path']
            if not destination.resolve().is_relative_to(root):
                raise ValueError('Record destination escapes the collection')
            data = bundle.read(member)
            is_link = stat.S_ISLNK(member.external_attr >> 16)
            if e['type'] == 'symlink':
                if not is_link or data.decode() != e['copied_link_target']:
                    raise ValueError('Unexpected input link')
                if not (destination.parent/data.decode()).resolve().is_relative_to(root):
                    raise ValueError('Input link escapes the collection')
            elif is_link or len(data) != e['bytes'] or hashlib.sha256(data).hexdigest() != e['sha256']:
                raise ValueError('Record bytes differ: '+e['path'])
            if os.path.lexists(destination):
                same = destination.is_symlink() and os.readlink(destination) == e.get('copied_link_target')
                if not same and (destination.is_symlink() or e['type'] == 'symlink' or
                                 not destination.is_file() or file_hash(destination) != e['sha256']):
                    raise ValueError('Existing local record differs: '+e['path'])
        for member in members:
            e = expected[member.filename]
            destination = root/e['path']
            if os.path.lexists(destination):
                continue
            destination.parent.mkdir(parents=True, exist_ok=True)
            if e['type'] == 'symlink':
                destination.symlink_to(e['copied_link_target'])
            else:
                with destination.open('xb') as stream:
                    stream.write(bundle.read(member))
    return len(expected)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--records', action='store_true', help='Also check downloaded full run records')
    parser.add_argument('--data', action='store_true', help='Also check separately obtained public inputs')
    parser.add_argument('--restore-records', type=Path, help='Verify and restore the Release ZIP')
    parser.add_argument('--check-originals', action='store_true', help='Read original source paths on the experimenter Mac')
    args = parser.parse_args()
    root = Path(__file__).resolve().parent
    manifest = json.loads((root/'SOURCES.json').read_text())
    restored = 0
    if args.restore_records:
        release = json.loads((root/'RELEASE_ASSETS.json').read_text())
        asset = next(a for a in release['assets'] if a['name'] == 'phase1-complete-logs.zip')
        restored = restore_records(root, manifest, args.restore_records.resolve(), asset)
        args.records = True
    checked = 0
    skipped = 0
    for entry in manifest['files']:
        if ((entry['path'].startswith('records/') and not args.records) or
                (entry['path'].startswith('data/') and not args.data)):
            skipped += 1
            continue
        file = root/entry['path']
        if entry['type'] == 'symlink':
            if not file.is_symlink() or os.readlink(file) != entry['copied_link_target']:
                raise ValueError('Link differs: '+entry['path'])
            if not file.resolve().is_relative_to(root):
                raise ValueError('Input link is outside collection')
            if args.data and not file.is_file():
                raise ValueError('Public input missing: '+entry['path'])
            if args.check_originals and os.readlink(entry['source']) != entry['original_link_target']:
                raise ValueError('Original link differs: '+entry['source'])
        else:
            if file.stat().st_size != entry['bytes'] or file_hash(file) != entry['sha256']:
                raise ValueError('Copy differs: '+entry['path'])
            if args.check_originals and entry['source']:
                original = Path(entry['source'])
                if original.stat().st_size != entry['bytes'] or file_hash(original) != entry['sha256']:
                    raise ValueError('Original differs: '+entry['source'])
        checked += 1
    print(json.dumps({'status': 'passed', 'verified_entries': checked, 'optional_entries_skipped': skipped,
                      'restored_records': restored, 'original_sources_checked': args.check_originals}))


if __name__ == '__main__':
    main()
