"""Score the paired prompt experiment from author scores and visible judge responses."""
from collections import Counter, defaultdict
import argparse
import gzip
import hashlib
import itertools
import json
from pathlib import Path
import random
from statistics import fmean

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
ARMS = ("original", "skill")
ORDERS = ("AB", "BA")


def read(path):
    return json.loads(path.read_text())


def write(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n")


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check_ground_truth(blind_rows, ground_rows):
    """Independently join code filenames and scores to the released author's pair."""
    blind = {row["pair_id"]: row for row in blind_rows}
    gold = {row["pair_id"]: row for row in ground_rows}
    assert len(blind) == len(blind_rows) and len(gold) == len(ground_rows)
    assert set(blind) == set(gold) and blind
    files = {}
    for pair, target in blind.items():
        stated = gold[pair]
        for key in ("task", "a_id", "b_id"):
            assert stated[key] == target[key], (pair, key)
        path = ROOT / stated["source_path"]
        if path not in files:
            files[path] = read(path)
        author = files[path][stated["source_index"]]
        author_names = [Path(p).name for p in author["paths"]]
        positions = []
        for side in ("a", "b"):
            source = ROOT / target[side + "_path"]
            assert digest(source) == target[side + "_sha256"], source
            pos = author_names.index(source.name)
            assert author["scores"][pos] == stated["score_" + side]
            positions.append(pos)
        assert len(set(positions)) == 2
        assert author["is_lower_better"] == stated["is_lower_better"]
        score_a, score_b = stated["score_a"], stated["score_b"]
        assert score_a != score_b
        a_wins = score_a < score_b if stated["is_lower_better"] else score_a > score_b
        winning_side = 0 if a_wins else 1
        assert stated["winner"] == "AB"[winning_side]
        assert positions[winning_side] == author["best_index"]
    return blind, gold


def visible_choice(answer):
    """Read the final JSON winner in the returned visible answer."""
    end = answer.rfind("}")
    start = answer.rfind("{", 0, end)
    if start == -1 or end == -1:
        return None
    try:
        parsed = json.loads(answer[start:end + 1])
        candidate = parsed.get("predicted_best_index")
        if candidate is None and parsed.get("predicted_ranking"):
            candidate = parsed["predicted_ranking"][0]
    except (ValueError, AttributeError):
        return None
    if type(candidate) in (int, str) and str(candidate) in ("0", "1"):
        return int(candidate)
    return None


def check_judgments(path, blind):
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt") as infile:
        outcomes = [json.loads(line) for line in infile if line.strip()]
    checked = {}
    models = Counter()
    unscored = Counter()
    for row in outcomes:
        pair, arm, order = row["pair_id"], row["arm"], row["order"]
        assert arm in ARMS and order in ORDERS, (arm, order)
        key = (pair, arm, order)
        assert key not in checked, key
        checked[key] = row
        manifest = blind[pair]
        ids = [manifest[side.lower() + "_id"] for side in order]
        assert row["presented_ids"] == ids, key
        if row.get("response_model"):
            models[row["response_model"]] += 1
        if row["valid"]:
            idx = row["predicted_index"]
            assert type(idx) is int and idx in (0, 1)
            assert visible_choice(row["final_answer"]) == idx, key
            assert ids[idx] == row["predicted_id"], key
        else:
            assert row["predicted_id"] is None
            unscored[str(row.get("error") or row.get("finish_reason") or "invalid")] += 1
    assert len(models) <= 1, "Mixed response models"
    return checked, models, unscored


def pair_results(blind, gold, judgments):
    results = {}
    for pair, manifest in blind.items():
        truth = gold[pair]
        correct_id = manifest[truth["winner"].lower() + "_id"]
        arms = {}
        for arm in ARMS:
            votes = [judgments.get((pair, arm, order), {}) for order in ORDERS]
            selected = [v.get("predicted_id") if v.get("valid") else None for v in votes]
            correct = [s == correct_id for s in selected]
            valid = sum(s is not None for s in selected)
            arms[arm] = dict(selected=selected, correct=correct, valid=valid,
                             consistent=(selected[0] == selected[1]) if valid == 2 else None)
        results[pair] = dict(task=manifest["task"], winner_id=correct_id, arms=arms)
    return results


def accuracy(results):
    """Task-equal accuracy, preserving the two correlated orientations within each pair."""
    by_task = defaultdict(lambda: defaultdict(list))
    for item in results.values():
        for arm in ARMS:
            by_task[item["task"]][arm].append(fmean(item["arms"][arm]["correct"]))
    return {t:{arm:fmean(by_task[t][arm]) for arm in ARMS} for t in sorted(by_task)}


def uncertainty(task_scores):
    differences = [v["skill"] - v["original"] for v in task_scores.values()]
    effect = fmean(differences)
    # This tests symmetry/exchangeability of the task-level paired differences
    # under the null. Zero-difference tasks need no sign enumeration.
    nonzero = [v for v in differences if v]
    observed = abs(sum(nonzero))
    count = sum(abs(sum(v*s for v,s in zip(nonzero, signs))) >= observed - 1e-12
                for signs in itertools.product((-1,1), repeat=len(nonzero)))
    rng = random.Random(20261110)
    bootstrap = sorted(fmean(rng.choices(differences,k=len(differences))) for _ in range(10000))
    return dict(skill_minus_original=effect, task_bootstrap_95=[bootstrap[249],bootstrap[9749]],
                exact_two_sided_task_sign_flip_p=count/2**len(nonzero),
                bootstrap_repetitions=10000, nonzero_task_differences=len(nonzero))


def summarize(rows):
    if not rows:
        return None
    task_scores = accuracy(rows)
    arm_totals = {}
    for arm in ARMS:
        votes = [p["arms"][arm] for p in rows.values()]
        arm_totals[arm] = dict(task_macro_accuracy=fmean(t[arm] for t in task_scores.values()),
            correct_by_order={order:sum(row["correct"][j] for row in votes) for j,order in enumerate(ORDERS)},
            valid_by_order={order:sum(row["selected"][j] is not None for row in votes)
                            for j,order in enumerate(ORDERS)}, valid=sum(v["valid"] for v in votes),
            num_correct=sum(sum(v["correct"]) for v in votes),
            both_correct=sum(all(v["correct"]) for v in votes),
            both_valid=sum(v["valid"] == 2 for v in votes),
            consistent=sum(v["consistent"] is True for v in votes))
    dist = Counter()
    for row in rows.values():
        arm = row["arms"]
        delta = sum(arm["skill"]["correct"]) - sum(arm["original"]["correct"])
        dist["improved" if delta > 0 else "worsened" if delta < 0 else "unchanged"] += 1
    return dict(pairs=len(rows), tasks=len(task_scores), arms=arm_totals,
                pair_change={k:dist[k] for k in ("improved","worsened","unchanged")},
                per_task=task_scores, paired_difference=uncertainty(task_scores))


def main(directory, judgments_file, partial):
    blind_path, gold_path = (directory / name for name in ("blind_manifest.json", "ground_truth.json"))
    blind, gold = check_ground_truth(read(blind_path)["pairs"], read(gold_path)["pairs"])
    votes, models, errors = check_judgments(judgments_file, blind)
    scheduled = 4*len(blind)
    if not partial and len(votes) != scheduled:
        raise ValueError("Incomplete journal: use --partial only after a confirmed interruption.")
    dispatched_file = directory/"results/dispatch.jsonl"
    dispatched = [json.loads(line) for line in dispatched_file.read_text().splitlines()]
    sent = {(d["pair_id"],d["arm"],d["order"]) for d in dispatched}
    assert set(votes) <= sent
    received = sum(row["completion_received"] for row in votes.values())
    rows = pair_results(blind, gold, votes)
    complete = {p:r for p,r in rows.items() if all(r["arms"][a]["valid"] == 2 for a in ARMS)}
    summary = dict(scheduled_pairs=len(blind), scheduled_judgments=scheduled, recorded=len(votes),
                   dispatched_cells=len(sent), completions_received=received, unsent_cells=scheduled-len(sent),
                   dispatched_without_final_record=len(sent)-len(votes),
                   final_records_without_completion=len(votes)-received,
                   response_models=dict(models), invalid_reasons=dict(errors), complete_pairs=len(complete),
                   file_sha256={p.name:digest(p) for p in (blind_path,gold_path,judgments_file)},
                   all_scheduled=summarize(rows) if received == scheduled else None,
                   four_valid_judgments=summarize(complete))
    write(directory / "summary.json", summary)
    write(directory / "per_pair.json", rows)
    print(json.dumps({k:v for k,v in summary.items() if k not in ("four_valid_judgments","file_sha256")},
                     indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--experiment",type=Path,default=HERE)
    parser.add_argument("--judgments",type=Path)
    parser.add_argument("--partial",action="store_true", help="Report coverage after a confirmed provider interruption.")
    args = parser.parse_args()
    main(args.experiment,args.judgments or args.experiment/"results/judgments.jsonl",args.partial)
