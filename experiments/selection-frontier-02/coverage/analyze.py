"""Reproduce frontier-02 coverage attribution and paired official-run analysis.

Run from project root after official CLI run/evaluate. Every decision is already
sealed by the CLI before this script reads evaluation labels.
"""
from collections import Counter, defaultdict
from fractions import Fraction
import gzip
import hashlib
import itertools
import json
import math
from pathlib import Path
import random
import statistics
import sys
import argparse

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from reproduction.clean_ranking_v1.ranking import allocate, top_set
from reproduction.clean_ranking_v1.run import evaluate, percentile
from reproduction.research_env_v1.core import public_feedback

HERE = Path(__file__).resolve().parent
PROTOCOL_SHA = '797f6c92ed5f2b824526017734017175e9cc624613d423c84893b1aa7aed9e37'
SEED = 20261108093
RUN = ROOT / 'experiments/research-env-v1/runs/frontier02-valid-coverage-full-001'


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def dump(p, x):
    p.write_text(json.dumps(x, sort_keys=True, indent=2, allow_nan=False) + '\n')


def lines(p, rows):
    p.write_text(''.join(json.dumps(r, sort_keys=True, allow_nan=False) + '\n' for r in rows))


def load_gz(p):
    with gzip.open(p, 'rt') as f:
        return [json.loads(x) for x in f]


def inference(values):
    rng = random.Random(SEED)
    draws = [statistics.fmean(rng.choices(values, k=len(values))) for _ in range(10000)]
    return {'gain': statistics.fmean(values), 'task_cluster_percentile_95': [percentile(draws, .025), percentile(draws, .975)],
            'tasks_positive': sum(v > 1e-12 for v in values), 'tasks_zero': sum(abs(v) <= 1e-12 for v in values),
            'tasks_negative': sum(v < -1e-12 for v in values), 'bootstrap_seed': SEED, 'draws': 10000}


def degree_stats(ids, trace):
    q, d, w = dict.fromkeys(ids, 0), dict.fromkeys(ids, 0), dict.fromkeys(ids, 0)
    for r in trace:
        a, b, winner = r['a'], r['b'], r['winner']
        q[a] += 1
        q[b] += 1
        if winner is not None:
            d[a] += 1
            d[b] += 1
            w[winner] += 1
    return q, d, w


def best_diagnostic(job, trace, selected, utility):
    ids = job['ids']
    q, d, w = degree_stats(ids, trace)
    best_score = max(utility[i] for i in ids)
    best = [i for i in ids if utility[i] == best_score]
    ranks = {i: (Fraction(w[i], d[i]) if d[i] else Fraction(1, 2), d[i]) for i in ids}
    undefeated = [i for i in ids if d[i] > 0 and w[i] == d[i]]
    unobserved = [i for i in ids if d[i] == 0]
    false_undefeated = [i for i in undefeated if i not in best]
    directed = defaultdict(set)
    for r in trace:
        if r['winner'] is not None:
            loser = r['b'] if r['winner'] == r['a'] else r['a']
            if utility[r['winner']] > utility[loser]:
                directed[r['winner']].add(loser)
    def descendants(i):
        out, todo = set(), list(directed[i])
        while todo:
            j = todo.pop()
            if j not in out:
                out.add(j)
                todo.extend(directed[j])
        return sorted(out)
    nodes = []
    for i in ids:
        category = 'no_incident_query' if q[i] == 0 else 'all_incident_abstain' if d[i] == 0 else 'one_valid_edge' if d[i] == 1 else 'multiple_valid_edges'
        nodes.append({'id': i, 'utility': utility[i], 'actual_best': i in best, 'selected': i in selected,
                      'queried_degree': q[i], 'valid_degree': d[i], 'wins': w[i], 'win_fraction': float(ranks[i][0]),
                      'coverage_category': category, 'valid_undefeated': i in undefeated,
                      'correctly_ever_beaten_strict_competitors': sorted(directed[i]),
                      'correctly_ever_beaten_strict_count': len(directed[i]),
                      'strict_win_path_descendants': descendants(i)})
    hit = sum(i in best for i in selected) / len(selected)
    selection = 'best_only' if hit == 1 else 'partial_tie' if hit > 0 else 'miss'
    best_rank = max(ranks[i] for i in best)
    global_rank = max(ranks.values())
    if hit > 0:
        mechanism = 'best_retained'
    elif best_rank[0] == global_rank[0]:
        mechanism = 'degree_tiebreak_suppression'
    elif all(d[i] == 0 for i in best):
        mechanism = 'best_has_no_valid_evidence_win_fraction_suppression'
    else:
        mechanism = 'best_win_fraction_suppression'
    return {'actual_best_ids': best, 'selection': selection, 'best_hit': hit, 'miss_mechanism': mechanism,
            'all_best_zero_valid': all(d[i] == 0 for i in best),
            'any_best_zero_valid': any(d[i] == 0 for i in best),
            'best_max_valid_degree': max(d[i] for i in best), 'best_mean_valid_degree': statistics.fmean(d[i] for i in best),
            'best_mean_query_degree': statistics.fmean(q[i] for i in best),
            'best_mean_correct_direct_victories': statistics.fmean(len(directed[i]) for i in best),
            'valid_undefeated_ids': undefeated, 'valid_undefeated_nonbest_ids': false_undefeated,
            'zero_valid_ids': unobserved, 'zero_valid_nonbest_ids': [i for i in unobserved if i not in best],
            'nonbest_undefeated_lack_loss_evidence': bool(false_undefeated),
            'zero_valid_candidates': len(unobserved), 'valid_edges': sum(d.values()) // 2,
            'candidates': nodes}


def independent_policy_replay(job, bank):
    rng = random.Random(job['seed'])
    chain = list(job['ids'])
    rng.shuffle(chain)
    initial = [tuple(sorted(p)) for p in zip(chain, chain[1:])]
    remaining = set(tuple(sorted(p)) for p in itertools.combinations(job['ids'], 2))
    trace = []
    for step in range(job['budget']):
        if step < len(initial):
            edge = initial[step]
        else:
            q, d, _ = degree_stats(job['ids'], trace)
            edges = sorted(remaining)
            rng.shuffle(edges)
            keys = {e: (sum(d[i] == 0 for i in e), -min(d[i] for i in e), -sum(d[i] for i in e), -sum(q[i] for i in e)) for e in edges}
            edge = max(edges, key=keys.__getitem__)
        remaining.remove(edge)
        trace.append(public_feedback(bank, *edge, .7))
    return trace


def main():
    global HERE, RUN
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', type=Path, default=RUN)
    parser.add_argument('--output', type=Path, default=HERE)
    args = parser.parse_args()
    RUN, HERE = args.run.resolve(), args.output.resolve()
    HERE.mkdir(parents=True, exist_ok=True)
    protocol = ROOT / 'experiments/selection-frontier-02/protocol.json'
    assert sha(protocol) == PROTOCOL_SHA
    prepared = ROOT / 'experiments/clean-ranking-v1/prepared'
    jobs = [json.loads(s) for s in (prepared / 'jobs.jsonl').read_text().splitlines()]
    all_frozen = load_gz(ROOT / 'experiments/clean-ranking-v1/results/decisions.jsonl.gz')
    random_rows = {r['job_id']: r for r in all_frozen if r['method'] == 'coverage_random'}
    c0 = {r['job_id']: r for r in all_frozen if r['method'] == 'corrected_tournament'}
    run_rows = load_gz(RUN / 'decisions.jsonl.gz')
    bank = json.loads((prepared / 'feedback.json').read_text())
    assert sha(RUN / 'policy.py') == sha(ROOT / 'research/policies/valid_coverage_v1.py')
    assert len(run_rows) == len(jobs) == len(random_rows) == len(c0) == 850
    assert all(r['status'] == 'ok' for r in run_rows)
    # Verify source-only independent replay BEFORE label join.
    for job, row in zip(jobs, run_rows, strict=True):
        assert job['job_id'] == row['job_id']
        replay = independent_policy_replay(job, bank[job['task']])
        assert replay == [{k: v for k, v in e.items() if k != 'cached'} for e in row['trace']]
        assert row['selected'] == top_set(job['ids'], [(e['a'], e['b'], e['winner']) for e in replay])
        frozen = random_rows[job['job_id']]
        cursor = [0]
        def query(a, b):
            e = frozen['trace'][cursor[0]]
            assert [a, b] == [e['a'], e['b']]
            cursor[0] += 1
            return e['winner']
        selected, original = allocate(job['ids'], query, job['budget'], job['seed'], 'coverage_random')
        assert selected == frozen['selected'] and cursor[0] == len(frozen['trace'])
        nchain = min(len(job['ids']) - 1, job['budget'])
        assert [(e['a'], e['b'], e['winner']) for e in row['trace'][:nchain]] == original[:nchain]
        assert len(row['trace']) == len(frozen['trace']) == job['budget']
        assert row['stats']['unique_feedback_reads'] == frozen['stats']['unique_feedback_reads'] == job['budget']
    verification = {'official_statuses': dict(Counter(r['status'] for r in run_rows)),
                    'independent_policy_trace_matches': 850, 'frozen_random_full_schedules_verified_label_free': 850,
                    'same_chain_and_feedback_prefix': 850, 'same_unique_budget': 850,
                    'protocol_sha256': sha(protocol), 'official_decisions_sha256': sha(RUN / 'decisions.jsonl.gz'),
                    'policy_sha256': sha(ROOT / 'research/policies/valid_coverage_v1.py'),
                    'labels_enter_only_after_decision_replay': True, 'new_model_calls': 0, 'new_training_runs': 0}
    dump(HERE / 'allocation_verification.json', verification)
    labels = json.loads((prepared / 'evaluation_labels.json').read_text())
    j1 = {r['job_id']: r for r in [json.loads(x) for x in (ROOT / 'experiments/selection-frontier-01/j1/run_2/per_episode.jsonl').read_text().splitlines()]}
    episodes, j1episodes = [], []
    task_counts = Counter(j['task'] for j in jobs)
    for job, run in zip(jobs, run_rows, strict=True):
        utility = labels[job['task']]
        base = random_rows[job['job_id']]
        arm_rows = {'valid_coverage_v1': run, 'coverage_random': base, 'C0': c0[job['job_id']]}
        scores, graphs = {}, {}
        for arm, row in arm_rows.items():
            scores[arm] = {**evaluate(job['ids'], row['selected'], utility), **row['stats']}
            graphs[arm] = best_diagnostic(job, row['trace'], row['selected'], utility)
            if arm == 'C0':
                graphs[arm]['miss_mechanism'] = 'C0_whole_tournament_procedure_separate_from_top_set'
        gains = {control: scores[control]['regret'] - scores['valid_coverage_v1']['regret'] for control in ('coverage_random', 'C0')}
        episodes.append({'job_id': job['job_id'], 'task': job['task'], 'pool_id': job['pool_id'], 'repeat': job['repeat'],
                         'scores': scores, 'regret_gains': gains,
                         'selections': {a: r['selected'] for a, r in arm_rows.items()}, 'graphs': graphs,
                         'same_selected_set_vs_random': set(run['selected']) == set(base['selected']),
                         'same_full_schedule_vs_random': [(e['a'], e['b']) for e in run['trace']] == [(e['a'], e['b']) for e in base['trace']]})
        corrected_trace = []
        for e in base['trace']:
            a, b, w = e['a'], e['b'], e['winner']
            new = max((a, b), key=lambda i: utility[i]) if w is not None and utility[w] < max(utility[a], utility[b]) else w
            corrected_trace.append({**e, 'winner': new})
        corrected_selected = top_set(job['ids'], [(e['a'], e['b'], e['winner']) for e in corrected_trace])
        old = j1[job['job_id']]
        assert corrected_selected == old['corrected_selected'] and base['selected'] == old['original_selected']
        assert math.isclose(evaluate(job['ids'], corrected_selected, utility)['regret'], old['corrected']['regret'], abs_tol=1e-12)
        j1episodes.append({'job_id': job['job_id'], 'task': job['task'], 'pool_id': job['pool_id'], 'repeat': job['repeat'],
                           'j1_outcome': old['outcome'], 'original_regret': old['original']['regret'],
                           'corrected_regret': old['corrected']['regret'], 'j1_gain': old['regret_gain'],
                           'original_task_macro_contribution': old['original']['regret'] / task_counts[job['task']] / 26,
                           'corrected_task_macro_contribution': old['corrected']['regret'] / task_counts[job['task']] / 26,
                           'original_selected': base['selected'], 'corrected_selected': corrected_selected,
                           'original': graphs['coverage_random'],
                           'corrected': best_diagnostic(job, corrected_trace, corrected_selected, utility),
                           'original_trace': base['trace'], 'corrected_trace': corrected_trace})
    lines(HERE / 'allocation_episodes.jsonl', episodes)
    lines(HERE / 'j1_coverage_episodes.jsonl', j1episodes)
    taskrows = []
    for task in sorted(task_counts):
        rr = [r for r in episodes if r['task'] == task]
        arms = {a: {k: statistics.fmean(r['scores'][a][k] for r in rr) for k in ('regret', 'best_hit', 'unique_feedback_reads', 'cache_reads', 'budget_denials')} for a in ('valid_coverage_v1', 'coverage_random', 'C0')}
        coverage = {a: {k: statistics.fmean(r['graphs'][a][k] for r in rr) for k in ('zero_valid_candidates', 'valid_edges', 'best_mean_valid_degree', 'best_mean_query_degree', 'best_mean_correct_direct_victories', 'all_best_zero_valid')} for a in arms}
        taskrows.append({'task': task, 'episodes': len(rr), 'arms': arms, 'coverage': coverage,
                         'regret_gains': {c: arms[c]['regret'] - arms['valid_coverage_v1']['regret'] for c in ('coverage_random', 'C0')},
                         'hit_gains': {c: arms['valid_coverage_v1']['best_hit'] - arms[c]['best_hit'] for c in ('coverage_random', 'C0')}})
    lines(HERE / 'allocation_tasks.jsonl', taskrows)
    macro = {a: {k: statistics.fmean(t['arms'][a][k] for t in taskrows) for k in taskrows[0]['arms'][a]} for a in taskrows[0]['arms']}
    coverage_macro = {a: {k: statistics.fmean(t['coverage'][a][k] for t in taskrows) for k in taskrows[0]['coverage'][a]} for a in taskrows[0]['arms']}
    contrasts = {}
    for c in ('coverage_random', 'C0'):
        values = [t['regret_gains'][c] for t in taskrows]
        lo = [{'omitted_task': t['task'], 'gain': statistics.fmean(v for other, v in zip(taskrows, values) if other is not t)} for t in taskrows]
        contrasts[c] = {'regret_gain': inference(values), 'hit_gain': inference([t['hit_gains'][c] for t in taskrows]),
                        'leave_one_task_out': lo, 'leave_one_min': min(t['gain'] for t in lo), 'leave_one_max': max(t['gain'] for t in lo)}
    coverage_effects = {k: inference([t['coverage']['valid_coverage_v1'][k] - t['coverage']['coverage_random'][k] for t in taskrows])
                        for k in taskrows[0]['coverage']['valid_coverage_v1']}
    # Descriptive transitions at the actual best: allocation changed query exposure.
    transition = {}
    for status in ('valid_gained', 'valid_lost', 'remained_zero', 'remained_nonzero'):
        rr = []
        for r in episodes:
            a = r['graphs']['coverage_random']['all_best_zero_valid']
            b = r['graphs']['valid_coverage_v1']['all_best_zero_valid']
            s = 'valid_gained' if a and not b else 'valid_lost' if b and not a else 'remained_zero' if a else 'remained_nonzero'
            if s == status:
                rr.append(r)
        transition[status] = {'episodes': len(rr), 'regret_gain_episode_mean': statistics.fmean(r['regret_gains']['coverage_random'] for r in rr),
                              'outcomes': dict(Counter('improved' if r['regret_gains']['coverage_random'] > 1e-12 else 'worsened' if r['regret_gains']['coverage_random'] < -1e-12 else 'unchanged' for r in rr))}
    summaries = {'macro': macro, 'coverage_task_macro': coverage_macro, 'contrasts': contrasts,
                 'coverage_effects_policy_minus_random': coverage_effects,
                 'best_valid_coverage_transitions_descriptive': transition,
                 'denominators': {'tasks': 26, 'jobs': 850, 'pools': 425},
                 'selection_or_schedule': {'same_selected_set': sum(r['same_selected_set_vs_random'] for r in episodes),
                                           'same_full_schedule': sum(r['same_full_schedule_vs_random'] for r in episodes)},
                 'episode_outcomes_vs_random': dict(Counter('improved' if r['regret_gains']['coverage_random'] > 1e-12 else 'worsened' if r['regret_gains']['coverage_random'] < -1e-12 else 'unchanged' for r in episodes)),
                 'total_unique_reads': {a: sum(r['scores'][a]['unique_feedback_reads'] for r in episodes) for a in macro},
                 'preregistration': str(protocol.relative_to(ROOT)), 'protocol_sha256': PROTOCOL_SHA,
                 'development_scope': '26 previously inspected tasks; 850 paired jobs; 425 candidate pools'}
    dump(HERE / 'allocation_summary.json', summaries)
    # Contributions retain the full 26-task denominator even within outcome subsets.
    groups = {}
    cases = {}
    for outcome in ('all', 'improved', 'equal', 'worsened'):
        group = [r for r in j1episodes if outcome == 'all' or r['j1_outcome'] == outcome]
        summary = {'episodes': len(group), 'tasks_represented': len({r['task'] for r in group}),
                   'original_residual_task_macro_contribution': sum(r['original_task_macro_contribution'] for r in group),
                   'corrected_residual_task_macro_contribution': sum(r['corrected_task_macro_contribution'] for r in group)}
        for arm in ('original', 'corrected'):
            counts = Counter()
            bestcounts = Counter(dict.fromkeys(('no_incident_query', 'all_incident_abstain', 'one_valid_edge', 'multiple_valid_edges'), 0))
            for r in group:
                g = r[arm]
                counts['selection_' + g['selection']] += 1
                counts['mechanism_' + g['miss_mechanism']] += 1
                counts['all_best_zero_valid'] += g['all_best_zero_valid']
                counts['has_nonbest_valid_undefeated'] += bool(g['valid_undefeated_nonbest_ids'])
                counts['has_nonbest_zero_valid'] += bool(g['zero_valid_nonbest_ids'])
                counts['nonbest_valid_undefeated_total'] += len(g['valid_undefeated_nonbest_ids'])
                counts['nonbest_zero_valid_total'] += len(g['zero_valid_nonbest_ids'])
                counts['all_actual_best_nodes'] += len(g['actual_best_ids'])
                if g['miss_mechanism'] == 'degree_tiebreak_suppression':
                    counts['degree_suppressed_best_one_valid'] += g['best_max_valid_degree'] == 1
                    counts['degree_suppressed_best_multiple_valid'] += g['best_max_valid_degree'] > 1
                for n in g['candidates']:
                    if n['actual_best']:
                        bestcounts[n['coverage_category']] += 1
                key = f"{outcome}:{arm}:{g['miss_mechanism']}"
                if key not in cases:
                    cases[key] = r
            summary[arm] = {'episode_counts': dict(counts), 'actual_best_node_coverage_counts': dict(bestcounts),
                             'mean_best_query_degree': statistics.fmean(r[arm]['best_mean_query_degree'] for r in group),
                             'mean_best_valid_degree': statistics.fmean(r[arm]['best_mean_valid_degree'] for r in group),
                             'mean_best_correct_direct_victories': statistics.fmean(r[arm]['best_mean_correct_direct_victories'] for r in group)}
            breakdown = defaultdict(lambda: {'episodes': 0, 'residual_task_macro_contribution': 0})
            for r in group:
                mechanism = r[arm]['miss_mechanism'] if r[arm]['selection'] == 'miss' else r[arm]['selection']
                breakdown[mechanism]['episodes'] += 1
                breakdown[mechanism]['residual_task_macro_contribution'] += r[arm + '_task_macro_contribution']
            summary[arm]['regret_contributions_by_selection_or_miss'] = dict(breakdown)
        groups[outcome] = summary
    dump(HERE / 'j1_coverage_summary.json', {'groups': groups, 'definitions': {
        'actual_best': 'all candidates tied for maximum frozen execution utility',
        'partial_tie': 'selected set includes best and nonbest; uniform-tie hit lies strictly between 0 and 1',
        'best_only': 'every selected candidate is an actual best; a subset of tied true-best IDs is sufficient for hit=1',
        'correctly_ever_beaten': 'distinct directly compared strictly lower-utility opponents defeated at least once on a valid edge',
        'valid_undefeated': 'valid degree > 0 and valid wins == valid degree; zero-valid candidates separately counted',
        'lack_of_distinguishing_evidence': 'a nonbest valid-undefeated candidate has no observed accepted loss; unobserved candidates kept separate',
        'degree_tiebreak_suppression': 'best candidate reaches global maximum win fraction but every best at that fraction has smaller valid degree than selected competitors',
        'contribution': 'sum episode regret / task episode count / 26; subgroup contributions sum to full task-macro regret',
        'oracle_scope': 'J1 only corrects strict wrong directions on already accepted, already queried edges; abstentions/ties/budget retained'},
        'verified_existing_j1_episodes': 850})
    dump(HERE / 'j1_coverage_cases.json', cases)
    used = [protocol, prepared / 'jobs.jsonl', prepared / 'feedback.json', prepared / 'evaluation_labels.json',
            ROOT / 'research/policies/valid_coverage_v1.py', ROOT / 'research/registry.json', ROOT / 'research/protected_manifest.json',
            RUN / 'decisions.jsonl.gz', RUN / 'policy.py', RUN / 'evaluation/summary.json',
            ROOT / 'experiments/clean-ranking-v1/results/decisions.jsonl.gz',
            ROOT / 'experiments/selection-frontier-01/j1/run_2/per_episode.jsonl', Path(__file__)]
    dump(HERE / 'input_sha256.json', {str(p.relative_to(ROOT)): sha(p) for p in used})
    print(json.dumps(summaries, indent=2))
    print('J1 corrected counts:', groups['all']['corrected']['episode_counts'])
    print('J1 corrected residual:', groups['all']['corrected']['regret_contributions_by_selection_or_miss'])


if __name__ == '__main__':
    main()
