"""Grade available switches with the fixed author graders. Cache publicly released files by blob."""
import argparse
import concurrent.futures
import hashlib
import importlib
import json
import math
import ssl
import sys
import time
import urllib.request
from pathlib import Path

import certifi
import pandas as pd
from inventory import ROOT, blob, LOCAL

BASE='https://huggingface.co/datasets/zjunlp/PredictBeforeExecute/resolve/6b322cb88bdbcb2b2d3897ec7d0ded94a5bb2d06/'
sys.path.insert(0,str(ROOT/'phase1-reproduction/code/author/mle-bench'))


def retrieve(pred, cache):
    if pred['source_run']==LOCAL:
        path=ROOT/pred['path']
    else:
        path=cache/(pred['oid']+'.csv')
        if not path.exists():
            for trial in range(3):
                try:
                    with urllib.request.urlopen(BASE+pred['path'],context=ssl.create_default_context(cafile=certifi.where()),timeout=55) as resp:
                        data=resp.read()
                    assert blob(data)==pred['oid']
                    path.write_bytes(data)
                    break
                except Exception:
                    if trial==2: raise
                    time.sleep(trial+1)
    assert blob(path.read_bytes())==pred['oid']
    return pred['oid'],path


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    for key in ('pairs','labels','cache','output'):
        ap.add_argument(key,type=Path)
    a=ap.parse_args()
    a.cache.mkdir(exist_ok=True,parents=True)
    rows=json.loads(a.pairs.read_text())
    refs={p['oid']:p for r in rows for k in ('c0','memory') for p in r[k]['predictions']}
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as ex:
        files=dict(ex.map(lambda p:retrieve(p,a.cache),refs.values()))
    scores=[]
    for task in sorted({r['task'] for r in rows}):
        selected=[(r,k,p) for r in rows if r['task']==task for k in ('c0','memory') for p in r[k]['predictions']]
        if not selected:continue
        label=a.labels/(task+'.csv')
        truth=pd.read_csv(label)
        truth_sha=hashlib.sha256(label.read_bytes()).hexdigest()
        grader=importlib.import_module('mlebench.competitions.'+task+'.grade').grade
        idcol='id_seqpos' if task=='stanford-covid-vaccine' else 'id'
        assert truth[idcol].is_unique
        for r,k,p in selected:
            pred=pd.read_csv(files[p['oid']]); assert pred[idcol].is_unique and set(pred[idcol])==set(truth[idcol])
            val=float(grader(pred.copy(),truth.copy()))
            # Audit the Stanford grader's mask/index sensitivity before reporting it.
            aligned=pred.set_index(idcol).loc[truth[idcol]].reset_index()
            aligned_val=float(grader(aligned,truth.copy()))
            assert math.isfinite(val) and abs(val-aligned_val)<1e-10, (r['run'],p['path'],val,aligned_val)
            scores.append(dict(task=task,run=r['run'],first_log_line=r['first_log_line'],arm=k,
                               candidate=r[k]['id'],prediction_git_blob=p['oid'],file=p['path'],
                               prediction_rows=len(pred),answers_sha256=truth_sha,official_score=val))
    a.output.write_text(json.dumps(scores,indent=2)+'\n')
    print('Scores',len(scores),'across',len({s['task'] for s in scores}),'tasks.')


if __name__=='__main__':
    main()
