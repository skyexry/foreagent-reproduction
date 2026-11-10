"""Fetch public tree listings and four pinned MLE-bench labels without storing the 33 GB ZIP."""
import argparse
import concurrent.futures
import hashlib
import json
import re
import ssl
import struct
import urllib.request
import zlib
from pathlib import Path

import certifi
from inventory import ROOT

REV='6b322cb88bdbcb2b2d3897ec7d0ded94a5bb2d06'
DATASET='https://huggingface.co/datasets/zjunlp/PredictBeforeExecute'
TREE=DATASET.replace('/datasets/','/api/datasets/')+'/tree/'+REV+'/'
ZIP=DATASET+'/resolve/'+REV+'/tasks/data.zip'
CTX=ssl.create_default_context(cafile=certifi.where())


def get_tree(name, dest):
    url=TREE+'agent_runs/ForeAgent/'+name+'?recursive=true&limit=1000'
    rows=[]
    while url:
        with urllib.request.urlopen(url, context=CTX,timeout=45) as resp:
            rows.extend(json.load(resp))
            nxt=re.search(r'<([^>]+)>;\s*rel="next"',resp.headers.get('Link',''))
            url=nxt[1] if nxt else None
    assert any(v['path'].endswith('/logs/journal.json') for v in rows)
    (dest/(name+'.json')).write_text(json.dumps(rows))


def span(start, length):
    end=start+length-1
    req=urllib.request.Request(ZIP+f'?download=true&bytes={start}-{end}',
                              headers={'Range':f'bytes={start}-{end}','Accept-Encoding':'identity'})
    with urllib.request.urlopen(req,context=CTX,timeout=90) as resp:
        assert resp.status==206 and resp.headers['Content-Range'].startswith(f'bytes {start}-{end}/')
        data=resp.read()
    assert len(data)==length
    return data


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('cache',type=Path)
    root=ap.parse_args().cache
    trees,labels=root/'trees',root/'labels'
    for p in (trees,labels):p.mkdir(exist_ok=True,parents=True)
    manifest=json.loads((ROOT/'experiments/historical-v1/source_manifest.json').read_text())
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
        list(pool.map(lambda name:get_tree(name,trees),sorted({v['run'] for v in manifest})))
    for task,spec in json.loads(Path(__file__).with_name('label_members.json').read_text()).items():
        off=spec['offset']
        h=struct.unpack('<4s5H3L2H',span(off,30))
        assert h[0]==b'PK\x03\x04' and h[3]==spec['method']==8
        prefix=span(off+30,h[-2]+h[-1])
        assert prefix[:h[-2]].decode()==spec['member']
        raw=zlib.decompress(span(off+30+len(prefix),spec['compressed_bytes']),-15)
        assert hashlib.sha256(raw).hexdigest()==spec['sha256']
        (labels/(task+'.csv')).write_bytes(raw)


if __name__=='__main__':
    main()
