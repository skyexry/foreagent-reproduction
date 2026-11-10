"""Audit saved decisions against author filenames, code, vectors, C0 ranks and utilities."""
from collections import defaultdict
from functools import lru_cache
import gzip
import json
from pathlib import Path
from statistics import fmean
import sys
from uuid import UUID

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
PREP = ROOT/"experiments/clean-ranking-v1/prepared"
OLD = HERE.parent/"embedding-rerank-v1"
TRAIN = HERE.parent/"trajectory-weighted-judge-v1"
sys.path.insert(0,str(TRAIN/"train"))
from data import load_codes


def load(path):
    return json.loads(path.read_bytes())


def run_id(path):
    prefix, _ = Path(path).stem.rsplit("_run_",1)
    try:
        return str(UUID(prefix.split("_")[-1]))
    except ValueError:
        return None


def mids(vals):
    # Twice the zero-based average rank; the common factors do not affect winners.
    return [sum(2*(y<x)+(y==x) for y in vals)-1 for x in vals]


def main(out):
    labels = load(PREP/"evaluation_labels.json")
    hashes = {t:{i:c["ast_sha256"] for i,c in d.items()} for t,d in load_codes().items()}
    runs = {t:{i:run_id(p) for i,p in d.items()} for t,d in load(PREP/"code_files.json").items()}
    ranks = {(r["bank"],r["job"]):r for r in map(json.loads,gzip.open(OLD/"ranks.jsonl.gz","rt"))}
    cover = load(out/"coverage.json")
    expected = load(out/"per-task.json")
    summaries = load(out/"summary.json")
    with np.load(TRAIN/"representation/run_1/embeddings.npz",allow_pickle=False) as emb:
        k = {x:i for i,x in enumerate(emb["code_keys"].tolist())}
        v = emb["code"].astype(float)
    v /= np.linalg.norm(v,axis=1)[:,None]
    cos = v @ v.T

    @lru_cache(maxsize=None)
    def validate_pool(pool, t, ids):
        r = {runs[t][i] for i in ids}
        blocked = {h for i,h in hashes[t].items() if runs[t][i] in r}
        allowed = {i for i,h in hashes[t].items() if h not in blocked and runs[t][i] is not None}
        distinct = {hashes[t][i] for i in allowed} if None not in r else set()
        n = min(10,len(distinct)//2)
        assert cover[pool]["n_available"]==n, pool
        return allowed, n if n>=3 else 0

    seen = set()
    cells = defaultdict(list)
    for b,j,s,hm,hs,c0,mix,strict in map(json.loads,gzip.open(out/"decisions.jsonl.gz","rt")):
        key = b,j,s
        assert key not in seen and 0<=s<5
        seen.add(key)
        row = ranks[b,j]
        ids,t = row["ids"],row["task"]
        pool = j.rsplit(":",1)[0]
        allowed,n = validate_pool(pool,t,tuple(sorted(ids)))
        assert len(hm)==len(hs)==n and set(hs)<=allowed
        targets = {hashes[t][i] for i in ids}
        base = mids(row["ranks"])
        for arm,h,picks in (("c0",[],c0),("mixed",hm,mix),("strict",hs,strict)):
            hr = {hashes[t][i] for i in h}
            assert len(hr)==len(h) and targets.isdisjoint(hr)
            fused = base
            if h:
                weights = mids([labels[t][i] for i in h])
                js = [k[t+"|"+i] for i in h]
                pred = []
                for i in ids:
                    sim = cos[k[t+"|"+i], js]
                    near = sorted(range(n),key=lambda a:-sim[a])[:3]
                    pred.append(-sum(weights[a] for a in near))
                fused = [x+y for x,y in zip(base,mids(pred))]
            assert picks==[i for i,r in zip(ids,fused) if r==min(fused)], key
            hi,lo = max(labels[t][i] for i in ids),min(labels[t][i] for i in ids)
            loss = (hi-fmean(labels[t][i] for i in picks))/(hi-lo) if hi>lo else 0.
            family = "DS" if b=="DS" else "GPT"
            for which in (("all","eligible") if n else ("all",)):
                cells[which,family,t,arm].append(loss)
    assert len(seen)==len(ranks)*5==17000
    old = load(OLD/"history-control/results.json")
    for g,groups in expected.items():
        for f,tasks in groups.items():
            for t,a in tasks.items():
                for arm,val in a.items():
                    assert abs(fmean(cells[g,f,t,arm])-val)<1e-12
            for arm in ("c0","mixed","strict"):
                macro = fmean(fmean(cells[g,f,t,arm]) for t in tasks)
                assert abs(macro-summaries["metrics"][g][f]["loss"][arm])<1e-12
            if g=="all":
                assert abs(summaries["metrics"][g][f]["loss"]["c0"]-old["summary"][f]["all"]["regret"]["c0"])<1e-12
    print(f"{len(seen)} decision records: coverage, matched history counts, run/AST isolation, all 3 winners and all task/family losses verified.")


if __name__=="__main__":
    main(Path(sys.argv[1]) if len(sys.argv)>1 else HERE/"run-001")
