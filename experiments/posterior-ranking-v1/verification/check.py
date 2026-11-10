"""Independent exact rank reconstruction and archive-field inventory. Run from project root."""
import gzip
import hashlib
import json
from collections import Counter, defaultdict
from functools import lru_cache
from pathlib import Path
from statistics import mean, median

import numpy as np

PREPARED = Path('experiments/clean-ranking-v1/prepared')
TRACES = Path('experiments/trajectory-weighted-judge-v1/evaluation/run_1/decisions.sealed.jsonl.gz')
OUT = Path(__file__).resolve().parent


def write_once(path, value):
    payload = (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + '\n').encode()
    if path.exists():
        assert path.read_bytes() == payload, path
    else:
        path.write_bytes(payload)


@lru_cache(None)
def subsets(n):
    masks = np.arange(1 << n)
    bits = 1 << np.arange(n)
    members = ((masks[:, None] & bits) != 0).astype('int64')
    sizes = members.sum(axis=1)
    layers = [np.flatnonzero(sizes == k) for k in range(n + 1)]
    return masks, bits, members, sizes, layers


def ranks(ids, trace):
    n = len(ids)
    masks, bits, members, sizes, layers = subsets(n)
    wins = np.zeros((n, n), dtype='int64')
    assert 1 <= n <= 10 and len(trace) <= 13
    seen = set()
    for row in trace:
        edge = frozenset((row['a'], row['b']))
        assert len(edge) == 2 and edge not in seen
        seen.add(edge)
        if row['winner'] is not None:
            winner = row['winner']
            assert winner in edge and .7 <= row['confidence'] <= 1
            loser, = edge - {winner}
            wins[ids.index(winner), ids.index(loser)] = 1

    # Z(S) sums weights of the orders within S. Condition on the final element.
    incoming = members @ wins
    z = np.ones(len(masks), dtype='int64')
    for layer in layers[1:]:
        rest = layer[:, None] ^ bits
        by_last = members[layer] * (z[rest] << incoming[layer])
        z[layer] = by_last.sum(axis=1)

    # For a candidate i, split each order as prefix P, then i, then suffix T.
    # The cross weight counts wins P -> (i,T) and i -> T.
    outside_wins = (incoming * (1 - members)).sum(axis=1)
    rank_sum, first_mass = [], []
    for i, bit in enumerate(bits):
        prefix = masks[(masks & bit) == 0]
        suffix = (len(masks) - 1) ^ (prefix | bit)
        i_beats_suffix = members[suffix] @ wins[i]
        weight = (z[prefix] * z[suffix]) << (outside_wins[prefix] + i_beats_suffix)
        assert weight.sum() == z[-1]
        rank_sum.append(int(np.dot(sizes[prefix] + 1, weight)))
        first_mass.append(int(weight[0]))
    assert sum(first_mass) == z[-1]
    return ([code for code, v in zip(ids, rank_sum) if v == min(rank_sum)],
            [code for code, v in zip(ids, first_mass) if v == max(first_mass)])


def check_reasoning():
    bank = json.loads((PREPARED / 'feedback.json').read_bytes())
    gt_root = Path('data/reward-model/corpus-6b322cb-raw-v1/solutions_subset_50')
    source = json.loads((PREPARED / 'source_manifest.json').read_bytes())['sha256']
    counts, length = Counter(), []
    for task, entries in sorted(bank.items()):
        file = Path('data/author_reference') / (task + '.json')
        assert hashlib.sha256(file.read_bytes()).hexdigest() == source[str(file)]
        rows = json.loads(file.read_bytes())['results']
        groups = json.loads((gt_root / task / 'ground_truth' / f'groups_{task}_n2.json').read_bytes())
        counts['all_rows'] += len(rows)
        counts['all_retained_text'] += sum(bool((row['prediction'].get('reasoning') or '').strip()) for row in rows)
        for rec in entries.values():
            index = rec['source_group_index']
            row = rows[index]
            assert [Path(p).stem[-4:] + '.py' for p in groups[index]['paths']] == [x['path'] for x in row['solutions']]
            assert rec['predicted_best_index'] == row['prediction']['best_index']
            assert rec['confidence'] == row['prediction']['confidence']
            counts['admitted'] += 1
            s = (row['prediction'].get('reasoning') or '').strip()
            if s:
                counts['admitted_retained_text'] += 1
                length.append(len(s))
    return dict(counts=counts, median_chars_present=median(length), tasks=len(bank),
                field='prediction.reasoning, nonempty stripped text; presence is not accuracy')


def main():
    jobs = {row['job_id']: row for row in map(json.loads,(PREPARED / 'jobs.jsonl').read_text().splitlines())}
    out = []
    with gzip.open(TRACES, 'rt') as stream:
        for row in map(json.loads, stream):
            if row['arm'] != 'C0':
                continue
            job = jobs[row['job_id']]
            primary, secondary = ranks(job['ids'], row['trace'])
            out.append([row['bank'], row['job_id'], sorted(primary), sorted(secondary), sorted(row['selected'])])
    assert len(out) == len({(b,j) for b,j,*_ in out}) == 3400
    data = ''.join(json.dumps(row,separators=(',',':'))+'\n' for row in out).encode()
    sealed = OUT / 'selections.jsonl.gz'
    if sealed.exists():
        assert gzip.decompress(sealed.read_bytes()) == data
    else:
        sealed.write_bytes(gzip.compress(data,mtime=0))
    with gzip.open(OUT.parent / 'decisions.sealed.jsonl.gz', 'rt') as stream:
        observed = {(row['bank'],row['job_id']): row['selected'] for row in map(json.loads,stream)}
    for bank, jid, primary, secondary, control in out:
        official = observed[(bank,jid)]
        assert [primary, secondary, control] == [sorted(official[a]) for a in ('E','B','C')]
    write_once(OUT / 'selection_match.json',dict(episodes=len(out), methods_per_episode=3))
    labels = json.loads((PREPARED / 'evaluation_labels.json').read_bytes())
    scores = defaultdict(lambda: defaultdict(list))
    for bank, jid, primary, secondary, control in out:
        job = jobs[jid]
        values = labels[job['task']]
        pool = [values[x] for x in job['ids']]
        low, high = min(pool), max(pool)
        deltas = []
        for chosen in (control,primary,secondary):
            deltas.append((high - mean(values[x] for x in chosen)) / (high - low) if high > low else 0)
        scores[bank][job['task']].append(deltas)
    per_bank = {b: np.mean([np.mean(v,axis=0) for v in task.values()],axis=0).tolist() for b,task in scores.items()}
    write_once(OUT / 'receipt.json',dict(rows=len(out), order_of_metrics=['C0','mean_rank','p_best'],
               task_macro_regret=per_bank, archive=check_reasoning(),
               sha256_uncompressed_selections=hashlib.sha256(data).hexdigest()))


if __name__ == '__main__':
    main()
