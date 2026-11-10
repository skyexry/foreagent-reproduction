#!/usr/bin/env python3
"""J1: evaluator-only strict-error correction on the frozen full random graph."""
import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
from fractions import Fraction
import gzip
import hashlib
import json
import math
from pathlib import Path
import platform
import random
import shlex
import shutil
import signal
import statistics
import subprocess
import sys
import time
import traceback

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
PROTOCOL_PATH = ROOT / 'experiments/selection-frontier-01/protocol.json'
PROTOCOL_SHA = 'fbd9f027a7f2afdce09b24927825df21f8714e864ba1c996e1e0a2a010fe1100'
sys.path.insert(0, str(ROOT))
sys.dont_write_bytecode = True


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def dump(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n')


def jsonl(path, rows):
    with Path(path).open('w') as stream:
        for row in rows:
            stream.write(json.dumps(row, sort_keys=True, ensure_ascii=False, allow_nan=False) + '\n')


def utc():
    return datetime.now(timezone.utc).isoformat()


def close(a, b):
    return math.isclose(a, b, rel_tol=1e-12, abs_tol=1e-12)


def independent_top(ids, feedback):
    # Independent integer-ratio comparison, including frozen degree tie-break.
    wins, degree = Counter(), Counter()
    for a, b, winner in feedback:
        if winner is not None:
            wins[winner] += 1
            degree[a] += 1
            degree[b] += 1
    best, chosen = None, []
    for candidate in ids:
        numerator, denominator = (wins[candidate], degree[candidate]) if degree[candidate] else (1, 2)
        key = (numerator, denominator, degree[candidate])
        if best is None:
            relation = 1
        else:
            relation = numerator * best[1] - best[0] * denominator
            if relation == 0:
                relation = degree[candidate] - best[2]
        if relation > 0:
            best, chosen = key, [candidate]
        elif relation == 0:
            chosen.append(candidate)
    return chosen


def independent_score(ids, selected, utility):
    best, worst = max(utility[i] for i in ids), min(utility[i] for i in ids)
    mean = math.fsum(utility[i] for i in selected) / len(selected)
    regret = 0 if best == worst else math.fsum(best - utility[i] for i in selected) / len(selected) / (best - worst)
    return {'regret': regret, 'best_hit': sum(utility[i] == best for i in selected) / len(selected),
            'mean_utility': mean, 'pool_best': best, 'pool_worst': worst, 'pool_range': best - worst}


def bootstrap(values, seed, repeats, percentile):
    rng = random.Random(seed)
    samples = [statistics.fmean(rng.choices(values, k=len(values))) for _ in range(repeats)]
    return {'mean': statistics.fmean(values), 'task_cluster_percentile_95': [percentile(samples, .025), percentile(samples, .975)],
            'seed': seed, 'repeats': repeats, 'resampling_unit': 'paired complete task', 'tasks': len(values)}


def outcome(value):
    return 'improved' if value > 1e-12 else 'worsened' if value < -1e-12 else 'equal'


def candidate_table(ids, trace, utility, selected):
    wins, degree = Counter(), Counter()
    for a, b, winner in trace:
        if winner is not None:
            degree[a] += 1
            degree[b] += 1
            wins[winner] += 1
    return [{'candidate': i, 'utility': utility[i], 'wins': wins[i], 'valid_degree': degree[i],
             'win_fraction': str(Fraction(wins[i], degree[i]) if degree[i] else Fraction(1, 2)),
             'selected': i in selected} for i in ids]


def analyze(out):
    from reproduction.clean_ranking_v1.ranking import allocate, top_set
    from reproduction.clean_ranking_v1.run import evaluate, percentile
    start = time.monotonic()
    assert sha(PROTOCOL_PATH) == PROTOCOL_SHA, 'Preregistered protocol SHA changed'
    protocol = json.loads(PROTOCOL_PATH.read_text())
    inputs = {str(PROTOCOL_PATH.relative_to(ROOT)): {'expected': PROTOCOL_SHA, 'actual': sha(PROTOCOL_PATH)}}
    for name, expected in protocol['frozen_sha256'].items():
        inputs[name] = {'expected': expected, 'actual': sha(ROOT / name)}
        assert inputs[name]['actual'] == expected, 'Frozen input/source changed: ' + name
    # Also record the transitive scoring import sources used by this invocation.
    for name in ('reproduction/clean_ranking_v1/__init__.py', 'reproduction/clean_ranking_v1/data.py',
                 'reproduction/clean_ranking_v1/correctness.py', 'reproduction/clean_ranking_v1/loader.py'):
        inputs[name] = {'actual': sha(ROOT / name), 'binding': 'recorded transitive import; protected manifest verified separately'}
    inputs['experiment.py'] = {'actual': sha(Path(__file__)), 'snapshot': sha(out / 'experiment.snapshot.py')}
    assert inputs['experiment.py']['actual'] == inputs['experiment.py']['snapshot']
    dump(out / 'input_sha256.json', inputs)
    shutil.copyfile(PROTOCOL_PATH, out / 'protocol.snapshot.json')
    jobs = [json.loads(line) for line in (ROOT / 'experiments/clean-ranking-v1/prepared/jobs.jsonl').read_text().splitlines()]
    by_id = {j['job_id']: j for j in jobs}
    assert len(jobs) == len(by_id) == protocol['population']['jobs'] == 850
    with gzip.open(ROOT / 'experiments/clean-ranking-v1/results/decisions.jsonl.gz', 'rt') as stream:
        rows = [json.loads(line) for line in stream]
    rows = [r for r in rows if r['method'] == 'coverage_random']
    recorded = {r['job_id']: r for r in rows}
    assert len(rows) == len(recorded) == 850 and set(recorded) == set(by_id)
    prior = json.loads((ROOT / 'experiments/clean-ranking-v1/results/summary.json').read_text())
    sealed = []
    # Phase 1 rebuilds the complete original graph and choices before reading labels.
    for job in jobs:
        row = recorded[job['job_id']]
        assert all(row[k] == job[k] for k in ('task', 'pool_id', 'repeat'))
        trace = row['trace']
        ids, edges = job['ids'], []
        assert len(ids) == len(set(ids))
        assert len(trace) == min(job['budget'], len(ids) * (len(ids) - 1) // 2)
        assert len(trace) == row['stats']['unique_feedback_reads'] == row['stats']['comparison_records']
        assert row['stats']['cache_reads'] == row['stats']['budget_denials'] == 0
        assert set(row['stats']) == {'unique_feedback_reads', 'comparison_records', 'cache_reads', 'budget_denials'}
        for event in trace:
            a, b, winner = event['a'], event['b'], event['winner']
            assert a in ids and b in ids and a != b and winner in (None, a, b)
            assert winner is None or event['confidence'] >= protocol['fixed']['gate']
            edges.append(tuple(sorted((a, b))))
        assert len(edges) == len(set(edges))
        cursor = [0]
        def original_query(a, b):
            event = trace[cursor[0]]
            assert (a, b) == (event['a'], event['b']), 'Frozen random schedule mismatch'
            cursor[0] += 1
            return event['winner']
        selected, reconstructed = allocate(ids, original_query, job['budget'], job['seed'], 'coverage_random')
        assert cursor[0] == len(trace)
        assert selected == row['selected'] == top_set(ids, reconstructed) == independent_top(ids, reconstructed)
        sealed.append({'job_id': job['job_id'], 'selected': selected, 'trace': reconstructed})
    jsonl(out / 'original_selections.sealed.jsonl', sealed)
    seal_sha = sha(out / 'original_selections.sealed.jsonl')
    print('Original choices and complete direction-independent schedules reconstructed: 850/850', flush=True)
    labels = json.loads((ROOT / 'experiments/clean-ranking-v1/prepared/evaluation_labels.json').read_text())
    episodes, edge_rows, cases = [], [], {}
    global_counts, distinct = Counter(), defaultdict(set)
    for number, job in enumerate(jobs):
        row, ids, utility = recorded[job['job_id']], job['ids'], labels[job['task']]
        assert all(math.isfinite(utility[i]) for i in ids)
        original, corrected, counts, episode_edges = [], [], Counter(), []
        for step, event in enumerate(row['trace'], 1):
            a, b, winner = event['a'], event['b'], event['winner']
            valid, tie = winner is not None, utility[a] == utility[b]
            strict_error = valid and utility[winner] < max(utility[a], utility[b])
            new_winner = max((a, b), key=lambda i: utility[i]) if strict_error else winner
            category = 'abstained' if not valid else 'valid_true_tie' if tie else 'valid_strict_error' if strict_error else 'valid_strict_correct'
            counts[category] += 1
            counts['queries'] += 1
            counts['valid'] += int(valid)
            counts['true_ties_all_queried'] += int(tie)
            original.append((a, b, winner))
            corrected.append((a, b, new_winner))
            edge = {'job_id': job['job_id'], 'task': job['task'], 'pool_id': job['pool_id'], 'repeat': job['repeat'],
                    'step': step, 'a': a, 'b': b, 'confidence': event['confidence'], 'source_group_index': event['source_group_index'],
                    'original_winner': winner, 'corrected_winner': new_winner, 'utility_a': utility[a], 'utility_b': utility[b],
                    'true_tie': tie, 'strict_error_corrected': strict_error, 'classification': category, 'unique_read_cost_each_arm': 1}
            edge_rows.append(edge)
            episode_edges.append(edge)
            key = (job['task'], *sorted((a, b)))
            distinct['queries'].add(key)
            distinct[category].add(key)
            if valid:
                distinct['valid'].add(key)
            assert (winner is None) == (new_winner is None)
            assert not tie or winner == new_winner
            assert not valid or utility[new_winner] >= utility[winner]
        original_selected = top_set(ids, original)
        corrected_selected = top_set(ids, corrected)
        assert original_selected == row['selected'] == independent_top(ids, original)
        assert corrected_selected == independent_top(ids, corrected)
        # Rebuild using corrected winners: every ordered endpoint must remain identical.
        cursor = [0]
        def corrected_query(a, b):
            event = corrected[cursor[0]]
            assert (a, b) == event[:2]
            cursor[0] += 1
            return event[2]
        selected_check, trace_check = allocate(ids, corrected_query, job['budget'], job['seed'], 'coverage_random')
        assert selected_check == corrected_selected and trace_check == corrected
        scores = {}
        for arm, selected in (('original', original_selected), ('corrected', corrected_selected)):
            frozen = evaluate(ids, selected, utility)
            independent = independent_score(ids, selected, utility)
            assert all(close(frozen[k], independent[k]) for k in ('regret', 'best_hit'))
            scores[arm] = {**independent, **frozen, **row['stats']}
        assert all(close(scores['original'][k], row['metrics'][k]) for k in row['metrics'])
        gain = scores['original']['regret'] - scores['corrected']['regret']
        hit_gain = scores['corrected']['best_hit'] - scores['original']['best_hit']
        raw_gain = scores['corrected']['mean_utility'] - scores['original']['mean_utility']
        changed = set(original_selected) != set(corrected_selected)
        status = outcome(gain)
        episode = {'frozen_job_order': number, 'job_id': job['job_id'], 'task': job['task'], 'pool_id': job['pool_id'],
                   'repeat': job['repeat'], 'seed': job['seed'], 'candidate_count': len(ids), 'ids': ids,
                   'original_selected': original_selected, 'corrected_selected': corrected_selected,
                   'original': scores['original'], 'corrected': scores['corrected'], 'regret_gain': gain,
                   'best_hit_gain': hit_gain, 'raw_utility_gain': raw_gain, 'outcome': status, 'set_changed': changed,
                   'original_selection_tied': len(original_selected) > 1, 'corrected_selection_tied': len(corrected_selected) > 1,
                   'counts': dict(counts)}
        episodes.append(episode)
        global_counts.update(counts)
        global_counts['episodes_with_strict_error'] += counts['valid_strict_error'] > 0
        global_counts['set_changed'] += changed
        global_counts['set_changed_with_error'] += changed and counts['valid_strict_error'] > 0
        global_counts['original_selection_tied'] += len(original_selected) > 1
        global_counts['corrected_selection_tied'] += len(corrected_selected) > 1
        global_counts[status] += 1
        assert not changed or counts['valid_strict_error'] > 0
        if status not in cases:
            cases[status] = {'selection_rule': 'first in frozen jobs.jsonl order for this outcome', 'episode': episode,
                             'edges': episode_edges, 'original_candidate_table': candidate_table(ids, original, utility, original_selected),
                             'corrected_candidate_table': candidate_table(ids, corrected, utility, corrected_selected)}
    grouped = defaultdict(list)
    for episode in episodes:
        grouped[episode['task']].append(episode)
    assert len(grouped) == 26
    tasks = []
    metric_keys = ('regret', 'best_hit', 'unique_feedback_reads', 'cache_reads', 'budget_denials')
    for task in sorted(grouped):
        records = grouped[task]
        arms = {arm: {key: statistics.fmean(r[arm][key] for r in records) for key in metric_keys}
                for arm in ('original', 'corrected')}
        assert all(close(arms['original'][key], prior['per_task'][task]['coverage_random'][key]) for key in metric_keys)
        task_counts = Counter()
        for record in records:
            task_counts.update(record['counts'])
            task_counts[record['outcome']] += 1
            task_counts['set_changed'] += record['set_changed']
        tasks.append({'task': task, 'episodes': len(records), 'pools': len({r['pool_id'] for r in records}), **arms,
                      'regret_gain': statistics.fmean(r['regret_gain'] for r in records),
                      'best_hit_gain': statistics.fmean(r['best_hit_gain'] for r in records),
                      'raw_utility_gain': statistics.fmean(r['raw_utility_gain'] for r in records),
                      'pool_range_mean': statistics.fmean(r['original']['pool_range'] for r in records),
                      'counts': dict(task_counts)})
    macro = {arm: {key: statistics.fmean(t[arm][key] for t in tasks) for key in metric_keys} for arm in ('original', 'corrected')}
    assert all(close(macro['original'][key], prior['macro']['coverage_random'][key]) for key in metric_keys)
    fixed = protocol['fixed']
    inference = {key: bootstrap([t[key] for t in tasks], fixed['bootstrap_seed'], fixed['paired_task_bootstrap_repeats'], percentile)
                 for key in ('regret_gain', 'best_hit_gain')}
    inference['corrected_residual_regret'] = bootstrap([t['corrected']['regret'] for t in tasks], fixed['bootstrap_seed'], fixed['paired_task_bootstrap_repeats'], percentile)
    inference['regret_gain']['tasks_improved'] = sum(outcome(t['regret_gain']) == 'improved' for t in tasks)
    inference['regret_gain']['tasks_equal'] = sum(outcome(t['regret_gain']) == 'equal' for t in tasks)
    inference['regret_gain']['tasks_worsened'] = sum(outcome(t['regret_gain']) == 'worsened' for t in tasks)
    # The same task draw indices are used for every paired endpoint.
    ltoo = [{'omitted_task': task['task'], 'regret_gain': statistics.fmean(t['regret_gain'] for t in tasks if t != task)} for task in tasks]
    rates = {'valid_strict_error_per_valid_query': global_counts['valid_strict_error'] / global_counts['valid'],
             'valid_strict_error_per_valid_nontie_query': global_counts['valid_strict_error'] / (global_counts['valid'] - global_counts['valid_true_tie']),
             'valid_strict_error_per_all_queries': global_counts['valid_strict_error'] / global_counts['queries'],
             'set_changed_per_episode': global_counts['set_changed'] / 850,
             'episodes_with_error_per_episode': global_counts['episodes_with_strict_error'] / 850}
    costs = {'each_arm': {'total_logical_unique_feedback_reads': global_counts['queries'],
                          'mean_logical_reads_per_episode': global_counts['queries'] / 850,
                          'task_macro_logical_reads': macro['original']['unique_feedback_reads'],
                          'cache_reads': 0, 'budget_denials': 0},
             'pairwise_logical_read_difference': 0, 'physical_new_api_calls': 0, 'candidate_training': 0, 'gpu': 0,
             'explanation': 'Each counterfactual arm inherits the exact complete original ledger; the local analysis rereads saved files only.'}
    denominators = {'planned_tasks': 26, 'included_tasks': len(tasks), 'planned_pools': 425,
                    'included_task_pool_pairs': len({(e['task'], e['pool_id']) for e in episodes}),
                    'planned_episodes': 850, 'included_episodes': len(episodes), 'selection_evaluations': len(episodes) * 2,
                    'excluded_episodes': 0, 'failed_episodes': 0, 'query_occurrences': global_counts['queries'],
                    'valid_query_occurrences': global_counts['valid'], 'valid_true_tie_occurrences': global_counts['valid_true_tie'],
                    'valid_nontie_query_occurrences': global_counts['valid'] - global_counts['valid_true_tie'],
                    'distinct_queried_task_pair_counts': {k: len(v) for k, v in distinct.items()},
                    'candidate_count_by_episode': dict(Counter(e['candidate_count'] for e in episodes))}
    checks = {'frozen_hashes_match': True, 'all_jobs_matched': 850, 'complete_random_schedules_original_rebuilt': 850,
              'complete_random_schedules_corrected_unchanged': 850, 'original_saved_selections_rebuilt': 850,
              'independent_integer_ratio_selections_match_both_arms': 1700, 'independent_scores_match_both_arms': 1700,
              'original_saved_episode_metrics_rebuilt': 850, 'original_saved_task_summaries_rebuilt': 26,
              'original_saved_macro_rebuilt': True, 'all_abstentions_preserved': True, 'all_true_tie_directions_preserved': True,
              'all_endpoint_orders_preserved': True, 'all_cost_ledgers_preserved': True, 'changed_sets_require_strict_error': True,
              'protocol_unchanged_at_end': sha(PROTOCOL_PATH) == PROTOCOL_SHA,
              'original_selections_sealed_before_label_read_sha256': seal_sha}
    for name, binding in inputs.items():
        if 'expected' in binding:
            assert sha(ROOT / name) == binding['expected'], 'Frozen input changed during run: ' + name
    summary = {'experiment_id': protocol['run_2']['id'], 'protocol_sha256': PROTOCOL_SHA, 'macro': macro,
               'primary_regret_gain_original_minus_corrected': inference['regret_gain'],
               'paired_best_hit_gain_corrected_minus_original': inference['best_hit_gain'],
               'corrected_residual_regret': inference['corrected_residual_regret'], 'counts': dict(global_counts),
               'rates': rates, 'denominators': denominators, 'costs': costs, 'checks': checks,
               'elapsed_analysis_seconds': time.monotonic() - start,
               'scope': 'One evaluator-side counterfactual on a fixed previously inspected development graph; existing execution labels define utility.',
               'identification_limits': ['Potential gain is conditional on this exact full random graph, gate, top_set and saved execution labels.',
                   'A feasible learned judge and a theoretical upper bound require separate evidence.',
                   'Residual combines graph missingness, unchanged abstentions, frozen aggregation and preserved true ties; their individual contributions remain unidentified.',
                   'Candidate generation quality, execution-label noise, actual rerun quality, new-task generalization, live timing/token costs and online end-to-end improvement require separate experiments.',
                   'Intervals describe resampling of 26 development tasks; repeated judge feedback and candidate execution variability are outside this resampling.']}
    jsonl(out / 'per_episode.jsonl', episodes)
    jsonl(out / 'per_edge.jsonl', edge_rows)
    dump(out / 'per_task.json', tasks)
    dump(out / 'predefined_cases.json', cases)
    dump(out / 'leave_one_task_out.json', ltoo)
    dump(out / 'summary.json', summary)
    dump(out / 'checks.json', checks)
    # Compact flat views complement complete JSON records.
    import csv
    with (out / 'per_task.csv').open('w', newline='') as stream:
        keys = ['task', 'episodes', 'pools', 'original_regret', 'corrected_regret', 'regret_gain', 'original_best_hit', 'corrected_best_hit', 'best_hit_gain', 'reads', 'valid', 'strict_errors', 'improved', 'equal', 'worsened', 'set_changed', 'raw_utility_gain', 'pool_range_mean']
        writer = csv.DictWriter(stream, keys)
        writer.writeheader()
        for t in tasks:
            writer.writerow({key: t[key] for key in ('task', 'episodes', 'pools', 'regret_gain', 'best_hit_gain', 'raw_utility_gain', 'pool_range_mean')} |
                            {'original_regret': t['original']['regret'], 'corrected_regret': t['corrected']['regret'], 'original_best_hit': t['original']['best_hit'], 'corrected_best_hit': t['corrected']['best_hit'], 'reads': t['counts']['queries'], 'valid': t['counts']['valid'], 'strict_errors': t['counts'].get('valid_strict_error', 0), **{k: t['counts'].get(k, 0) for k in ('improved', 'equal', 'worsened', 'set_changed')}})
    return summary


def write_notes(out, summary):
    s, gain, residual = summary, summary['primary_regret_gain_original_minus_corrected'], summary['corrected_residual_regret']
    original, corrected = s['macro']['original'], s['macro']['corrected']
    cases = json.loads((out / 'predefined_cases.json').read_text())
    case_text = '\n'.join(f"- {label}: `{case['episode']['job_id']}`，损失 {case['episode']['original']['regret']:.8f} → {case['episode']['corrected']['regret']:.8f}，纠正 {case['episode']['counts'].get('valid_strict_error', 0)} 条严格错边。" for label, case in cases.items())
    counts, denom = s['counts'], s['denominators']
    notes = f'''# J1 完整随机赛程中的方向纠正诊断

任务等权损失由 **{original['regret']:.8f}** 变为 **{corrected['regret']:.8f}**。预注册主差（原始−纠正）为 **{gain['mean']:.8f}**，95%任务簇区间 **{gain['task_cluster_percentile_95']}**。固定图上的裁判严格错向纠正呈现的潜在收益方向与预测一致。

最佳命中率由 {original['best_hit']:.8f} 变为 {corrected['best_hit']:.8f}；配对差（纠正−原始）为 {s['paired_best_hit_gain_corrected_minus_original']['mean']:.8f}，95%任务簇区间 {s['paired_best_hit_gain_corrected_minus_original']['task_cluster_percentile_95']}。

## 冻结控制与分母

- 全部26开发任务、425池、850场、1700次派生评分；排除0场，失败0场。各池两次种子共享语料，以任务为重采样簇。
- `coverage_random` 完整原始赛程先独立重建并封存，之后读取评分标签。原选择、850场指标、26任务指标和宏平均均与冻结记录一致。纠正臂使用同一 `top_set` 和 `evaluate`，另以整数交叉乘法排名、独立公式评分核对。
- 查询发生次数 {denom['query_occurrences']}，其中有效 {denom['valid_query_occurrences']}，弃权 {counts['abstained']}，有效真实并列 {denom['valid_true_tie_occurrences']}；有效严格错向 {counts['valid_strict_error']}，占有效查询 {s['rates']['valid_strict_error_per_valid_query']:.4%}，占有效非并列查询 {s['rates']['valid_strict_error_per_valid_nontie_query']:.4%}。
- 所有已查询端点及顺序、confidence、真实并列原方向、弃权和成本保持。纠正仅应用于有效反馈中胜者严格劣于另一端点的边。
- 场次改善 {counts['improved']}、持平 {counts['equal']}、恶化 {counts['worsened']}；选择集合改变 {counts['set_changed']}/850。任务改善/持平/恶化：{gain['tasks_improved']}/{gain['tasks_equal']}/{gain['tasks_worsened']}。恶化结果完整保留，提示固定胜率汇总与图结构间存在交互。
- 每臂逻辑唯一读取总数 {s['costs']['each_arm']['total_logical_unique_feedback_reads']}，场均 {s['costs']['each_arm']['mean_logical_reads_per_episode']:.8f}，任务等权 {s['costs']['each_arm']['task_macro_logical_reads']:.8f}；配对成本差0。新增API、候选训练、GPU均0。

## 预定案例

按冻结 `jobs.jsonl` 顺序分别取首个改善、恶化和持平场；详见 `predefined_cases.json` 的全边记录、候选效用、胜场、有效度数和选择集合。案例用于解释该场。

{case_text}

## 残余与解释范围

纠正后任务等权残余损失 **{residual['mean']:.8f}**，95%任务簇区间 {residual['task_cluster_percentile_95']}。残余由缺边、保留弃权、固定汇总和保留真实并列方向共同形成；本设计识别这些模块的合计条件结果，各模块单独份额留待单因素对照。

主差是这个已查看开发银行、完整随机图、0.7门槛和固定汇总下的评价侧潜在收益。可实现学习裁判的实际收益、理论上界、标签重复执行噪声、新任务泛化、生成质量、线上时延/token成本和端到端Agent收益分别需要后续证据。10,000次配对任务簇percentile区间使用锁定种子20261108093，反映开发任务组成波动。

## 复跑与收据

从项目根目录：`python3 -B experiments/selection-frontier-01/j1/experiment.py --out_dir=run_2`。每次使用独立的新目录名；`experiment.snapshot.py`为运行前脚本快照，`command.json`记录命令、启动时刻、Python、平台和Git基点；`input_sha256.json`绑定冻结输入与脚本，`output_sha256.json`绑定产物，`run.log`与`failure.log`保留运行记录。脚本使用本机CPU并设置600秒上限。`final_info.json`记录最终状态与耗时。
'''
    (out / 'notes.md').write_text(notes)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out_dir', required=True)
    args = parser.parse_args()
    out = (HERE / args.out_dir).resolve()
    if out.parent != HERE or out.exists():
        raise ValueError('Use a fresh direct child output directory under j1')
    out.mkdir()
    shutil.copyfile(Path(__file__), out / 'experiment.snapshot.py')
    began_utc, began = utc(), time.monotonic()
    command = {'argv': sys.argv, 'shell_command': shlex.join([sys.executable, '-B', *sys.argv]), 'cwd': str(Path.cwd()),
               'started_utc': began_utc, 'python': sys.version, 'platform': platform.platform(), 'max_seconds': 600,
               'git_branch': subprocess.check_output(['git', '-C', str(ROOT), 'branch', '--show-current'], text=True).strip(),
               'git_head': subprocess.check_output(['git', '-C', str(ROOT), 'rev-parse', 'HEAD'], text=True).strip(),
               'script_sha256': sha(Path(__file__)), 'snapshot_sha256': sha(out / 'experiment.snapshot.py'),
               'execution_mode': 'local CPU evaluator-only replay; AI Scientist organization; native launcher adaptation remains separate'}
    dump(out / 'command.json', command)
    (out / 'failure.log').write_text('')
    def stop(signum, frame):
        raise TimeoutError('Analysis invocation exceeded 600-second protocol cap')
    signal.signal(signal.SIGALRM, stop)
    signal.alarm(600)
    status, summary, error = 'failed', None, None
    try:
        with (out / 'run.log').open('w') as log:
            original_stdout = sys.stdout
            class Tee:
                def write(self, text):
                    log.write(text)
                    original_stdout.write(text)
                def flush(self):
                    log.flush()
                    original_stdout.flush()
            sys.stdout = Tee()
            try:
                print('J1 started ' + began_utc, flush=True)
                summary = analyze(out)
                write_notes(out, summary)
                print(json.dumps({k: summary[k] for k in ('macro', 'primary_regret_gain_original_minus_corrected', 'paired_best_hit_gain_corrected_minus_original', 'corrected_residual_regret', 'counts', 'denominators', 'costs')}, ensure_ascii=False, indent=2), flush=True)
                status = 'success'
                print('J1 successful ' + utc(), flush=True)
            finally:
                sys.stdout = original_stdout
    except BaseException:
        error = traceback.format_exc()
        (out / 'failure.log').write_text(error)
    finally:
        signal.alarm(0)
        final = {'experiment_id': 'judge-direction-diagnostic-j1', 'status': status, 'started_utc': began_utc,
                 'ended_utc': utc(), 'elapsed_wall_seconds': time.monotonic() - began, 'max_seconds': 600,
                 'protocol_sha256': PROTOCOL_SHA, 'script_sha256': command['script_sha256'],
                 'new_api_calls': 0, 'candidate_training': 0, 'gpu': 0, 'error': error,
                 'results': summary, 'hash_manifest_scope': 'All output files except output_sha256.json itself, which would require a self hash.'}
        dump(out / 'final_info.json', final)
        dump(out / 'output_sha256.json', {str(p.relative_to(out)): sha(p) for p in sorted(out.rglob('*')) if p.is_file() and p.name != 'output_sha256.json'})
    if error:
        raise RuntimeError(error)


if __name__ == '__main__':
    main()
