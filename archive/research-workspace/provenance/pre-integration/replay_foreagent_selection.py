"""Offline paired replay of pinned ForeAgent and the cache-direction repair."""
from collections import Counter, defaultdict
import hashlib
import json
import math
from pathlib import Path
import random
from statistics import mean
from types import SimpleNamespace

from foreagent_selection import CacheFixedWorldModel, COMMIT, ROOT, SOURCE_SHA256, pinned

SEED = 20261107
POOL_COUNT, POOL_SIZE, ORDER_COUNT, PENDING_SEEDS = 10, 10, 5, 2
OUTPUT = ROOT / 'outputs' / 'tournament-replay-20261107'
PROTOCOL = ROOT / 'experiments' / 'tournament_replay_protocol.md'


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_tasks():
    manifest = json.loads((ROOT / 'experiments/coverage_manifest.json').read_text())
    reference = json.loads((ROOT / 'experiments/coverage_author_reference.json').read_text())
    if manifest['dataset_revision'] != reference['dataset_revision']:
        raise ValueError('Dataset revisions differ')
    refs = {t['task']: t for t in reference['tasks']}
    tasks = []
    for t in manifest['tasks']:
        name = t['task']
        relative = f'solutions_subset_50/{name}/ground_truth/groups_{name}_n2.json'
        ground = ROOT / 'data/coverage' / relative
        author = ROOT / 'data/author_reference' / f'{name}.json'
        if sha256(ground) != manifest['sha256'][relative] or sha256(author) != refs[name]['sha256']:
            raise ValueError(f'Data checksum mismatch: {name}')
        groups = json.loads(ground.read_text())
        ids = sorted({Path(p).name for g in groups for p in g['paths']})
        edges = {tuple(sorted(Path(p).name for p in g['paths'])) for g in groups}
        if len(edges) != len(groups):
            raise ValueError(f'Duplicate source pairs: {name}')
        if len(ids) < POOL_SIZE or len(edges) != len(ids) * (len(ids) - 1) // 2:
            continue
        rows = json.loads(author.read_text())['results']
        index = defaultdict(list)
        for i, row in enumerate(rows):
            key = tuple((s['path'], s['score']) for s in row['solutions'])
            index[key].append((i, row))
        scores, feedback, directions = {}, {}, set()
        for g in groups:
            pair = tuple(Path(p).name for p in g['paths'])
            if len(set(pair)) != 2:
                raise ValueError(f'Self comparison: {name}')
            directions.add(g['is_lower_better'])
            expected = (min if g['is_lower_better'] else max)(range(2), key=lambda i: g['scores'][i])
            if g['best_index'] != expected or g['scores'][0] == g['scores'][1]:
                raise ValueError(f'Invalid label or tied source pair: {name}')
            for candidate, score in zip(pair, g['scores']):
                if not math.isfinite(score) or (candidate in scores and scores[candidate] != score):
                    raise ValueError(f'Invalid/conflicting candidate scores: {name}')
                scores[candidate] = score
            key = tuple((Path(p).stem[-4:] + '.py', score) for p, score in zip(g['paths'], g['scores']))
            matches = index[key]
            if len(matches) != 1:
                raise ValueError(f'Non-unique author match: {name}/{pair}')
            i, row = matches[0]
            if row['groundtruth']['best_index'] != expected or row['groundtruth']['is_lower_better'] != g['is_lower_better']:
                raise ValueError(f'Author ground truth differs: {name}/{pair}')
            prediction = row['prediction']
            winner = prediction.get('best_index')
            if type(winner) is not int or winner not in (0, 1):
                raise ValueError(f'Invalid author winner: {name}/{i}')
            raw_confidence = prediction.get('confidence')
            try:
                confidence = float(raw_confidence)
            except (TypeError, ValueError):
                confidence = 0.5
            if not math.isfinite(confidence) or not 0 <= confidence <= 1:
                raise ValueError(f'Invalid author confidence: {name}/{i}')
            feedback[tuple(sorted(pair))] = dict(winner=pair[winner], confidence=confidence,
                                                confidence_fallback=raw_confidence is None or not _numeric(raw_confidence),
                                                author_row=i, source_order=pair)
        if len(directions) != 1:
            raise ValueError(f'Metric direction conflict: {name}')
        tasks.append(dict(task=name, ids=ids, scores=scores, lower=directions.pop(), feedback=feedback,
                          hashes=dict(ground_truth=sha256(ground), author=sha256(author))))
    if len(tasks) != 5:
        raise ValueError(f'Expected five eligible tasks, got {len(tasks)}')
    return tasks, manifest['dataset_revision'], reference['author_run']


def _numeric(value):
    try:
        float(value)
        return True
    except (TypeError, ValueError):
        return False


class FeedbackBackend:
    def __init__(self, feedback):
        self.feedback = feedback
        self.calls = 0

    def query(self, *, user_message, **kwargs):
        a, b = user_message
        entry = self.feedback[tuple(sorted((a, b)))]
        self.calls += 1
        result = dict(predicted_best_index=(a, b).index(entry['winner']))
        if not entry['confidence_fallback']:
            result['confidence'] = entry['confidence']
        return json.dumps(result)


class ReplayMixin:
    def __init__(self, backend):
        config = pinned.WorldModelConfig(confidence_threshold=0.7, exec_probability=0.2,
                                        temperature=1.0, max_concurrent_requests=1)
        super().__init__('offline replay', '', config=config)
        self._comparison_cache = {}
        self.backend = backend
        self.trace = []
        self.first_orders = {}

    def _predict_pairwise_single(self, a, b, round_num=0):
        key = tuple(sorted((hash(a.code), hash(b.code))))
        cached = key in self._comparison_cache
        first = self.first_orders.setdefault(key, (a.id, b.id))
        result = super()._predict_pairwise_single(a, b, round_num)
        entry = self.backend.feedback[tuple(sorted((a.id, b.id)))]
        actual = (a.id, b.id)[result.winner_idx] if result.winner_idx is not None else None
        # A confident stored response must remain a valid comparison in replay.
        if result.is_valid != (entry['confidence'] >= 0.7):
            raise ValueError('Replay backend failed or confidence changed')
        self.trace.append(dict(a=a.id, b=b.id, round=round_num, cache_hit=cached,
                               reversed_cache_hit=cached and first != (a.id, b.id),
                               actual_winner=actual, expected_winner=entry['winner'],
                               cache_identity_error=cached and result.is_valid and actual != entry['winner'],
                               confidence=result.confidence, confidence_fallback=entry['confidence_fallback'],
                               author_row=entry['author_row']))
        return result

    def _batch_predict_pairwise(self, pairs, max_workers=None):
        # Preserve pair order and history, replacing thread scheduling only.
        return [self.predict_pairwise(a, b, r) for a, b, r in pairs]


class OriginalReplay(ReplayMixin, pinned.WorldModel):
    pass


class FixedReplay(ReplayMixin, CacheFixedWorldModel):
    pass


def score_selection(selected, top, pool, scores, lower):
    values = [scores[c] for c in pool]
    best = (min if lower else max)(values)
    better = lambda a, b: a < b if lower else a > b
    loss = lambda c: sum(better(v, scores[c]) for v in values) / (len(pool) - 1)
    return dict(top1_hit=int(scores[selected] == best), rank_regret=loss(selected),
                top_tie=int(len(top) > 1), top_size=len(top),
                uniform_top_hit=sum(scores[c] == best for c in top) / len(top),
                random_hit=sum(v == best for v in values) / len(pool),
                random_rank_regret=mean(loss(c) for c in pool))


def run_one(kind, order, pending_seed, feedback, scores, lower):
    backend = FeedbackBackend(feedback)
    wm = (OriginalReplay if kind == 'original' else FixedReplay)(backend)
    old_query, old_prompt, old_random = pinned.query, pinned.build_pairwise_prompt, pinned.random
    pinned.query = backend.query
    pinned.build_pairwise_prompt = lambda **kwargs: (kwargs['code_a'], kwargs['code_b'])
    pinned.random = random.Random(pending_seed)
    try:
        ranked, comparisons, ranks = wm.tournament_rank([SimpleNamespace(id=c, code=c) for c in order])
    finally:
        pinned.query, pinned.build_pairwise_prompt, pinned.random = old_query, old_prompt, old_random
    if len(comparisons) != len(wm.trace):
        raise ValueError('Comparison trace is incomplete')
    top = [node.id for node in ranked if ranks[node.id]['rank'] == 0]
    selected = ranked[0].id
    metrics = score_selection(selected, top, order, scores, lower)
    metrics.update(attempts=len(wm.trace), unique_feedback=backend.calls,
                   cache_hits=sum(t['cache_hit'] for t in wm.trace),
                   reversed_cache_hits=sum(t['reversed_cache_hit'] for t in wm.trace),
                   cache_identity_errors=sum(t['cache_identity_error'] for t in wm.trace),
                   missing_confidence_unique=sum(t['confidence_fallback'] for t in wm.trace if not t['cache_hit']),
                   safety_exit=int(max((t['round'] for t in wm.trace), default=0) > 2 * len(order)))
    if metrics['attempts'] != metrics['unique_feedback'] + metrics['cache_hits']:
        raise ValueError('Cache accounting mismatch')
    if kind == 'cache_fixed' and metrics['cache_identity_errors']:
        raise ValueError('Cache repair returned a wrong identity')
    return dict(selected=selected, top=top, ranked=[n.id for n in ranked], ranks=ranks,
                metrics=metrics, trace=wm.trace)


def main():
    tasks, revision, author_run = load_tasks()
    OUTPUT.mkdir(parents=True, exist_ok=True)
    aggregates, paired = defaultdict(list), Counter()
    with (OUTPUT / 'runs.jsonl').open('w') as stream:
        for task in tasks:
            name = task['task']
            pools = set()
            rng = random.Random(f'{SEED}:{name}:pools')
            while len(pools) < POOL_COUNT:
                pools.add(tuple(sorted(rng.sample(task['ids'], POOL_SIZE))))
            for pool_id, pool in enumerate(sorted(pools)):
                orders = [list(pool)]
                order_rng = random.Random(f'{SEED}:{name}:{pool_id}:orders')
                while len(orders) < ORDER_COUNT:
                    order = order_rng.sample(list(pool), POOL_SIZE)
                    if order not in orders:
                        orders.append(order)
                for order_id, order in enumerate(orders):
                    for pending_id in range(PENDING_SEEDS):
                        pending_seed = f'{SEED}:{name}:{pool_id}:{order_id}:pending:{pending_id}'
                        results = {}
                        for kind in ('original', 'cache_fixed'):
                            result = run_one(kind, order, pending_seed, task['feedback'], task['scores'], task['lower'])
                            row = dict(task=name, pool_id=pool_id, order_id=order_id,
                                       pending_seed=pending_seed, variant=kind, order=order, **result)
                            stream.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + '\n')
                            aggregates[name, kind].append(result['metrics'])
                            results[kind] = result
                        a, b = results['original'], results['cache_fixed']
                        paired['scenarios'] += 1
                        paired['selected_changed'] += a['selected'] != b['selected']
                        paired['fixed_better_rank'] += b['metrics']['rank_regret'] < a['metrics']['rank_regret']
                        paired['fixed_worse_rank'] += b['metrics']['rank_regret'] > a['metrics']['rank_regret']
                        paired['fixed_only_hit'] += b['metrics']['top1_hit'] > a['metrics']['top1_hit']
                        paired['original_only_hit'] += b['metrics']['top1_hit'] < a['metrics']['top1_hit']
            print(f'{name}: {POOL_COUNT * ORDER_COUNT * PENDING_SEEDS} paired scenarios', flush=True)
    per_task = []
    for task in tasks:
        for kind in ('original', 'cache_fixed'):
            rows = aggregates[task['task'], kind]
            per_task.append(dict(task=task['task'], variant=kind, scenarios=len(rows),
                                 means={k: mean(r[k] for r in rows) for k in rows[0]},
                                 cache_identity_errors_total=sum(r['cache_identity_errors'] for r in rows)))
    overall = {kind: {k: mean(t['means'][k] for t in per_task if t['variant'] == kind)
                      for k in per_task[0]['means']} for kind in ('original', 'cache_fixed')}
    summary = dict(seed=SEED, pools_per_task=POOL_COUNT, pool_size=POOL_SIZE,
                   orders_per_pool=ORDER_COUNT, pending_seeds=PENDING_SEEDS,
                   upstream_commit=COMMIT, source_sha256=SOURCE_SHA256, dataset_revision=revision,
                   author_run=author_run, protocol_sha256=sha256(PROTOCOL),
                   source_hashes={t['task']: t['hashes'] for t in tasks},
                   script_sha256=sha256(Path(__file__)), adapter_sha256=sha256(ROOT / 'foreagent_selection.py'),
                   run_trace_sha256=sha256(OUTPUT / 'runs.jsonl'),
                   per_task=per_task, overall_task_macro=overall, paired=dict(paired),
                   scope='Exploratory replay using one released author run; correlated pools and permutations; no API calls or candidate execution.')
    target = ROOT / 'experiments/tournament_replay_results.json'
    target.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n')
    write_report(summary)
    print(json.dumps(dict(overall=overall, paired=dict(paired)), ensure_ascii=False))


def write_report(summary):
    table = []
    for row in summary['per_task']:
        m = row['means']
        table.append(f"| {row['task']} | {row['variant']} | {m['top1_hit']:.1%} | {m['rank_regret']:.3f} | {m['top_tie']:.1%} | {m['unique_feedback']:.2f} | {row['cache_identity_errors_total']} |")
    overall = summary['overall_task_macro']
    a, b = overall['original'], overall['cache_fixed']
    report = f'''# ForeAgent tournament 离线回放（2026-11-07）

## 范围

五个完整比较图任务，每任务 10 个池，每池 10 个候选、5 种排列、2 个复赛种子，共 {summary['paired']['scenarios']} 个配对场景、两版本共 {2 * summary['paired']['scenarios']} 次 tournament。
使用作者一次公开预测，本轮 API 调用为 0，候选训练为 0。它是筛选模块的离线适配；当前模型的 246 对结果属于另一组实验。

## 结果

任务等权平均：原版最佳命中率 {a['top1_hit']:.1%}，修正版 {b['top1_hit']:.1%}，随机选择期望 {b['random_hit']:.1%}；归一化排名损失分别 {a['rank_regret']:.3f}、{b['rank_regret']:.3f}，随机期望 {b['random_rank_regret']:.3f}（越低越好）。
原版缓存身份错误均值 {a['cache_identity_errors']:.3f} 次/场景，修正版 {b['cache_identity_errors']:.3f}；选择不同的场景 {summary['paired']['selected_changed']} 个。
并列时使用原排序第一项；并列率分别 {a['top_tie']:.1%}、{b['top_tie']:.1%}。完整 JSON 同时报告并列集合均匀选取时的命中概率。

**安全退出是本轮最突出的现象。** 原版 {a['safety_exit']:.1%}、修正版 {b['safety_exit']:.1%} 的场景触发 `round_num > 2*n`。平均比较尝试分别 {a['attempts']:.2f}、{b['attempts']:.2f} 次，而唯一反馈只有 {a['unique_feedback']:.2f}、{b['unique_feedback']:.2f} 条。复赛反复读取同一低置信度缓存不会产生新证据。该现象依赖本轮公开反馈的置信度与离线复用设置，需要后续实时 Agent 验证。

| 任务 | 版本 | 最佳命中率 | 排名损失 | 并列率 | 唯一反馈/场景 | 缓存身份错误总数 |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
{chr(10).join(table)}

## 如何解释

- 缓存修复是身份一致性修复。选择质量的上升或下降都作为观测保留。
- 同池排列、种子和不同池共享候选，500 个场景存在依赖；上述为描述性平均，独立任务数为 5。
- 候选池由同任务已发布候选构造，尚未证明它们来自同父节点的同一轮生成。
- 原版和修正版每次均清空缓存；跨任务缓存污染被隔离，不计为本轮修复效果。
- feedback 的反向读取复用同一作者判断，不能作为真实位置交换实验。
- benchmark prompt 与实时 Agent prompt 不同；缺失 confidence 回退为 0.5，不等于校准过的实时判断。
- 此轮任务用于开发诊断。后续效果主张需要独立评测边界及更广任务覆盖。

## 复现与证据

`python3 -m unittest discover -s tests -v`

`python3 verify_foreagent_selection.py`

`python3 replay_foreagent_selection.py`

协议：`experiments/tournament_replay_protocol.md`；逐次比较：`outputs/tournament-replay-20261107/runs.jsonl`；汇总及版本/哈希：`experiments/tournament_replay_results.json`。
轨迹 SHA-256：`{summary['run_trace_sha256']}`。
'''
    (ROOT / 'experiments/tournament_replay_report.md').write_text(report)


if __name__ == '__main__':
    main()
