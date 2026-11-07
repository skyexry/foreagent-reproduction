"""Independent R6 check: reconstruct votes, scores and paired summaries."""
import argparse
import gzip
import hashlib
import io
import json
import math
from pathlib import Path
import random
import zipfile

ROOT = Path(__file__).resolve().parents[2]
E = ROOT/'experiments/round-06'
METRICS = ['uniform_tie_best_hit', 'normalized_regret', 'selected_percentile',
           'top_group_size', 'contains_best']


def close(a, b):
    assert math.isclose(a, b, abs_tol=1e-10), (a, b)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--control-archive', type=Path, required=True)
    p.add_argument('--output', type=Path, default=ROOT/'runs/round06')
    args = p.parse_args(); out = args.output
    protocol = json.loads((E/'protocol.json').read_text())
    registration = json.loads((E/'registration.json').read_text())
    for name, expected in registration['files'].items():
        assert hashlib.sha256((E/name).read_bytes()).hexdigest() == expected
    assert hashlib.sha256(args.control_archive.read_bytes()).hexdigest() == protocol['input_archive']['sha256']
    jobs = [json.loads(s) for s in (E/'jobs.jsonl').read_text().splitlines()]
    summary = json.loads((out/'summary.json').read_text())
    corpus = json.loads((ROOT/'experiments/corpus26-v2/protocol.json').read_text())
    labels = {}; accum = {}; graph_accum = {}; changed = {}; all_feedback = set()
    for t in corpus['tasks']:
        task = t['task']
        path = ROOT/f'data/coverage/solutions_subset_50/{task}/ground_truth/groups_{task}_n2.json'
        assert hashlib.sha256(path.read_bytes()).hexdigest() == t['source']['ground_truth_sha256']
        labels[task] = {}
        for g in json.loads(path.read_text()):
            for name, score in zip(g['paths'], g['scores']):
                if math.isfinite(score):
                    labels[task][Path(name).name] = -score if g['is_lower_better'] else score
        accum[task] = {'control': [], 'treatment': []}; graph_accum[task] = []; changed[task] = 0
    totals = dict(comparison_records=0, cache_reads=0, shared_unique_feedback=0, valid_unique_feedback=0,
                  new_feedback_queries=0, actual_api_calls=0, candidate_training_runs=0, selected_set_changed=0)
    prefix = protocol['input_archive']['prefix']; count = 0
    with zipfile.ZipFile(args.control_archive) as z, gzip.open(out/'runs.jsonl.gz', 'rt') as rows, \
         io.TextIOWrapper(z.open(prefix+'/runs.jsonl')) as controls, \
         gzip.open(z.open(prefix+'/traces.jsonl.gz'), 'rt') as traces:
        for job, line, control_line, trace_line in zip(jobs, rows, controls, traces, strict=True):
            r, c, t = json.loads(line), json.loads(control_line), json.loads(trace_line)
            task = job['task']; ids = r['candidates']
            assert all(r[k] == job[k] for k in ['job_id', 'task', 'pool_id', 'repeat', 'seed'])
            assert ids == c['candidate_order'] and r['control_top'] == c['top_group']
            expected = {}
            for raw in t['comparisons']:
                a, b = sorted((raw['a'], raw['b']))
                e = dict(a=a, b=b, winner=raw['winner'], confidence=raw['confidence'], valid=raw['valid'])
                key = (a, b)
                if key in expected:
                    assert expected[key] == e
                else:
                    expected[key] = e
            assert r['feedback'] == list(expected.values())
            assert len(expected) == job['shared_unique_feedback_budget']
            wins = dict.fromkeys(ids, 0); losses = dict.fromkeys(ids, 0); adjacency = {x: set() for x in ids}
            for e in r['feedback']:
                all_feedback.add((task, e['a'], e['b']))
                assert e['valid'] == (e['confidence'] >= .7)
                if e['valid']:
                    assert e['winner'] in (e['a'], e['b'])
                    loser = next(x for x in (e['a'], e['b']) if x != e['winner'])
                    wins[e['winner']] += 1; losses[loser] += 1
                    adjacency[e['a']].add(e['b']); adjacency[e['b']].add(e['a'])
                else:
                    assert e['winner'] is None
            ratios = {x: (wins[x], wins[x]+losses[x]) if wins[x]+losses[x] else (1, 2) for x in ids}
            selected = [x for x in ids if all(ratios[x][0]*ratios[y][1] >= ratios[y][0]*ratios[x][1] for y in ids)]
            assert selected == r['treatment_top']
            for x in ids:
                stats = r['treatment_statistics'][x]
                assert stats['wins'] == wins[x] and stats['losses'] == losses[x]
                assert stats['numerator']*ratios[x][1] == ratios[x][0]*stats['denominator']
            unvisited = set(ids); components = 0
            while unvisited:
                components += 1; frontier = {unvisited.pop()}
                while frontier:
                    group = {y for x in frontier for y in adjacency[x]} & unvisited
                    unvisited -= group; frontier = group
            graph = dict(unique_feedback=len(expected), valid_unique_edges=sum(e['valid'] for e in r['feedback']),
                         isolated_candidates=sum(not adjacency[x] for x in ids), components=components,
                         all_uninformative=not any(e['valid'] for e in r['feedback']),
                         selected_isolated=sum(not adjacency[x] for x in selected))
            assert graph == r['graph']; graph_accum[task].append(graph)
            u = labels[task]; best, worst = max(u[x] for x in ids), min(u[x] for x in ids)
            for kind in ['control', 'treatment']:
                top = r[kind+'_top']; k = len(top)
                exact = dict(uniform_tie_best_hit=sum(u[x] == best for x in top)/k,
                             normalized_regret=(best-sum(u[x] for x in top)/k)/(best-worst) if best != worst else 0.,
                             selected_percentile=sum((sum(u[y] < u[x] for y in ids)+
                                                      (sum(u[y] == u[x] for y in ids)-1)/2)/(len(ids)-1) for x in top)/k,
                             top_group_size=k, contains_best=float(any(u[x] == best for x in top)))
                for metric in METRICS:
                    close(exact[metric], r[kind+'_metrics'][metric])
                accum[task][kind].append(exact)
            change = set(r['control_top']) != set(selected); changed[task] += change
            budget = r['budget']
            assert budget['comparison_records'] == len(t['comparisons'])
            assert budget['cache_reads'] == len(t['comparisons'])-len(expected)
            assert budget['shared_unique_feedback'] == len(expected)
            assert budget['new_feedback_queries'] == budget['actual_api_calls'] == 0
            for field in ['comparison_records', 'cache_reads', 'shared_unique_feedback']:
                totals[field] += budget[field]
            totals['valid_unique_feedback'] += graph['valid_unique_edges']
            totals['selected_set_changed'] += change; count += 1
    assert count == summary['paired_jobs'] == 7800
    totals['distinct_feedback_across_experiment'] = len(all_feedback)
    assert totals == summary['budget']
    assert totals['shared_unique_feedback'] == 102473 and len(all_feedback) == 13592
    task_deltas = {m: [] for m in METRICS}; means = {'control': {}, 'treatment': {}}
    for task, data in accum.items():
        saved = next(t for t in summary['per_task'] if t['task'] == task)
        assert saved['jobs'] == len(data['control']) == 300 and saved['selected_set_changed'] == changed[task]
        for kind in ['control', 'treatment']:
            means[kind][task] = {m: sum(row[m] for row in data[kind])/len(data[kind]) for m in METRICS}
            for m in METRICS:
                close(means[kind][task][m], saved[kind][m])
        for m in METRICS:
            d = means['treatment'][task][m]-means['control'][task][m]
            close(d, saved['delta'][m]); task_deltas[m].append(d)
        for m in saved['graph_mean']:
            close(sum(g[m] for g in graph_accum[task])/300, saved['graph_mean'][m])
    for kind in means:
        for m in METRICS:
            close(sum(t[m] for t in means[kind].values())/26, summary['macro'][kind][m])
    rng = random.Random(protocol['bootstrap']['seed'])
    indices = [[rng.choice(range(26)) for _ in range(26)] for _ in range(protocol['bootstrap']['replicates'])]
    for m, values in task_deltas.items():
        close(sum(values)/26, summary['delta'][m])
        samples = sorted(sum(values[i] for i in index)/26 for index in indices)
        for label, prob in [('low', .025), ('high', .975)]:
            pos = (len(samples)-1)*prob; lo, hi = math.floor(pos), math.ceil(pos)
            value = samples[lo]*(hi-pos)+samples[hi]*(pos-lo) if hi != lo else samples[lo]
            close(value, summary['paired_task_bootstrap_95'][m][label])
    assert summary['direction_prediction_supported'] == (summary['delta'][METRICS[0]] > 0)
    assert summary['practical_threshold_met'] == (summary['delta'][METRICS[0]] >= .01 and summary['delta']['normalized_regret'] <= 0)
    with gzip.open(out/'runs.jsonl.gz', 'rb') as f:
        content_hash = hashlib.sha256(f.read()).hexdigest()
    assert content_hash == summary['runs_content_sha256']
    assert hashlib.sha256((out/'runs.jsonl.gz').read_bytes()).hexdigest() == summary['runs_gzip_sha256']
    record = dict(status='passed', paired_jobs=count, independent_vote_and_top_group_checks=count,
                  independent_candidate_selection_scores=2*count, task_means_checked=26,
                  bootstrap_checked=True, feedback_matches_pinned_control_trace=True,
                  registered_input_hashes_match=True, new_feedback_queries=0, actual_api_calls=0,
                  candidate_training_runs=0, runs_content_sha256=content_hash,
                  protocol_commit=summary['provenance']['protocol_commit'], implementation_commit=summary['provenance']['implementation_commit'])
    (out/'verification.json').write_text(json.dumps(record, indent=2)+'\n')
    print(json.dumps(record))


if __name__ == '__main__':
    main()
