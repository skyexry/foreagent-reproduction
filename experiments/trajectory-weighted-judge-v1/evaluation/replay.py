"""Run frozen C0 for every sealed judge and mask. This process does not open score labels."""
import argparse
from collections import Counter
import gzip
import hashlib
from itertools import combinations
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
EXP = HERE.parent
ROOT = EXP.parents[1]
PREP = ROOT / 'experiments/clean-ranking-v1/prepared'
FRONTIER = ROOT / 'experiments/selection-frontier-02'
REFERENCE = FRONTIER / 'c0-final-selection/run-002/decisions.sealed.jsonl.gz'
TRAIN = EXP / 'train'
PRED = TRAIN / 'oof_predictions.jsonl.gz'
PRED_SEAL = TRAIN / 'prediction_seal.json'
ARMS = ('uniform', 'gap', 'terminal', 'shuffled')
PROTOCOL_SHA = '685f804875aa35a2c6b0e13ec6ac73747f793d338d3e8a7e2604a3757bc46c46'
REFERENCE_SHA = '848f6b26d39e0b9aafcc295ec6ceb512cad3f27b6353de0f4d11020b7bff5d59'
sys.path.insert(0, str(ROOT))
from reproduction.clean_ranking_v1.correctness import response_values
from reproduction.clean_ranking_v1.loader import load_world
from reproduction.clean_ranking_v1.run import select


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(ok, message):
    if not ok:
        raise ValueError(message)


def checked(path, expected):
    require(sha(path) == expected, f'Hash mismatch: {path}')
    return path


def read(path):
    return json.loads(path.read_bytes())


def write(path, obj):
    path.write_text(json.dumps(obj, sort_keys=True, indent=2, allow_nan=False) + '\n')


def records(path):
    with gzip.open(path, 'rt') as stream:
        for line in stream:
            yield json.loads(line)


def frozen():
    protocol = read(checked(EXP / 'protocol.json', PROTOCOL_SHA))
    for path in (PREP/'feedback.json', PREP/'jobs.jsonl', PREP/'code_files.json'):
        checked(path, protocol['inputs'][str(path.relative_to(ROOT))])
    manifest = ROOT/'experiments/clean-ranking-v1/implementation-lock.json'
    lock = read(checked(manifest, '26d10844abfce2d331a850595cdc19df831c361e429eca09edde340f91852c9f'))
    for name, expected in lock['sha256'].items():
        if name.startswith('reproduction/clean_ranking_v1/'):
            checked(ROOT/name, expected)
    return protocol


def banks():
    yield 'DS', read(PREP/'feedback.json')
    manifest = checked(FRONTIER/'banks/manifest.json', '75a90a6de33bf97a8e8fd24fa1340a93f9d034a29dd0f9e9b394d58ef54e48be')
    for name, info in read(manifest)['banks'].items():
        with gzip.open(checked(ROOT/info['path'], info['sha256'])) as stream:
            yield name, json.load(stream)


def predictions(paths):
    pred_sha = read(PRED_SEAL)['predictions_sha256']
    pred = {task: {} for task in paths}
    for row in records(checked(PRED, pred_sha)):
        task, pair, winners = row['task'], row['pair'], row['winners']
        ids = pair.split('|')
        require(len(ids) == 2 and ids[0] < ids[1] and set(ids) <= paths[task].keys(), f'Invalid pair {pair}')
        require(pair not in pred[task] and set(winners) == set(ARMS), f'Duplicate or missing arms {pair}')
        require(all(i in ids for i in winners.values()), f'Winner outside pair {pair}')
        ties = row['ties']
        require(set(ties) == set(ARMS) and all(type(v) is bool for v in ties.values()), f'Invalid tie flags {pair}')
        require(all(not ties[arm] or winners[arm] == ids[0] for arm in ARMS), f'Tie convention {pair}')
        pred[task][pair] = winners
    for task, files in paths.items():
        expected = {'|'.join(pair) for pair in combinations(sorted(files), 2)}
        require(pred[task].keys() == expected, f'Incomplete forecast grid {task}')
    return pred, pred_sha


def replace_directions(bank, task_pred, arm):
    adjusted = {}
    for pair, item in bank.items():
        require(sorted(item['order']) == pair.split('|'), f'Bank order mismatch {pair}')
        index, confidence = response_values(item)
        adjusted[pair] = item
        if index is not None and confidence >= .7:
            # The source order can be opposite both canonical and query order.
            winner = task_pred[pair][arm]
            adjusted[pair] = dict(item, predicted_best_index=item['order'].index(winner))
    return adjusted


def check_trace(job, trace, stats, selected, original, preds, arm):
    ids = set(job['ids'])
    require(0 < len(set(selected)) == len(selected) and set(selected) <= ids, 'Invalid selection')
    keys = set()
    for edge in trace:
        a, b = edge['a'], edge['b']
        key = '|'.join(sorted((a, b)))
        require(a != b and {a,b} <= ids and key not in keys, 'Invalid or repeated read')
        keys.add(key)
        source = original[key]
        index, confidence = response_values(source)
        winner = None
        if index is not None and confidence >= .7:
            winner = source['order'][index] if arm == 'C0' else preds[key][arm]
        require((edge['winner'], edge['confidence'], edge['source_group_index']) ==
                (winner, confidence, source['source_group_index']), 'Trace gate/order/source mismatch')
    require(len(keys) == stats['unique_feedback_reads'] <= job['budget'] <= 13, 'Read cap exceeded')


def main(out):
    frozen()
    paths = read(PREP/'code_files.json')
    pred, pred_sha = predictions(paths)
    jobs = [json.loads(line) for line in (PREP/'jobs.jsonl').read_text().splitlines()]
    code = {}
    for task, files in paths.items():
        code[task] = {}
        for cid, relative in files.items():
            raw = (ROOT/relative).read_bytes()
            require(hashlib.sha256(raw).hexdigest()[:20] == cid, f'Code digest {task}/{cid}')
            code[task][cid] = raw.decode()
    require(len(jobs) == len({j['job_id'] for j in jobs}) == 850 and len(paths) == 26, 'Frozen job universe')
    ref = {(r['bank'], r['job_id']): r for r in records(checked(REFERENCE, REFERENCE_SHA))}
    model = load_world()
    out.mkdir(parents=True, exist_ok=False)
    decisions = out/'decisions.sealed.jsonl.gz'
    checks = Counter()
    with gzip.GzipFile(filename=str(decisions), mode='wb', compresslevel=5, mtime=0) as stream:
        for name, original in banks():
            for job in jobs:
                keys = {'|'.join(pair) for pair in combinations(sorted(job['ids']), 2)}
                require(keys <= original[job['task']].keys(), f"Uncovered archived pool {job['job_id']}")
            for arm in ('C0', *ARMS):
                bank = original if arm == 'C0' else {
                    task: replace_directions(items, pred[task], arm) for task, items in original.items()}
                for job in jobs:
                    task = job['task']
                    codes = {cid: code[task][cid] for cid in job['ids']}
                    selected, trace, stats = select(model, job, bank[task], codes, 'corrected_tournament', .7)
                    check_trace(job, trace, stats, selected, original[task], pred[task], arm)
                    if arm == 'C0':
                        old = ref[name, job['job_id']]
                        require((selected, trace, stats) == (old['selected']['C'], old['trace'], old['stats']),
                                f"C0 differs from reference {name}/{job['job_id']}")
                        checks[name] += 1
                    record = dict(bank=name, arm=arm, job_id=job['job_id'], task=task, selected=selected,
                                  trace=trace, stats=stats)
                    stream.write((json.dumps(record, sort_keys=True, separators=(',', ':'))+'\n').encode())
                print(f'{name} {arm}: 850 complete', flush=True)
    require(len(checks) == 4 and all(v == 850 for v in checks.values()), 'Incomplete C0 audit')
    write(out/'selection_seal.json', dict(
        decisions_sha256=sha(decisions), predictions_sha256=pred_sha, prediction_seal_sha256=sha(PRED_SEAL),
        protocol_sha256=PROTOCOL_SHA, replay_script_sha256=sha(Path(__file__)), baseline_reference_sha256=REFERENCE_SHA,
        reference_selections_traces_and_ledgers_exact=dict(checks), selection_count=17000,
        heldout_score_files_opened_by_replay=0, missing_or_illegal_predictions=0,
        code_candidates=sum(map(len, paths.values())), predicted_pairs=sum(map(len,pred.values()))))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    main(parser.parse_args().output)
