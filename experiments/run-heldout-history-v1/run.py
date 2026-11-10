"""Compare same-task history sources on frozen selections, matching score budgets."""
import argparse
from collections import Counter, defaultdict
import gzip
import hashlib
import json
from pathlib import Path
import random
import re
from statistics import fmean
import sys

import numpy as np
from scipy.stats import rankdata

HERE = Path(__file__).resolve().parent
EXP = HERE.parent / "embedding-rerank-v1"
sys.path.insert(0, str(EXP))
from study import PREP, ROOT, TRAIN, intervals, load_codes, save
sys.path.insert(0, str(ROOT))
from reproduction.clean_ranking_v1.correctness import response_values

ARMS = ("c0", "mixed", "strict")
RUN = re.compile(r"_([0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12})_run_[^/]+\.py$")


def libraries(ids, hashes, runs):
    target = {runs[x] for x in ids}
    pool_hashes = {hashes[x] for x in ids}
    # Removing blocked hashes before choosing representatives also excludes aliases
    # of off-pool programs from the target runs.
    blocked = {hashes[x] for x in hashes if runs[x] in target}
    mixed, strict = [], []
    seen_m, seen_s = pool_hashes.copy(), blocked | pool_hashes
    for x in sorted(hashes):
        h = hashes[x]
        if h not in seen_m:
            mixed.append(x)
            seen_m.add(h)
        if None not in target and runs[x] is not None and h not in seen_s:
            strict.append(x)
            seen_s.add(h)
    assert set(strict) <= set(mixed)
    return mixed, strict, target


def paired_draw(pool, seed, mixed, strict, n):
    rng = random.Random(f"advisor-history-v1|{pool.rsplit(':',1)[0]}|{pool}|{seed}")
    mixed_draw = rng.sample(mixed, 2 * n)
    strict_ids = set(strict)
    keep = set(mixed_draw) & strict_ids
    repl = random.Random(f"run-heldout-replace|{pool}|{seed}").sample(
        sorted(strict_ids - keep), 2*n - len(keep))
    new = iter(repl)
    strict_draw = [x if x in strict_ids else next(new) for x in mixed_draw]
    return (mixed_draw, strict_draw), [rng.choice((0, 1)) for _ in range(n)]


def reveal(draw, coins, archive):
    out = []
    for (a, b), coin in zip(zip(draw[::2], draw[1::2]), coins):
        fb = archive.get("|".join(sorted((a, b))))
        win, conf = response_values(fb) if fb is not None else (None, 0.)
        out.append(fb["order"][win] if win is not None and conf >= .7 else (a,b)[coin])
    return out


def top(rank):
    return np.flatnonzero(rank == np.min(rank)).tolist()


def choose(base, sims, observed):
    percentile = (rankdata(observed) - 1) / (len(observed) - 1)
    nearest = np.argsort(-sims, axis=1, kind="stable")[:, :3]
    memory = np.round(percentile[nearest].mean(axis=1), 12)
    return top(base + rankdata(-memory))


def summarize(cells):
    per_task = {}
    summary = {}
    for group in ("all", "eligible"):
        per_task[group], summary[group] = {}, {}
        for family in ("DS", "GPT"):
            tasks = {t: {a:fmean(scores[a]) for a in ARMS}
                     for (s,f,t),scores in sorted(cells.items()) if (s,f)==(group,family)}
            per_task[group][family] = tasks
            summary[group][family] = {
                "loss": {a:fmean(s[a] for s in tasks.values()) for a in ARMS},
                "differences": {f"{a}_minus_{b}":intervals([s[a]-s[b] for s in tasks.values()])
                                for a,b in (("c0","strict"),("mixed","strict"),("c0","mixed"))}}
    return per_task, summary


def main(out):
    out.mkdir(exist_ok=False)
    files = json.loads((PREP/"code_files.json").read_text())
    runs = {t:{i:(m[1] if (m:=RUN.search(p)) else None) for i,p in paths.items()} for t,paths in files.items()}
    hashes = {t:{i:c["ast_sha256"] for i,c in cs.items()} for t,cs in load_codes().items()}
    scores = json.loads((PREP/"evaluation_labels.json").read_text())
    emb = TRAIN/"representation/run_1/embeddings.npz"
    assert hashlib.sha256(emb.read_bytes()).hexdigest() == json.loads((emb.parent/"receipt.json").read_text())["feature_sha256"]
    with np.load(emb,allow_pickle=False) as f:
        keys = f["code_keys"].tolist()
        v = f["code"].astype(float)
    index = {key:i for i,key in enumerate(keys)}
    v /= np.linalg.norm(v,axis=1,keepdims=True)
    sims = v @ v.T
    banks = json.loads((ROOT/"experiments/selection-frontier-02/banks/manifest.json").read_text())["banks"]
    archives = {"DS":json.loads((PREP/"feedback.json").read_text()),
                **{k:json.loads(gzip.decompress((ROOT/b["path"]).read_bytes())) for k,b in banks.items()}}
    cells = defaultdict(lambda:defaultdict(list))
    cover = {}
    plans = {}
    diag = defaultdict(lambda:defaultdict(list))
    rr = [json.loads(s) for s in gzip.open(EXP/"ranks.jsonl.gz","rt")]
    with (out/"decisions.jsonl.gz").open("wb") as raw, gzip.GzipFile(fileobj=raw,filename="",mode="wb",mtime=0) as log:
        for r in rr:
            t, ids, job, bank = r["task"],r["ids"],r["job"],r["bank"]
            family = "DS" if bank=="DS" else "GPT"
            pool = job.rsplit(":",1)[0]
            if pool not in cover:
                mixed, strict, target = libraries(ids,hashes[t],runs[t])
                n = min(10,len(strict)//2,len(mixed)//2)
                cover[pool] = {"task":t,"n_available":n,"mixed_available":min(10,len(mixed)//2),
                               "known":None not in target,"target_run_count":len(target-{None})}
                plans[pool] = (set(ids),target,[paired_draw(pool,seed,mixed,strict,n) for seed in range(5)] if n>=3 else [])
            id_set,target,draws = plans[pool]
            assert set(ids)==id_set
            eligible = bool(draws)
            base = rankdata(r["ranks"])
            qi = [index[t+"|"+i] for i in ids]
            for seed in range(5):
                tops = dict.fromkeys(ARMS,top(base))
                history = {"mixed":[],"strict":[]}
                if eligible:
                    orders,coins = draws[seed]
                    for arm,order in zip(ARMS[1:],orders):
                        h = reveal(order,coins,archives[bank][t])
                        assert len(set(h))==len(coins) and id_set.isdisjoint(h)
                        assert arm!="strict" or all(runs[t][x] not in target and runs[t][x] is not None for x in h)
                        history[arm] = h
                        sim = sims[np.ix_(qi,[index[t+"|"+x] for x in h])]
                        tops[arm] = choose(base,sim,[scores[t][i] for i in h])
                        diag[family,t][arm+"_mean_nearest_cosine"].append(float(sim.max(axis=1).mean()))
                        diag[family,t][arm+"_share_from_target_run"].append(fmean(runs[t][x] in target for x in h))
                # Selections are now fixed; only here access target outcomes.
                truth = [scores[t][i] for i in ids]
                hi,lo = max(truth),min(truth)
                for arm,ix in tops.items():
                    loss = fmean((hi-truth[i])/(hi-lo) for i in ix) if hi>lo else 0.
                    cells["all",family,t][arm].append(loss)
                    if eligible: cells["eligible",family,t][arm].append(loss)
                log.write((json.dumps([bank,job,seed,history["mixed"],history["strict"],
                                      *([ids[i] for i in tops[a]] for a in ARMS)],separators=(",",":"))+"\n").encode())
    per, summary = summarize(cells)
    save(out/"per-task.json",per)
    save(out/"coverage.json",cover)
    gate = all(summary["all"][f]["differences"]["c0_minus_strict"]["gain"]>=.01 and
               summary["all"][f]["differences"]["c0_minus_strict"]["ci95"][0]>0 for f in ("DS","GPT"))
    save(out/"summary.json",dict(advance=gate,metrics=summary,eligible_pools=sum(x["n_available"]>=3 for x in cover.values()),
         eligible_tasks=len(per["eligible"]["DS"]),total_pools=len(cover),total_tasks=len(per["all"]["DS"]),
         references_available=sorted(Counter(x["n_available"] for x in cover.values()).items()),
         missing_uuid_codes=sum(x is None for task in runs.values() for x in task.values()),
         known_uuid_runs=len({(t,r) for t,d in runs.items() for r in d.values() if r is not None}),
         eligible_task_macro_diagnostics={f:{m:fmean(fmean(d[m]) for (fam,_),d in diag.items() if fam==f)
            for m in next(iter(diag.values()))} for f in ("DS","GPT")}))
    print(out/"summary.json")


if __name__=="__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output",type=Path)
    main(parser.parse_args().output)
