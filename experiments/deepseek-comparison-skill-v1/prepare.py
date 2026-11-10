"""Draw a deterministic task-balanced pilot from the author's original scored pairs."""
import argparse
import ast
from collections import Counter
from functools import lru_cache
import hashlib
import json
import math
from pathlib import Path
import warnings

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
CORPUS = ROOT / "data/reward-model/corpus-6b322cb-raw-v1"
REVISION = "6b322cb88bdbcb2b2d3897ec7d0ded94a5bb2d06"
SEED = "foreagent-comparison-skill-v1-20261110"
TASKS, PAIRS_PER_TASK, MAX_CODE_BYTES = 12, 2, 48_000


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def priority(*fields):
    return digest("\0".join([SEED, *fields]).encode())


@lru_cache(maxsize=None)
def code_metadata(path):
    raw = path.read_bytes()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", SyntaxWarning)
        tree = ast.dump(ast.parse(raw), include_attributes=False)
    return digest(raw), digest(tree.encode()), len(raw)


def choose_task_pairs(label_file):
    task_dir = label_file.parents[1]
    task = task_dir.name
    rows = json.loads(label_file.read_bytes())
    allowed = []
    filters = Counter()
    for index, row in enumerate(rows):
        scores = list(map(float, row["scores"]))
        if not all(map(math.isfinite, scores)):
            filters["nonfinite"] += 1
            continue
        if scores[0] == scores[1]:
            filters["tie"] += 1
            continue
        author_best = (min if row["is_lower_better"] else max)(range(2), key=scores.__getitem__)
        assert author_best == row["best_index"], (task, index)
        paths = [task_dir/"code"/Path(p).name for p in row["paths"]]
        metadata = list(map(code_metadata, paths))
        if metadata[0][1] == metadata[1][1]:
            filters["same_ast"] += 1
            continue
        if sum(item[2] for item in metadata) > MAX_CODE_BYTES:
            filters["over_code_byte_cap"] += 1
            continue
        unordered_names = sorted(p.name for p in paths)
        allowed.append((priority("pair", task, *unordered_names), index, paths, metadata))
    selected = []
    taken = set()
    for _, index, paths, meta in sorted(allowed):
        structural = {item[1] for item in meta}
        if structural & taken:
            continue
        taken |= structural
        selected.append((index, rows[index], paths, meta))
        if len(selected) == PAIRS_PER_TASK:
            break
    counts = dict(source_rows=len(rows), eligible_rows=len(allowed), **filters)
    assert sum(filters.values()) + len(allowed) == len(rows)
    return selected, counts


def write(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False)+"\n")


def main(out):
    source = json.loads((CORPUS/"MANIFEST.json").read_bytes())
    assert source["dataset_revision"] == REVISION
    by_task, counts, originals = {}, {}, {}
    for path in sorted((CORPUS/"solutions_subset_50").glob("*/ground_truth/*_n2.json")):
        task = path.parents[1].name
        assert digest(path.read_bytes()) == source["files"][str(path.relative_to(CORPUS))]["sha256"]
        selected, counts[task] = choose_task_pairs(path)
        if len(selected) == PAIRS_PER_TASK:
            by_task[task] = selected
        originals[task] = str(path.relative_to(ROOT))
    assert len(counts) == 26 and len(by_task) >= TASKS
    tasks = sorted(by_task, key=lambda task: priority("task", task))[:TASKS]
    blind, truth = [], []
    for task in tasks:
        for index, row, paths, meta in by_task[task]:
            a,b = sorted(range(2), key=lambda i: meta[i][0])
            a_sha,b_sha = meta[a][0],meta[b][0]
            for path, (actual,*_) in zip(paths, meta):
                assert actual == source["files"][str(path.relative_to(CORPUS))]["sha256"]
            key = {"pair_id": priority("id",task,a_sha,b_sha)[:16], "task":task,
                   "a_id":a_sha[:20], "b_id":b_sha[:20]}
            blind.append(dict(**key, a_path=str(paths[a].relative_to(ROOT)), b_path=str(paths[b].relative_to(ROOT)),
                              a_sha256=a_sha, b_sha256=b_sha))
            truth.append(dict(**key, score_a=row["scores"][a], score_b=row["scores"][b],
                              is_lower_better=row["is_lower_better"], winner="A" if row["best_index"]==a else "B",
                              source_path=originals[task], source_index=index))
    assert len({r["pair_id"] for r in blind}) == TASKS*PAIRS_PER_TASK
    out.mkdir(parents=True,exist_ok=True)
    write(out/"blind_manifest.json",dict(revision=REVISION,seed=SEED,max_combined_code_bytes=MAX_CODE_BYTES,pairs=blind))
    write(out/"ground_truth.json",dict(revision=REVISION,eligible_tasks=len(by_task),
                                        filter_counts_by_task=counts,pairs=truth))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out",type=Path,default=HERE)
    main(parser.parse_args().out)
