#!/usr/bin/env python3
"""frontier-02-fixed-graph-v1: sealed label-free gate/aggregation/judge replay."""
import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
from fractions import Fraction
import gzip
import hashlib
import itertools
import json
import math
from pathlib import Path
import platform
import random
import shutil
import signal
import statistics
import subprocess
import sys
import time
import traceback

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT))
sys.dont_write_bytecode = True
SEED, REPEATS = 20261108093, 10000
ARMS = {'g70_raw': (.7, False), 'g50_raw': (.5, False),
        'g70_smooth': (.7, True), 'g50_smooth': (.5, True)}


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def dump(p, x):
    Path(p).write_text(json.dumps(x, ensure_ascii=False, indent=2, allow_nan=False) + '\n')


def lines(p, rows):
    with Path(p).open('w') as f:
        for x in rows:
            f.write(json.dumps(x, ensure_ascii=False, sort_keys=True, allow_nan=False)+'\n')


def read_json(p):
    with (gzip.open(p, 'rt') if str(p).endswith('.gz') else Path(p).open()) as f:
        return json.load(f)


def winner(item, gate):
    # C0 parser, including string indexes, default confidence .5, invalid abstentions.
    from reproduction.clean_ranking_v1.correctness import response_values
    index, conf = response_values(item)
    return (item['order'][index] if index is not None and conf >= gate else None), conf


def choose(ids, trace, smooth):
    wins, degree = Counter(), Counter()
    for a, b, w, conf in trace:
        if w is not None:
            wins[w] += 1
            degree[a] += 1
            degree[b] += 1
    keys = {i: (Fraction(wins[i]+1, degree[i]+2) if smooth else
                Fraction(wins[i], degree[i]) if degree[i] else Fraction(1, 2), degree[i]) for i in ids}
    best = max(keys.values())
    selected = [i for i in ids if keys[i] == best]
    # Separate integer cross-product implementation checks every chosen set.
    nums = {i: ((wins[i]+1, degree[i]+2) if smooth else
                (wins[i], degree[i]) if degree[i] else (1, 2)) for i in ids}
    independent = [i for i in ids if all(
        nums[i][0]*nums[j][1] > nums[j][0]*nums[i][1] or
        (nums[i][0]*nums[j][1] == nums[j][0]*nums[i][1] and degree[i] >= degree[j]) for j in ids)]
    assert selected == independent
    return selected


def ci(values):
    from reproduction.clean_ranking_v1.run import percentile
    rng = random.Random(SEED)
    samples = [statistics.fmean(rng.choices(values, k=len(values))) for _ in range(REPEATS)]
    loo = [(math.fsum(values)-v)/(len(values)-1) for v in values]
    return {'mean': statistics.fmean(values), 'task_cluster_percentile_95':
            [percentile(samples, .025), percentile(samples, .975)],
            'leave_one_min': min(loo), 'leave_one_max': max(loo),
            'all_leave_one_positive': min(loo) > 0,
            'positive_tasks': sum(x > 1e-12 for x in values),
            'equal_tasks': sum(abs(x) <= 1e-12 for x in values),
            'negative_tasks': sum(x < -1e-12 for x in values)}


def score(ids, selected, labels):
    from reproduction.clean_ranking_v1.run import evaluate
    result = evaluate(ids, selected, labels)
    hi, lo = max(labels[i] for i in ids), min(labels[i] for i in ids)
    independent = 0 if hi == lo else math.fsum(hi-labels[i] for i in selected)/(len(selected)*(hi-lo))
    assert math.isclose(result['regret'], independent, abs_tol=1e-12, rel_tol=1e-12)
    return result


def select_phase(out, jobs, old, banks):
    """No execution labels or historical metric fields enter this phase."""
    from reproduction.clean_ranking_v1.ranking import allocate, top_set
    from reproduction.clean_ranking_v1.loader import load_world
    from reproduction.clean_ranking_v1.run import select
    parsed = []
    checks = Counter()
    # Independently rerun original C0 whole procedure, keeping its unique ledger distinct.
    model = load_world()
    files = read_json(ROOT/'experiments/clean-ranking-v1/prepared/code_files.json')
    code = {t: {i: (ROOT/p).read_text() for i, p in table.items()} for t, table in files.items()}
    for job in jobs:
        jid, ids = job['job_id'], job['ids']
        for schedule in ('coverage_random', 'random_pairs'):
            row = old[(jid, schedule)]
            endpoints = [(e['a'], e['b']) for e in row['trace']]
            for direction in (None, 'first'):
                _, rebuilt = allocate(ids, lambda a,b: None if direction is None else a,
                                      job['budget'], job['seed'], schedule)
                assert endpoints == [(a,b) for a,b,w in rebuilt]
            checks['zero_label_schedules_rebuilt'] += 1
        original, trace, stats = select(model, job, banks['DeepSeek'][job['task']],
                                      {i: code[job['task']][i] for i in ids}, 'corrected_tournament', .7)
        saved = old[(jid, 'corrected_tournament')]
        assert original == saved['selected'] and trace == saved['trace'] and stats == saved['stats']
        checks['actual_C0_whole_procedure_rebuilt'] += 1
        parsed.append({'job_id': jid, 'task': job['task'], 'bank': 'DeepSeek', 'schedule': 'actual_C0',
                       'arm': 'actual_C0', 'selected': original, 'stats': stats,
                       'trace': [[e['a'], e['b'], e['winner'], e['confidence']] for e in trace]})
        for name, bank in banks.items():
            schedules = ('coverage_random', 'random_pairs', 'C0_trace') if name == 'DeepSeek' else ('coverage_random',)
            for schedule in schedules:
                source = old[(jid, 'corrected_tournament' if schedule == 'C0_trace' else schedule)]
                endpoints = [(e['a'], e['b']) for e in source['trace']]
                assert len(endpoints) == len(set(tuple(sorted(e)) for e in endpoints)) <= job['budget']
                for arm, (gate, smooth) in ARMS.items():
                    events = []
                    for a, b in endpoints:
                        item = bank[job['task']]['|'.join(sorted((a,b)))]
                        w, conf = winner(item, gate)
                        events.append([a,b,w,conf])
                    selected = choose(ids, events, smooth)
                    if name == 'DeepSeek' and gate == .7:
                        assert events == [[e['a'],e['b'],e['winner'],e['confidence']] for e in source['trace']]
                    if name == 'DeepSeek' and arm == 'g70_raw' and schedule != 'C0_trace':
                        assert selected == source['selected'] == top_set(ids, [e[:3] for e in events])
                        checks['original_fixed_graph_selections_rebuilt'] += 1
                    parsed.append({'job_id':jid, 'task':job['task'], 'bank':name, 'schedule':schedule,
                                   'arm':arm, 'selected':selected, 'trace':events,
                                   'stats':{'unique_feedback_reads':len(events), 'cache_reads':0,
                                            'comparison_records':len(events), 'budget_denials':0}})
        if (len(parsed)//(13+4*(len(banks)-1))) % 100 == 0:
            print('label-free selection '+jid, flush=True)
    # Materialize all choices before evaluation-label file is opened.
    lines(out/'selections.sealed.jsonl', parsed)
    seal = {'phase':'completed before evaluation_labels.json open', 'sha256':sha(out/'selections.sealed.jsonl'),
            'selection_records':len(parsed), 'selection_inputs':
            ['candidate IDs/order, seed, budget, feedback banks, frozen endpoint schedules, C0 code'],
            'checks':dict(checks)}
    dump(out/'selection_seal.json', seal)
    return parsed, checks


def analyze(out, bank_paths):
    began = time.monotonic()
    protocol_path = HERE.parent/'protocol.json'
    protocol = read_json(protocol_path)
    frozen = protocol['frozen_sha256']
    binding = {}
    for relative, expected in frozen.items():
        actual = sha(ROOT/relative)
        assert actual == expected, relative
        binding[relative] = actual
    for relative in ('reproduction/clean_ranking_v1/correctness.py','reproduction/clean_ranking_v1/ranking.py',
                     'reproduction/clean_ranking_v1/run.py','reproduction/clean_ranking_v1/loader.py',
                     'reproduction/clean_ranking_v1/overlay/world_model.py'):
        binding[relative] = sha(ROOT/relative)
    binding['protocol.json'] = sha(protocol_path)
    shutil.copyfile(protocol_path, out/'protocol.snapshot.json')
    jobs = [json.loads(s) for s in (ROOT/'experiments/clean-ranking-v1/prepared/jobs.jsonl').read_text().splitlines()]
    assert len(jobs) == 850 and len({j['task'] for j in jobs}) == 26
    by_id = {j['job_id']:j for j in jobs}
    banks = {'DeepSeek':read_json(ROOT/'experiments/clean-ranking-v1/prepared/feedback.json')}
    signatures = {}
    expected_keys = {t:set(rows) for t,rows in banks['DeepSeek'].items()}
    if bank_paths:
        manifest_path = HERE.parent/'banks/manifest.json'
        manifest = read_json(manifest_path)
        assert manifest['status'] == 'passed' and manifest['labels_in_bank'] is False
        binding[str(manifest_path.relative_to(ROOT))] = sha(manifest_path)
        audit_path = HERE.parent/'banks/mapping_audit.json'
        assert sha(audit_path) == manifest['mapping_audit_sha256']
        binding[str(audit_path.relative_to(ROOT))] = sha(audit_path)
    for p in bank_paths:
        bank = read_json(p)
        name = Path(p).name.removesuffix('.gz').removesuffix('.json')
        assert name not in banks
        assert sha(p) == manifest['banks'][name]['sha256']
        banks[name] = bank
        binding[str(Path(p).relative_to(ROOT))] = sha(p)
    for name, bank in banks.items():
        assert set(bank) == set(expected_keys)
        counts = Counter()
        for task, table in bank.items():
            assert set(table) == expected_keys[task]
            for pair, item in table.items():
                assert set(item['order']) == set(pair.split('|')) and len(item['order']) == 2
                counts['pairs'] += 1
                for gate in (.7,.5):
                    w,c = winner(item,gate)
                    counts['accepted_'+str(gate)] += w is not None
        sig = hashlib.sha256(json.dumps({t:{p:sorted(v['order']) for p,v in sorted(table.items())}
                                         for t,table in sorted(bank.items())}, sort_keys=True).encode()).hexdigest()
        order_sig = hashlib.sha256(json.dumps({t:{p:v['order'] for p,v in sorted(table.items())}
                                               for t,table in sorted(bank.items())}, sort_keys=True).encode()).hexdigest()
        signatures[name] = {'task_pair_order_sha256':sig, 'original_order_sha256':order_sig,
                            'order_semantics':'original bank order retained; pair signature uses unordered endpoints',**counts}
    assert len({s['task_pair_order_sha256'] for s in signatures.values()}) == 1
    dump(out/'input_sha256.json', binding)
    dump(out/'bank_signature_checks.json', signatures)
    with gzip.open(ROOT/'experiments/clean-ranking-v1/results/decisions.jsonl.gz','rt') as f:
        # Historic score metrics are discarded at this boundary.
        old = {}
        for s in f:
            row = json.loads(s)
            old[(row['job_id'],row['method'])] = {k:row[k] for k in ('selected','trace','stats')}
    choices, checks = select_phase(out,jobs,old,banks)
    # Independent scoring begins only after the complete selection artifact is sealed.
    labels = read_json(ROOT/'experiments/clean-ranking-v1/prepared/evaluation_labels.json')
    prior = read_json(ROOT/'experiments/clean-ranking-v1/results/summary.json')
    episodes, edges = [], []
    grouped = defaultdict(list)
    for row in choices:
        job = by_id[row['job_id']]
        utility = labels[row['task']]
        metrics = score(job['ids'],row['selected'],utility)
        counts = Counter(queries=len(row['trace']))
        qdeg, vdeg = Counter(),Counter()
        for num,(a,b,w,c) in enumerate(row['trace']):
            qdeg[a] += 1; qdeg[b] += 1
            valid = w is not None
            counts['valid'] += valid
            counts['abstain'] += not valid
            if valid:
                vdeg[a] += 1; vdeg[b] += 1
                loser = b if w == a else a
                correct = utility[w] > utility[loser]
                tie = utility[w] == utility[loser]
                counts['strict_correct'] += correct
                counts['true_tie'] += tie
                counts['strict_error'] += not correct and not tie
                if c < .7:
                    counts['new_valid'] += 1
                    counts['new_strict_correct'] += correct
                    counts['new_true_tie'] += tie
                    counts['new_strict_error'] += not correct and not tie
            # Edge direction diagnostics need each gate, once rather than each aggregation.
            if row['arm'] in ('g70_raw','g50_raw'):
                edges.append({'job_id':row['job_id'],'task':row['task'],'bank':row['bank'],
                              'schedule':row['schedule'],'arm':row['arm'],'edge_number':num,
                              'a':a,'b':b,'winner':w,'confidence':c,
                              'utility_a':utility[a],'utility_b':utility[b]})
        best = max(utility[i] for i in job['ids'])
        best_ids = [i for i in job['ids'] if utility[i] == best]
        coverage = {'best_candidates':len(best_ids),'best_unqueried':sum(qdeg[i]==0 for i in best_ids),
                    'best_zero_valid_degree':sum(vdeg[i]==0 for i in best_ids),
                    'best_query_degree_mean':statistics.fmean(qdeg[i] for i in best_ids),
                    'best_valid_degree_mean':statistics.fmean(vdeg[i] for i in best_ids),
                    'all_candidates_zero_valid':sum(vdeg[i]==0 for i in job['ids'])}
        episode = {k:row[k] for k in ('job_id','task','bank','schedule','arm','selected')}
        episode.update(metrics=metrics,stats=row['stats'],counts=dict(counts),coverage=coverage)
        episodes.append(episode)
        grouped[(row['bank'],row['schedule'],row['arm'],row['task'])].append(episode)
    tasks = []
    for (bank,schedule,arm,task), records in sorted(grouped.items()):
        metrics = {m:statistics.fmean(r['metrics'][m] for r in records) for m in ('regret','best_hit')}
        stats = {m:statistics.fmean(r['stats'][m] for r in records) for m in records[0]['stats']}
        coverage = {m:statistics.fmean(r['coverage'][m] for r in records) for m in records[0]['coverage']}
        counts = Counter()
        for r in records: counts.update(r['counts'])
        tasks.append({'bank':bank,'schedule':schedule,'arm':arm,'task':task,'episodes':len(records),
                      'metrics':metrics,'stats':stats,'coverage':coverage,'counts':dict(counts)})
        if bank == 'DeepSeek' and ((arm == 'g70_raw' and schedule in ('coverage_random','random_pairs')) or schedule == 'actual_C0'):
            method = 'corrected_tournament' if schedule == 'actual_C0' else schedule
            for k,v in {**metrics,**stats}.items():
                if k in prior['per_task'][task][method]:
                    assert math.isclose(v,prior['per_task'][task][method][k],abs_tol=1e-12)
            checks['saved_task_metrics_rebuilt'] += 1
    # GPT repeat aggregation is task-first: 3 banks within each task, then 26 tasks.
    gpt_names = [n for n in banks if n != 'DeepSeek']
    if gpt_names:
        assert len(gpt_names) == 3
        table = {(t['bank'],t['schedule'],t['arm'],t['task']):t for t in tasks}
        for task in sorted(labels):
            for arm in ARMS:
                rows = [table[(n,'coverage_random',arm,task)] for n in gpt_names]
                tasks.append({'bank':'GPT_task_first_mean','schedule':'coverage_random','arm':arm,'task':task,
                              'episodes':rows[0]['episodes'],'repeated_banks':3,
                              'metrics':{m:statistics.fmean(r['metrics'][m] for r in rows) for m in rows[0]['metrics']},
                              'stats':{m:statistics.fmean(r['stats'][m] for r in rows) for m in rows[0]['stats']},
                              'coverage':{m:statistics.fmean(r['coverage'][m] for r in rows) for m in rows[0]['coverage']},
                              'counts':{m:math.fsum(r['counts'].get(m,0) for r in rows) for m in set().union(*(r['counts'] for r in rows))}})
    taskmap = {(t['bank'],t['schedule'],t['arm'],t['task']):t for t in tasks}
    combinations = sorted({k[:3] for k in taskmap})
    macro = []
    for bank,schedule,arm in combinations:
        ts = [taskmap[(bank,schedule,arm,t)] for t in sorted(labels)]
        counts = Counter()
        for t in ts: counts.update(t['counts'])
        total, valid = counts['queries'],counts['valid']
        denom = valid-counts['true_tie']
        newdenom = counts['new_valid']-counts['new_true_tie']
        macro.append({'bank':bank,'schedule':schedule,'arm':arm,
                      'metrics':{m:statistics.fmean(t['metrics'][m] for t in ts) for m in ts[0]['metrics']},
                      'stats':{m:statistics.fmean(t['stats'][m] for t in ts) for m in ts[0]['stats']},
                      'coverage':{m:statistics.fmean(t['coverage'][m] for t in ts) for m in ts[0]['coverage']},
                      'counts':dict(counts),'direction_accuracy_strict':counts['strict_correct']/denom if denom else None,
                      'new_direction_accuracy_strict':counts['new_strict_correct']/newdenom if newdenom else None,
                      'accepted_fraction':valid/total})
    contrasts,leave = {},{}
    def contrast(name,left,right):
        # The contrast is baseline-left regret minus intervention-right regret.
        vals = [taskmap[(*left,t)]['metrics']['regret']-taskmap[(*right,t)]['metrics']['regret'] for t in sorted(labels)]
        hits = [taskmap[(*right,t)]['metrics']['best_hit']-taskmap[(*left,t)]['metrics']['best_hit'] for t in sorted(labels)]
        contrasts[name] = {'baseline':left,'intervention':right,'regret_gain':ci(vals),'hit_gain':ci(hits),
                           'per_task_gain':dict(zip(sorted(labels), vals))}
        leave[name] = {t:(math.fsum(vals)-v)/25 for t,v in zip(sorted(labels),vals)}
    for bank,schedule,arm in combinations:
        if arm == 'actual_C0':continue
        if arm != 'g70_raw':
            contrast(f'{bank}/{schedule}/{arm}_vs_g70_raw',(bank,schedule,'g70_raw'),(bank,schedule,arm))
        if bank == 'DeepSeek':
            contrast(f'DeepSeek/{schedule}/{arm}_vs_actual_C0',('DeepSeek','actual_C0','actual_C0'),(bank,schedule,arm))
    for bank in ['DeepSeek',*gpt_names, *(['GPT_task_first_mean'] if gpt_names else [])]:
        schedule = 'coverage_random'
        contrast(f'{bank}/direct_gate_vs_smoothing',(bank,schedule,'g50_raw'),(bank,schedule,'g70_smooth'))
        contrast(f'{bank}/smooth_at_g50',(bank,schedule,'g50_raw'),(bank,schedule,'g50_smooth'))
        contrast(f'{bank}/gate_at_smooth',(bank,schedule,'g70_smooth'),(bank,schedule,'g50_smooth'))
        vals = []
        for t in sorted(labels):
            a = {arm:taskmap[(bank,schedule,arm,t)]['metrics']['regret'] for arm in ARMS}
            vals.append((a['g50_raw']-a['g50_smooth'])-(a['g70_raw']-a['g70_smooth']))
        contrasts[f'{bank}/interaction'] = {'definition':'smoothing regret gain at .5 minus smoothing regret gain at .7',
                                           'regret_gain':ci(vals),'per_task_gain':dict(zip(sorted(labels),vals))}
    if gpt_names:
        for bank in [*gpt_names,'GPT_task_first_mean']:
            contrast(f'judge/{bank}_vs_DeepSeek',('DeepSeek','coverage_random','g70_raw'),(bank,'coverage_random','g70_raw'))
    criteria = {}
    for arm in ('g50_raw','g70_smooth','g50_smooth'):
        ds = contrasts[f'DeepSeek/coverage_random/{arm}_vs_g70_raw']['regret_gain']
        entry = {'DS_gain_ge_001':ds['mean'] >= .01,'DS_all_leave_one_positive':ds['all_leave_one_positive']}
        if gpt_names:
            g = [contrasts[f'{b}/coverage_random/{arm}_vs_g70_raw']['regret_gain']['mean'] for b in gpt_names]
            pooled = contrasts[f'GPT_task_first_mean/coverage_random/{arm}_vs_g70_raw']['regret_gain']['mean']
            entry.update(GPT_at_least_2_positive=sum(x>0 for x in g)>=2,GPT_task_first_mean_positive=pooled>0,
                         GPT_individual_gains=g,GPT_task_first_gain=pooled)
            entry['research_priority_criteria_pass'] = all(v for k,v in entry.items() if k in
                ('DS_gain_ge_001','DS_all_leave_one_positive','GPT_at_least_2_positive','GPT_task_first_mean_positive'))
        criteria[arm] = entry
    if gpt_names:
        pooled = contrasts['judge/GPT_task_first_mean_vs_DeepSeek']['regret_gain']
        individuals = [contrasts[f'judge/{b}_vs_DeepSeek']['regret_gain']['mean'] for b in gpt_names]
        criteria['judge_swap'] = {'pooled_gain_ge_001':pooled['mean']>=.01,'pooled_all_leave_one_positive':pooled['all_leave_one_positive'],
                                  'at_least_2_individual_positive':sum(x>0 for x in individuals)>=2}
        criteria['judge_swap']['research_priority_criteria_pass'] = all(criteria['judge_swap'].values())
    checks.update(all_selection_records=len(choices), independent_selection_cross_checks=len(choices)-850,
                  independent_scoring_cross_checks=len(episodes), excluded_episodes=0,failed_episodes=0)
    for p,h in frozen.items(): assert sha(ROOT/p)==h
    dump(out/'checks.json',dict(checks))
    lines(out/'per_episode.jsonl',episodes)
    lines(out/'per_edge.jsonl',edges)
    dump(out/'per_task.json',tasks)
    dump(out/'leave_one_task_out.json',leave)
    dump(out/'contrasts.json',contrasts)
    summary = {'version':'frontier-02-fixed-graph-v1','tasks':26,'pools':425,'jobs_per_arm':850,
               'banks':list(banks),'macro':macro,'contrasts':contrasts,'preregistered_criteria':criteria,
               'checks':dict(checks),'bootstrap':{'seed':SEED,'repeats':REPEATS,'unit':'paired task, GPT repeats averaged within task first'},
               'elapsed_seconds':time.monotonic()-began,
               'scope':'All 26 previously inspected development tasks; fixed graph reaggregation. Actual C0 whole procedure is a separate reference.',
               'cost':{'new_API_calls':0,'GPU':0,'candidate_training':0,'mode':'local CPU'},
               'interpretation':['C0_trace interventions retain actual C0 revealed unique edges and are fixed-trace reaggregations.',
                                 'coverage_random and random_pairs have 11004 reads; C0 actual and fixed C0 trace have 10574 reads.',
                                 'Judge setting replacement changes the archived complete judge setting; currency/token and pure model effects are unidentified.',
                                 'A combined arm is an interaction diagnostic; its priority requires single-factor attribution follow-up.',
                                 'Default switch requires evidence against actual C0 plus method freeze and fresh confirmation.']}
    dump(out/'summary.json',summary)
    return summary


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--out',required=True)
    p.add_argument('--bank',action='append',default=[],type=Path)
    args = p.parse_args()
    out = (HERE/args.out).resolve()
    assert out.parent == HERE and not out.exists(), 'Fresh direct child output required'
    out.mkdir()
    shutil.copyfile(__file__,out/'experiment.snapshot.py')
    started = time.monotonic()
    dump(out/'command.json',{'argv':sys.argv,'cwd':str(Path.cwd()),'python':sys.version,
                            'platform':platform.platform(),'script_sha256':sha(__file__),
                            'git_head':subprocess.check_output(['git','-C',str(ROOT),'rev-parse','HEAD'],text=True).strip(),
                            'started_utc':datetime.now(timezone.utc).isoformat(),'max_seconds':600})
    def timeout(*a): raise TimeoutError('600 second analysis budget')
    signal.signal(signal.SIGALRM,timeout); signal.alarm(600)
    status,error = 'failed',None
    try:
        summary = analyze(out,args.bank)
        status='success'
        print(json.dumps({'status':status,'out':str(out),'criteria':summary['preregistered_criteria']},indent=2),flush=True)
    except BaseException:
        error=traceback.format_exc()
        print(error,flush=True)
    finally:
        signal.alarm(0)
        (out/'failure.log').write_text(error or '')
        dump(out/'final_info.json',{'status':status,'error':error,'elapsed_seconds':time.monotonic()-started,
                                   'new_API_calls':0,'GPU':0,'candidate_training':0})
        dump(out/'output_sha256.json',{str(p.relative_to(out)):sha(p) for p in sorted(out.rglob('*'))
                                      if p.is_file() and p.name!='output_sha256.json'})
    if error:sys.exit(1)


if __name__ == '__main__':main()
