"""Check certified parsed-feedback solutions via the frozen select() broker and cache."""
import argparse
import gzip
import json
from collections import defaultdict
from itertools import combinations
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from c0_replay import ROOT, reconstruct_inputs
from inputs import code_digest, past_query_index
from reproduction.clean_ranking_v1 import run as native
from reproduction.clean_ranking_v1.loader import load_world


class AuditedBank(dict):
    def __missing__(self, key):
        self.missed.add(key)
        raise KeyError(key)


class DrawWitness:
    """Pick one feasible boundary index at each revival; preserve aligned draw lengths."""
    def __init__(self, draws, boundary):
        self.draws, self.boundary = iter(draws), boundary
        self.aligned = True

    def choice(self, options):
        old, indices = next(self.draws, ((), ()))
        self.aligned &= len(old) == len(options)
        return options[(indices if self.aligned else range(len(options)))[self.boundary]]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('rows', type=Path)
    args = parser.parse_args()
    groups = defaultdict(list)
    for line in args.rows.read_text().splitlines():
        row = json.loads(line)
        if row['c0_top'] is not None and row['accepted_edges'] is not None:
            groups[row['run']].append(row)
    jobs = batches = max_reads = 0
    module = load_world()
    for name, rows in groups.items():
        def read(file):
            if name == 'stanford-autodl-v2':
                return (ROOT/'phase1-reproduction/records/stanford-autodl-v2/logs/exp'/file).read_bytes()
            return gzip.decompress((ROOT/'data/historical/source_records'/name/(file+'.gz')).read_bytes())
        lines = read('aide.log').decode().splitlines()
        nodes = {n['id']: n for n in json.loads(read('journal.json'))['nodes']}
        earliest = past_query_index(lines)
        for row in rows:
            ids, start = row['candidates'], row['first_log_line']-1
            codes = {i: nodes[i]['code'] for i in ids}
            dig = {i: code_digest(c) for i,c in codes.items()}
            earlier = {frozenset((i,j)) for i,j in combinations(ids,2)
                       if earliest.get(frozenset((dig[i],dig[j])),len(lines)) < start}
            feedback, draws, _ = reconstruct_inputs(lines,start,[nodes[i] for i in ids], earlier)
            bank = AuditedBank({'|'.join(sorted(pair)): dict(order=v.order, predicted_best_index=v.slot,
                        confidence=v.conf, source_group_index=k) for k,(pair,v) in enumerate(feedback.items())})
            bank.missed = set()
            job = dict(task=name, ids=ids, seed=0, budget=13)
            for boundary in (0,-1):
                witness = DrawWitness(draws,boundary)
                with patch.object(native,'random',SimpleNamespace(Random=lambda _: witness)):
                    top, ledger, counts = native.select(module, job, bank, codes, 'corrected_tournament', .7)
                edges = {(s['winner'],s['b'] if s['a']==s['winner'] else s['a']) for s in ledger if s['winner']}
                assert set(top) == set(row['c0_top']) and edges == set(map(tuple,row['accepted_edges'])), (name,start,boundary)
                assert counts['unique_feedback_reads'] <= 13
                assert not bank.missed, (name,start,bank.missed)
                max_reads = max(max_reads, len(ledger))
                jobs += 1
            batches += 1
    print(json.dumps(dict(certified_batches=batches, frozen_select_calls=jobs,
                          maximum_unique_reads=max_reads, top_sets_and_graphs_match=True)))


if __name__ == '__main__':
    main()
