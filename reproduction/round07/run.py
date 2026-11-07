"""Preregistered R7 ablation using the immutable R6 feedback/result attachment."""
import hashlib
import argparse
import csv
import datetime
import gzip
import io
import json
import math
from pathlib import Path
import platform
import statistics
import subprocess
import sys
import time
import zipfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from reproduction.round06.methods import unique_feedback, win_rate_select
from reproduction.round06.run import METRICS, bootstrap, dump, score_selection, sha, stream_sha
from reproduction.round07.methods import evidence_tiebreak_select

E = ROOT/'experiments/round-07'


def load_labels():
    corpus_path = ROOT/'experiments/corpus26-v2/protocol.json'
    settings = json.loads((E/'protocol.json').read_text())
    assert sha(corpus_path.read_bytes()) == settings['corpus_protocol_sha256']
    labels = {}
    for t in json.loads(corpus_path.read_text())['tasks']:
        task = t['task']
        p = ROOT/f'data/coverage/solutions_subset_50/{task}/ground_truth/groups_{task}_n2.json'
        assert sha(p.read_bytes()) == t['source']['ground_truth_sha256']
        labels[task] = {}
        for g in json.loads(p.read_text()):
            for name, value in zip(g['paths'], g['scores']):
                if math.isfinite(value):
                    oriented = -value if g['is_lower_better'] else value
                    key = Path(name).name
                    assert key not in labels[task] or labels[task][key] == oriented
                    labels[task][key] = oriented
    return labels


def main():
    if not __debug__:
        raise RuntimeError('Research checks require assertions enabled')
    registration_path = Path(__file__).resolve().parents[2]/'experiments/round-07/registration.json'
    if hashlib.sha256(registration_path.read_bytes()).hexdigest() != '0c11ff5229af73531ab8f1b9f574768f0fac9ce042f39fbfe509a392a75a483e':
        raise ValueError('Original round 07 registration mismatch')
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--r6-archive', type=Path, required=True)
    p.add_argument('--output', type=Path, default=ROOT/'runs/round07')
    args = p.parse_args(); started = time.monotonic()
    config = json.loads((E/'protocol.json').read_text())
    registration = json.loads((E/'registration.json').read_text())
    for name, value in registration['files'].items():
        assert sha((E/name).read_bytes()) == value
    protocol_commit = subprocess.check_output(['git', 'log', '-1', '--format=%H', '--',
                         'experiments/round-07/registration.json'], cwd=ROOT, text=True).strip()
    subprocess.run(['git', 'merge-base', '--is-ancestor', protocol_commit, 'HEAD'], cwd=ROOT, check=True)
    assert not subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT, text=True)
    for name, value in registration['files'].items():
        assert sha(subprocess.check_output(['git', 'show', protocol_commit+':experiments/round-07/'+name], cwd=ROOT)) == value
    assert sha(args.r6_archive.read_bytes()) == config['input_archive']['sha256']
    assert args.r6_archive.stat().st_size == config['input_archive']['bytes']
    r6_jobs_path = ROOT/'experiments/round-06/jobs.jsonl'
    assert sha(r6_jobs_path.read_bytes()) == config['r6_jobs_sha256']
    jobs = [json.loads(s) for s in (E/'jobs.jsonl').read_text().splitlines()]
    r6_jobs = [json.loads(s) for s in r6_jobs_path.read_text().splitlines()]
    for a, b in zip(jobs, r6_jobs, strict=True):
        assert {k: v for k, v in a.items() if k != 'methods'} == {k: v for k, v in b.items() if k != 'methods'}
    labels = load_labels(); task_order = list(labels)
    out = args.output.resolve(); assert not out.exists(), 'Preserve existing output first'
    out.mkdir(parents=True)
    provenance = dict(protocol_commit=protocol_commit,
                      implementation_commit=subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
                      started_at_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                      python=platform.python_version(), platform=platform.platform(),
                      registration=registration['files'], input_archive_sha256=config['input_archive']['sha256'])
    dump(out/'started.json', provenance)
    accum = {t: {'control': [], 'treatment': [], 'changed': 0} for t in task_order}
    totals = dict(shared_unique_feedback=0, valid_unique_feedback=0, new_feedback_queries=0,
                  actual_api_calls=0, candidate_training_runs=0,
                  historical_tournament_comparison_records=0, historical_cache_reads=0)
    diagnostics = dict(selected_set_changed=0, control_tie_jobs=0, treatment_tie_jobs=0,
                       removed_candidates=0, all_uninformative_jobs=0,
                       job_regret_improved=0, job_regret_tied=0, job_regret_worsened=0,
                       job_hit_improved=0, job_hit_tied=0, job_hit_worsened=0)
    union = set(); prefix = config['input_archive']['prefix']
    with zipfile.ZipFile(args.r6_archive) as archive:
        for name, expected in config['input_content_hashes'].items():
            with archive.open(prefix+'/'+name) as raw:
                if name.endswith('.gz'):
                    with gzip.GzipFile(fileobj=raw) as stream:
                        value = stream_sha(stream)
                else:
                    value = stream_sha(raw)
            assert value == expected, name
        source_summary = json.loads(archive.read(prefix+'/summary.json'))
        assert json.loads(archive.read(prefix+'/verification.json'))['status'] == 'passed'
        with gzip.open(archive.open(prefix+'/runs.jsonl.gz'), 'rt') as source, \
             (out/'runs.jsonl.gz').open('wb') as raw_out, \
             gzip.GzipFile(filename='', fileobj=raw_out, mode='wb', mtime=0) as gz_out, \
             io.TextIOWrapper(gz_out, encoding='utf-8') as output:
            count = 0
            for job, line in zip(jobs, source, strict=True):
                assert time.monotonic()-started < config['budget']['max_wall_seconds_per_attempt']
                r = json.loads(line); ids = r['candidates']; task = job['task']
                assert all(r[k] == job[k] for k in ['job_id', 'task', 'pool_id', 'repeat', 'seed'])
                assert sha(json.dumps(ids, separators=(',', ':')).encode()) == job['candidate_order_sha256']
                feedback = unique_feedback(ids, r['feedback'])
                assert feedback == r['feedback'] and len(feedback) == job['shared_unique_feedback_budget']
                ctop, cstats, graph = win_rate_select(ids, feedback)
                assert ctop == r['treatment_top'] and cstats == r['treatment_statistics'] and graph == r['graph']
                ttop, tstats, _ = evidence_tiebreak_select(ids, feedback)
                assert tstats == cstats and set(ttop) <= set(ctop) and ttop
                assert len({cstats[x]['wins']+cstats[x]['losses'] for x in ttop}) == 1
                # Labels enter only after both policies produce their selection groups.
                cm = score_selection(ids, ctop, labels[task]); tm = score_selection(ids, ttop, labels[task])
                for m in METRICS:
                    assert math.isclose(cm[m], r['treatment_metrics'][m], abs_tol=1e-12), m
                budget = dict(shared_unique_feedback=len(feedback), valid_unique_feedback=graph['valid_unique_edges'],
                              new_feedback_queries=0, actual_api_calls=0,
                              historical_tournament_comparison_records=r['budget']['comparison_records'],
                              historical_cache_reads=r['budget']['cache_reads'])
                output.write(json.dumps(dict(job_id=job['job_id'], task=task, pool_id=job['pool_id'], repeat=job['repeat'],
                            seed=job['seed'], candidates=ids, feedback=feedback, statistics=cstats,
                            control_top=ctop, treatment_top=ttop, control_metrics=cm, treatment_metrics=tm,
                            budget=budget), separators=(',', ':'))+'\n')
                accum[task]['control'].append(cm); accum[task]['treatment'].append(tm)
                changed = set(ctop) != set(ttop); accum[task]['changed'] += changed
                diagnostics['selected_set_changed'] += changed
                diagnostics['control_tie_jobs'] += len(ctop) > 1
                diagnostics['treatment_tie_jobs'] += len(ttop) > 1
                diagnostics['removed_candidates'] += len(ctop)-len(ttop)
                diagnostics['all_uninformative_jobs'] += graph['all_uninformative']
                for label, metric in [('regret', 'normalized_regret'), ('hit', 'uniform_tie_best_hit')]:
                    delta = tm[metric]-cm[metric]
                    result = 'tied' if abs(delta) <= 1e-12 else 'improved' if (delta < 0 if label == 'regret' else delta > 0) else 'worsened'
                    diagnostics['job_'+label+'_'+result] += 1
                for k, value in budget.items():
                    totals[k] += value
                union.update((task, e['a'], e['b']) for e in feedback)
                count += 1
                if count % 300 == 0:
                    print('Completed', task, '300 paired jobs', flush=True)
    assert count == config['budget']['jobs'] == 7800
    assert totals['shared_unique_feedback'] == config['budget']['shared_unique_feedback_total']
    assert totals['valid_unique_feedback'] == config['budget']['valid_unique_feedback_total']
    assert len(union) == config['budget']['distinct_feedback_across_experiment']
    totals['distinct_feedback_across_experiment'] = len(union)
    tasks = []
    for task in task_order:
        a = accum[task]
        c = {m: statistics.mean(r[m] for r in a['control']) for m in METRICS}
        t = {m: statistics.mean(r[m] for r in a['treatment']) for m in METRICS}
        expected = next(x for x in source_summary['per_task'] if x['task'] == task)['treatment']
        for m in METRICS:
            assert math.isclose(c[m], expected[m], abs_tol=1e-12)
        tasks.append(dict(task=task, jobs=len(a['control']), control=c, treatment=t,
                          delta={m: t[m]-c[m] for m in METRICS}, selected_set_changed=a['changed']))
    macro = {kind: {m: statistics.mean(t[kind][m] for t in tasks) for m in METRICS} for kind in ['control', 'treatment']}
    for m in METRICS:
        assert math.isclose(macro['control'][m], source_summary['macro']['treatment'][m], abs_tol=1e-12)
    delta = {m: macro['treatment'][m]-macro['control'][m] for m in METRICS}
    criteria = config['practical_advancement_rule']
    summary = dict(experiment_id='round-07', provenance=provenance, tasks=len(tasks), paired_jobs=count,
                   selection_evaluations=2*count, macro=macro, delta=delta,
                   paired_task_bootstrap_95={m: bootstrap([t['delta'][m] for t in tasks], config['bootstrap']) for m in METRICS},
                   regret_prediction_supported=delta['normalized_regret'] < 0,
                   hit_constraint_supported=delta['uniform_tie_best_hit'] >= 0,
                   practical_threshold_met=macro['treatment']['normalized_regret'] <= criteria['regret_at_most_frozen_tournament']
                     and macro['treatment']['uniform_tie_best_hit'] >= criteria['hit_at_least_r6'],
                   budget=totals, diagnostics=diagnostics, per_task=tasks,
                   frozen_tournament_reference=source_summary['macro']['control'], scope=config['scope'])
    for label, metric, sign in [('regret', 'normalized_regret', -1), ('hit', 'uniform_tie_best_hit', 1)]:
        summary['task_'+label+'_improved'] = sum(t['delta'][metric]*sign > 1e-12 for t in tasks)
        summary['task_'+label+'_tied'] = sum(abs(t['delta'][metric]) <= 1e-12 for t in tasks)
        summary['task_'+label+'_worsened'] = sum(t['delta'][metric]*sign < -1e-12 for t in tasks)
    with gzip.open(out/'runs.jsonl.gz', 'rb') as f:
        summary['runs_content_sha256'] = stream_sha(f)
    summary['runs_gzip_sha256'] = sha((out/'runs.jsonl.gz').read_bytes())
    assert time.monotonic()-started < config['budget']['max_wall_seconds_per_attempt']
    dump(out/'summary.json', summary)
    with (out/'per_task.csv').open('w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=['task', 'jobs', 'r6_regret', 'r7_regret', 'regret_delta',
                                               'r6_hit', 'r7_hit', 'hit_delta_pp', 'changed'], lineterminator='\n')
        writer.writeheader()
        for t in tasks:
            writer.writerow(dict(task=t['task'], jobs=t['jobs'], r6_regret=t['control']['normalized_regret'],
              r7_regret=t['treatment']['normalized_regret'], regret_delta=t['delta']['normalized_regret'],
              r6_hit=t['control']['uniform_tie_best_hit'], r7_hit=t['treatment']['uniform_tie_best_hit'],
              hit_delta_pp=100*t['delta']['uniform_tie_best_hit'], changed=t['selected_set_changed']))
    dump(out/'execution.json', dict(wall_seconds=time.monotonic()-started,
                                   completed_at_utc=datetime.datetime.now(datetime.timezone.utc).isoformat()))
    print(json.dumps({k: summary[k] for k in ['macro', 'delta', 'regret_prediction_supported',
                  'hit_constraint_supported', 'practical_threshold_met', 'diagnostics', 'budget']}), flush=True)


if __name__ == '__main__':
    main()
