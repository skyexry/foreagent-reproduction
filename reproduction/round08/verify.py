"""Independent full R8 vote/scoring/pooling audit plus 78 native control checks."""
import argparse
from collections import Counter
import gzip
import json
import math
from pathlib import Path
import random
import sys
import types
import hashlib

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from reproduction.round08.data import check_registration, load_groups, load_table
from reproduction.round08.run import load_canonical

E = ROOT/'experiments/round-08'
METRICS = ['uniform_tie_best_hit', 'normalized_regret', 'selected_percentile', 'top_group_size', 'contains_best']
METHODS = ['tournament', 'r6', 'r7']


def close(a, b):
    assert math.isclose(a, b, abs_tol=1e-10), (a, b)


def native_check(module, row, trace):
    module.random.seed(row['seed']); module.WorldModel._comparison_cache.clear()
    wm = module.WorldModel(row['task'], '', config=module.WorldModelConfig(
        confidence_threshold=.7, temperature=1., exec_probability=.2, max_concurrent_requests=1))
    fixed = {(e['a'], e['b']): e for e in row['feedback']}; cursor = [0]
    def batch(pairs, max_workers=None):
        results = []
        for a, b, round_num in pairs:
            e = fixed[tuple(sorted((a.id, b.id)))]; observed = trace[cursor[0]]; cursor[0] += 1
            expected = dict(a=a.id, b=b.id, round=round_num, winner=e['winner'],
                            confidence=e['confidence'], valid=e['valid'])
            assert observed == expected
            winner = None if e['winner'] is None else (a.id, b.id).index(e['winner'])
            results.append(module.ComparisonResult(winner_idx=winner, loser_idx=None if winner is None else 1-winner,
                confidence=e['confidence'], round_num=round_num, is_valid=e['valid']))
        return results
    wm._batch_predict_pairwise = batch
    nodes = [types.SimpleNamespace(id=x, code=x) for x in row['candidates']]
    ranked, comparisons, meta = wm.tournament_rank(nodes)
    assert meta == row['rank_meta'] and cursor[0] == len(comparisons) == len(trace)
    assert [x.id for x in ranked if meta[x.id]['rank'] == 0] == row['selected']['tournament']


def main():
    import os
    if not __debug__:
        raise SystemExit("Verification requires Python assertions enabled")
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, default=ROOT/'runs/round08')
    p.add_argument('--all-native', action='store_true')
    args = p.parse_args(); out = args.output
    assert os.environ.get('PYTHONHASHSEED') == '0'
    check_registration(); config = json.loads((E/'protocol.json').read_text())
    jobs = [json.loads(s) for s in (E/'jobs.jsonl').read_text().splitlines()]
    summary = json.loads((out/'summary.json').read_text()); groups = load_groups()
    labels = {task: {Path(n).name: (-v if g['is_lower_better'] else v)
              for g in rows for n, v in zip(g['paths'], g['scores']) if math.isfinite(v)} for task, rows in groups.items()}
    tables = {}
    for entry in json.loads((E/'data_manifest.json').read_text())['files']:
        table, _ = load_table(entry, groups[entry['task']]); tables[entry['feedback_run'], entry['task']] = table
    accum = {(run, task): [] for run in config['feedback_runs'] for task in groups}
    budgets = {run: Counter() for run in config['feedback_runs']}; diagnostics = {run: Counter() for run in config['feedback_runs']}
    source_union = set(); pair_union = set(); count = audits = 0; module = load_canonical()
    with gzip.open(out/'runs.jsonl.gz', 'rt') as rows, gzip.open(out/'traces.jsonl.gz', 'rt') as traces:
        for job, line, trace_line in zip(jobs, rows, traces, strict=True):
            r, trace_row = json.loads(line), json.loads(trace_line); run, task = job['feedback_run'], job['task']
            assert all(r[k] == v for k, v in job.items())
            assert trace_row['job_id'] == job['job_id'] and trace_row['feedback_run'] == run and trace_row['task'] == task
            ids = r['candidates']; assert hashlib.sha256(json.dumps(ids, separators=(',', ':')).encode()).hexdigest() == job['candidate_order_sha256']
            assert len(ids) == len(set(ids))
            assert set(r['rank_meta']) == set(r['statistics']) == set(ids)
            trace = trace_row['comparisons']; first = {}; table = tables[run, task]
            for c in trace:
                assert c['a'] in ids and c['b'] in ids and c['a'] != c['b']
                key = tuple(sorted((c['a'], c['b']))); saved = table[key]
                assert c['confidence'] == saved['confidence']
                valid = saved['winner'] is not None and saved['confidence'] >= .7
                assert c['valid'] == valid and c['winner'] == (saved['winner'] if valid else None)
                e = dict(a=key[0], b=key[1], winner=c['winner'], confidence=c['confidence'], valid=valid)
                if key in first: assert first[key] == e
                else: first[key] = e
            assert r['feedback'] == list(first.values())
            wins = dict.fromkeys(ids, 0); losses = dict.fromkeys(ids, 0)
            for e in r['feedback']:
                pair_union.add((task, e['a'], e['b'])); source_union.add((run, task, e['a'], e['b']))
                if e['valid']:
                    wins[e['winner']] += 1
                    losses[next(x for x in (e['a'], e['b']) if x != e['winner'])] += 1
            degree = {x: wins[x]+losses[x] for x in ids}
            ratios = {x: (wins[x], degree[x]) if degree[x] else (1, 2) for x in ids}
            r6 = [x for x in ids if all(ratios[x][0]*ratios[y][1] >= ratios[y][0]*ratios[x][1] for y in ids)]
            r7 = [x for x in r6 if degree[x] == max(degree[y] for y in r6)]
            assert r6 == r['selected']['r6'] and r7 == r['selected']['r7']
            assert set(r['selected']['tournament']) == {x for x, m in r['rank_meta'].items() if m['rank'] == 0}
            for x, st in r['statistics'].items():
                assert st['wins'] == wins[x] and st['losses'] == losses[x]
                assert st['numerator']*ratios[x][1] == ratios[x][0]*st['denominator']
            u = labels[task]; best, worst = max(u[x] for x in ids), min(u[x] for x in ids)
            computed = {}
            for method in METHODS:
                top = r['selected'][method]; k = len(top); assert k and len(set(top)) == k
                m = dict(uniform_tie_best_hit=sum(u[x] == best for x in top)/k,
                         normalized_regret=(best-sum(u[x] for x in top)/k)/(best-worst) if best != worst else 0.,
                         selected_percentile=sum((sum(u[y] < u[x] for y in ids)+
                             (sum(u[y] == u[x] for y in ids)-1)/2)/(len(ids)-1) for x in top)/k,
                         top_group_size=k, contains_best=float(any(u[x] == best for x in top)))
                for metric in METRICS: close(m[metric], r['metrics'][method][metric])
                computed[method] = m
            accum[run, task].append(computed)
            budget = dict(unique_feedback=len(first), unique_feedback_cap=math.comb(len(ids), 2),
                comparison_records=len(trace), cache_reads=len(trace)-len(first),
                valid_unique_feedback=sum(e['valid'] for e in r['feedback']),
                invalid_winner_feedback=sum(table[key]['invalid_winner'] for key in first),
                confidence_fallback_feedback=sum(table[key]['confidence_fallback'] for key in first),
                recovered_original_failure_feedback=sum(table[key].get('recovered_raw', False) for key in first),
                new_model_calls=0, candidate_training_runs=0)
            assert budget == r['budget'] and budget['unique_feedback'] <= job['unique_feedback_cap']
            budgets[run].update(budget)
            diagnostics[run].update(dict(selected_set_changed=set(r6) != set(r7), r6_tie=len(r6)>1,
                r7_tie=len(r7)>1, all_uninformative=not any(degree.values()),
                tournament_safety_exit=max((c['round'] for c in trace), default=0) > 2*len(ids)))
            expected_audit = job['pool_id'] == 0 and job['repeat'] == 0
            assert r['native_audit_case'] == expected_audit
            if expected_audit or args.all_native:
                native_check(module, r, trace); audits += 1
            count += 1
    assert count == summary['scenarios'] == 23400 and audits == (count if args.all_native else 78)
    per_run_task = {}; run_deltas = []
    for run in config['feedback_runs']:
        saved = next(x for x in summary['per_feedback_run'] if x['feedback_run'] == run)
        for task in groups:
            block = accum[run, task]; assert len(block) == 300
            means = {method: {m: sum(r[method][m] for r in block)/300 for m in METRICS} for method in METHODS}
            per_run_task[run, task] = means
            st = next(x for x in saved['per_task'] if x['task'] == task)
            for method in METHODS:
                for m in METRICS: close(means[method][m], st['methods'][method][m])
            for m in METRICS: close(means['r7'][m]-means['r6'][m], st['delta_r7_minus_r6'][m])
        macro = {method: {m: sum(per_run_task[run, task][method][m] for task in groups)/26 for m in METRICS} for method in METHODS}
        for method in METHODS:
            for m in METRICS: close(macro[method][m], saved['methods'][method][m])
        for m in METRICS: close(macro['r7'][m]-macro['r6'][m], saved['delta_r7_minus_r6'][m])
        run_deltas.append(macro['r7']['normalized_regret']-macro['r6']['normalized_regret'])
    pooled_tasks = {}; deltas = {m: [] for m in METRICS}
    for task in groups:
        means = {method: {m: sum(per_run_task[run, task][method][m] for run in config['feedback_runs'])/3
                         for m in METRICS} for method in METHODS}
        pooled_tasks[task] = means; saved = next(x for x in summary['pooled_per_task'] if x['task'] == task)
        for method in METHODS:
            for m in METRICS: close(means[method][m], saved['methods'][method][m])
        for m in METRICS:
            d = means['r7'][m]-means['r6'][m]; deltas[m].append(d)
            close(d, saved['delta_r7_minus_r6'][m])
            close(means['r7'][m]-means['tournament'][m], saved['delta_r7_minus_tournament'][m])
    for method in METHODS:
        for m in METRICS: close(sum(t[method][m] for t in pooled_tasks.values())/26, summary['pooled_methods'][method][m])
    rng = random.Random(config['bootstrap']['seed'])
    indices = [[rng.choice(range(26)) for _ in range(26)] for _ in range(config['bootstrap']['replicates'])]
    for m, values in deltas.items():
        close(sum(values)/26, summary['delta_r7_minus_r6'][m])
        samples = sorted(sum(values[i] for i in ix)/26 for ix in indices)
        for label, probability in [('low', .025), ('high', .975)]:
            pos = (len(samples)-1)*probability; lo, hi = math.floor(pos), math.ceil(pos)
            close(samples[lo]+(samples[hi]-samples[lo])*(pos-lo), summary['paired_task_bootstrap_95'][m][label])
    total = Counter()
    for run in budgets:
        assert dict(budgets[run]) == summary['budget_by_feedback_run'][run]
        assert dict(diagnostics[run]) == summary['diagnostics_by_feedback_run'][run]
        total.update(budgets[run])
    assert dict(total) == summary['budget'] and total['unique_feedback_cap'] == 903600
    assert summary['distinct_source_feedback'] == len(source_union) and summary['distinct_candidate_pairs'] == len(pair_union)
    d = summary['delta_r7_minus_r6']; ci = summary['paired_task_bootstrap_95']
    assert summary['feedback_runs_with_regret_decrease'] == sum(x < 0 for x in run_deltas)
    assert summary['regret_prediction_supported'] == (d['normalized_regret'] < 0)
    assert summary['hit_constraint_supported'] == (d['uniform_tie_best_hit'] >= 0)
    assert summary['point_robustness_rule_met'] == (d['normalized_regret'] < 0 and d['uniform_tie_best_hit'] >= 0 and sum(x < 0 for x in run_deltas)>=2)
    assert summary['interval_evidence_rule_met'] == (ci['normalized_regret']['high'] < 0 and ci['uniform_tie_best_hit']['low'] >= 0)
    assert set(summary['content_hashes']) == {'runs.jsonl.gz', 'traces.jsonl.gz'}
    for name, expected in summary['content_hashes'].items():
        h = hashlib.sha256()
        with gzip.open(out/name, 'rb') as f:
            while chunk := f.read(1024*1024): h.update(chunk)
        assert h.hexdigest() == expected
    result = dict(status='passed', scenarios=count, independent_method_scores=3*count,
        feedback_task_blocks_checked=78, pooled_task_blocks_checked=26, native_control_audits=audits,
        bootstrap_preserves_feedback_runs_within_tasks=True, budgets_checked=True,
        protocol_commit=summary['provenance']['protocol_commit'], implementation_commit=summary['provenance']['implementation_commit'],
        new_model_calls=0, candidate_training_runs=0, content_hashes=summary['content_hashes'])
    (out/'verification.json').write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
