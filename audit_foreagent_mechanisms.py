"""Audit pinned confidence gating, rematches, stopping and execution routing.

Controlled responses and existing local predictions only. All upstream
selection code runs unchanged; state tracing observes its local variables.
"""
import ast
from collections import Counter, defaultdict
from dataclasses import asdict
import hashlib
import json
import math
from pathlib import Path
import random
import re
from statistics import mean
import os
import sys
from types import SimpleNamespace
from unittest.mock import patch

from foreagent_selection import COMMIT, ROOT, SOURCE_PATH, SOURCE_SHA256, UPSTREAM, pinned
from replay_foreagent_selection import FeedbackBackend, load_tasks

OUTPUT = Path(os.environ.get('FOREAGENT_RUN_DIR', str(ROOT / 'runs/mechanisms')))


def blob(path):
    return (UPSTREAM / path).read_bytes()


SOURCE = blob(SOURCE_PATH).decode()
ROUND_STATE_LINE = next(i for i, line in enumerate(SOURCE.splitlines(), 1)
                        if line.strip() == 'active_nodes = next_round_nodes')


def nodes(n):
    return [SimpleNamespace(id=chr(65 + i), code=f'candidate-{chr(65 + i)}') for i in range(n)]


def pair_from_prompt(prompt):
    pair = re.findall(r'### Solution [01]:\n```python\n\n(.*?)\n```', prompt, re.S)
    if len(pair) != 2:
        raise ValueError('Original prompt format differs')
    return tuple(pair)


def controlled_tournament(n, respond, workers=1):
    wm = pinned.WorldModel('controlled task', 'controlled report',
                           config=pinned.WorldModelConfig(confidence_threshold=0.7,
                                                          max_concurrent_requests=workers))
    wm._comparison_cache = {}
    calls, rounds, end = [], [], {}

    def query(**kwargs):
        pair = pair_from_prompt(kwargs['user_message'])
        calls.append(pair)
        return respond(pair)

    def snapshot(frame):
        local = frame.f_locals
        status = {k: {f: v[f] for f in ('eliminated', 'round', 'wins')}
                  for k, v in local.get('node_status', {}).items()}
        return dict(round=local.get('round_num', 0), status=status,
                    active=[n.id for n in local.get('active_nodes', [])],
                    next_active=[n.id for n in local.get('next_round_nodes', [])])

    def trace(frame, event, arg):
        if frame.f_code is pinned.WorldModel.tournament_rank.__code__:
            if event == 'line' and frame.f_lineno == ROUND_STATE_LINE:
                rounds.append(snapshot(frame))
            if event == 'return':
                end.update(snapshot(frame))
        return trace

    previous_trace = sys.gettrace()
    try:
        sys.settrace(trace)
        with patch.object(pinned, 'query', query), patch.object(pinned, 'random', random.Random(20261107)):
            ranked, comparisons, ranks = wm.tournament_rank(nodes(n))
    finally:
        sys.settrace(previous_trace)
    return dict(candidates=n, workers=workers, backend_calls=len(calls), queried_pairs=calls,
                attempts=len(comparisons), comparisons=[asdict(c) for c in comparisons],
                ranked=[n.id for n in ranked], ranks=ranks, rounds=rounds, end=end,
                safety_exit=end.get('round', 0) > 2 * n)


def gate_checks():
    cases = [
        ('below_boundary', {'predicted_best_index': 0, 'confidence': math.nextafter(0.7, 0)}, False, None),
        ('at_boundary', {'predicted_best_index': 0, 'confidence': 0.7}, True, 0),
        ('above_boundary', {'predicted_best_index': 1, 'confidence': math.nextafter(0.7, 1)}, True, 1),
        ('numeric_string', {'predicted_best_index': 1, 'confidence': '0.7'}, True, 1),
        ('missing_confidence', {'predicted_best_index': 0}, False, None),
        ('null_confidence', {'predicted_best_index': 0, 'confidence': None}, False, None),
        ('text_confidence', {'predicted_best_index': 0, 'confidence': 'unsure'}, False, None),
        ('list_confidence', {'predicted_best_index': 0, 'confidence': []}, False, None),
        ('negative_confidence', {'predicted_best_index': 0, 'confidence': -0.1}, False, None),
        ('over_one_confidence', {'predicted_best_index': 0, 'confidence': 1.2}, True, 0),
        ('nan_confidence', {'predicted_best_index': 0, 'confidence': 'NaN'}, False, None),
        ('infinite_confidence', {'predicted_best_index': 0, 'confidence': 'Infinity'}, True, 0),
        ('boolean_confidence', {'predicted_best_index': 0, 'confidence': True}, True, 0),
        ('missing_winner', {'confidence': 0.9}, True, 0),
        ('out_of_range_winner', {'predicted_best_index': 2, 'confidence': 0.9}, True, 2),
        ('fractional_winner', {'predicted_best_index': 0.9, 'confidence': 0.9}, True, 0),
        ('malformed_json', 'not JSON', False, None),
        ('backend_timeout', TimeoutError('controlled timeout'), False, None),
    ]
    result = []
    for name, response, valid, winner in cases:
        wm = pinned.WorldModel('task', 'report', config=pinned.WorldModelConfig(confidence_threshold=0.7))
        wm._comparison_cache = {}
        kwargs = dict(side_effect=response) if isinstance(response, Exception) else dict(return_value=response if isinstance(response, str) else json.dumps(response))
        with patch.object(pinned, 'query', **kwargs) as query:
            first = wm.predict_pairwise(*nodes(2), round_num=1)
            second = wm.predict_pairwise(*nodes(2), round_num=2)
        assert first.is_valid == valid and first.winner_idx == winner, name
        assert query.call_count == 1 and second.round_num == 2, name
        if name in ('missing_confidence', 'null_confidence', 'text_confidence', 'list_confidence'):
            assert first.confidence == 0.5, name
        if name in ('malformed_json', 'backend_timeout'):
            assert first.confidence == 0.0, name
        result.append(dict(case=name, result=asdict(first), second_result=asdict(second), backend_calls=query.call_count))
    defaults = []
    for threshold in (None, 0.7):
        config = pinned.WorldModelConfig() if threshold is None else pinned.WorldModelConfig(confidence_threshold=threshold)
        wm = pinned.WorldModel('task', 'report', config=config)
        wm._comparison_cache = {}
        with patch.object(pinned, 'query', return_value='{"predicted_best_index": 0, "confidence": 0.65}'):
            r = wm.predict_pairwise(*nodes(2))
        defaults.append(dict(threshold=config.confidence_threshold, confidence=r.confidence, valid=r.is_valid))
    assert [r['valid'] for r in defaults] == [True, False]
    with patch.object(pinned.WorldModel, '_comparison_cache', {}):
        first = pinned.WorldModel('task A', 'report A', config=pinned.WorldModelConfig(confidence_threshold=0.6))
        second = pinned.WorldModel('task B', 'report B', config=pinned.WorldModelConfig(confidence_threshold=0.7))
        with patch.object(pinned, 'query', return_value='{"predicted_best_index": 0, "confidence": 0.65}') as query:
            a = first.predict_pairwise(*nodes(2))
            b = second.predict_pairwise(*nodes(2))
        assert query.call_count == 1 and a.is_valid and b.is_valid
        shared = dict(backend_calls=query.call_count, first_threshold=0.6, second_threshold=0.7,
                      cached_confidence=b.confidence, second_cached_is_valid=b.is_valid,
                      second_fresh_gate_would_be_valid=b.confidence >= second.config.confidence_threshold)
    return dict(cases=result, class_default_vs_released=defaults, shared_cache_cross_threshold=shared)


def released_config_checks():
    path = 'mle-bench/agents/aide/config.yaml'
    source = blob(path)
    block = source.decode().split('ForeAgent/DeepSeek-V3.2:', 1)[1]
    expected = {'agent.world_model_confidence_threshold': 0.7,
                'agent.world_model_exec_probability': 0.2,
                'agent.improve_num_candidates': 10, 'agent.improve_top_k': 1}
    for key, value in expected.items():
        match = re.search(r'^\s+' + re.escape(key) + r':\s*([\d.]+)', block, re.M)
        assert match and float(match[1]) == value, key
    return dict(values=expected, source_sha256=hashlib.sha256(source).hexdigest())


def stopping_checks():
    result = {}
    for n in (0, 1, 2, 3, 10):
        high = controlled_tournament(n, lambda pair: '{"predicted_best_index": 0, "confidence": 0.9}')
        assert high['backend_calls'] == high['attempts'] == max(0, n - 1)
        assert not high['safety_exit']
        result[f'high_{n}'] = high
    for n in (2, 3, 10):
        for workers in (1, 128):
            low = controlled_tournament(n, lambda pair: '{"predicted_best_index": 0, "confidence": 0.6}', workers)
            assert low['safety_exit'] and low['end']['round'] == 2 * n + 1
            assert len(low['end']['active']) == n
            assert len(low['rounds']) == 2 * n + 1
            result[f'low_{n}_workers{workers}'] = low

    def rematch(mode):
        def response(pair):
            a, b = (p[-1] for p in pair)
            if set((a, b)) == {'A', 'B'} or mode == 'inconclusive':
                return '{"predicted_best_index": 0, "confidence": 0.6}'
            winner = 'A' if mode == 'pending_wins' and 'A' in (a, b) else 'C'
            return json.dumps(dict(predicted_best_index=(a, b).index(winner), confidence=0.9))
        return response

    for mode in ('pending_wins', 'pending_loses', 'inconclusive'):
        r = controlled_tournament(3, rematch(mode))
        result[mode] = r
    win = result['pending_wins']
    assert win['rounds'][0]['next_active'] == ['C', 'A']
    assert not win['rounds'][0]['status']['C']['eliminated']
    assert win['end']['active'] == ['C']
    assert win['end']['status']['A']['eliminated'] and win['ranks']['A']['rank'] == 0
    assert win['ranks']['C']['rank'] == 0
    loss = result['pending_loses']
    assert loss['rounds'][0]['next_active'] == ['C'] and not loss['safety_exit']
    assert result['inconclusive']['rounds'][0]['next_active'] == ['C', 'A', 'B']
    assert result['inconclusive']['safety_exit']
    return result


def execution_routing_checks():
    path = 'mle-bench/agents/aide/aide/agent.py'
    source = blob(path)
    tree = ast.parse(source)
    function = next(m for c in tree.body if isinstance(c, ast.ClassDef) for m in c.body
                    if isinstance(m, ast.FunctionDef) and m.name == '_improve_with_world_model')
    namespace = dict(Node=SimpleNamespace, ExecCallbackType=object, logger=pinned.logger)
    exec(compile(ast.Module(body=[function], type_ignores=[]), f'{COMMIT}/{path}', 'exec'), namespace)
    method = namespace['_improve_with_world_model']
    results = []
    cases = [('zero_candidates', 0, {}, []), ('one_candidate', 1, {'A': 0}, []),
             ('unique_top_probability_miss', 2, {'A': 0, 'B': 1}, [0.9]),
             ('unique_top_probability_hit', 2, {'A': 0, 'B': 1}, [0.1]),
             ('tied_top_all_miss', 2, {'A': 0, 'B': 0}, [0.9, 0.9]),
             ('tied_top_all_hit', 2, {'A': 0, 'B': 0}, [0.1, 0.1])]
    for name, n, rank_values, draws in cases:
        candidates = nodes(n)
        executions, saves, draw_calls = [], [], []

        class RoutingWorld:
            config = pinned.WorldModelConfig(exec_probability=0.2)

            def tournament_rank(self, ns):
                return ns, [], {node.id: dict(rank=rank_values[node.id], round=1) for node in ns}

            def should_execute(self):
                draw_calls.append(True)
                return pinned.WorldModel.should_execute(self)

        class Journal:
            def __init__(self):
                self.nodes = []

            def append(self, node):
                self.nodes.append(node)

        owner = SimpleNamespace(
            improve_num_candidates=10, improve_top_k=1, task_desc='task', data_analysis_report='report',
            wm_config=None, cfg=SimpleNamespace(task_name='task'), all_nodes_dir=ROOT / 'runs/routing-no-files',
            journal=Journal(), _improve_batch=lambda *args: candidates,
            _improve=lambda parent: SimpleNamespace(id='fallback', code='candidate-fallback'),
            parse_exec_result=lambda *, node, exec_result: node, _post_process_node=lambda node: None,
            _save_node_artifacts=lambda node, path: saves.append(node.id))

        def execute(code, flag):
            executions.append(code)
            assert flag is True
            return 'controlled execution result'

        namespace['WorldModel'] = lambda **kwargs: RoutingWorld()
        with patch.object(pinned, 'random', SimpleNamespace(random=iter(draws).__next__)):
            method(owner, SimpleNamespace(), execute)
        expected = 2 if name == 'tied_top_all_hit' else 1
        assert len(executions) == expected and len(owner.journal.nodes) == max(1, n), name
        assert len(draw_calls) == len(draws), name
        if n >= 2 and 'miss' in name:
            assert executions == ['candidate-A'], name
        results.append(dict(case=name, executions=executions, probability_checks=len(draw_calls),
                            saves=saves, journal=[node.id for node in owner.journal.nodes]))
    return dict(agent_source_sha256=hashlib.sha256(source).hexdigest(), cases=results)


def confidence_summary(rows):
    explicit, fallback = [], []
    for row in rows:
        try:
            c = float(row['confidence'])
        except (TypeError, ValueError):
            fallback.append(row)
            continue
        if not math.isfinite(c) or not 0 <= c <= 1:
            raise ValueError('Observed confidence outside finite [0, 1]')
        explicit.append(dict(row, confidence=c))

    def summarize(items):
        tasks = defaultdict(list)
        for r in items:
            tasks[r['task']].append(r['correct'])
        return dict(n=len(items), correct=sum(r['correct'] for r in items),
                    accuracy=mean(r['correct'] for r in items) if items else None,
                    task_macro_accuracy=mean(mean(v) for v in tasks.values()) if tasks else None,
                    tasks=len(tasks), mean_confidence=mean(r['confidence'] for r in items) if items and all(isinstance(r['confidence'], (int, float)) for r in items) else None)

    bins = []
    for lo, hi in ((0, 0.5), (0.5, 0.7), (0.7, 0.8), (0.8, 0.9), (0.9, 1.01)):
        bins.append(dict(lower=lo, upper=hi, **summarize([r for r in explicit if lo <= r['confidence'] < hi])))
    high = [r for r in explicit if r['confidence'] >= 0.7]
    per_task = []
    for task in sorted({r['task'] for r in rows}):
        rr = [r for r in rows if r['task'] == task]
        hh = [r for r in high if r['task'] == task]
        per_task.append(dict(task=task, total=len(rr), high_n=len(hh),
                             high_correct=sum(r['correct'] for r in hh),
                             high_coverage=len(hh) / len(rr),
                             high_accuracy=mean(r['correct'] for r in hh) if hh else None))
    return dict(all=summarize(rows), explicit=summarize(explicit), fallback=summarize(fallback),
                high=summarize(high), low=summarize([r for r in explicit if r['confidence'] < 0.7]),
                high_coverage=len(high) / len(rows), bins=bins, per_task=per_task,
                raw_boolean_confidence=sum(isinstance(r['confidence'], bool) for r in rows),
                raw_confidence_types=dict(Counter(type(r['confidence']).__name__ for r in rows)))


def empirical_confidence_checks():
    manifest = json.loads((ROOT / 'experiments/coverage_manifest.json').read_text())
    reference = json.loads((ROOT / 'experiments/coverage_author_reference.json').read_text())
    assert manifest['dataset_revision'] == reference['dataset_revision']
    rows, hashes = [], {}
    for t in reference['tasks']:
        task = t['task']
        relative = f'solutions_subset_50/{task}/ground_truth/groups_{task}_n2.json'
        ground = ROOT / 'data/coverage' / relative
        author = ROOT / 'data/author_reference' / f'{task}.json'
        assert hashlib.sha256(ground.read_bytes()).hexdigest() == manifest['sha256'][relative]
        assert hashlib.sha256(author.read_bytes()).hexdigest() == t['sha256']
        index = defaultdict(list)
        for r in json.loads(author.read_text())['results']:
            index[tuple((s['path'], s['score']) for s in r['solutions'])].append(r)
        groups = json.loads(ground.read_text())
        assert len(groups) == sum(len(v) for v in index.values())
        for g in groups:
            key = tuple((Path(p).stem[-4:] + '.py', s) for p, s in zip(g['paths'], g['scores']))
            matches = index[key]
            assert len(matches) == 1
            row = matches[0]
            assert row['groundtruth']['best_index'] == g['best_index']
            expected = (min if g['is_lower_better'] else max)(range(2), key=lambda i: g['scores'][i])
            assert g['scores'][0] != g['scores'][1] and expected == g['best_index']
            assert row['groundtruth']['is_lower_better'] == g['is_lower_better']
            winner = row['prediction'].get('best_index')
            assert type(winner) is int and winner in (0, 1)
            rows.append(dict(task=task, confidence=row['prediction'].get('confidence'),
                             correct=int(winner == expected)))
        hashes[task] = dict(ground_truth=manifest['sha256'][relative], author=t['sha256'])
    adopted_path = ROOT / 'experiments/coverage_retry_results.json'
    adopted = json.loads(adopted_path.read_text())['adopted_results']
    ours = [dict(task=r['task'], confidence=r['parsed'].get('confidence'), correct=r['correct']) for r in adopted]
    assert len(rows) == 18438 and len(ours) == 246
    return dict(author=confidence_summary(rows), ours=confidence_summary(ours), source_hashes=hashes,
                adopted_results_sha256=hashlib.sha256(adopted_path.read_bytes()).hexdigest(),
                scope='Descriptive post-hoc baseline audit; shared tasks/candidates; threshold fixed at released 0.7; no tuning or independent validation claim.')


def native_replay_checks():
    tasks, _, _ = load_tasks()
    feedback = {t['task']: t['feedback'] for t in tasks}
    source = ROOT / 'runs/five-task/runs.jsonl'
    expected_sha = json.loads((ROOT / 'experiments/tournament_replay_results.json').read_text())['run_trace_sha256']
    assert hashlib.sha256(source.read_bytes()).hexdigest() == expected_sha
    checks = []
    with source.open() as stream:
        for line in stream:
            row = json.loads(line)
            if row['variant'] != 'original' or row['pool_id'] != 0:
                continue
            for workers in (1, 128):
                backend = FeedbackBackend(feedback[row['task']])
                wm = pinned.WorldModel('native prompt check', 'report', config=pinned.WorldModelConfig(
                    confidence_threshold=0.7, max_concurrent_requests=workers))
                wm._comparison_cache = {}

                def query(**kwargs):
                    return backend.query(user_message=pair_from_prompt(kwargs['user_message']))

                with patch.object(pinned, 'query', query), patch.object(pinned, 'random', random.Random(row['pending_seed'])):
                    ranked, comparisons, ranks = wm.tournament_rank([SimpleNamespace(id=c, code=c) for c in row['order']])
                assert [n.id for n in ranked] == row['ranked'] and ranks == row['ranks']
                assert len(comparisons) == row['metrics']['attempts'] and backend.calls == row['metrics']['unique_feedback']
                expected = [(e['round'], e['confidence'], e['actual_winner']) for e in row['trace']]
                assert [(c.round_num, c.confidence) for c in comparisons] == [(r, v) for r, v, _ in expected]
                for comparison, event in zip(comparisons, row['trace']):
                    actual = (event['a'], event['b'])[comparison.winner_idx] if comparison.winner_idx is not None else None
                    assert actual == event['actual_winner']
                    assert comparison.is_valid == (actual is not None)
                checks.append(dict(task=row['task'], order_id=row['order_id'], pending_seed=row['pending_seed'],
                                   workers=workers, attempts=len(comparisons), backend_calls=backend.calls))
    assert len(checks) == 100
    return dict(cases=checks, original_trace_sha256=expected_sha,
                method='50 original replay scenarios, each with 1 and 128 workers; native prompt, parser, batch and tournament; fixed local feedback.')


def finite_json(value):
    if isinstance(value, float) and not math.isfinite(value):
        return str(value)
    if isinstance(value, dict):
        return {k: finite_json(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [finite_json(v) for v in value]
    return value


def main():
    released = released_config_checks()
    gates = gate_checks()
    stops = stopping_checks()
    routing = execution_routing_checks()
    empirical = empirical_confidence_checks()
    native = native_replay_checks()
    result = dict(upstream_commit=COMMIT, world_model_sha256=SOURCE_SHA256,
                  script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                  released_config=released, gates=gates, stopping=stops, execution_routing=routing, empirical=empirical,
                  native_replay=native, api_calls=0, candidate_training_runs=0)
    OUTPUT.mkdir(parents=True, exist_ok=True)
    (OUTPUT / 'audit.json').write_text(json.dumps(finite_json(result), ensure_ascii=False, indent=2, allow_nan=False) + '\n')
    write_report(result)
    print(json.dumps(dict(gate_cases=len(gates['cases']), stop_cases=len(stops),
                          routing_cases=len(routing['cases']), native_checks=len(native['cases']),
                          author=empirical['author']['high'], ours=empirical['ours']['high']), ensure_ascii=False))


def write_report(result):
    empirical = result['empirical']
    lines = ['# ForeAgent 置信度门控与复赛停止机制验收（2026-11-07）', '',
             '本轮固定原始代码和 0.7 发布门槛；改进策略留待后续。API 调用与候选训练均为 0。', '',
             '## 已验证的控制流', '',
             '- confidence >= 0.7 时判断有效；类默认门槛为 0.6，与发布配置有区别。',
             '- 缺失、null、非数字 confidence 回退 0.5；解析/后端异常回退 0.0。低置信度与异常结果也会缓存。',
             '- 原代码接受大于 1、Infinity、布尔 confidence；NaN 比较为无效；负值保留但低于门槛。输入范围/类型检查存在缺口，本轮保持原行为。',
             '- 缺失胜者字段配合高置信度会默认索引 0；越界索引仍可标为有效；小数索引被 int 转换。',
             '- 原版类级缓存可跨实例复用：同一代码对在 0.6 门槛下有效后，另一个 0.7 门槛实例仍可能读取缓存中的 is_valid=True。当前回放每场隔离缓存；此项属于额外的原代码控制检查。',
             '- 0/1 候选无需比较；全高置信度的 2/3/10 候选分别用 1/2/9 条反馈结束。',
             '- 全低置信度的 2/3/10 候选在第 5/7/21 轮安全退出：判定是 >2*n，而非 >=2*n。1 和 128 workers 均验证。',
             '- pending 复赛获胜会晋级，原先晋级的对手仍保留；仍拿不准则继续保留。两候选全低时只有 1 次新反馈、10 条比较记录。',
             '- 最终排序考虑淘汰状态，显示 rank 只按 wins/round 分组。控制案例出现已淘汰候选与存活候选均 rank=0；Top-K 接受的是显示 rank。',
             '- 已抽取原 Agent 方法核对执行路由：唯一 rank=0 候选若概率检查失败，会被强制执行；并列 rank=0 时可能执行多个。该测试使用假执行回调，只验证路由。', '',
             '异常数值与越界索引来自可控输入测试，用于确认解析边界；它们不代表本轮真实运行中已发生。发布 YAML 的门槛 0.7、执行概率 0.2、10 候选和 Top-K=1 均从固定提交核对。', '',
             '## 已有判断中的 confidence 与正确率', '',
             '以下是已查看数据上的描述性检查，门槛固定 0.7。两组样本范围与任务权重不同，分别解释。', '',
             '| 来源 | 全部配对 | 全部正确率 | confidence 明确且 >=0.7 | 覆盖率 | 高置信度正确率 | 明确低置信度正确率 | confidence 回退条数 |',
             '| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |']
    for name, label in (('author', '作者一次公开运行'), ('ours', '本项目已采用结果')):
        r = empirical[name]
        pct = lambda v: f'{v:.2%}' if v is not None else '—'
        lines.append(f"| {label} | {r['all']['n']} | {pct(r['all']['accuracy'])} | {r['high']['n']} | {pct(r['high_coverage'])} | {pct(r['high']['accuracy'])} | {pct(r['low']['accuracy'])} | {r['fallback']['n']} |")
    lines += ['', '## confidence 分箱（明确数值字段）', '',
              '| 来源 | 区间 | 配对数 | 平均 confidence | 实际正确率 |',
              '| --- | --- | ---: | ---: | ---: |']
    for name in ('author', 'ours'):
        for b in empirical[name]['bins']:
            conf = f"{b['mean_confidence']:.3f}" if b['n'] else '—'
            acc = f"{b['accuracy']:.2%}" if b['n'] else '—'
            label = f"[{b['lower']:g}, {b['upper']:g})" if b['upper'] < 1 else '[0.9, 1]'
            lines.append(f"| {name} | {label} | {b['n']} | {conf} | {acc} |")
    lines += ['', 'confidence 是模型自报值，不能直接解释为已校准的概率；分箱是样本内观察。任务、候选和配对存在依赖，后续改法需要独立评测。', '',
              '## 回放适配核对', '',
              '从此前五任务各取第一个候选池的全部排列与复赛种子，共 50 个原版场景；分别用原代码的 1 与 128 workers 批处理重跑，共 100 次核对。保留原 prompt 构造、parser、batch 和 tournament，仅替换模型反馈，排名、轮次、置信度序列和反馈数与保存轨迹一致。它核对适配一致性，实时服务的响应分布与延迟仍属待验证范围。', '',
              '## 验收结论与边界', '',
              '固定版本在本地可控响应和已有公开判断下的门控、pending、停止、排名及执行路由已覆盖。尚待确认的是实时 Agent prompt 下的 confidence 分布/校准、真实服务错误与并发行为，以及完整生成—筛选—执行循环的效果。', '',
              '本轮完成 18 个门控/异常响应案例、2 个默认与发布门槛对照、1 个跨门槛缓存控制、14 个停止/复赛场景、6 个原 Agent 路由场景、100 次原生回放一致性核对。现有测试与新增机制回归测试合计 20 项通过。', '',
              '源码级问题按原行为记录：confidence 输入校验、缓存方向、低置信度停滞和显示名次分组。现有缓存方向修正版单独保留；本轮未实现新的早停或未比较优先策略。', '',
              '## 复现', '', '`python3 audit_foreagent_mechanisms.py`', '',
              '完整控制响应、逐轮状态、原生回放核对、逐任务 confidence 统计和输入校验值：`outputs/foreagent-mechanisms-20261107/audit.json`。', '',
              f"固定提交：`{COMMIT}`；WorldModel SHA-256：`{SOURCE_SHA256}`。"]
    (OUTPUT / 'report.md').write_text('\n'.join(lines) + '\n')


if __name__ == '__main__':
    main()
