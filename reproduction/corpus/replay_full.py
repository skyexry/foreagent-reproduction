"""Fresh paired replays using the original full execution policy and frozen v1 pools.
PYTHONHASHSEED=0 python replay_full.py --variant original
PYTHONHASHSEED=0 python replay_full.py --variant cache-fixed
"""
import argparse
import ast
import csv
import gzip
import hashlib
import json
import logging
import math
import os
from pathlib import Path
import statistics
import sys
import types
sys.dont_write_bytecode=True
from execution_policy import apply_execution_policy, verify_execution_policy
ROOT=Path(os.environ['FOREAGENT_RUN_DIR'])
PROJECT=Path(__file__).resolve().parents[2]
EXPECTED='df85087f0a23e5d95cb507fadc36fd5694f6abafe80d9ae2a841cdb838915d79'
SPEC=json.loads((ROOT/'v2_spec.json').read_text())
VARIANT=None
HERE=None

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def dump(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2))

def load_task(task):
    root = PROJECT / 'data/coverage/solutions_subset_50' / task
    truth_file = root / 'ground_truth' / f'groups_{task}_n2.json'
    author_file = PROJECT / 'data/author_reference' / f'{task}.json'
    groups = json.loads(truth_file.read_text())
    ids = sorted({Path(p).name for g in groups for p in g['paths']})
    # Released author rows use unique 4-character suffixes. Identity joins use
    # filenames only; scores and correctness are never used to match records.
    suffix_map = {name[-7:]: name for name in ids}
    assert len(suffix_map) == len(ids), (task, 'ambiguous filename suffix')
    ground_edges = {frozenset(Path(p).name for p in g['paths']) for g in groups}
    rows = json.loads(author_file.read_text())['results']
    feedback = {}
    missing_confidence = 0
    for i, row in enumerate(rows):
        a, b = [suffix_map[s['path']] for s in row['solutions']]
        key = frozenset((a, b))
        assert key not in feedback
        pred = row['prediction']
        winner_slot = int(pred['best_index'])
        assert winner_slot in (0, 1)
        conf = pred.get('confidence')
        missing = conf is None
        try:
            conf = float(conf)
            assert 0 <= conf <= 1
        except (ValueError, TypeError):
            conf = 0.5
            missing = True
        missing_confidence += missing
        feedback[key] = {'winner': (a, b)[winner_slot], 'confidence': conf,
                         'missing_confidence': missing, 'author_row': i}
    assert set(feedback) == ground_edges
    # Only some source texts were downloaded in the earlier 246-pair study.
    # Identity-only Node.code stubs let the original prompt/parser/cache path
    # execute while local query() returns released feedback. This preserves
    # unordered-pair caching and its direction bug for distinct identities;
    # equality of full source texts across different IDs is not evaluated.
    codes = {name: name for name in ids}
    # Scoring labels are held separately from policy feedback.
    scores = {}
    lower = {g['is_lower_better'] for g in groups}
    assert len(lower) == 1
    for g in groups:
        for p, score in zip(g['paths'], g['scores']):
            name = Path(p).name
            assert name not in scores or scores[name] == score or (math.isnan(scores[name]) and math.isnan(score))
            scores[name] = score
        values = [(-s if g['is_lower_better'] else s) for s in g['scores']]
        if all(math.isfinite(x) for x in values):
            assert values[g['best_index']] == max(values)
    utility = {name: (-s if next(iter(lower)) else s) for name, s in scores.items()}
    excluded = sorted(name for name in ids if not math.isfinite(utility[name]))
    ids = [name for name in ids if name not in excluded]
    feedback = {edge: row for edge,row in feedback.items() if not edge.intersection(excluded)}
    codes = {name:codes[name] for name in ids}
    utility = {name:utility[name] for name in ids}
    return ids, feedback, codes, utility, {
        'ground_truth_sha256': digest(truth_file), 'author_sha256': digest(author_file),
        'identity_stub_sha256': {k: hashlib.sha256(v.encode()).hexdigest() for k, v in codes.items()},
        'candidate_count': len(ids), 'pair_count': len(feedback),
        'excluded_nonfinite_score_candidates': excluded,
        'missing_confidence_pairs': missing_confidence,
    }

def score_selection(ids, selected, utility):
    vals = [utility[x] for x in ids]
    best, worst = max(vals), min(vals)
    optimal = {x for x in ids if utility[x] == best}
    k, n = len(selected), len(ids)
    assert k >= 1 and n >= 2
    percentile = statistics.mean((sum(v < utility[x] for v in vals) +
                                 0.5*(sum(v == utility[x] for v in vals)-1))/(n-1)
                                for x in selected)
    return {
        'top_group_size': k, 'contains_best': float(bool(optimal.intersection(selected))),
        'uniform_tie_best_hit': len(optimal.intersection(selected))/k,
        'random_best_hit': len(optimal)/n,
        'random_same_size_contains_best': 1 - __import__('math').comb(n-len(optimal), k)/__import__('math').comb(n, k)
            if k <= n-len(optimal) else 1.,
        'selected_percentile': percentile, 'random_percentile': 0.5,
        'normalized_regret': (best-statistics.mean(utility[x] for x in selected))/(best-worst)
            if best > worst else 0.,
        'random_normalized_regret': (best-statistics.mean(vals))/(best-worst) if best > worst else 0.,
        'expected_empty_execution': 0.8**k, 'expected_execution_count': 0.2*k,
        'expected_execute_best': 1-0.8**len(optimal.intersection(selected)),
    }, optimal

def original_module():
    source = ROOT / ('world_model_original.py' if VARIANT == 'original' else 'world_model_cache_fixed.py')
    assert digest(source) == SPEC['variants'][VARIANT]
    tree = ast.parse(source.read_text())
    tree.body = [n for n in tree.body if not (isinstance(n, ast.ImportFrom) and n.level)]
    mod = types.ModuleType('pinned_foreagent_replay')
    sys.modules[mod.__name__] = mod
    def network_disabled(**kwargs):
        raise AssertionError('Network disabled: a local response provider must be injected.')
    mod.__dict__.update(Node=types.SimpleNamespace, query=network_disabled)
    exec(compile(tree, str(source), 'exec'), mod.__dict__)
    mod.logger.setLevel(logging.CRITICAL)
    return mod

def verify(mod):
    # Meaningful checks: original cache reversal, parser fallback, exact toy
    # tournament outcome, and tie-adjusted metric versus a full-set selection.
    assert mod.parse_pairwise_response('{"predicted_best_index":0}')['confidence'] == 0.5
    cfg = mod.WorldModelConfig(confidence_threshold=.7, exec_probability=.2, max_concurrent_requests=1)
    nodes = [types.SimpleNamespace(id=x, code=x) for x in ['A', 'B', 'C', 'D']]
    mod.query = lambda **kwargs: '{"predicted_best_index":0,"confidence":0.9}'
    mod.WorldModel._comparison_cache.clear()
    wm = mod.WorldModel('toy', '', config=cfg)
    ranked, comparisons, meta = wm.tournament_rank(nodes)
    assert ranked[0].id == 'A' and len(comparisons) == 3
    assert meta['A']['rank'] == 0
    mod.WorldModel._comparison_cache.clear()
    ab = wm.predict_pairwise(nodes[0], nodes[1])
    ba = wm.predict_pairwise(nodes[1], nodes[0])
    assert ab.winner_idx == 0
    assert ba.winner_idx == (0 if VARIANT == 'original' else 1)
    scored, _ = score_selection(['A','B','C'], ['A','B','C'], {'A':3,'B':2,'C':1})
    assert scored['uniform_tie_best_hit'] == 1/3 and scored['selected_percentile'] == .5
    assert scored['contains_best'] == 1
    dump(HERE / 'verification.json', {'original_source_hash_verified': True,
         'original_tournament_toy_case': 'passed', 'variant_cache_behavior': 'passed', 'variant': VARIANT, 'complete_execution_policy': verify_execution_policy(),
         'confidence_fallback': 'passed', 'tie_adjusted_metric': 'passed'})

def run():
    assert os.environ.get('PYTHONHASHSEED') == '0', 'Run with PYTHONHASHSEED=0 for reproducible cache keys.'
    protocol = json.loads((HERE/'protocol.json').read_text())
    assert not (HERE/'results.json').exists(), 'Existing results: inspect rather than overwrite.'
    mod = original_module()
    verify(mod)
    task_results = []
    example = None
    with gzip.open(HERE/'traces.jsonl.gz', 'wt', encoding='utf-8') as tracefile, \
         (HERE/'runs.jsonl').open('w') as runfile:
        for task_spec in protocol['tasks']:
            task = task_spec['task']
            ids, feedback, codes, utility, meta = load_task(task)
            assert meta == task_spec['source'], 'Input changed since protocol freeze.'
            code_to_id = {code: name for name, code in codes.items()}
            calls = []
            def query(**kwargs):
                text = kwargs['user_message']
                body = text.split('### Solution 0:\n```python\n\n', 1)[1]
                code_a, code_b = body.split('\n```\n\n### Solution 1:\n```python\n\n', 1)
                code_b = code_b.rsplit('\n```', 1)[0]
                a, b = code_to_id[code_a], code_to_id[code_b]
                row = feedback[frozenset((a,b))]
                response = {'predicted_best_index': 0 if row['winner'] == a else 1}
                if not row['missing_confidence']:
                    response['confidence'] = row['confidence']
                calls.append((a,b))
                return json.dumps(response)
            mod.query = query
            records = []
            for pool in task_spec['pools']:
                order = pool['candidate_order']
                nodes = [types.SimpleNamespace(id=x, code=codes[x]) for x in order]
                for ri, seed in enumerate(pool['replay_seeds']):
                    mod.random.seed(seed)
                    mod.WorldModel._comparison_cache.clear()
                    calls.clear()
                    wm = mod.WorldModel(task, '', config=mod.WorldModelConfig(
                        confidence_threshold=.7, exec_probability=.2, temperature=1., max_concurrent_requests=1))
                    trace = []
                    original_batch = wm._batch_predict_pairwise
                    def traced_batch(pairs, max_workers=None):
                        results = original_batch(pairs, max_workers=max_workers)
                        for (a,b,r), result in zip(pairs, results):
                            expected = feedback[frozenset((a.id,b.id))]
                            actual = None if result.winner_idx is None else (a.id,b.id)[result.winner_idx]
                            trace.append({'a':a.id,'b':b.id,'round':r,'winner':actual,
                                          'confidence':result.confidence,'valid':result.is_valid,
                                          'stored_winner':expected['winner'],
                                          'missing_confidence':expected['missing_confidence'],
                                          'cache_direction_mismatch': bool(result.is_valid and actual != expected['winner'])})
                        return results
                    wm._batch_predict_pairwise = traced_batch
                    ranked, comparisons, rank_meta = wm.tournament_rank(nodes)
                    chosen = [node.id for node in ranked if rank_meta[node.id]['rank'] < 1]
                    # Only after the policy completes do labels reach the scorer.
                    metrics, optimal = score_selection(order, chosen, utility)
                    policy = apply_execution_policy(ranked, rank_meta, wm)
                    executed = policy['final_executed']
                    probability_empty = metrics['expected_empty_execution']
                    metrics['probability_phase_expected_empty_execution'] = probability_empty
                    metrics['expected_empty_execution'] = 0.0
                    metrics['expected_execution_count'] += probability_empty
                    metrics['expected_execute_best'] += probability_empty * int(chosen[0] in optimal)
                    metrics.update({
                        'actual_empty_execution': float(not executed),
                        'probability_phase_empty_execution': float(not policy['probability_executed']),
                        'forced_fallback': float(policy['forced_fallback']),
                        'actual_execution_count': len(executed),
                        'actual_execute_best': float(bool(optimal.intersection(executed))),
                        'comparisons': len(comparisons), 'unique_feedback_queries': len(calls),
                        'cache_hits': len(comparisons)-len(calls),
                        'cache_direction_mismatches': sum(t['cache_direction_mismatch'] for t in trace),
                        'missing_confidence_comparisons': sum(t['missing_confidence'] for t in trace),
                        'low_confidence_comparisons': sum(not t['valid'] for t in trace),
                        'rounds': max([t['round'] for t in trace],default=0),
                        'safety_exit': float(max([t['round'] for t in trace],default=0) > 2*len(order)),
                        'tie': float(len(chosen)>1),
                    })
                    assert len(trace) == len(comparisons)
                    assert metrics['unique_feedback_queries'] == len({frozenset(pair) for pair in calls})
                    record = {'task':task,'pool_id':pool['pool_id'],'repeat':ri,'seed':seed,
                              'candidate_order':order,'top_group':chosen,'simulated_executed':executed,
                              'probability_executed':policy['probability_executed'],
                              'forced_fallback':policy['forced_fallback'],
                              'execution_events':policy['execution_events'],
                              'rank_meta':rank_meta, 'metrics':metrics}
                    runfile.write(json.dumps(record)+'\n')
                    tracefile.write(json.dumps({'task':task,'pool_id':pool['pool_id'],
                                               'repeat':ri,'comparisons':trace})+'\n')
                    if task == 'leaf-classification' and pool['pool_id'] == ri == 0:
                        example = {**record,'comparisons':trace,
                                   'scoring_only_utility':{x:utility[x] for x in order}}
                    records.append(metrics)
            keys = records[0].keys()
            means = {k:statistics.mean(r[k] for r in records) for k in keys}
            entry = {'task':task,'pool_size':task_spec['pool_size'],'pools':len(task_spec['pools']),
                     'replays':len(records),'distinct_unordered_pools':len({tuple(sorted(p['candidate_order']))
                                                                          for p in task_spec['pools']}),
                     'mean':means}
            task_results.append(entry)
            print('Completed',task, 'hit',round(means['uniform_tie_best_hit'],4),
                  'random',round(means['random_best_hit'],4),flush=True)
    macro = {k:statistics.mean(t['mean'][k] for t in task_results) for k in task_results[0]['mean']}
    summary = {'protocol_sha256':digest(HERE/'protocol.json'), 'tasks':len(task_results),
               'pools':sum(t['pools'] for t in task_results), 'replays':sum(t['replays'] for t in task_results),
               'macro':macro,'per_task':task_results,
               'network_calls':0,'candidate_training_runs':0,
               'variant':VARIANT, 'version':'v2_complete_execution_policy',
               'world_model_sha256':SPEC['variants'][VARIANT],
               'execution_policy_source_sha256':SPEC['agent_source_sha256'],
               'note':'Dependent exploratory offline replay using complete original execution policy with forced fallback. Probability-only fields are explicitly separated.'}
    dump(HERE/'results.json',summary)
    dump(HERE/'example_leaf.json',example)
    with (HERE/'per_task.csv').open('w',newline='') as f:
        fields=['task','pool_size','distinct_unordered_pools']+list(macro)
        writer=csv.DictWriter(f,fieldnames=fields);writer.writeheader()
        for t in task_results:
            writer.writerow({k:t[k] for k in fields[:3]}|t['mean'])
    print('MACRO',json.dumps(macro),flush=True)
if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--variant',choices=['original','cache-fixed'],required=True)
    args=parser.parse_args()
    VARIANT=args.variant
    HERE=ROOT/VARIANT
    assert digest(HERE/'protocol.json') == SPEC['baseline_protocol_sha256']
    run()
