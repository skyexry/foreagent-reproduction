#!/usr/bin/env python3
"""Fetch pinned metadata first, then hash-verify only the two preregistered reports."""
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import ssl
import sys
import time
import urllib.error
import urllib.request

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
PROTO=json.loads((HERE/'protocol.json').read_text())
REPO=PROTO['source']['dataset'];REV=PROTO['source']['revision'];RUNS=PROTO['source']['banks']
CACHE=Path(PROTO['limits']['download_location']);CACHE.mkdir(parents=True,exist_ok=True)
OUT=HERE/sys.argv[1]
assert not OUT.exists();OUT.mkdir()
shutil.copyfile(__file__,OUT/'fetch.snapshot.py')
shutil.copyfile(HERE/'protocol.json',OUT/'protocol.snapshot.json')
started=time.monotonic()
try:
    import certifi
    CONTEXT=ssl.create_default_context(cafile=certifi.where())
except ImportError:CONTEXT=ssl.create_default_context()


def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def dump(p,x):Path(p).write_text(json.dumps(x,indent=2,sort_keys=True)+'\n')
def read_url(url):
    req=urllib.request.Request(url,headers={'User-Agent':'ForeAgent-reproducibility/1.0'})
    return urllib.request.urlopen(req,context=CONTEXT,timeout=120)


def metadata(task):
    url=f'https://huggingface.co/api/datasets/{REPO}/tree/{REV}/solutions_subset_50/{task}/report?recursive=false&expand=false'
    path=CACHE/('tree_'+task+'.json')
    try:
        if path.exists():raw=path.read_bytes()
        else:
            with read_url(url) as response:raw=response.read()
            path.write_bytes(raw)
        rows=json.loads(raw)
        assert isinstance(rows,list)
        expected={f'alignment_{task}_n2_data-both_{run}.json':run for run in RUNS}
        found=[]
        for row in rows:
            filename=Path(row.get('path','')).name
            if filename in expected:
                found.append({'feedback_run':expected[filename],'task':task,'source_path':row['path'],
                              'bytes':row['size'],'git_blob_oid':row['oid'],'lfs':row.get('lfs'),
                              'url':f'https://huggingface.co/datasets/{REPO}/resolve/{REV}/'+row['path'],
                              'target':str(CACHE/'sources'/expected[filename]/(task+'.json'))})
        return {'task':task,'metadata_url':url,'metadata_path':str(path),'metadata_sha256':sha(path),
                'found':found,'missing_runs':sorted(set(RUNS)-{r['feedback_run'] for r in found})}
    except Exception as e:return {'task':task,'error':repr(e),'metadata_url':url}


def verify(entry,path):
    data=path.read_bytes();assert len(data)==entry['bytes'],'byte size mismatch'
    if entry['lfs']:
        assert hashlib.sha256(data).hexdigest()==entry['lfs']['oid'],'LFS SHA256 mismatch'
        pointer=f'version https://git-lfs.github.com/spec/v1\noid sha256:{entry["lfs"]["oid"]}\nsize {len(data)}\n'.encode()
        assert hashlib.sha1(b'blob '+str(len(pointer)).encode()+b'\0'+pointer).hexdigest()==entry['git_blob_oid'],'LFS pointer Git blob mismatch'
    else:assert hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()==entry['git_blob_oid'],'Git blob mismatch'
    return hashlib.sha256(data).hexdigest()


def fetch(entry):
    path=Path(entry['target']);path.parent.mkdir(parents=True,exist_ok=True)
    result=dict(entry);errors=[]
    for attempt in range(2):
        if time.monotonic()-started>570:
            errors.append('analysis 600s cap approaching');break
        try:
            if path.exists():digest=verify(entry,path)
            else:
                temp=path.with_suffix('.attempt_'+str(attempt)+'.part')
                with read_url(entry['url']) as response,temp.open('wb') as stream:
                    shutil.copyfileobj(response,stream,1024*1024)
                digest=verify(entry,temp);temp.replace(path)
            result.update(status='verified',sha256=digest,attempt=attempt,previous_errors=errors)
            return result
        except Exception as e:errors.append(repr(e))
    result.update(status='failed',errors=errors)
    return result


jobs=[json.loads(s) for s in (ROOT/'experiments/clean-ranking-v1/prepared/jobs.jsonl').read_text().splitlines()]
tasks=sorted({j['task'] for j in jobs})
with ThreadPoolExecutor(max_workers=8) as pool:
    meta=sorted(pool.map(metadata,tasks),key=lambda x:x['task'])
dump(OUT/'metadata_manifest.json',{'revision':REV,'repo':REPO,'tasks':meta,'registered_protocol_sha256':sha(HERE/'protocol.json')})
entries=[r for task in meta for r in task.get('found',[])]
print(json.dumps({'stage':'metadata','found':len(entries),'tasks':len(meta),'errors':[m for m in meta if 'error' in m]}),flush=True)
results=[]
with ThreadPoolExecutor(max_workers=4) as pool:
    pending=[pool.submit(fetch,e) for e in entries]
    for future in as_completed(pending):
        result=future.result();results.append(result)
        print(json.dumps({'stage':'fetch','task':result['task'],'run':result['feedback_run'],'status':result['status'],
                          'bytes':result['bytes'],'errors':result.get('errors')}),flush=True)
dump(OUT/'download_manifest.json',{'status':'complete' if len(results)==52 and all(r['status']=='verified' for r in results) else 'partial',
    'files':sorted(results,key=lambda r:(r['feedback_run'],r['task'])),'metadata_manifest_sha256':sha(OUT/'metadata_manifest.json'),
    'elapsed_seconds':time.monotonic()-started,'timestamp_utc':datetime.now(timezone.utc).isoformat(),
    'new_API_or_model_calls':0,'script_sha256':sha(__file__)})
dump(OUT/'hashes.json',{p.name:sha(p) for p in OUT.iterdir() if p.is_file() and p.name!='hashes.json'})
print('download stage finished',flush=True)
