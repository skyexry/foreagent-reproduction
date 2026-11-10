"""Independent cross-multiplication audit of R7 votes, tie-break and scores."""
import argparse
import gzip
import hashlib
import json
import math
from pathlib import Path
import random
import zipfile

ROOT = Path(__file__).resolve().parents[2]
E = ROOT/'experiments/round-07'
METRICS = ['uniform_tie_best_hit', 'normalized_regret', 'selected_percentile', 'top_group_size', 'contains_best']


def close(a, b):
    assert math.isclose(a, b, abs_tol=1e-10), (a, b)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--r6-archive', type=Path, required=True)
    parser.add_argument('--output', type=Path, default=ROOT/'runs/round07')
    args = parser.parse_args(); out = args.output
    p = json.loads((E/'protocol.json').read_text())
    reg = json.loads((E/'registration.json').read_text())
    for name, value in reg['files'].items():
        assert hashlib.sha256((E/name).read_bytes()).hexdigest() == value
    assert hashlib.sha256(args.r6_archive.read_bytes()).hexdigest() == p['input_archive']['sha256']
    jobs = [json.loads(s) for s in (E/'jobs.jsonl').read_text().splitlines()]
    s = json.loads((out/'summary.json').read_text()); corpus = json.loads((ROOT/'experiments/corpus26-v2/protocol.json').read_text())
    labels = {}; accum = {}; changed = {}
    for t in corpus['tasks']:
        task = t['task']; path = ROOT/f'data/coverage/solutions_subset_50/{task}/ground_truth/groups_{task}_n2.json'
        assert hashlib.sha256(path.read_bytes()).hexdigest() == t['source']['ground_truth_sha256']
        labels[task] = {Path(name).name: (-value if g['is_lower_better'] else value)
                       for g in json.loads(path.read_text()) for name, value in zip(g['paths'], g['scores']) if math.isfinite(value)}
        accum[task] = {'control': [], 'treatment': []}; changed[task] = 0
    totals = dict(shared_unique_feedback=0, valid_unique_feedback=0, new_feedback_queries=0, actual_api_calls=0,
                  candidate_training_runs=0, historical_tournament_comparison_records=0, historical_cache_reads=0)
    diagnostics = dict.fromkeys(s['diagnostics'], 0); union = set(); count = 0
    with zipfile.ZipFile(args.r6_archive) as z, gzip.open(z.open(p['input_archive']['prefix']+'/runs.jsonl.gz'), 'rt') as old_rows, \
         gzip.open(out/'runs.jsonl.gz', 'rt') as new_rows:
        for job, old_line, new_line in zip(jobs, old_rows, new_rows, strict=True):
            old, r = json.loads(old_line), json.loads(new_line); task = job['task']; ids = r['candidates']
            assert all(r[k] == old[k] == job[k] for k in ['job_id', 'task', 'pool_id', 'repeat', 'seed'])
            assert ids == old['candidates'] and r['feedback'] == old['feedback']
            wins = dict.fromkeys(ids, 0); losses = dict.fromkeys(ids, 0); seen = set()
            for edge in r['feedback']:
                pair = (edge['a'], edge['b']); assert pair not in seen; seen.add(pair); union.add((task, *pair))
                assert edge['valid'] == (edge['confidence'] >= .7)
                if edge['valid']:
                    assert edge['winner'] in pair
                    wins[edge['winner']] += 1
                    losses[next(x for x in pair if x != edge['winner'])] += 1
                else:
                    assert edge['winner'] is None
            degrees = {x: wins[x]+losses[x] for x in ids}
            ratios = {x: (wins[x], degrees[x]) if degrees[x] else (1, 2) for x in ids}
            control = [x for x in ids if all(ratios[x][0]*ratios[y][1] >= ratios[y][0]*ratios[x][1] for y in ids)]
            maximum_degree = max(degrees[x] for x in control)
            treatment = [x for x in control if degrees[x] == maximum_degree]
            assert control == old['treatment_top'] == r['control_top'] and treatment == r['treatment_top']
            assert r['statistics'] == old['treatment_statistics']
            for x in ids:
                st = r['statistics'][x]
                assert st['wins'] == wins[x] and st['losses'] == losses[x]
                assert st['numerator']*ratios[x][1] == ratios[x][0]*st['denominator']
            u = labels[task]; best, worst = max(u[x] for x in ids), min(u[x] for x in ids)
            computed = {}
            for kind, top in [('control', control), ('treatment', treatment)]:
                k = len(top)
                values = dict(uniform_tie_best_hit=sum(u[x] == best for x in top)/k,
                              normalized_regret=(best-sum(u[x] for x in top)/k)/(best-worst) if best != worst else 0.,
                              selected_percentile=sum((sum(u[y] < u[x] for y in ids)+
                                (sum(u[y] == u[x] for y in ids)-1)/2)/(len(ids)-1) for x in top)/k,
                              top_group_size=k, contains_best=float(any(u[x] == best for x in top)))
                for m in METRICS:
                    close(values[m], r[kind+'_metrics'][m])
                accum[task][kind].append(values); computed[kind] = values
            budget = r['budget']; assert budget['shared_unique_feedback'] == len(seen) == job['shared_unique_feedback_budget']
            assert budget['valid_unique_feedback'] == sum(e['valid'] for e in r['feedback'])
            assert budget['historical_tournament_comparison_records'] == old['budget']['comparison_records']
            assert budget['historical_cache_reads'] == old['budget']['cache_reads']
            assert budget['new_feedback_queries'] == budget['actual_api_calls'] == 0
            for key, value in budget.items(): totals[key] += value
            different = set(control) != set(treatment); changed[task] += different
            diagnostics['selected_set_changed'] += different
            diagnostics['control_tie_jobs'] += len(control) > 1
            diagnostics['treatment_tie_jobs'] += len(treatment) > 1
            diagnostics['removed_candidates'] += len(control)-len(treatment)
            diagnostics['all_uninformative_jobs'] += not any(degrees.values())
            for label, metric, sign in [('regret', 'normalized_regret', -1), ('hit', 'uniform_tie_best_hit', 1)]:
                d = (computed['treatment'][metric]-computed['control'][metric])*sign
                kind = 'tied' if abs(d) <= 1e-12 else 'improved' if d > 0 else 'worsened'
                diagnostics['job_'+label+'_'+kind] += 1
            count += 1
    assert count == s['paired_jobs'] == p['budget']['jobs'] == 7800
    totals['distinct_feedback_across_experiment'] = len(union)
    assert totals == s['budget'] and diagnostics == s['diagnostics']
    assert totals['shared_unique_feedback'] == 102473 and totals['valid_unique_feedback'] == 51593 and len(union) == 13592
    means = {}; task_deltas = {m: [] for m in METRICS}
    for task, a in accum.items():
        saved = next(t for t in s['per_task'] if t['task'] == task)
        assert saved['jobs'] == len(a['control']) == 300 and saved['selected_set_changed'] == changed[task]
        means[task] = {kind: {m: sum(row[m] for row in a[kind])/300 for m in METRICS} for kind in a}
        for kind in a:
            for m in METRICS: close(means[task][kind][m], saved[kind][m])
        for m in METRICS:
            d = means[task]['treatment'][m]-means[task]['control'][m]
            close(d, saved['delta'][m]); task_deltas[m].append(d)
    for kind in ['control', 'treatment']:
        for m in METRICS: close(sum(t[kind][m] for t in means.values())/26, s['macro'][kind][m])
    rng = random.Random(p['bootstrap']['seed'])
    indices = [[rng.choice(range(26)) for _ in range(26)] for _ in range(p['bootstrap']['replicates'])]
    for m, values in task_deltas.items():
        close(sum(values)/26, s['delta'][m])
        samples = sorted(sum(values[i] for i in sample)/26 for sample in indices)
        for label, probability in [('low', .025), ('high', .975)]:
            pos = (len(samples)-1)*probability; a, b = math.floor(pos), math.ceil(pos)
            value = samples[a]+(samples[b]-samples[a])*(pos-a)
            close(value, s['paired_task_bootstrap_95'][m][label])
    assert s['regret_prediction_supported'] == (s['delta']['normalized_regret'] < 0)
    assert s['hit_constraint_supported'] == (s['delta']['uniform_tie_best_hit'] >= 0)
    criteria = p['practical_advancement_rule']; t = s['macro']['treatment']
    assert s['practical_threshold_met'] == (t['normalized_regret'] <= criteria['regret_at_most_frozen_tournament'] and
                                          t['uniform_tie_best_hit'] >= criteria['hit_at_least_r6'])
    with gzip.open(out/'runs.jsonl.gz', 'rb') as f: content_hash = hashlib.sha256(f.read()).hexdigest()
    assert content_hash == s['runs_content_sha256']
    assert hashlib.sha256((out/'runs.jsonl.gz').read_bytes()).hexdigest() == s['runs_gzip_sha256']
    result = dict(status='passed', paired_jobs=count, independent_vote_rate_and_support_checks=count,
                  independent_selection_scores=2*count, task_means_checked=26, bootstrap_checked=True,
                  registered_protocol_and_jobs_unchanged=True, r6_feedback_counts_and_winners_unchanged=True,
                  treatment_is_subset_of_r6_top_group=True, new_feedback_queries=0, actual_api_calls=0,
                  candidate_training_runs=0, protocol_commit=s['provenance']['protocol_commit'],
                  implementation_commit=s['provenance']['implementation_commit'], runs_content_sha256=content_hash)
    (out/'verification.json').write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
