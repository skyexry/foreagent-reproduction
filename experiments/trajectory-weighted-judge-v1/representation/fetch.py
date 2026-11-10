import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import subprocess


def obtain(folder):
    spec=json.loads(Path(__file__).with_name('spec.json').read_bytes())
    folder.mkdir(parents=True, exist_ok=True)
    def fetch(item):
        name, info=item
        path=folder/name
        destination=path if path.exists() else folder/(name+'.partial')
        if not path.exists():
            url=f"https://huggingface.co/{spec['repo']}/resolve/{spec['revision']}/{name}"
            subprocess.run(['curl','-fsSL','--retry','2','--connect-timeout','12','--max-time','240',url,'-o',str(destination)],check=True)
        blob=destination.read_bytes()
        assert len(blob)==info['bytes'], name
        if info['sha256']:
            assert hashlib.sha256(blob).hexdigest()==info['sha256'],name
        else:
            assert hashlib.sha1(f'blob {len(blob)}\0'.encode()+blob).hexdigest()==info['git_blob_sha1'],name
        if destination!=path:
            destination.replace(path)
        return name
    with ThreadPoolExecutor(max_workers=4) as pool:
        for name in pool.map(fetch,spec['files'].items()):
            print('Verified',name,flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('folder',type=Path)
    obtain(p.parse_args().folder)
