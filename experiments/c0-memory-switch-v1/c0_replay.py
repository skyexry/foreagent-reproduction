"""Certify archived parsed-feedback C0 top groups and accepted comparison graphs."""
import argparse
from collections import defaultdict, Counter
from dataclasses import dataclass
import gzip
import hashlib
import inspect
import json
from pathlib import Path
import re
import sys
from types import SimpleNamespace

from inputs import code_digest, past_query_index, transport_events

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from reproduction.clean_ranking_v1.loader import load_world

GEN10 = re.compile(r'^\[[^]]+\] INFO: Generated improvement candidate 10/10:')
DONE = re.compile(r'^\[[^]]+\] INFO: World Model prediction completed in ')
NORMAL = re.compile(r'^\[[^]]+\] INFO: Round (\d+): Node ([0-9a-f]{8}) (beats|vs) ([0-9a-f]{8})')
REVIVAL = re.compile(r'^\[[^]]+\] INFO: Round (\d+) \(Re-match\): Node ([0-9a-f]{8}) (.*)')
BUDGET = 13


class Missing(Exception):
    pass


class Branch(Exception):
    pass


@dataclass
class Read:
    slot: int | None
    conf: float
    order: tuple

    def winner(self):
        return self.order[self.slot] if self.slot is not None else None


def verified(path, sha):
    data = path.read_bytes()
    if path.suffix == '.gz':
        data = gzip.decompress(data)
    assert hashlib.sha256(data).hexdigest() == sha, path
    return data


def reconstruct_inputs(lines, start, candidates, earlier_queries):
    """Pair stage-local fresh prompts with journal results by original control order."""
    if len({n['code'] for n in candidates}) < len(candidates):
        raise Missing('duplicate_code_rejected_by_frozen_selector')
    ids = [n['id'] for n in candidates]
    prefix = {i[:8]:i for i in ids}
    opening = next(i for i in range(start, len(lines)) if GEN10.match(lines[i])) + 1
    end = next(i for i in range(opening,len(lines)) if DONE.match(lines[i]))
    transport = transport_events(lines, opening, end, candidates)
    records = candidates[0]['wm_comparison_results']
    assert all(n['wm_comparison_results'] == records for n in candidates)
    events = []
    for i in range(opening, end):
        m = NORMAL.match(lines[i])
        v = REVIVAL.match(lines[i])
        if m or v:
            kind = 'normal' if m else 'revival'
            groups = (m or v).groups()
            events.append((i, kind, int(groups[0]), groups[1:]))
    assert len(events) == len(records) == len(transport)
    # Agent logs each wave's decision events only after all its transport has returned.
    stages = []
    for event, record in zip(events, records):
        line, kind, rnd, details = event
        assert record['round'] == rnd and record['valid'] == (record['confidence'] >= .7)
        if not stages or stages[-1][0] != (kind, rnd):
            stages.append(((kind,rnd),[]))
        stages[-1][1].append((line,details,record))
    net_i = 0
    active = ids
    wins = dict.fromkeys(ids, 0)
    elimination = {}
    bank = {}
    draws = []
    for (kind, rnd), stage in stages:
        stop = stage[0][0]
        fresh = {}
        count = 0
        while net_i < len(transport) and transport[net_i][0] < stop:
            _, mode, ab = transport[net_i]
            if mode == 'query':
                assert ab[0] not in fresh
                fresh[ab[0]] = ab
            net_i += 1
            count += 1
        assert count == len(stage)
        if kind == 'normal':
            advance = active[-1:] if len(active)%2 else []
            pending = []
            assert len(stage) == len(active)//2
        else:
            if not advance:
                advance.append(pending.pop(0))
            options = tuple(advance)
            assert len(stage) == len(pending)
        for k, (_, details, r) in enumerate(stage):
            slot = r['winner']
            conf = r['confidence']
            assert (slot in (0,1)) if r['valid'] else slot is None
            if kind == 'normal':
                a,b = active[2*k:2*k+2]
                pair = (a,b)
                first, verb, second = details
                assert set(pair) == {prefix[first],prefix[second]}
                if verb == 'beats':
                    assert pair[slot] == prefix[first]
                    advance.append(pair[slot])
                    wins[pair[slot]] += 1
                    elimination[pair[1-slot]] = rnd
                else:
                    assert slot is None and pair[0] == prefix[first]
                    pending += list(pair)
            else:
                a = pending[k]
                assert prefix[details[0]] == a
                if slot == 0:
                    assert details[1].startswith('beats winner')
                elif slot == 1:
                    assert details[1].startswith('lost to winner')
                else:
                    assert 'inconclusive' in details[1]
                if a in fresh:
                    choices = (fresh[a][1],)
                    assert choices[0] in options
                else:
                    # A cached result retains its original position and confidence,
                    # even on a reversed pair. Multi-hit order in a thread pool is
                    # deliberately unused. An unbound hit could be cross-batch.
                    choices = []
                    for b in options:
                        key = frozenset((a,b))
                        old = bank.get(key)
                        if ((old is None and key in earlier_queries) or
                                (old is not None and old.slot == slot and old.conf == conf)):
                            choices.append(b)
                    assert choices
                draws.append((options, tuple(options.index(b) for b in choices)))
                if slot != 1:
                    advance.append(a)
                if slot == 0:
                    wins[a] += 1
                elif slot == 1:
                    elimination[a] = rnd
            if a in fresh:
                pair = fresh.pop(a)
                if kind == 'normal':
                    assert pair == (a,b)
                key = frozenset(pair)
                assert key not in bank
                bank[key] = Read(slot, conf, pair)
        assert not fresh
        active = list(advance)
    assert net_i == len(transport)
    last_round = stages[-1][0][1]
    keys = {i:(int(i not in elimination), wins[i], elimination.get(i, last_round)) for i in ids}
    ranked = sorted(set(keys.values()), reverse=True)
    assert all(ranked.index(keys[n['id']]) == n['wm_predicted_rank']
               and keys[n['id']][2] == n['wm_round'] for n in candidates)
    return bank, draws, len(records)


def one_replay(module, ids, bank, draws, decisions, complete_missing=False):
    """Execute the checked-in ranking controller with original random-index constraints."""
    nodes = [SimpleNamespace(id=i) for i in ids]
    model = module.WorldModel('historical siblings', '', config=module.WorldModelConfig(confidence_threshold=.7))
    active_reads = {}
    draw_no = 0
    branch_no = 0
    aligned = True
    edges = set()
    def take(options):
        nonlocal branch_no
        if branch_no == len(decisions):
            raise Branch(tuple(options))
        index = decisions[branch_no]
        branch_no += 1
        assert index in options
        return index

    def choice(options):
        nonlocal draw_no, aligned
        hist_options, indices = draws[draw_no] if draw_no < len(draws) else ((),())
        # CPython random.choice depends on sequence length. Equal lengths through
        # this draw preserve indices even if some candidate identities change.
        if len(hist_options) != len(options):
            aligned = False
        indices = indices if aligned else tuple(range(len(options)))
        draw_no += 1
        if len(indices) == 1:
            return options[indices[0]]
        a = inspect.currentframe().f_back.f_locals['pending_node'].id
        possibilities = [frozenset((a,options[i].id)) for i in indices]
        # In a revival only the pending node gains a win. A consulted edge is
        # already present in the read graph, and a denied unseen edge abstains.
        # Collapsing alternatives here leaves the entire future decision state
        # identical, except for cached denials that will always abstain anyway.
        if all(k in active_reads or len(active_reads) == BUDGET for k in possibilities):
            statuses = set()
            for k in possibilities:
                w = active_reads.get(k)
                statuses.add(None if w is None else w == a)
            if len(statuses) == 1:
                return options[indices[0]]
        return options[take(indices)]

    def batch(pairs, max_workers=None):
        results = []
        for na,nb,rnd in pairs:
            a,b = na.id,nb.id
            key = frozenset((a,b))
            if key not in active_reads and len(active_reads) < BUDGET:
                if key in bank:
                    w = bank[key].winner()
                elif complete_missing:
                    w = (None,a,b)[take(range(3))]
                else:
                    raise Missing('required_first_read_without_bound_judgment')
                active_reads[key] = w
                if w:
                    edges.add((w,b if w==a else a))
            winner = active_reads.get(key)
            slot = (a,b).index(winner) if winner else None
            results.append(module.ComparisonResult(slot,1-slot if winner else None,
                           bank[key].conf if key in active_reads and key in bank else float(bool(winner)),
                           rnd, winner is not None,''))
        return results
    module.random = SimpleNamespace(choice=choice)
    model._batch_predict_pairwise = batch
    ranked, _, meta = model.tournament_rank(nodes)
    return tuple(sorted(n.id for n in ranked if meta[n.id]['rank']==0)), tuple(sorted(edges))


def identify(module, ids, bank, draws, *, complete_missing=False, limit=10000):
    paths = [()]
    leaves = set()
    count = 0
    while paths:
        decisions = paths.pop()
        count += 1
        if count > limit:
            return None,None,'unresolved_branch_limit',count,None
        try:
            leaves.add(one_replay(module, ids, bank, draws, decisions, complete_missing))
        except Branch as branch:
            paths.extend(decisions+(i,) for i in branch.args[0])
        except Missing as missing:
            return None,None,str(missing),count,None
    tops = {top for top,graph in leaves}
    graphs = {graph for top,graph in leaves}
    top = list(next(iter(tops))) if len(tops)==1 else None
    graph = list(next(iter(graphs))) if len(graphs)==1 else None
    alternatives = [dict(c0_top=t,accepted_edges=g) for t,g in sorted(leaves)] if len(leaves)>1 else None
    return top,graph,'certified_parsed' if top is not None else 'alternative_top_groups',count,alternatives


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output',type=Path)
    args=parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    ref = ROOT/'experiments/chronological-memory-v1/run-001/batches.jsonl'
    cohort = defaultdict(list)
    for line in ref.read_text().splitlines():
        r = json.loads(line)
        cohort[r['run']].append(r)
    hist = ROOT/'experiments/historical-v1'
    sources = {(r['run'],r['file']):r for r in json.loads((hist/'source_manifest.json').read_text())}
    phase = ROOT/'phase1-reproduction'
    local_sources = {r['path']:r['sha256'] for r in json.loads((phase/'SOURCES.json').read_text())['files'] if 'sha256' in r}
    module = load_world()
    rows = []
    for name,batches in cohort.items():
        def read(file):
            if name=='stanford-autodl-v2':
                path = phase/'records/stanford-autodl-v2/logs/exp'/file
                return verified(path,local_sources[str(path.relative_to(phase))])
            spec=sources[name,file]
            return verified(ROOT/'data/historical'/spec['compressed_file'],spec['sha256'])
        nodes={n['id']:n for n in json.loads(read('journal.json'))['nodes']}
        lines=read('aide.log').decode().splitlines()
        earliest = past_query_index(lines)
        for r in batches:
            ids=r['candidates']
            ns=[nodes[i] for i in ids]
            ranks={n['id']:n['wm_predicted_rank'] for n in ns}
            row=dict(run=name,task=r['task'],first_log_line=r['first_log_line'],candidates=ids,
                     logged_ranks=ranks,logged_top=[i for i in ids if ranks[i]==0],
                     c0_top=None,accepted_edges=None)
            try:
                digests={n['id']:code_digest(n['code']) for n in ns}
                start=r['first_log_line']-1
                earlier = {frozenset((a,b)) for ia,a in enumerate(ids) for b in ids[:ia]
                           if earliest.get(frozenset((digests[a],digests[b])), len(lines)) < start}
                bank,draws,num=reconstruct_inputs(lines,start,ns,earlier)
                top,graph,reason,count,alternatives=identify(module,ids,bank,draws)
                if reason == 'required_first_read_without_bound_judgment':
                    top,graph,reason,count,alternatives=identify(module,ids,bank,draws,complete_missing=True)
                    row['counterfactual_input_gap'] = True
                if alternatives is not None:
                    row.update(alternatives=alternatives,exhaustive=True)
                row.update(c0_top=top,accepted_edges=graph,reason=reason,proof_nodes=count,
                           raw_parser_top_graph_certified=bool(top is not None and not any(x.slot is not None for x in bank.values())),
                           first_pair_seen_in_earlier_batch_count=len(earlier),
                           fresh_pairs=len(bank),accepted_fresh_pairs=sum(x.slot is not None for x in bank.values()),
                           historical_draws=len(draws),ambiguous_draws=sum(len(ix)>1 for _,ix in draws))
            except Missing as exc:
                row['reason']=str(exc)
            rows.append(row)
        print(name,Counter(x['reason'] for x in rows if x['run']==name), flush=True)
    assert sum(map(len,cohort.values()))==len(rows)==136
    args.output.write_text(''.join(json.dumps(r)+'\n' for r in rows))
    print(Counter(x['reason'] for x in rows))


if __name__=='__main__':
    main()
