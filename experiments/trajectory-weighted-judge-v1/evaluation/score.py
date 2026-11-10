"""Score only a sealed complete tournament and prediction grid; bootstrap over tasks."""
import argparse
from collections import Counter, defaultdict
import gzip
import json
import random
from pathlib import Path
from statistics import fmean
from replay import (ARMS, EXP, FRONTIER, HERE, PRED_SEAL, PREP, PROTOCOL_SHA, ROOT,
                    banks, checked, frozen, predictions, read, records, require, sha, write)
from reproduction.clean_ranking_v1.correctness import response_values
from reproduction.clean_ranking_v1.run import evaluate, percentile

METRICS = ('regret', 'best_hit', 'unique_reads', 'accepted_reads', 'cache_reads', 'budget_denials',
           'read_edge_fraction', 'accepted_edge_fraction', 'accepted_candidate_fraction',
           'best_candidate_accepted_fraction', 'selected_size')
ALL = ('C0', *ARMS)
SEED = 20261108093


def episode(job, row, scores):
    ids = job['ids']
    best = max(scores[cid] for cid in ids)
    worst = min(scores[cid] for cid in ids)
    winners = {cid for cid in ids if scores[cid] == best}
    selected = row['selected']
    metrics = evaluate(ids, selected, scores)
    independent = (best - fmean(scores[cid] for cid in selected))/(best-worst) if best > worst else 0.
    require(abs(metrics['regret'] - independent) < 1e-10 and
            abs(metrics['best_hit'] - len(set(selected) & winners)/len(selected)) < 1e-12, 'Independent scorer')
    trace, stats = row['trace'], row['stats']
    accepted = [edge for edge in trace if edge['winner'] is not None]
    touched = {edge[k] for edge in accepted for k in ('a', 'b')}
    strict = [edge for edge in accepted if scores[edge['a']] != scores[edge['b']]]
    correct = sum(scores[e['winner']] == max(scores[e['a']], scores[e['b']]) for e in strict)
    possible = len(ids)*(len(ids)-1)//2
    metrics.update(unique_reads=len(trace), accepted_reads=len(accepted), cache_reads=stats['cache_reads'],
                   budget_denials=stats['budget_denials'], read_edge_fraction=len(trace)/possible,
                   accepted_edge_fraction=len(accepted)/possible, accepted_candidate_fraction=len(touched)/len(ids),
                   best_candidate_accepted_fraction=len(winners & touched)/len(winners), selected_size=len(selected),
                   accepted_strict_correct=correct, accepted_strict_total=len(strict))
    return metrics


def collapse(rows):
    out = {k: fmean(r[k] for r in rows) for k in METRICS}
    out.update({k: sum(r[k] for r in rows) for k in ('accepted_strict_correct', 'accepted_strict_total')})
    out['accepted_query_strict_accuracy'] = (out['accepted_strict_correct']/out['accepted_strict_total']
                                               if out['accepted_strict_total'] else None)
    out['episodes'] = len(rows)
    return out


def contrast(deltas, bootstrap):
    values = list(deltas.values())
    draws = [fmean(values[i] for i in sample) for sample in bootstrap]
    loo = {key: fmean(v for k, v in deltas.items() if k != key) for key in deltas}
    return dict(gain=fmean(values), ci95=[percentile(draws, .025), percentile(draws, .975)],
                improved=sum(v > 1e-12 for v in values), worsened=sum(v < -1e-12 for v in values),
                tied=sum(abs(v) <= 1e-12 for v in values), leave_one_task_out=loo,
                leave_one_min=min(loo.values()), leave_one_max=max(loo.values()))


def summarize(data, bootstrap):
    macro = {arm: {metric: fmean(t[arm][metric] for t in data.values()) for metric in METRICS} for arm in ALL}
    contrasts = {}
    for control in ('uniform', 'gap', 'shuffled', 'C0'):
        contrasts[control] = {}
        for metric in ('regret', 'best_hit'):
            sign = 1 if metric == 'regret' else -1
            deltas = {task: sign * (item[control][metric]-item['terminal'][metric])
                      for task, item in data.items()}
            contrasts[control][metric] = contrast(deltas, bootstrap)
    vs_baseline = {}
    for arm in ARMS:
        vs_baseline[arm] = {}
        for metric in ('regret', 'best_hit'):
            sign = 1 if metric == 'regret' else -1
            deltas = {task: sign * (item['C0'][metric]-item[arm][metric]) for task,item in data.items()}
            vs_baseline[arm][metric] = contrast(deltas, bootstrap)
    return dict(macro=macro, terminal_gains=contrasts, gains_over_C0=vs_baseline)


def tally_pairs(bank, pred, labels):
    # Each strict unordered pair contributes once per task/grid. Empty C0 directions stay uncovered.
    per_task = {}
    for task, pairs in pred.items():
        groups = {group: {arm: Counter() for arm in ALL}
                  for group in ('all_code_pairs', 'archived_pairs', 'accepted_mask_pairs')}
        utility = labels[task]
        for key, model_winners in pairs.items():
            a, b = key.split('|')
            source = bank[task].get(key)
            idx, conf = response_values(source) if source else (None, 0)
            archived_winner = source['order'][idx] if idx is not None else None
            gated = idx is not None and conf >= .7
            winners = dict(model_winners, C0=archived_winner)
            for group in groups:
                if group == 'archived_pairs' and source is None or group == 'accepted_mask_pairs' and not gated:
                    continue
                for arm, winner in winners.items():
                    tally = groups[group][arm]
                    tally['pairs'] += 1
                    if utility[a] == utility[b]:
                        tally['execution_ties'] += 1
                        continue
                    tally['strict_pairs'] += 1
                    if winner is not None:
                        tally['strict_predicted'] += 1
                        tally['correct'] += utility[winner] == max(utility[a], utility[b])
        per_task[task] = groups
    totals = {}
    for group in next(iter(per_task.values())):
        totals[group] = {}
        for arm in ALL:
            counts = [task[group][arm] for task in per_task.values()]
            agg = sum(counts, Counter())
            rates = [c['correct']/c['strict_predicted'] for c in counts if c['strict_predicted']]
            totals[group][arm] = dict(agg, micro_accuracy=agg['correct']/agg['strict_predicted'],
                                      macro_accuracy=fmean(rates), tasks_with_strict_predictions=len(rates),
                                      strict_prediction_coverage=agg['strict_predicted']/agg['strict_pairs'])
    # Gate-accepted keys supply a common strict denominator for learned vs archived directions.
    accepted = totals['accepted_mask_pairs']
    for arm in ARMS:
        accepted[arm]['macro_gain_over_C0'] = accepted[arm]['macro_accuracy'] - accepted['C0']['macro_accuracy']
        accepted[arm]['micro_gain_over_C0'] = accepted[arm]['micro_accuracy'] - accepted['C0']['micro_accuracy']
    return dict(summary=totals, per_task=per_task)


def main(out):
    protocol = frozen()
    seal = read(out/'selection_seal.json')
    checked(HERE/'replay.py', seal['replay_script_sha256'])
    checked(PRED_SEAL, seal['prediction_seal_sha256'])
    records_file = checked(out/'decisions.sealed.jsonl.gz', seal['decisions_sha256'])
    rows = list(records(records_file))
    jobs = {j['job_id']: j for j in [json.loads(line) for line in (PREP/'jobs.jsonl').read_text().splitlines()]}
    gates = ['DS', *read(FRONTIER/'banks/manifest.json')['banks']]
    require({(r['bank'],r['arm'],r['job_id']) for r in rows} ==
            {(gate,arm,job) for gate in gates for arm in ALL for job in jobs} and len(rows) == 17000,
            'Incomplete or duplicate decision grid')
    require(seal['protocol_sha256'] == PROTOCOL_SHA, 'Wrong protocol')
    pred, pred_sha = predictions(read(PREP/'code_files.json'))
    require(pred_sha == seal['predictions_sha256'], 'Prediction/selection seals disagree')
    label_file = PREP/'evaluation_labels.json'
    labels = read(checked(label_file, protocol['inputs'][str(label_file.relative_to(ROOT))]))
    tasks = sorted(labels)
    rng = random.Random(SEED)
    bootstrap = [rng.choices(range(len(tasks)), k=len(tasks)) for _ in range(10000)]
    baseline = ROOT/'experiments/clean-ranking-v1/results/decisions.jsonl.gz'
    frozen_ds = {r['job_id']: r for r in records(checked(baseline, protocol['inputs'][str(baseline.relative_to(ROOT))]))
                 if r['method'] == 'corrected_tournament'}
    reference = FRONTIER/'c0-final-selection/run-002/per_episode.jsonl'
    checked(reference, 'ca5ec391a6d9776e5e4a73a4693548e69367cacc129fdcbcd16f936a17580f7d')
    prior = {(r['bank'],r['job_id']): r['metrics']['C'] for r in map(json.loads,reference.read_text().splitlines())}
    trajectory_by_key = {(r['bank'],r['job_id'],r['arm']):r for r in rows}
    relations = [('terminal',a) for a in ('uniform','gap','shuffled','C0')] + [('gap','uniform'),('shuffled','uniform')]
    disagreement = {g:{} for g in gates}
    for gate in gates:
        for arm,control in relations:
            changed = Counter()
            for job_id in jobs:
                original = trajectory_by_key[gate,job_id,control]
                alternative = trajectory_by_key[gate,job_id,arm]
                changed['selected_set_changes'] += set(original['selected']) != set(alternative['selected'])
                changed['queried_sequence_changes'] += (
                    [(e['a'],e['b']) for e in original['trace']] != [(e['a'],e['b']) for e in alternative['trace']])
                job = jobs[job_id]
                utility = labels[job['task']]
                def regret(row):
                    return evaluate(job['ids'], row['selected'], utility)['regret']
                gain = regret(original) - regret(alternative)
                changed['regret_improved'] += gain > 1e-12
                changed['regret_worsened'] += gain < -1e-12
                changed['regret_tied'] += abs(gain) <= 1e-12
            disagreement[gate][arm+'_vs_'+control] = changed
    pair_disagreement = {arm+'_vs_'+control:sum(w[arm] != w[control] for pairs in pred.values() for w in pairs.values())
                         for arm,control in relations if control != 'C0'}
    groups, size_groups = defaultdict(list), defaultdict(list)
    read_totals = defaultdict(Counter)
    with gzip.GzipFile(filename=str(out/'per_episode.jsonl.gz'), mode='wb', compresslevel=5, mtime=0) as stream:
        for r in rows:
            gate, arm, job_id, task = (r[k] for k in ('bank', 'arm', 'job_id', 'task'))
            job = jobs[job_id]
            require(task == job['task'], 'Job task mismatch')
            m = episode(job, r, labels[task])
            if arm == 'C0':
                for k in ('regret', 'best_hit'):
                    require(abs(m[k] - prior[gate,job_id][k]) < 1e-12, 'Four-bank reference score')
                if gate == 'DS':
                    old = frozen_ds[job_id]
                    require(all(r[k] == old[k] for k in ('trace','stats','selected')) and
                            all(abs(m[k] - old['metrics'][k]) < 1e-12 for k in ('regret','best_hit')),
                            'Original DS reference score or trajectory')
            groups[gate,task,arm].append(m)
            size_groups[gate,len(job['ids']),task,arm].append(m)
            read_totals[gate,arm].update({k:m[k] for k in ('unique_reads','accepted_reads','cache_reads','budget_denials',
                                                         'accepted_strict_correct','accepted_strict_total')})
            stream.write((json.dumps(dict(bank=gate, arm=arm, task=task, job_id=job_id, n=len(job['ids']), metrics=m),
                                     sort_keys=True, separators=(',', ':')) + '\n').encode())
    per_task = {g: {t: {arm: collapse(groups[g,t,arm]) for arm in ALL} for t in tasks} for g in gates}
    pool = {t:{arm:{k:fmean(per_task[g][t][arm][k] for g in gates[1:]) for k in METRICS} for arm in ALL} for t in tasks}
    summaries = {g:summarize(data,bootstrap) for g,data in {**per_task,'GPT_task_first_pooled':pool}.items()}
    by_size = {}
    for gate in gates:
        by_size[gate] = {}
        for n in sorted({len(job['ids']) for job in jobs.values()}):
            cell = {t:{a:collapse(size_groups[gate,n,t,a]) for a in ALL} for t in tasks if (gate,n,t,'C0') in size_groups}
            by_size[gate][n] = dict(tasks=len(cell), jobs=sum(x['C0']['episodes'] for x in cell.values()),
                task_macro={a:{m:fmean(t[a][m] for t in cell.values()) for m in METRICS} for a in ALL})
    static = {g:tally_pairs(bank,pred,labels) for g,bank in banks()}
    write(out/'pair_accuracy.json', static)
    write(out/'per_task.json', per_task)
    write(out/'per_pool_size.json', by_size)
    primary = summaries['DS']['terminal_gains']
    checks = dict(primary_gain_ge_01=primary['uniform']['regret']['gain'] >= .01,
                  every_leave_one_primary_positive=primary['uniform']['regret']['leave_one_min'] > 0,
                  better_than_gap=primary['gap']['regret']['gain'] > 0,
                  better_than_shuffled=primary['shuffled']['regret']['gain'] > 0)
    write(out/'summary.json', dict(summaries=summaries, method_gate_inputs=checks, method_gate=all(checks.values()),
         beats_actual_DS_C0=primary['C0']['regret']['gain'] > 0, fresh_task_confirmation=False,
         complete_episodes=len(rows), original_DS_match=850, prior_four_gate_C0_match=3400, bootstrap_seed=SEED,
         pair_disagreements_on_full_grid=pair_disagreement, selection_disagreements=disagreement,
         actual_read_totals={g:{a:read_totals[g,a] for a in ALL} for g in gates},
         interval_scope='26 development tasks conditional on overlapping fitted folds; descriptive, paired task bootstrap',
         paired_gains='positive favors terminal; lower regret and higher best-hit probability',
         pair_accuracy='All-code and archived C0 use parseable raw directions at any confidence, with coverage. Accepted-mask uses only valid confidence >= 0.7. Execution ties excluded from strict accuracy.',
         selection_seal_sha256=sha(out/'selection_seal.json'), score_script_sha256=sha(Path(__file__))))
    write(out/'hashes.json', {p.name:sha(p) for p in sorted(out.iterdir()) if p.is_file() and p.name != 'hashes.json'})
    print(json.dumps(dict(decision=checks, primary=primary['uniform']['regret']['gain']), indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    main(parser.parse_args().output)
