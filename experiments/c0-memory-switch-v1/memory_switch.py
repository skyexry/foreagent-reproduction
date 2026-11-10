"""Count C0/memory and separately logged-order/memory switches on frozen batches."""
import argparse
import gzip
import hashlib
import json
from collections import Counter
from fractions import Fraction
from pathlib import Path
from statistics import median

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
MEMORY = ROOT/'experiments/chronological-memory-v1/run-001/batches.jsonl'
MEMORY_SHA = '54f4ae682fa4593648580e1fa6a6132865a92d738154b34295833a906ec72e6f'
SEED = 'c0-memory-switch-v1/20261110'


def json_lines(path):
    return list(map(json.loads, path.read_text().splitlines()))


def doubled_midranks(keys):
    """Ordered worst-to-best keys; return twice each zero-based midrank, best first."""
    counts = Counter(keys.values())
    start, ranks = 0, {}
    for key in sorted(counts, reverse=True):
        ranks[key] = 2 * start + counts[key] - 1
        start += counts[key]
    return {candidate: ranks[key] for candidate, key in keys.items()}


def winners(keys):
    maximum = max(keys.values())
    return {i for i, value in keys.items() if value == maximum}


def fusion(judge, memory):
    j, m = doubled_midranks(judge), doubled_midranks(memory)
    return winners({i: -(j[i] + m[i]) for i in j})


def judge_keys(ids, top, edges):
    wins, degree = Counter(), Counter()
    seen = set()
    for winner, loser in edges:
        pair = frozenset([winner, loser])
        assert len(pair) == 2 and pair <= set(ids) and pair not in seen
        seen.add(pair)
        wins[winner] += 1
        degree[winner] += 1
        degree[loser] += 1
    return {i: (i in top, Fraction(wins[i], degree[i]) if degree[i] else Fraction(1, 2), degree[i])
            for i in ids}


def choice_comparison(top, new_top, priority):
    a, b = min(top, key=priority.index), min(new_top, key=priority.index)
    p = 1 - Fraction(len(top & new_top), len(top | new_top))
    return dict(baseline=sorted(top), fusion=sorted(new_top), baseline_choice=a, fusion_choice=b,
                set_changed=(top != new_top), switch=(a != b), p_switch=str(p))


def memory_input(row):
    ids = row['candidates']
    assert len(ids) == len(set(ids)) == 10
    assert len(row['history']) == min(row['available'], 10)
    if row['available'] < 3:
        assert 'prediction' not in row
        return None
    assert len(row['prediction']) == len(ids)
    return dict(zip(ids, row['prediction']))


def tie_order(row):
    prefix = f"{SEED}|{row['run']}|{row['first_log_line']}|"
    return sorted(row['candidates'], key=lambda i: hashlib.sha256((prefix + i).encode()).digest())


def journal_nodes(runs):
    manifest = {r['run']:r for r in json.loads((ROOT/'experiments/historical-v1/source_manifest.json').read_text())
                if r['file'] == 'journal.json'}
    for run in sorted(runs):
        if run == 'stanford-autodl-v2':
            path = ROOT/'phase1-reproduction/records/stanford-autodl-v2/logs/exp/journal.json'
            digest = json.loads((ROOT/'experiments/online-stanford-v2/final-summary.json').read_text())['journal_sha256']
            data = path.read_bytes()
        else:
            spec = manifest[run]
            data = gzip.decompress((ROOT/'data/historical'/spec['compressed_file']).read_bytes())
            digest = spec['sha256']
        assert hashlib.sha256(data).hexdigest() == digest
        yield run, json.loads(data)['nodes']


def journal_ranks(runs):
    return {run:{n['id']:n['wm_predicted_rank'] for n in nodes}
            for run,nodes in journal_nodes(runs)}


def logged_comparison(row, ranks):
    ids = row['candidates']
    assert all(type(ranks[i]) is int for i in ids)
    keys = {i: -ranks[i] for i in ids}
    best = winners(keys)
    mem = memory_input(row)
    return choice_comparison(best, fusion(keys, mem) if mem is not None else best, tie_order(row))


def known_comparison(row, c0):
    ids = row['candidates']
    assert set(c0['candidates']) == set(ids)
    if c0['reason'] == 'duplicate_code_rejected_by_frozen_selector':
        assert c0['c0_top'] is None and c0['accepted_edges'] is None
        return 'outside_frozen_input_domain', {'outside_domain': True}
    mem = memory_input(row)
    top = c0['c0_top']
    edges = c0['accepted_edges']
    if top is not None:
        top = set(top)
        assert top and top <= set(ids)
        if mem is None:
            return 'history_fallback', choice_comparison(top, top, tie_order(row))
        if edges is not None:
            keys = judge_keys(ids, top, edges)
            return 'c0_top_and_graph', choice_comparison(top, fusion(keys, mem), tie_order(row))
        if len(top) == 1 and top <= winners(mem):
            # Its judge rank is strictly first for every possible accepted graph.
            return 'joint_top_certificate', choice_comparison(top, top, tie_order(row))
    if c0.get('exhaustive') and c0.get('alternatives'):
        possible = []
        for state in c0['alternatives']:
            base = set(state['c0_top'])
            assert base and base <= set(ids)
            keys = judge_keys(ids, base, state['accepted_edges'])
            fused = fusion(keys, mem) if mem is not None else base
            possible.append(choice_comparison(base, fused, tie_order(row)))
        ret = dict(alternatives=possible)
        for key in ('switch','set_changed','p_switch'):
            values = {s[key] for s in possible}
            if len(values) == 1:
                ret[key] = values.pop()
        return 'invariant_switch_across_alternatives' if 'switch' in ret else 'switch_depends_on_unseen_vote', ret
    if mem is None:
        return 'history_fallback_unknown_c0', dict(switch=False, set_changed=False, p_switch='0')
    return 'unresolved', {}


def describe(comparisons):
    known = [r for r in comparisons if 'switch' in r]
    outside = sum(r.get('outside_domain', False) for r in comparisons)
    missing = len(comparisons) - len(known) - outside
    switches = sum(r['switch'] for r in known)
    p = [Fraction(r['p_switch']) for r in comparisons if 'p_switch' in r]
    probs = []
    for r in comparisons:
        if r.get('outside_domain'):
            continue
        if 'p_switch' in r:
            probs.append([Fraction(r['p_switch'])])
        elif r.get('alternatives'):
            probs.append([Fraction(v['p_switch']) for v in r['alternatives']])
        else:
            probs.append([Fraction(0), Fraction(1)])
    return dict(total=len(comparisons), in_frozen_domain=len(comparisons)-outside, outside_domain=outside,
                identified=len(known), unresolved_in_domain=missing,
                fixed_tie_order_switches=switches, fixed_tie_order_unchanged=len(known)-switches,
                switched_batches_interval_in_domain=[switches, switches+missing],
                top_set_relation_identified=sum('set_changed' in r for r in comparisons),
                different_top_sets=sum(r.get('set_changed', False) for r in comparisons),
                disjoint_top_sets=sum(x==1 for x in p), partial_overlap=sum(0<x<1 for x in p),
                uniform_probability_identified=len(p),
                expected_switches_on_identified_probabilities=float(sum(p)),
                expected_switches_in_domain_interval=[float(sum(map(min,probs))),float(sum(map(max,probs)))])


def process(replay):
    assert hashlib.sha256(MEMORY.read_bytes()).hexdigest() == MEMORY_SHA
    mem_rows = json_lines(MEMORY)
    refs = {(r['run'], r['first_log_line']):r for r in json_lines(replay)}
    assert len(refs) == len(mem_rows) == 136
    logs = journal_ranks({r['run'] for r in mem_rows})
    results = []
    for r in mem_rows:
        run, start = r['run'], r['first_log_line']
        c0 = refs.pop((run, start))
        s, comparison = known_comparison(r, c0)
        logged = logged_comparison(r, logs[run])
        if 'logged_top' in c0:
            assert set(c0['logged_top']) == set(logged['baseline'])
        pred = r.get('prediction', [])
        results.append(dict(run=run, first_log_line=start, task=r['task'], available=r['available'],
                            distinct_memory_values=len(set(pred)),
                            memory_span=(max(pred)-min(pred) if pred else None), c0_top_known=c0['c0_top'] is not None,
                            c0_graph_known=c0['accepted_edges'] is not None,
                            raw_parser_certified=bool(c0.get('raw_parser_top_graph_certified')),
                            c0_switch_identification=s, c0=comparison,
                            logged_order_proxy=logged))
    assert not refs
    return results


def report(rows):
    spans = [r['memory_span'] for r in rows if r['memory_span'] is not None]
    return dict(batches=len(rows), history_usable=sum(r['available']>=3 for r in rows),
                memory_distinguishes_siblings=sum(r['distinct_memory_values']>1 for r in rows),
                memory_span_on_usable=(dict(min=min(spans), median=median(spans), max=max(spans))
                                       if spans else None),
                c0_top_identified=sum(r['c0_top_known'] for r in rows),
                c0_top_and_graph_identified=sum(r['c0_top_known'] and r['c0_graph_known'] for r in rows),
                c0_switch_identification=dict(Counter(r['c0_switch_identification'] for r in rows)),
                c0_switch=describe([r['c0'] for r in rows]),
                identified_c0_top_only_denominator=describe([r['c0'] for r in rows if r['c0_top_known']]),
                raw_parser_certified_subset=describe([r['c0'] for r in rows if r['raw_parser_certified']]),
                logged_order_proxy=describe([r['logged_order_proxy'] for r in rows]))


def main():
    arg = argparse.ArgumentParser(description=__doc__)
    arg.add_argument('replay', type=Path)
    arg.add_argument('out', type=Path, help='fresh directory')
    args = arg.parse_args()
    rows = process(args.replay)
    summary = dict(seed=SEED, chronological_sha256=MEMORY_SHA,
                   replay_sha256=hashlib.sha256(args.replay.read_bytes()).hexdigest(),
                   all=report(rows), by_task={t:report([r for r in rows if r['task']==t])
                                             for t in sorted({r['task'] for r in rows})})
    args.out.mkdir(parents=True)
    (args.out/'switches.jsonl').write_text(''.join(json.dumps(r, sort_keys=True)+'\n' for r in rows))
    (args.out/'summary.json').write_text(json.dumps(summary, indent=2)+'\n')
    print(json.dumps(summary['all'], indent=2))


if __name__ == '__main__':
    main()
