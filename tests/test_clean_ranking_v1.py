"""Counterexamples and invariants for the new source overlay and policies."""
from concurrent.futures import ThreadPoolExecutor
import csv
import json
import math
from pathlib import Path
import tempfile
import types
import unittest
from unittest.mock import patch

from reproduction.clean_ranking_v1.correctness import (
    prepare_submission, save_checkpoint, response_values, stanford_score,
    submission_problem, verify_checkpoint,
)
from reproduction.clean_ranking_v1.loader import load_world, agent_methods
from reproduction.clean_ranking_v1.ranking import allocate, top_set
from reproduction.clean_ranking_v1.run import select, evaluate


class CleanRankingTests(unittest.TestCase):
    def test_original_cache_counterexample_and_fixed_direction(self):
        a, b = [types.SimpleNamespace(id=x, code=x) for x in ['A','B']]
        for original in (True, False):
            module = load_world(original)
            module.query = lambda **kw:'{"predicted_best_index":0,"confidence":0.9}'
            model = module.WorldModel('task','report')
            ab, ba = model.predict_pairwise(a,b), model.predict_pairwise(b,a)
            self.assertEqual(ab.winner_idx, 0)
            self.assertEqual(ba.winner_idx, 0 if original else 1)

    def test_cache_context_threshold_and_same_pair_concurrency(self):
        module = load_world(); calls=[]
        module.query = lambda **kw:(calls.append(kw) or '{"predicted_best_index":0,"confidence":0.65}')
        a, b = [types.SimpleNamespace(id=x,code=x) for x in ['A','B']]
        model = module.WorldModel('task','report',config=module.WorldModelConfig(confidence_threshold=.7))
        self.assertFalse(model.predict_pairwise(a,b).is_valid)
        model.config.confidence_threshold=.6
        self.assertTrue(model.predict_pairwise(b,a).is_valid)
        self.assertEqual(len(calls),1)
        model.task_desc='another task'; model.predict_pairwise(a,b)
        self.assertEqual(len(calls),2)
        other=module.WorldModel('task','report')
        with ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(lambda n:other.predict_pairwise(*( (a,b) if n%2 else (b,a))), range(12)))
        self.assertEqual(len(calls),3)

    def test_strict_response_contract(self):
        for winner,confidence in [(True,.9),(.2,.9),(2,.9),(None,.9),(0,True),(0,1.2),(0,float('inf'))]:
            self.assertIsNone(response_values(dict(predicted_best_index=winner,confidence=confidence))[0])
        self.assertEqual(response_values({'predicted_best_index':'1','confidence':'0.9'}),(1,.9))
        module=load_world()
        for raw in ['{"predicted_best_index":true,"confidence":0.9}',
                    '{"predicted_best_index":0.2,"confidence":0.9}',
                    '{"confidence":0.9}']:
            module.query=lambda **kw:raw
            model=module.WorldModel('task','report')
            self.assertFalse(model.predict_pairwise(types.SimpleNamespace(code='a'),types.SimpleNamespace(code='b')).is_valid)

    def test_stale_submission_and_symlink_isolation(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td);prepare_submission(p);(p/'submission/submission.csv').write_text('id,value\na,1\n')
            self.assertIsNone(submission_problem(p));prepare_submission(p)
            self.assertIsNotNone(submission_problem(p))
            (p/'outside').mkdir();(p/'outside/keep').write_text('keep')
            (p/'submission').rmdir();(p/'submission').symlink_to(p/'outside',target_is_directory=True)
            prepare_submission(p);self.assertTrue((p/'outside/keep').exists())

    def test_checkpoint_uses_best_archive_not_latest_file(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td);art=p/'all_nodes/node_A';art.mkdir(parents=True)
            (art/'code.py').write_text('code A');(art/'submission.csv').write_text('A predictions')
            prepare_submission(p);(p/'submission/submission.csv').write_text('B predictions')
            node=types.SimpleNamespace(id='A',code='code A',plan='A plan',metric=0.0)
            save_checkpoint(p,p/'all_nodes',node)
            self.assertEqual((p/'best_submission/submission.csv').read_text(),'A predictions')
            self.assertEqual(verify_checkpoint(p)['node_id'],'A')
            (p/'best_submission/submission.csv').write_text('tampered')
            with self.assertRaises(ValueError):verify_checkpoint(p)

    def test_corrected_agent_step_isolates_each_execution(self):
        method=agent_methods({'step'})['step']
        with tempfile.TemporaryDirectory() as td:
            p=Path(td);events=[]
            def execute(code, reset):
                events.append((p/'submission/submission.csv').exists())
                (p/'submission/submission.csv').write_text(code)
            owner=types.SimpleNamespace(cfg=types.SimpleNamespace(workspace_dir=p),
                journal=types.SimpleNamespace(nodes=[1]),data_preview='ready',
                search_policy=lambda:types.SimpleNamespace(is_buggy=False),use_world_model=True,
                _improve_with_world_model=lambda parent,cb:(cb('A',True),cb('B',True)),
                _update_best_solution=lambda:None,current_step=0)
            method(owner,execute);self.assertEqual(events,[False,False])

    def test_score_order_mask_and_nonfinite_targets(self):
        columns=('reactivity','deg_Mg_pH10','deg_Mg_50C','deg_pH10','deg_50C')
        pred=[dict(id_seqpos=i,**dict.fromkeys(columns,v)) for i,v in [('a',1),('b',3),('c',100)]]
        truth=[dict(id_seqpos=i,keep=keep,**dict.fromkeys(columns,0)) for i,keep in [('a',True),('b',True),('c',False)]]
        self.assertAlmostEqual(stanford_score(pred[::-1],truth),math.sqrt(5))
        self.assertAlmostEqual(stanford_score(pred,truth[::-1]),math.sqrt(5))
        with self.assertRaises(ValueError):stanford_score([pred[0],pred[0],pred[2]],truth)
        truth[0]['reactivity']=float('nan')
        with self.assertRaises(ValueError):stanford_score(pred,truth)

    def test_policies_budget_no_duplicates_and_shared_initial_coverage(self):
        ids=list('ABCDEFGHIJ');traces={}
        for policy in ['random_pairs','coverage_random','coverage_decision_sensitive']:
            trace=[]
            top,_=allocate(ids,lambda a,b:(trace.append((a,b)) or min(a,b)),13,91,policy)
            self.assertTrue(top);self.assertEqual(len(trace),13);self.assertEqual(len(set(trace)),13)
            traces[policy]=trace
        self.assertEqual(traces['coverage_random'][:9],traces['coverage_decision_sensitive'][:9])
        self.assertEqual(set(sum((list(e) for e in traces['coverage_random'][:9]),[])),set(ids))

    def test_small_pools_and_uninformative_feedback(self):
        for n in [0,1,2,3]:
            ids=list(range(n));top,feedback=allocate(ids,lambda a,b:None,13,1,'coverage_decision_sensitive')
            self.assertEqual(set(top),set(ids));self.assertEqual(len(feedback),n*(n-1)//2)

    def test_overlay_original_order_key_and_default_policy(self):
        module=load_world();self.assertEqual(module.WorldModelConfig().selection_policy,'original')
        path=Path(__file__).resolve().parents[1]/'reproduction/clean_ranking_v1/overlay/world_model.py'
        self.assertIn('k = sort_key(info)',path.read_text())

    def test_selection_requires_no_evaluation_label_file(self):
        ids=['a','b','c'];job=dict(ids=ids,budget=3,seed=17,task='synthetic')
        bank={a+'|'+b:dict(order=[a,b],predicted_best_index=0,confidence=.9,source_group_index=i)
              for i,(a,b) in enumerate([('a','b'),('a','c'),('b','c')])}
        module=load_world();original_read=Path.read_text
        def guarded(path,*args,**kwargs):
            if 'evaluation_labels' in str(path):raise AssertionError('Test-label access during selection')
            return original_read(path,*args,**kwargs)
        with patch.object(Path,'read_text',guarded):
            top,trace,stats=select(module,job,bank,{i:'code '+i for i in ids},'coverage_decision_sensitive',.7)
        first=evaluate(ids,top,dict(a=3,b=2,c=1));second=evaluate(ids,top,dict(a=1,b=2,c=3))
        self.assertNotEqual(first['regret'],second['regret']);self.assertEqual(stats['unique_feedback_reads'],3)

    def test_budget_cap_is_counted_as_denied_not_new_evidence(self):
        ids=list('abcde');job=dict(ids=ids,budget=2,seed=17,task='synthetic')
        import itertools
        bank={'|'.join((a,b)):dict(order=[a,b],predicted_best_index=0,confidence=.6,source_group_index=i)
              for i,(a,b) in enumerate(itertools.combinations(ids,2))}
        _,trace,stats=select(load_world(),job,bank,{i:'code '+i for i in ids},'corrected_tournament',.7)
        self.assertEqual(len(trace),2);self.assertGreater(stats['budget_denials'],0)


if __name__ == '__main__':
    unittest.main()
