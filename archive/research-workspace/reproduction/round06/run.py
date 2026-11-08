"""Execute preregistered R6 reaggregation using a checksum-pinned control archive."""
import argparse
import csv
import datetime
import gzip
import hashlib
import io
import json
import math
from pathlib import Path
import platform
import random
import statistics
import subprocess
import sys
import time
import zipfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from reproduction.round06.methods import unique_feedback, win_rate_select

EXPERIMENT = ROOT/'experiments/round-06'
METRICS = ['uniform_tie_best_hit', 'normalized_regret', 'selected_percentile',
           'top_group_size', 'contains_best']


def sha(data):
    return hashlib.sha256(data).hexdigest()


def stream_sha(stream):
    digest = hashlib.sha256()
    while chunk := stream.read(1024*1024):
        digest.update(chunk)
    return digest.hexdigest()


def dump(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2)+'\n')


def score_selection(candidates, selected, utility):
    assert selected and len(set(selected)) == len(selected) and set(selected) <= set(candidates)
    values = [utility[x] for x in candidates]
    best, worst = max(values), min(values)
    k, n = len(selected), len(candidates)
    return dict(uniform_tie_best_hit=sum(utility[x] == best for x in selected)/k,
                normalized_regret=(best-statistics.mean(utility[x] for x in selected))/(best-worst)
                if best > worst else 0.,
                selected_percentile=statistics.mean(
                    (sum(v < utility[x] for v in values)+.5*(sum(v == utility[x] for v in values)-1))/(n-1)
                    for x in selected),
                top_group_size=k, contains_best=float(any(utility[x] == best for x in selected)))


def load_task(task, expected):
    ground = ROOT/f'data/coverage/solutions_subset_50/{task}/ground_truth/groups_{task}_n2.json'
    author = ROOT/f'data/author_reference/{task}.json'
    assert sha(ground.read_bytes()) == expected['ground_truth_sha256']
    assert sha(author.read_bytes()) == expected['author_sha256']
    groups = json.loads(ground.read_text())
    utility = {}
    all_names = set()
    for g in groups:
        for path, value in zip(g['paths'], g['scores']):
            name = Path(path).name
            all_names.add(name)
            if math.isfinite(value):
                oriented = -value if g['is_lower_better'] else value
                assert name not in utility or utility[name] == oriented
                utility[name] = oriented
    suffixes = {name[-7:]: name for name in all_names}
    assert len(suffixes) == len(all_names)
    feedback = {}
    for row in json.loads(author.read_text())['results']:
        a, b = [suffixes[x['path']] for x in row['solutions']]
        pred = row['prediction']; confidence = pred.get('confidence')
        try:
            confidence = float(confidence)
            assert 0 <= confidence <= 1
        except (TypeError, ValueError):
            confidence = .5
        key = tuple(sorted((a, b)))
        assert key not in feedback
        index = pred["best_index"]
        assert type(index) in (int, float) and index in (0, 1), (task, "invalid winner", index)
        feedback[key] = dict(winner=(a, b)[int(index)], confidence=confidence)
    return utility, feedback


def quantile(values, p):
    pos = (len(values)-1)*p
    low, high = math.floor(pos), math.ceil(pos)
    return values[low]+(values[high]-values[low])*(pos-low)


def bootstrap(task_deltas, settings):
    rng = random.Random(settings['seed']); samples = []
    for _ in range(settings['replicates']):
        samples.append(statistics.mean(rng.choice(task_deltas) for _ in task_deltas))
    samples.sort()
    return dict(low=quantile(samples, .025), high=quantile(samples, .975),
                unit='task', paired=True, replicates=settings['replicates'], seed=settings['seed'])


def check_archive(archive, config):
    with archive.open('tournament-full-execution-v2/protocol.json') as f:
        assert stream_sha(f) == config['corpus_protocol_sha256']
    prefix = config['input_archive']['prefix']
    for name, expected in config['control_content_hashes'].items():
        with archive.open(prefix+'/'+name) as raw:
            if name.endswith('.gz'):
                with gzip.GzipFile(fileobj=raw) as content:
                    actual = stream_sha(content)
            else:
                actual = stream_sha(raw)
        assert actual == expected, name


def main():
    if not __debug__:
        raise RuntimeError('Research checks require assertions enabled')
    registration_path = Path(__file__).resolve().parents[2]/'experiments/round-06/registration.json'
    if hashlib.sha256(registration_path.read_bytes()).hexdigest() != 'f636f256fff40784193d5f08f68ce82de6c3e8afb82385d194ee0e12fa9fe2d6':
        raise ValueError('Original round 06 registration mismatch')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--control-archive', required=True, type=Path)
    parser.add_argument('--output', type=Path, default=ROOT/'runs/round06')
    args = parser.parse_args(); started = time.monotonic()
    config = json.loads((EXPERIMENT/'protocol.json').read_text())
    registration = json.loads((EXPERIMENT/'registration.json').read_text())
    for name, expected in registration['files'].items():
        assert sha((EXPERIMENT/name).read_bytes()) == expected, name
    protocol_commit = subprocess.check_output(
        ['git', 'log', '-1', '--format=%H', '--', 'experiments/round-06/registration.json'], cwd=ROOT, text=True).strip()
    subprocess.run(['git', 'merge-base', '--is-ancestor', protocol_commit, 'HEAD'], cwd=ROOT, check=True)
    assert not subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT, text=True), 'Commit implementation before comparison'
    for name, expected in registration['files'].items():
        assert sha(subprocess.check_output(['git', 'show', protocol_commit+':experiments/round-06/'+name], cwd=ROOT)) == expected
    with args.control_archive.open('rb') as f:
        assert stream_sha(f) == config['input_archive']['sha256']
    jobs = [json.loads(s) for s in (EXPERIMENT/'jobs.jsonl').read_text().splitlines()]
    corpus = json.loads((ROOT/'experiments/corpus26-v2/protocol.json').read_text())
    assert sha((ROOT/'experiments/corpus26-v2/protocol.json').read_bytes()) == config['corpus_protocol_sha256']
    utilities = {}; recorded = {}; task_order = []
    pools = {}
    for task in corpus['tasks']:
        name = task['task']; task_order.append(name)
        utilities[name], recorded[name] = load_task(name, task['source'])
        for pool in task['pools']:
            for repeat, seed in enumerate(pool['replay_seeds']):
                pools[name, pool['pool_id'], repeat] = (pool['candidate_order'], seed)
    out = args.output.resolve()
    assert not out.exists(), 'Preserve existing output before another attempt'
    out.mkdir(parents=True)
    provenance = dict(experiment=config['experiment_id'], protocol_commit=protocol_commit,
                      implementation_commit=subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
                      started_at_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                      python=platform.python_version(), platform=platform.platform(),
                      registration=registration['files'], control_archive_sha256=config['input_archive']['sha256'],
                      actual_api_calls=0, candidate_training_runs=0)
    dump(out/'started.json', provenance)
    accum = {name: {'control': [], 'treatment': [], 'graphs': [], 'changed': 0} for name in task_order}
    totals = dict(comparison_records=0, cache_reads=0, shared_unique_feedback=0,
                  valid_unique_feedback=0, new_feedback_queries=0, actual_api_calls=0,
                  candidate_training_runs=0, selected_set_changed=0)
    union = set(); prefix = config['input_archive']['prefix']
    with zipfile.ZipFile(args.control_archive) as archive:
        check_archive(archive, config)
        control_summary = json.loads(archive.read(prefix+'/results.json'))
        with io.TextIOWrapper(archive.open(prefix+'/runs.jsonl')) as control_stream, \
             gzip.open(archive.open(prefix+'/traces.jsonl.gz'), 'rt') as trace_stream, \
             (out/'runs.jsonl.gz').open('wb') as raw_output, \
             gzip.GzipFile(filename='', fileobj=raw_output, mode='wb', mtime=0) as gz_output, \
             io.TextIOWrapper(gz_output, encoding='utf-8') as output:
            count = 0
            for job, control_line, trace_line in zip(jobs, control_stream, trace_stream, strict=True):
                assert time.monotonic()-started < config['budget']['max_wall_seconds_per_attempt']
                c, t = json.loads(control_line), json.loads(trace_line)
                key = (job['task'], job['pool_id'], job['repeat']); order, seed = pools[key]
                assert key == (c['task'], c['pool_id'], c['repeat']) == (t['task'], t['pool_id'], t['repeat'])
                assert c['candidate_order'] == order and c['seed'] == job['seed'] == seed
                assert sha(json.dumps(order, separators=(',', ':')).encode()) == job['candidate_order_sha256']
                assert not any(e['cache_direction_mismatch'] for e in t['comparisons'])
                feedback = unique_feedback(order, t['comparisons'])
                assert len(feedback) == job['shared_unique_feedback_budget'] == c['metrics']['unique_feedback_queries']
                for e in feedback:
                    pair = (e['a'], e['b']); saved = recorded[job['task']][pair]
                    assert e['confidence'] == saved['confidence']
                    assert e['winner'] == (saved['winner'] if e['valid'] else None)
                    union.add((job['task'], *pair))
                # The treatment receives exactly these IDs and queried responses, without labels or control ranks.
                top, stats, graph = win_rate_select(order, feedback)
                baseline_top = c['top_group']
                assert set(baseline_top) == {x for x, meta in c['rank_meta'].items() if meta['rank'] == 0}
                cm = score_selection(order, baseline_top, utilities[job['task']])
                tm = score_selection(order, top, utilities[job['task']])
                for metric in METRICS:
                    assert math.isclose(cm[metric], c['metrics'][metric], abs_tol=1e-12), metric
                budget = dict(shared_unique_feedback=len(feedback), comparison_records=len(t['comparisons']),
                              cache_reads=len(t['comparisons'])-len(feedback), new_feedback_queries=0, actual_api_calls=0)
                assert budget['cache_reads'] == c['metrics']['cache_hits']
                changed = set(top) != set(baseline_top)
                row = dict(job_id=job['job_id'], task=job['task'], pool_id=job['pool_id'], repeat=job['repeat'],
                           seed=seed, candidates=order, feedback=feedback, control_top=baseline_top,
                           treatment_top=top, treatment_statistics=stats, graph=graph,
                           control_metrics=cm, treatment_metrics=tm, budget=budget)
                output.write(json.dumps(row, separators=(',', ':'))+'\n')
                a = accum[job['task']]
                a['control'].append(cm); a['treatment'].append(tm); a['graphs'].append(graph); a['changed'] += changed
                totals['comparison_records'] += budget['comparison_records']
                totals['cache_reads'] += budget['cache_reads']
                totals['shared_unique_feedback'] += len(feedback)
                totals['valid_unique_feedback'] += graph['valid_unique_edges']
                totals['selected_set_changed'] += changed
                count += 1
                if count % 300 == 0:
                    print('Completed', job['task'], len(a['control']), 'paired jobs', flush=True)
    assert count == len(jobs) == config['budget']['jobs']
    assert totals['shared_unique_feedback'] == config['budget']['shared_unique_feedback_total']
    assert totals['comparison_records'] == 614747 and totals['cache_reads'] == 512274
    assert len(union) == 13592
    per_task = []
    for task in task_order:
        a = accum[task]
        c = {m: statistics.mean(r[m] for r in a['control']) for m in METRICS}
        t = {m: statistics.mean(r[m] for r in a['treatment']) for m in METRICS}
        frozen = next(x['mean'] for x in control_summary['per_task'] if x['task'] == task)
        for m in METRICS:
            assert math.isclose(c[m], frozen[m], abs_tol=1e-12), (task, m)
        per_task.append(dict(task=task, jobs=len(a['control']), control=c, treatment=t,
                             delta={m: t[m]-c[m] for m in METRICS},
                             graph_mean={m: statistics.mean(g[m] for g in a['graphs']) for m in a['graphs'][0]},
                             selected_set_changed=a['changed']))
    macro = {kind: {m: statistics.mean(t[kind][m] for t in per_task) for m in METRICS}
             for kind in ['control', 'treatment']}
    delta = {m: macro['treatment'][m]-macro['control'][m] for m in METRICS}
    intervals = {m: bootstrap([t['delta'][m] for t in per_task], config['bootstrap']) for m in METRICS}
    totals['distinct_feedback_across_experiment'] = len(union)
    summary = dict(experiment_id=config['experiment_id'], provenance=provenance,
                   tasks=len(task_order), paired_jobs=count, selection_evaluations=2*count,
                   macro=macro, delta=delta, paired_task_bootstrap_95=intervals,
                   task_primary_improved=sum(t['delta'][METRICS[0]] > 1e-12 for t in per_task),
                   task_primary_tied=sum(abs(t['delta'][METRICS[0]]) <= 1e-12 for t in per_task),
                   task_primary_declined=sum(t['delta'][METRICS[0]] < -1e-12 for t in per_task),
                   direction_prediction_supported=delta[METRICS[0]] > 0,
                   practical_threshold_met=delta[METRICS[0]] >= .01 and delta['normalized_regret'] <= 0,
                   budget=totals,
                   diagnostics={m: statistics.mean(g[m] for a in accum.values() for g in a['graphs'])
                                for m in next(iter(accum.values()))['graphs'][0]},
                   per_task=per_task, scope=config['scope'])
    with gzip.open(out/'runs.jsonl.gz', 'rb') as f:
        summary['runs_content_sha256'] = stream_sha(f)
    summary['runs_gzip_sha256'] = sha((out/'runs.jsonl.gz').read_bytes())
    assert time.monotonic()-started < config['budget']['max_wall_seconds_per_attempt']
    dump(out/'summary.json', summary)
    with (out/'per_task.csv').open('w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=['task', 'jobs', 'control_hit', 'winrate_hit', 'delta_pp',
                                               'control_regret', 'winrate_regret', 'changed'])
        writer.writeheader()
        for t in per_task:
            writer.writerow(dict(task=t['task'], jobs=t['jobs'], control_hit=t['control'][METRICS[0]],
                                 winrate_hit=t['treatment'][METRICS[0]], delta_pp=100*t['delta'][METRICS[0]],
                                 control_regret=t['control']['normalized_regret'],
                                 winrate_regret=t['treatment']['normalized_regret'], changed=t['selected_set_changed']))
    dump(out/'execution.json', dict(wall_seconds=time.monotonic()-started,
                                    completed_at_utc=datetime.datetime.now(datetime.timezone.utc).isoformat()))
    print(json.dumps({k: summary[k] for k in ['macro', 'delta', 'direction_prediction_supported',
                                              'practical_threshold_met', 'budget']}), flush=True)


if __name__ == '__main__':
    main()
