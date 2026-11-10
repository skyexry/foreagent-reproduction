"""Audit retrieval from validation records already available at batch creation."""
import argparse
import gzip
import hashlib
import itertools
import json
import math
import re
from collections import defaultdict
from pathlib import Path
from statistics import fmean

import numpy as np
from scipy.stats import rankdata
from sklearn.feature_extraction.text import TfidfVectorizer

ROOT = Path(__file__).resolve().parents[2]
GEN = re.compile(r'^\[[^]]+\] INFO: Generated improvement candidate (\d+)/(\d+): ([0-9a-f]{8})')
PARSE = re.compile(r'^\[[^]]+\] INFO: Agent is parsing execution results for node ([0-9a-f]+)')
END = re.compile(r'^\[[^]]+\] INFO: World Model prediction completed in ')
MAXIMIZE = {'aerial-cactus-identification', 'histopathologic-cancer-detection'}


def read_verified(path, expected):
    data = path.read_bytes()
    if path.suffix == '.gz':
        data = gzip.decompress(data)
    assert hashlib.sha256(data).hexdigest() == expected, path
    return data


def batches(log, prefixes):
    parsed, groups, current = {}, [], []
    for line_no, line in enumerate(log.splitlines(), 1):
        if match := PARSE.match(line):
            parsed.setdefault(match[1], line_no)
        if match := GEN.match(line):
            ordinal, size, short = match.groups()
            if ordinal == '1':
                current = []
                start = line_no
            current.append((int(ordinal), int(size), short))
        if current and END.match(line):
            if ([(i, n) for i, n, _ in current] == [(i, 10) for i in range(1, 11)]
                    and all(s in prefixes for _, _, s in current)):
                groups.append((start, [prefixes[s] for _, _, s in current]))
            current = []
    return parsed, groups


def utility(node, maximize):
    metric = node.get('metric') or {}
    val = metric.get('value')
    if (node.get('is_buggy') is False and node.get('is_skipped') is False
            and node.get('exec_time') is not None and metric.get('maximize') is maximize
            and type(val) in (float, int) and math.isfinite(val)):
        return val if maximize else -val
    return None


def predict(history_codes, history_scores, current_codes, seed):
    docs = history_codes + current_codes
    matrix = TfidfVectorizer(token_pattern=r'[A-Za-z_][A-Za-z0-9_]*|\d+\.?\d*',
                              ngram_range=(1, 2), sublinear_tf=True).fit_transform(docs)
    n = len(history_codes)
    sims = (matrix[n:] @ matrix[:n].T).toarray()
    # Break equal-similarity ties by history order (most recent first).
    ix = np.argsort(-sims, axis=1, kind='stable')[:, :3]
    weights = np.take_along_axis(sims, ix, axis=1) + 1e-9
    weights /= weights.sum(axis=1, keepdims=True)
    ranks = (rankdata(history_scores) - 1) / (n - 1)
    rng = np.random.default_rng(seed)
    permutations = [ranks] + [rng.permutation(ranks) for _ in range(100)]
    return np.round(np.sum(np.array(permutations)[:, ix] * weights, axis=2), 12)


def audit(name, task, journal, log, expected):
    nodes = journal['nodes']
    prefixes = {n['id'][:8]: n for n in nodes}
    assert len(prefixes) == len(nodes)
    parsed, groups = batches(log, prefixes)
    assert len(groups) == expected, (name, len(groups), expected)
    rows = []
    for start, current in groups:
        assert len({journal['node2parent'][n['id']] for n in current}) == 1
        first_step = min(n['step'] for n in current)
        prior = [n for n in nodes if n['step'] < first_step
                 and parsed.get(n['id'], math.inf) < start
                 and utility(n, task in MAXIMIZE) is not None]
        prior.sort(key=lambda n: parsed[n['id']], reverse=True)
        history = prior[:10]
        row = dict(run=name, task=task, first_log_line=start, available=len(prior),
                   history=[n['id'] for n in history], candidates=[n['id'] for n in current])
        assert not set(row['history']).intersection(row['candidates'])
        rows.append(row)
        if len(history) < 3:
            continue
        preds = predict([n['code'] for n in history], [utility(n, task in MAXIMIZE) for n in history],
                        [n['code'] for n in current], start)
        row['prediction'] = preds[0].tolist()
        observed = [utility(n, task in MAXIMIZE) for n in current]
        pairs = [(i, j) if observed[i] > observed[j] else (j, i)
                 for i, j in itertools.combinations(range(len(current)), 2)
                 if observed[i] is not None and observed[j] is not None and observed[i] != observed[j]]
        row['strict_pairs'] = len(pairs)
        if pairs:
            good, bad = np.array(pairs).T
            order = (1 + np.sign(preds[:, good] - preds[:, bad])) / 2
            display = np.array([n['wm_predicted_rank'] for n in current])
            row.update(memory=float(order[0].mean()), shuffled=float(order[1:].mean()),
                       logged=float(((1 + np.sign(display[bad] - display[good])) / 2).mean()))
    return rows


def main():
    arg = argparse.ArgumentParser()
    arg.add_argument('out', type=Path, help='new output directory')
    out = arg.parse_args().out
    if out.exists():
        raise FileExistsError(out)
    hist = ROOT / 'experiments/historical-v1'
    inputs = {(r['run'], r['file']): r for r in json.loads((hist/'source_manifest.json').read_text())}
    runs = json.loads((hist/'summary.json').read_text())['per_run']
    rows = []
    for run in runs:
        name = run['run']
        def read(file):
            spec = inputs[name, file]
            return read_verified(ROOT/'data/historical'/spec['compressed_file'], spec['sha256'])
        rows += audit(name, name.split('_')[0], json.loads(read('journal.json')),
                      read('aide.log').decode(), run['verified_batches'])
    folder = ROOT/'phase1-reproduction/records/stanford-autodl-v2/logs/exp'
    source = json.loads((ROOT/'phase1-reproduction/SOURCES.json').read_text())
    hashes = {r['path']: r['sha256'] for r in source['files'] if 'sha256' in r}
    def local(file):
        path = folder/file
        return read_verified(path, hashes[str(path.relative_to(ROOT/'phase1-reproduction'))])
    rows += audit('stanford-autodl-v2', 'stanford-covid-vaccine',
                  json.loads(local('journal.json')), local('aide.log').decode(), 7)
    by_task = defaultdict(list)
    for r in rows:
        by_task[r['task']].append(r)
    table = {}
    for task, records in by_task.items():
        eligible = [r for r in records if r.get('strict_pairs', 0)]
        stats = dict(batches=len(records), at_least_three=sum(r['available']>=3 for r in records),
                     at_least_ten=sum(r['available']>=10 for r in records),
                     evaluable_batches=len(eligible), strict_pairs=sum(r['strict_pairs'] for r in eligible),
                     evaluable_runs=len({r['run'] for r in eligible}))
        for key in ('memory', 'shuffled', 'logged'):
            by_run = defaultdict(list)
            for r in eligible:
                by_run[r['run']].append(r[key])
            stats[key] = fmean(fmean(x) for x in by_run.values()) if by_run else None
        table[task] = stats
    macro = {key: fmean(t[key] for t in table.values() if t[key] is not None)
             for key in ('memory','shuffled','logged') if any(t[key] is not None for t in table.values())}
    result = dict(batches=len(rows), runs=len({r['run'] for r in rows}), tasks=table,
                  totals={key:sum(t[key] for t in table.values()) for key in
                          ('at_least_three','at_least_ten','evaluable_batches','evaluable_runs','strict_pairs')},
                  observed_task_macro=macro)
    assert len(rows) == 136 and len(by_task) == 5
    out.mkdir(parents=True)
    (out/'batches.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in rows))
    (out/'summary.json').write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps(result['totals']), macro)


if __name__ == '__main__':
    main()
