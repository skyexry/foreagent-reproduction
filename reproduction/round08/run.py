"""Frozen canonical tournament plus R6/R7 under three preregistered GPT tables."""
import argparse
import ast
from collections import Counter
import datetime
import gzip
import io
import json
import logging
import math
from pathlib import Path
import platform
import statistics
import subprocess
import sys
import time
import types

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from reproduction.round06.methods import unique_feedback, win_rate_select
from reproduction.round06.run import METRICS, bootstrap, dump, score_selection, sha, stream_sha
from reproduction.round07.methods import evidence_tiebreak_select
from reproduction.round08.data import check_registration, load_groups, load_table

E = ROOT/'experiments/round-08'
METHODS = ['tournament', 'r6', 'r7']


def load_canonical():
    config = json.loads((E/'protocol.json').read_text())
    path = ROOT/config['canonical_source']
    assert sha(path.read_bytes()) == config['canonical_source_sha256']
    tree = ast.parse(path.read_text())
    tree.body = [n for n in tree.body if not (isinstance(n, ast.ImportFrom) and n.level)]
    module = types.ModuleType('_r8_canonical')
    sys.modules[module.__name__] = module
    def disabled(**kwargs):
        raise AssertionError('Only a registered saved-response backend is supported')
    module.__dict__.update(Node=types.SimpleNamespace, query=disabled)
    exec(compile(tree, str(path), 'exec'), module.__dict__)
    module.logger.setLevel(logging.CRITICAL)
    return module


def saved_response_query(table, calls):
    def query(**kwargs):
        body = kwargs['user_message'].split('### Solution 0:\n```python\n\n', 1)[1]
        a, b = body.split('\n```\n\n### Solution 1:\n```python\n\n', 1)
        b = b.rsplit('\n```', 1)[0]
        key = tuple(sorted((a, b))); row = table[key]
        calls.append(key)
        if row['winner'] is None:
            raise RuntimeError('Recorded invalid model winner')
        assert row['winner'] in (a, b)
        return json.dumps({'predicted_best_index': 0 if row['winner'] == a else 1,
                           'confidence': row['confidence']})
    return query


def run_tournament(module, candidates, table, seed, task):
    module.random.seed(seed); module.WorldModel._comparison_cache.clear()
    calls = []; module.query = saved_response_query(table, calls)
    wm = module.WorldModel(task, '', config=module.WorldModelConfig(
        confidence_threshold=.7, temperature=1., exec_probability=.2, max_concurrent_requests=1))
    nodes = [types.SimpleNamespace(id=x, code=x) for x in candidates]
    trace = []; batch = wm._batch_predict_pairwise
    def traced(pairs, max_workers=None):
        results = batch(pairs, max_workers=max_workers)
        for (a, b, round_num), result in zip(pairs, results, strict=True):
            winner = None if result.winner_idx is None else (a.id, b.id)[result.winner_idx]
            trace.append(dict(a=a.id, b=b.id, round=round_num, winner=winner,
                              confidence=result.confidence, valid=result.is_valid))
        return results
    wm._batch_predict_pairwise = traced
    ranked, comparisons, meta = wm.tournament_rank(nodes)
    top = [x.id for x in ranked if meta[x.id]['rank'] == 0]
    assert len(trace) == len(comparisons)
    feedback = unique_feedback(candidates, trace)
    assert len(calls) == len(set(calls)) == len(feedback)
    assert set(calls) == {(e['a'], e['b']) for e in feedback}
    for e in feedback:
        saved = table[e['a'], e['b']]
        assert e['confidence'] == saved['confidence']
        assert e['winner'] == (saved['winner'] if e['valid'] else None)
    return top, meta, trace, feedback


def task_means(accum, config, task_order):
    per_run = []
    for run in config['feedback_runs']:
        tasks = []
        for task in task_order:
            rows = accum[run, task]
            assert len(rows) == 300
            means = {kind: {m: statistics.mean(r[kind][m] for r in rows) for m in METRICS} for kind in METHODS}
            tasks.append(dict(task=task, scenarios=len(rows), methods=means,
                              delta_r7_minus_r6={m: means['r7'][m]-means['r6'][m] for m in METRICS}))
        macro = {kind: {m: statistics.mean(t['methods'][kind][m] for t in tasks) for m in METRICS} for kind in METHODS}
        per_run.append(dict(feedback_run=run, scenarios=sum(t['scenarios'] for t in tasks), methods=macro,
                            delta_r7_minus_r6={m: macro['r7'][m]-macro['r6'][m] for m in METRICS}, per_task=tasks))
    pooled_tasks = []
    for task in task_order:
        blocks = [next(t for t in run['per_task'] if t['task'] == task) for run in per_run]
        means = {kind: {m: statistics.mean(t['methods'][kind][m] for t in blocks) for m in METRICS} for kind in METHODS}
        pooled_tasks.append(dict(task=task, methods=means,
             delta_r7_minus_r6={m: means['r7'][m]-means['r6'][m] for m in METRICS},
             delta_r7_minus_tournament={m: means['r7'][m]-means['tournament'][m] for m in METRICS}))
    pooled = {kind: {m: statistics.mean(t['methods'][kind][m] for t in pooled_tasks) for m in METRICS} for kind in METHODS}
    return per_run, pooled_tasks, pooled


def main():
    import os
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT/'runs/round08')
    args = parser.parse_args(); started = time.monotonic()
    assert os.environ.get('PYTHONHASHSEED') == '0', 'Set PYTHONHASHSEED=0'
    protocol_commit = check_registration()
    assert not subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT, text=True), 'Commit implementation before comparison'
    config = json.loads((E/'protocol.json').read_text())
    validation = json.loads((E/'data_validation.json').read_text())
    assert validation['status'] == 'passed' and validation['files_verified'] == 78
    source_records = {(x['feedback_run'], x['task']): x for x in validation['files']}
    corpus_path = ROOT/'experiments/corpus26-v2/protocol.json'
    assert sha(corpus_path.read_bytes()) == config['corpus_protocol_sha256']
    corpus = json.loads(corpus_path.read_text()); groups = load_groups(); task_order = list(groups)
    prior_jobs_path = ROOT/'experiments/round-07/jobs.jsonl'
    assert sha(prior_jobs_path.read_bytes()) == config['prior_jobs_sha256']
    prior_jobs = [json.loads(s) for s in prior_jobs_path.read_text().splitlines()]
    jobs = [json.loads(s) for s in (E/'jobs.jsonl').read_text().splitlines()]
    pools = {(t['task'], p['pool_id']): p for t in corpus['tasks'] for p in t['pools']}
    labels = {task: {Path(name).name: (-score if g['is_lower_better'] else score)
                    for g in rows for name, score in zip(g['paths'], g['scores']) if math.isfinite(score)}
              for task, rows in groups.items()}
    tables = {}
    for entry in json.loads((E/'data_manifest.json').read_text())['files']:
        table, record = load_table(entry, groups[entry['task']])
        assert record == source_records[entry['feedback_run'], entry['task']]
        tables[entry['feedback_run'], entry['task']] = table
    out = args.output.resolve(); assert not out.exists(), 'Preserve previous output'
    out.mkdir(parents=True)
    provenance = dict(protocol_commit=protocol_commit,
        implementation_commit=subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
        started_at_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(), python=platform.python_version(),
        platform=platform.platform(), canonical_sha256=config['canonical_source_sha256'],
        data_validation_sha256=sha((E/'data_validation.json').read_bytes()),
        data_source_addendum_commit=validation['data_source_addendum_commit'])
    dump(out/'started.json', provenance)
    accum = {(run, task): [] for run in config['feedback_runs'] for task in task_order}
    budgets = {run: Counter() for run in config['feedback_runs']}; diagnostics = {run: Counter() for run in config['feedback_runs']}
    source_union = set(); pair_union = set(); module = load_canonical()
    with (out/'runs.jsonl.gz').open('wb') as raw, gzip.GzipFile(filename='', fileobj=raw, mode='wb', mtime=0) as gz, \
         io.TextIOWrapper(gz, encoding='utf-8') as output, (out/'traces.jsonl.gz').open('wb') as trace_raw, \
         gzip.GzipFile(filename='', fileobj=trace_raw, mode='wb', mtime=0) as trace_gz, \
         io.TextIOWrapper(trace_gz, encoding='utf-8') as traces:
        count = 0
        for job in jobs:
            assert time.monotonic()-started < config['budget']['max_wall_seconds_per_attempt']
            base = prior_jobs[job['base_job_id']]; run, task = job['feedback_run'], job['task']
            assert all(job[k] == base[k] for k in ['task', 'pool_id', 'repeat', 'seed', 'candidate_order_sha256'])
            pool = pools[task, job['pool_id']]; ids = pool['candidate_order']
            assert job['seed'] == pool['replay_seeds'][job['repeat']]
            assert sha(json.dumps(ids, separators=(',', ':')).encode()) == job['candidate_order_sha256']
            table = tables[run, task]
            top, meta, trace, feedback = run_tournament(module, ids, table, job['seed'], task)
            r6, stats, graph = win_rate_select(ids, feedback)
            r7, other_stats, _ = evidence_tiebreak_select(ids, feedback)
            assert stats == other_stats and r7 and set(r7) <= set(r6)
            selected = dict(tournament=top, r6=r6, r7=r7)
            scores = {kind: score_selection(ids, chosen, labels[task]) for kind, chosen in selected.items()}
            budget = dict(unique_feedback=len(feedback), unique_feedback_cap=job['unique_feedback_cap'],
                          comparison_records=len(trace), cache_reads=len(trace)-len(feedback),
                          valid_unique_feedback=graph['valid_unique_edges'],
                          invalid_winner_feedback=sum(table[e['a'], e['b']]['invalid_winner'] for e in feedback),
                          confidence_fallback_feedback=sum(table[e['a'], e['b']]['confidence_fallback'] for e in feedback),
                          recovered_original_failure_feedback=sum(table[e['a'], e['b']].get('recovered_raw', False) for e in feedback),
                          new_model_calls=0, candidate_training_runs=0)
            assert budget['unique_feedback'] <= budget['unique_feedback_cap'] == math.comb(len(ids), 2)
            budgets[run].update(budget)
            diagnostics[run].update(dict(selected_set_changed=set(r6) != set(r7),
                r6_tie=len(r6) > 1, r7_tie=len(r7) > 1, all_uninformative=graph['all_uninformative'],
                tournament_safety_exit=max((e['round'] for e in trace), default=0) > 2*len(ids)))
            row = dict(**job, candidates=ids, feedback=feedback, selected=selected, metrics=scores,
                       statistics=stats, rank_meta=meta, budget=budget,
                       native_audit_case=job['pool_id'] == 0 and job['repeat'] == 0)
            output.write(json.dumps(row, separators=(',', ':'))+'\n')
            traces.write(json.dumps(dict(job_id=job['job_id'], feedback_run=run, task=task, comparisons=trace), separators=(',', ':'))+'\n')
            accum[run, task].append(scores)
            for e in feedback:
                pair_union.add((task, e['a'], e['b'])); source_union.add((run, task, e['a'], e['b']))
            count += 1
            if count % 300 == 0:
                print('Completed', run, task, '300 scenarios', flush=True)
    assert count == len(jobs) == config['budget']['scenarios']
    per_run, per_task, pooled = task_means(accum, config, task_order)
    delta = {m: pooled['r7'][m]-pooled['r6'][m] for m in METRICS}
    ci = {m: bootstrap([t['delta_r7_minus_r6'][m] for t in per_task], config['bootstrap']) for m in METRICS}
    runs_better = sum(r['delta_r7_minus_r6']['normalized_regret'] < 0 for r in per_run)
    total_budget = Counter()
    for b in budgets.values(): total_budget.update(b)
    assert total_budget['unique_feedback_cap'] == config['budget']['unique_feedback_cap_summed']
    summary = dict(experiment_id='round-08', provenance=provenance, scenarios=count, method_selection_scores=3*count,
        per_feedback_run=per_run, pooled_per_task=per_task, pooled_methods=pooled, delta_r7_minus_r6=delta,
        delta_r7_minus_tournament={m: pooled['r7'][m]-pooled['tournament'][m] for m in METRICS},
        paired_task_bootstrap_95=ci, feedback_runs_with_regret_decrease=runs_better,
        regret_prediction_supported=delta['normalized_regret'] < 0,
        hit_constraint_supported=delta['uniform_tie_best_hit'] >= 0,
        point_robustness_rule_met=delta['normalized_regret'] < 0 and delta['uniform_tie_best_hit'] >= 0 and runs_better >= 2,
        interval_evidence_rule_met=ci['normalized_regret']['high'] < 0 and ci['uniform_tie_best_hit']['low'] >= 0,
        budget=dict(total_budget), budget_by_feedback_run={k: dict(v) for k, v in budgets.items()},
        diagnostics_by_feedback_run={k: dict(v) for k, v in diagnostics.items()},
        distinct_source_feedback=len(source_union), distinct_candidate_pairs=len(pair_union), scope=config['scope'])
    summary['content_hashes'] = {}
    for name in ['runs.jsonl.gz', 'traces.jsonl.gz']:
        with gzip.open(out/name, 'rb') as f: summary['content_hashes'][name] = stream_sha(f)
    assert time.monotonic()-started < config['budget']['max_wall_seconds_per_attempt']
    dump(out/'summary.json', summary)
    dump(out/'execution.json', dict(wall_seconds=time.monotonic()-started,
        completed_at_utc=datetime.datetime.now(datetime.timezone.utc).isoformat()))
    print(json.dumps({k: summary[k] for k in ['pooled_methods', 'delta_r7_minus_r6', 'point_robustness_rule_met',
          'interval_evidence_rule_met', 'budget']}), flush=True)


if __name__ == '__main__':
    main()
