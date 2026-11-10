#!/usr/bin/env python3
"""D1 fixed-prefix diagnostic. stdlib + hash-verified frozen aggregation/scoring.
Run from this directory: python3 -B experiment.py --out_dir=run_1
Each invocation requires a fresh output directory. Selection is sealed in a
separate process before the evaluator imports scoring or opens labels/metrics.
"""
import argparse
from collections import Counter, defaultdict
import contextlib
import datetime as dt
import gzip
import hashlib
import json
import math
from pathlib import Path
import platform
import random
import signal
import statistics as st
import subprocess
import sys
import time
import traceback

PROTOCOL_SHA = 'fbd9f027a7f2afdce09b24927825df21f8714e864ba1c996e1e0a2a010fe1100'
METHODS = {'U': 'coverage_random', 'T': 'coverage_decision_sensitive'}
FIELDS = ('a', 'b', 'winner', 'confidence', 'source_group_index')
BOOT_SEED = 20261108093
BOOT_N = 10000

def root_dir():
    return next(p for p in Path(__file__).resolve().parents if (p/'research/registry.json').is_file())

ROOT = root_dir()
BASE = ROOT/'experiments/clean-ranking-v1'
PROTOCOL = ROOT/'experiments/selection-frontier-01/protocol.json'

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def read(path):
    return json.loads(Path(path).read_text())

def dump(path, obj):
    Path(path).write_text(json.dumps(obj, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)+'\n')

def write_rows(path, rows):
    with Path(path).open('w') as f:
        for row in rows:
            f.write(json.dumps(row, sort_keys=True, ensure_ascii=False, allow_nan=False)+'\n')

def rows(path):
    return [json.loads(line) for line in Path(path).read_text().splitlines()]

def utc():
    return dt.datetime.now(dt.timezone.utc).isoformat()

def check(ok, why):
    if not ok:
        raise ValueError(why)

def verify_inputs():
    check(sha(PROTOCOL) == PROTOCOL_SHA, 'Preregistered protocol hash mismatch')
    p = read(PROTOCOL)
    entries = dict(p['frozen_sha256'])
    entries.update(read(ROOT/'research/protected_manifest.json')['sha256'])
    entries.update(read(BASE/'implementation-lock.json')['sha256'])
    entries['experiments/selection-frontier-01/protocol.json'] = PROTOCOL_SHA
    for name, expected in entries.items():
        check(sha(ROOT/name) == expected, 'Frozen input mismatch: '+name)
    return entries

def frozen_top():
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from reproduction.clean_ranking_v1.ranking import top_set
    return top_set

def counts(ids, edges):
    wins, degree = dict.fromkeys(ids, 0), dict.fromkeys(ids, 0)
    for e in edges:
        if e['winner'] is not None:
            wins[e['winner']] += 1
            degree[e['a']] += 1
            degree[e['b']] += 1
    return {'wins': wins, 'degree': degree}

def selection_worker(out):
    # The only historical fields projected here are job_id/method/trace and
    # the five trace fields above. No selected/stats/metrics are retained.
    verify_inputs()
    top_set = frozen_top()
    jobs = rows(BASE/'prepared/jobs.jsonl')
    check(len(jobs) == 850 and len({j['job_id'] for j in jobs}) == 850, 'Job denominator')
    projected = {}
    with gzip.open(BASE/'results/decisions.jsonl.gz', 'rt') as f:
        for line in f:
            r = json.loads(line)
            if r['method'] in METHODS.values():
                key = (r['job_id'], r['method'])
                check(key not in projected, 'Duplicate historical branch')
                projected[key] = {'job_id': r['job_id'], 'method': r['method'],
                    'trace': [{k:e[k] for k in FIELDS} for e in r['trace']]}
    check(len(projected) == 1700, 'Historical branch denominator')
    sealed, projection = [], []
    for job in jobs:
        jid, ids = job['job_id'], job['ids']
        n = len(ids)
        chain = list(ids)
        random.Random(job['seed']).shuffle(chain)
        chain = [tuple(sorted(e)) for e in zip(chain, chain[1:])]
        pair = {b:projected[(jid,m)]['trace'] for b,m in METHODS.items()}
        for b, trace in pair.items():
            check(len(trace) == job['budget'] and len(trace) >= n, 'Full branch length')
            keys = [tuple(sorted((e['a'],e['b']))) for e in trace]
            check(len(set(keys)) == len(keys), 'Duplicate historical query')
            check(keys[:n-1] == chain, 'Chain endpoint/order mismatch: '+jid)
            check(all(e['a'] in ids and e['b'] in ids and e['a'] != e['b'] and
                      e['winner'] in (None,e['a'],e['b']) and
                      (e['winner'] is None or e['confidence'] >= .7) for e in trace), 'Illegal trace')
            projection.append(projected[(jid, METHODS[b])])
        check(pair['U'][:n-1] == pair['T'][:n-1], 'Shared complete prefix mismatch: '+jid)
        branches = {'S':pair['U'][:n-1], 'U':pair['U'][:n], 'T':pair['T'][:n]}
        for branch, edges in branches.items():
            sealed.append({'job_id':jid, 'branch':branch, 'edges':edges,
                'valid':[e['winner'] is not None for e in edges],
                'selected':top_set(ids, [(e['a'],e['b'],e['winner']) for e in edges]),
                'counts':counts(ids,edges), 'logical_reads':len(edges), 'cache_reads':0,
                'status':'ok'})
    write_rows(out/'projected_full_traces.jsonl', projection)
    write_rows(out/'sealed_selections.jsonl', sealed)
    dump(out/'selection_seal.json', {'status':'sealed', 'sealed_utc':utc(),
        'jobs':850, 'selections':len(sealed), 'projected_historical_branches':len(projection),
        'labels_opened':False, 'historical_metrics_retained':False,
        'projection_fields':list(FIELDS),
        'sha256':{n:sha(out/n) for n in ('projected_full_traces.jsonl','sealed_selections.jsonl')}})
    print('Sealed 2550 selections and 1700 projected traces before evaluator start', flush=True)

def mean(xs):
    return st.fmean(xs)

def bootstrap(values):
    from reproduction.clean_ranking_v1.run import percentile
    rng = random.Random(BOOT_SEED)
    samples = [mean(rng.choices(values,k=len(values))) for _ in range(BOOT_N)]
    return {'mean':mean(values), 'task_cluster_95':[percentile(samples,.025),percentile(samples,.975)]}

def direction(x):
    # Descriptive count tolerance follows the frozen summarizer.
    return 'improved' if x < -1e-12 else 'worsened' if x > 1e-12 else 'equal'

def score(out):
    seal = read(out/'selection_seal.json')
    for n,h in seal['sha256'].items():
        check(sha(out/n) == h, 'Selection seal changed')
    check(seal['labels_opened'] is False, 'Seal boundary invalid')
    top_set = frozen_top()
    from reproduction.clean_ranking_v1.run import evaluate
    from reproduction.clean_ranking_v1.correctness import response_values
    evaluation_started = utc()
    jobs = rows(BASE/'prepared/jobs.jsonl')
    by_id = {j['job_id']:j for j in jobs}
    labels = read(BASE/'prepared/evaluation_labels.json')
    bank = read(BASE/'prepared/feedback.json')
    original_summary = read(BASE/'results/summary.json')
    original, historical = {}, []
    with gzip.open(BASE/'results/decisions.jsonl.gz','rt') as f:
        for line in f:
            r = json.loads(line)
            if r['method'] in METHODS.values():
                original[(r['job_id'],r['method'])] = r
    # Independent full-length replay must pass before prefix scores enter output.
    for r in rows(out/'projected_full_traces.jsonl'):
        job = by_id[r['job_id']]
        old = original[(r['job_id'],r['method'])]
        trace = r['trace']
        for e in trace:
            source = bank[job['task']]['|'.join(sorted((e['a'],e['b'])))]
            idx, conf = response_values(source)
            winner = source['order'][idx] if idx is not None and conf >= .7 else None
            check(e['winner'] == winner and e['confidence'] == conf and
                  e['source_group_index'] == source['source_group_index'], 'Full trace source mismatch')
        selected = top_set(job['ids'], [(e['a'],e['b'],e['winner']) for e in trace])
        check(selected == old['selected'], 'Full-length selected mismatch')
        metric = evaluate(job['ids'], selected, labels[job['task']])
        for k,v in metric.items():
            check(v == old['metrics'][k], 'Full-length saved score mismatch')
        ledger = {'unique_feedback_reads':len(trace), 'cache_reads':0,
                  'budget_denials':0, 'comparison_records':len(trace)}
        check(ledger == old['stats'], 'Full-length ledger mismatch')
        check(old['metrics'] == {**metric,**ledger}, 'Full-length metrics/ledger mismatch')
        historical.append({'task':job['task'],'method':r['method'],**metric,**ledger})
    full_task = {}
    for task in sorted(labels):
        full_task[task] = {}
        for m in METHODS.values():
            group = [r for r in historical if r['task']==task and r['method']==m]
            if not group:
                continue
            stats = {k:mean(r[k] for r in group) for k in ('regret','best_hit','unique_feedback_reads','cache_reads','budget_denials')}
            for k,v in stats.items():
                check(v == original_summary['per_task'][task][m][k], 'Full-length task summary mismatch: '+task)
            full_task[task][m] = stats
    full_task = {t:v for t,v in full_task.items() if v}
    check(len(full_task)==26 and len(historical)==1700,'Full-length verification denominator')
    for m in METHODS.values():
        for k,v in original_summary['macro'][m].items():
            check(mean(full_task[t][m][k] for t in full_task)==v, 'Full-length macro mismatch')
    dump(out/'full_length_verification.json', {'status':'passed','branches':1700,'tasks':26,
        'checks':['source winner/confidence/index','complete selected sets','saved job scores',
                  'complete query ledger','per-task historical summary','historical macro'],
        'per_task':full_task, 'selection_sealed_before_evaluation':True,
        'evaluation_started_utc':evaluation_started, 'seal_sha256':sha(out/'selection_seal.json')})
    print('Full-length 1700 branches/26 tasks verified against source, selections and scores',flush=True)
    sealed = {(r['job_id'],r['branch']):r for r in rows(out/'sealed_selections.jsonl')}
    evidence = []
    for job in jobs:
        jid, ids, utility = job['job_id'],job['ids'],labels[job['task']]
        branch = {b:sealed[(jid,b)] for b in ('S','U','T')}
        scores = {b:evaluate(ids,r['selected'],utility) for b,r in branch.items()}
        span = max(utility[i] for i in ids)-min(utility[i] for i in ids)
        selected_mean = {b:mean(utility[i] for i in r['selected']) for b,r in branch.items()}
        gains = {b:scores['S']['regret']-scores[b]['regret'] for b in ('U','T')}
        delta = scores['T']['regret']-scores['U']['regret']
        harm = {b:max(-gains[b],0) for b in gains}
        benefit = {b:max(gains[b],0) for b in gains}
        dh, dm = harm['T']-harm['U'], benefit['U']-benefit['T']
        check(math.isclose(delta,dh+dm,abs_tol=1e-14),'Harm/missed identity')
        same_edge = {branch['U']['edges'][-1]['a'],branch['U']['edges'][-1]['b']} == {branch['T']['edges'][-1]['a'],branch['T']['edges'][-1]['b']}
        row = {'job_id':jid,'task':job['task'],'pool_id':job['pool_id'],'repeat':job['repeat'],
            'n':len(ids),'pool_span':span,'pool_best':max(utility[i] for i in ids),
            'pool_worst':min(utility[i] for i in ids),'scores':scores,'selected_mean_utility':selected_mean,
            'same_next_edge':same_edge,'delta_T_minus_U':delta,'D_harm':dh,'D_missed':dm,
            'gains':gains,'harm':harm,'benefit':benefit,
            'raw_utility_gains':{b:selected_mean[b]-selected_mean['S'] for b in gains},
            'diagnostics':{},'primary_outcome':direction(delta)}
        for b in ('U','T'):
            e = branch[b]['edges'][-1]
            top = set(branch['S']['selected'])
            degree = branch['S']['counts']['degree']
            opponent_degrees = [degree[e['b']] if e['a'] in top else None,
                                degree[e['a']] if e['b'] in top else None]
            opponent_degrees = [x for x in opponent_degrees if x is not None]
            changed = set(branch[b]['selected']) != top
            valid = e['winner'] is not None
            if not valid:
                check(not changed and gains[b]==0,'Abstention changed selection')
            gap = utility[e['a']]-utility[e['b']]
            judge = ('abstained' if not valid else 'utility_tie' if gap==0 else
                'correct' if utility[e['winner']]==max(utility[e['a']],utility[e['b']]) else 'incorrect')
            row['diagnostics'][b] = {'changed':changed,'valid':valid,
                'touches_S_top':bool(opponent_degrees),'endpoint_S_degrees':[degree[e['a']],degree[e['b']]],
                'opponent_S_degrees':opponent_degrees,'judge_direction':judge,
                'utility_outcome':direction(-gains[b]), 'selected_count':len(branch[b]['selected']),
                'logical_reads':branch[b]['logical_reads'],'cache_reads':0,'failed':False}
        if same_edge:
            check(branch['U']['selected']==branch['T']['selected'] and delta==0,'Identical edge natural check')
        if len(ids)==3:
            check(same_edge,'n=3 single remaining edge natural check')
        evidence.append(row)
    write_rows(out/'per_job_evidence.jsonl', evidence)
    tasks = sorted({r['task'] for r in evidence})
    grouped = {t:[r for r in evidence if r['task']==t] for t in tasks}
    def metric(r,key):
        if key in ('delta_T_minus_U','D_harm','D_missed'):
            return r[key]
        category,b = key.split(':')
        if category in ('regret','best_hit'):
            return r['scores'][b][category]
        if category=='logical_reads':
            return len(ids) if False else sealed[(r['job_id'],b)]['logical_reads']
        if category in ('gains','harm','benefit','raw_utility_gains'):
            return r[category][b]
        raise ValueError(key)
    keys = ['delta_T_minus_U','D_harm','D_missed'] + [f'{k}:{b}' for k in ('regret','best_hit','logical_reads') for b in ('S','U','T')] + [f'{k}:{b}' for k in ('gains','harm','benefit','raw_utility_gains') for b in ('U','T')]
    per_task = []
    for task,g in grouped.items():
        rec = {'task':task,'jobs':len(g),'pools':len({r['pool_id'] for r in g}),
            'metrics':{k:mean(metric(r,k) for r in g) for k in keys},
            'pool_span':{'min':min(r['pool_span'] for r in g),'median':st.median(r['pool_span'] for r in g),'max':max(r['pool_span'] for r in g)},
            'outcomes':dict(Counter(r['primary_outcome'] for r in g)),
            'raw_unit_note':'Utility is direction-normalized execution score; compare raw values within task.'}
        per_task.append(rec)
    write_rows(out/'per_task.jsonl',per_task)
    macro = {k:mean(t['metrics'][k] for t in per_task) for k in keys}
    ci_keys = ['delta_T_minus_U','D_harm','D_missed','gains:U','gains:T','regret:S','regret:U','regret:T','best_hit:S','best_hit:U','best_hit:T','harm:U','harm:T','benefit:U','benefit:T']
    intervals = {k:bootstrap([t['metrics'][k] for t in per_task]) for k in ci_keys}
    for b in ('U','T'):
        check(math.isclose(macro['gains:'+b],macro['benefit:'+b]-macro['harm:'+b],abs_tol=1e-14),'Benefit-harm macro identity')
    check(math.isclose(macro['delta_T_minus_U'],macro['D_harm']+macro['D_missed'],abs_tol=1e-14),'Macro decomposition identity')
    leave_one = [{'excluded_task':t['task'],'delta_T_minus_U':mean(x['metrics']['delta_T_minus_U'] for x in per_task if x is not t)} for t in per_task]
    dump(out/'leave_one_task_out.json',leave_one)
    # Full-denominator contribution preserves the 26-task macro decomposition;
    # conditional means use represented tasks only, with task/job counts reported.
    def subset_summary(g):
        present = sorted({r['task'] for r in g})
        return {'jobs':len(g),'tasks':len(present),'pools':len({(r['task'],r['pool_id']) for r in g}),
            'full_jobs_denominator':850,'full_tasks_denominator':26,
            'task_macro_conditional':{k:mean(mean(metric(r,k) for r in g if r['task']==t) for t in present) if present else None for k in ('delta_T_minus_U','D_harm','D_missed','gains:U','gains:T')},
            'full_task_macro_contribution':{k:mean(sum(metric(r,k) for r in g if r['task']==t)/len(grouped[t]) for t in tasks) for k in ('delta_T_minus_U','D_harm','D_missed','gains:U','gains:T')}}
    strata = {}
    for n in sorted({r['n'] for r in evidence}):
        strata['pool_size_'+str(n)] = subset_summary([r for r in evidence if r['n']==n])
    for flag in (True,False):
        strata['same_edge_'+str(flag)] = subset_summary([r for r in evidence if r['same_next_edge']==flag])
        for b in ('U','T'):
            for feature in ('changed','valid','touches_S_top'):
                strata[b+'_'+feature+'_'+str(flag)] = subset_summary([r for r in evidence if r['diagnostics'][b][feature]==flag])
    for b in ('U','T'):
        for judge in ('correct','incorrect','utility_tie','abstained'):
            strata[b+'_judge_'+judge] = subset_summary([r for r in evidence if r['diagnostics'][b]['judge_direction']==judge])
    dump(out/'strata.json',strata)
    diagnostics = {}
    for b in ('U','T'):
        def macro_indicator(fn):
            return mean(mean(fn(r) for r in grouped[t]) for t in tasks)
        opp = [v for r in evidence for v in r['diagnostics'][b]['opponent_S_degrees']]
        diagnostics[b] = {'jobs_denominator':850,'tasks_denominator':26,
            'counts':{f:sum(r['diagnostics'][b][f] for r in evidence) for f in ('changed','valid','touches_S_top')},
            'task_macro_rates':{f:macro_indicator(lambda r,f=f:float(r['diagnostics'][b][f])) for f in ('changed','valid','touches_S_top')},
            'utility_outcome_counts':dict(Counter(r['diagnostics'][b]['utility_outcome'] for r in evidence)),
            'judge_direction_counts':dict(Counter(r['diagnostics'][b]['judge_direction'] for r in evidence)),
            'S_top_tie_jobs':sum(len(sealed[(r['job_id'],'S')]['selected'])>1 for r in evidence),
            'branch_tie_jobs':sum(r['diagnostics'][b]['selected_count']>1 for r in evidence),
            'opponent_degree_incidence_count':len(opp),'opponent_degree_incidence_mean':mean(opp) if opp else None,
            'opponent_degree_definition':'One incidence per endpoint in S top: degree of its opposite endpoint; both-top edges contribute two. Conditional incidence mean, all-job touch denominator reported.',
            'logical_reads_total':sum(r['diagnostics'][b]['logical_reads'] for r in evidence),'cache_reads_total':0,'failures':0}
    dump(out/'diagnostics.json',diagnostics)
    # Prespecified gates, in priority order.
    both_weak = all(macro['gains:'+b]<0 and intervals['gains:'+b]['task_cluster_95'][1]<.01 for b in ('U','T'))
    sign_changes = any(v['delta_T_minus_U']<=0 for v in leave_one) if macro['delta_T_minus_U']>0 else any(v['delta_T_minus_U']>=0 for v in leave_one)
    gate = {'both_weak_vs_stop':both_weak,'all_T_minus_U_positive':macro['delta_T_minus_U']>0,
        'every_leave_one_T_minus_U_positive':all(v['delta_T_minus_U']>0 for v in leave_one),
        'D_harm_positive_and_at_least_D_missed':macro['D_harm']>0 and macro['D_harm']>=macro['D_missed'],
        'leave_one_direction_changes_or_touches_zero':sign_changes,'margin':.01}
    gate['eligible_for_D2_registration'] = not both_weak and gate['all_T_minus_U_positive'] and gate['every_leave_one_T_minus_U_positive'] and gate['D_harm_positive_and_at_least_D_missed']
    if both_weak:
        decision = 'End current one-query-gain direction; next proposal may preregister a fixed-sequence prefix quality-cost curve.'
    elif sign_changes:
        decision = 'Retain C0; end this development decision and inspect influential task evidence before any new strategy.'
    elif gate['eligible_for_D2_registration']:
        decision = 'D1 gates support registering one D2 development probe in a separate wave; current wave ends with D1.'
    else:
        decision = 'End H1→H2 branch and retain C0; record the alternative explanation supported by the decomposition.'
    summary = {'status':'success','experiment_id':'selection-prefix-value-d1','jobs':850,'tasks':26,
        'pools':425,'selections':2550,'macro':macro,'intervals':intervals,'gates':gate,
        'decision':decision,'per_job_primary_counts':dict(Counter(r['primary_outcome'] for r in evidence)),
        'per_task_primary_counts':dict(Counter(direction(t['metrics']['delta_T_minus_U']) for t in per_task)),
        'pool_size_counts':dict(Counter(r['n'] for r in evidence)),
        'same_next_edge_jobs':sum(r['same_next_edge'] for r in evidence),
        'leave_one_range':[min(r['delta_T_minus_U'] for r in leave_one),max(r['delta_T_minus_U'] for r in leave_one)],
        'costs':{'logical_reads':{b:sum(sealed[(j['job_id'],b)]['logical_reads'] for j in jobs) for b in ('S','U','T')},
                 'cache_reads':0,'failures':0,'new_API_calls':0,'candidate_training':0,'GPU':0},
        'scope':'Fixed previously inspected 26-task development bank, 425 pools and two paired seeds; task bootstrap describes task-composition variation. Preserved one original judge draw; execution labels are historical, direction-normalized scores.',
        'limitations':['D1 compares the complete old active edge rule against random at the first post-chain query.',
            'Two seeds are paired repeats rather than independent task corpora.',
            'Conditional diagnostic strata describe associations; raw utility scales differ across tasks.',
            'No new-task, online-agent, retraining, judge-repeat or monetary-cost effect is estimated.',
            'AI Scientist-style records are local scripts and numbered run artifacts; native launcher integration remains a separate task.'],
        'seal_sha256':sha(out/'selection_seal.json'),'full_length_verification_sha256':sha(out/'full_length_verification.json')}
    dump(out/'summary.json',summary)
    return summary

class Tee:
    def __init__(self,*streams):self.streams=streams
    def write(self,s):
        for f in self.streams:f.write(s);f.flush()
    def flush(self):
        for f in self.streams:f.flush()

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out_dir',required=True)
    p.add_argument('--internal-select',action='store_true',help=argparse.SUPPRESS)
    args=p.parse_args()
    out=Path(args.out_dir).resolve()
    if args.internal_select:
        selection_worker(out)
        return
    check(not out.exists(),'Output directory exists; choose a new numbered directory')
    out.mkdir(parents=True)
    started=time.monotonic()
    source=Path(__file__).resolve()
    (out/'experiment.py').write_bytes(source.read_bytes())
    (out/'command.json').write_text(json.dumps({'argv':sys.argv,'cwd':str(Path.cwd()),
        'python_executable':sys.executable,'python_version':platform.python_version(),
        'platform':platform.platform(),'started_utc':utc(),'deadline_seconds':600,
        'script_source':str(source),'snapshot_sha256':sha(out/'experiment.py')},indent=2)+'\n')
    def deadline(signum,frame):raise TimeoutError('600-second analysis invocation limit')
    signal.signal(signal.SIGALRM,deadline)
    signal.alarm(600)
    summary=None
    try:
        with (out/'stdout.log').open('w') as log, contextlib.redirect_stdout(Tee(sys.stdout,log)):
            entries=verify_inputs()
            dump(out/'input_manifest.json',entries)
            receipt=subprocess.run([sys.executable,'-B','-m','reproduction.research_env_v1','status','--json'],cwd=ROOT,
                text=True,capture_output=True,timeout=max(1,600-(time.monotonic()-started)))
            (out/'environment_status.stdout.json').write_text(receipt.stdout)
            (out/'environment_status.stderr.log').write_text(receipt.stderr)
            check(receipt.returncode==0,'Environment status failed')
            command=[sys.executable,'-B',str(out/'experiment.py'),'--out_dir',str(out),'--internal-select']
            dump(out/'selection_command.json',command)
            worker=subprocess.run(command,cwd=ROOT,text=True,capture_output=True,
                timeout=max(1,600-(time.monotonic()-started)))
            (out/'selection.stdout.log').write_text(worker.stdout)
            (out/'selection.stderr.log').write_text(worker.stderr)
            print(worker.stdout,end='')
            check(worker.returncode==0,'Selection worker failed; see selection stderr')
            summary=score(out)
            verify_inputs()
            check(sha(source)==sha(out/'experiment.py'),'Source changed during invocation')
            summary['wall_seconds']=time.monotonic()-started
            summary['finished_utc']=utc()
            summary['script_sha256']=sha(out/'experiment.py')
            dump(out/'final_info.json',summary)
            (out/'notes.md').write_text('# D1 execution notes\n\n'+summary['decision']+'\n\n'
                'Primary T−U: '+str(summary['intervals']['delta_T_minus_U'])+'\n\n'
                'S is chain-only; U adds the recorded random edge; T adds the recorded old-active edge. '
                'Positive T−U means higher regret for T. All 850 jobs are paired, 26 tasks weighted equally. '
                '10,000 paired task-cluster resamples use seed 20261108093; percentile interpolation matches the frozen scorer.\n\n'
                'Selection process projects only five trace fields and seals 2,550 choices in a separate process. '
                'Evaluator opens labels and historical selected/metrics after seal, verifies 1,700 full branches first, '
                'then scores prefixes. Full protected input hashes are checked before and after analysis.\n\n'
                'Strata report represented-task conditional means and additive contributions with all 26 tasks as denominator. '
                'Opponent-degree summaries count one focal incidence for each queried endpoint in the chain-top set. '
                'Outcome counts use the frozen 1e-12 descriptive tolerance; gain/harm decomposition uses unrounded values.\n\n'
                'Records follow the AI Scientist numbered-run/snapshot/final_info convention through local execution. '
                'Resource use: one local CPU diagnostic; new API, training and GPU use are zero.\n')
            print(json.dumps({'status':'success','wall_seconds':summary['wall_seconds'],
                'primary':summary['intervals']['delta_T_minus_U'],'decision':summary['decision']},ensure_ascii=False,indent=2))
    except BaseException as exc:
        (out/'failure.log').write_text(traceback.format_exc())
        dump(out/'final_info.json',{'status':'failed','error':type(exc).__name__+': '+str(exc),
            'finished_utc':utc(),'wall_seconds':time.monotonic()-started,'new_API_calls':0,
            'candidate_training':0,'GPU':0,'script_sha256':sha(out/'experiment.py')})
        raise
    finally:
        signal.alarm(0)
        dump(out/'output_manifest.json',{str(f.relative_to(out)):sha(f) for f in sorted(out.rglob('*')) if f.is_file() and f.name!='output_manifest.json'})

if __name__=='__main__':main()
