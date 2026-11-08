"""Offline checks of pinned upstream selection code, with fake LLM responses only."""
import ast
from collections import defaultdict
import hashlib
import json
import os
import os
import logging
from pathlib import Path
import sys
import types

ROOT = Path(__file__).resolve().parent
UPSTREAM = ROOT / 'vendor/foreagent_upstream'
COMMIT = 'c4d52cf99bd870d830b456ac7c0684aec1aef375'


def main():
    Path(os.environ.get("FOREAGENT_RUN_DIR", str(ROOT / "runs/selection"))).mkdir(parents=True, exist_ok=True)
    Path(os.environ.get("FOREAGENT_RUN_DIR", str(ROOT / "runs/selection"))).mkdir(parents=True, exist_ok=True)
    relative = 'mle-bench/agents/aide/aide/world_model.py'
    source = (UPSTREAM/relative).read_bytes()
    assert hashlib.sha256(source).hexdigest() == 'df85087f0a23e5d95cb507fadc36fd5694f6abafe80d9ae2a841cdb838915d79'
    tree = ast.parse(source)
    # Remove only package imports: backend and Node are replaced below. The original
    # parser, pairwise method, cache, tournament and execution predicate run unchanged.
    tree.body = [node for node in tree.body if not (isinstance(node,ast.ImportFrom) and node.level)]
    module = types.ModuleType('foreagent_selection_audit')
    sys.modules[module.__name__] = module
    calls = []
    def query(**kwargs):
        calls.append(kwargs)
        return '{"predicted_best_index": 0, "confidence": 0.8}'
    module.__dict__.update(Node=types.SimpleNamespace, query=query)
    exec(compile(tree, str(UPSTREAM/relative), 'exec'),module.__dict__)
    module.logger.setLevel(logging.CRITICAL)
    config=module.WorldModelConfig(confidence_threshold=0.7,exec_probability=0.2,temperature=1.0)
    wm=module.WorldModel('task','report',config=config)
    a=types.SimpleNamespace(id='A',code='code-A'); b=types.SimpleNamespace(id='B',code='code-B')
    module.WorldModel._comparison_cache.clear()
    ab=wm.predict_pairwise(a,b);ba=wm.predict_pairwise(b,a)
    assert len(calls)==1 and ab.winner_idx==0 and ba.winner_idx==0
    cache={'fake_api_calls':len(calls),'AB_winner_slot':ab.winner_idx,'BA_cached_winner_slot':ba.winner_idx,
           'AB_winner_identity':'A','BA_cached_winner_identity':'B','expected_BA_slot_for_cached_A':1}
    nodes=[types.SimpleNamespace(id=str(i),code=f'code-{i}') for i in range(10)]
    module.WorldModel._comparison_cache.clear(); calls.clear()
    ranked,comparisons,ranks=wm.tournament_rank(nodes)
    assert len(calls)==9 and len(comparisons)==9
    assert len([v for v in ranks.values() if v['rank']==0])==1
    decisive={'candidates':10,'fake_api_calls':len(calls),'comparison_records':len(comparisons),'top_rank_ids':[k for k,v in ranks.items() if v['rank']==0]}
    def uncertain(**kwargs):
        calls.append(kwargs)
        return '{"predicted_best_index": 0, "confidence": 0.6}'
    module.query=uncertain
    module.WorldModel._comparison_cache.clear();calls.clear()
    ranked,comparisons,ranks=wm.tournament_rank([a,b])
    assert len(comparisons)==10 and len(calls)==1
    assert ranks['A']['rank']==ranks['B']['rank']==0
    uncertain_case={'candidates':2,'fake_api_calls':len(calls),'comparison_records':len(comparisons),
                    'last_round':max(c.round_num for c in comparisons),'rank_meta':ranks}
    module.random.random=lambda:0.19
    assert wm.should_execute()
    module.random.random=lambda:0.21
    assert not wm.should_execute()
    result={'upstream_commit':COMMIT,'source_path':relative,'source_sha256':hashlib.sha256(source).hexdigest(),
            'method':'Pinned source executed with package imports removed and Node/query replaced by local stubs. No network or candidate-code execution.',
            'cache_reversal_check':cache,'fully_confident_tournament':decisive,
            'all_low_confidence_check':uncertain_case,
            'execution_probability_check':{'configured_probability':0.2,'draw_0_19':True,'draw_0_21':False}}
    (Path(os.environ.get('FOREAGENT_RUN_DIR', str(ROOT / 'runs/selection'))) / 'foreagent_selection_checks.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
    manifest = json.loads((ROOT/'experiments/coverage_manifest.json').read_text())
    coverage = []
    for task_entry in manifest['tasks']:
        task = task_entry['task']
        groups = json.loads((ROOT/'data/coverage/solutions_subset_50'/task/'ground_truth'/f'groups_{task}_n2.json').read_text())
        ids = {Path(p).name for g in groups for p in g['paths']}
        edges = {tuple(sorted(Path(p).name for p in g['paths'])) for g in groups}
        raw = json.loads((ROOT/'data/author_reference'/f'{task}.json').read_text())['results']
        scores = defaultdict(set)
        for g in groups:
            for p,score in zip(g['paths'],g['scores']): scores[Path(p).name].add(score)
        coverage.append({'task':task,'candidates':len(ids),'pairs':len(edges),'possible':len(ids)*(len(ids)-1)//2,
                         'author_rows':len(raw),'missing_confidence':sum(r['prediction'].get('confidence') is None for r in raw),
                         'conflicting_candidate_scores':sum(len(v)>1 for v in scores.values())})
    (Path(os.environ.get('FOREAGENT_RUN_DIR', str(ROOT / 'runs/selection'))) / 'foreagent_replay_coverage_check.json').write_text(json.dumps(coverage,ensure_ascii=False,indent=2))
    print(json.dumps(result,ensure_ascii=False))


if __name__=='__main__':
    main()
