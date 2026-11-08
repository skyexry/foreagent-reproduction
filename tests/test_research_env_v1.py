"""Contract, isolation and scoring checks for the frozen offline environment."""
import copy
import gzip
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from reproduction.research_env_v1 import core
from reproduction.research_env_v1.core import Episode, dump, public_feedback, verify_episode
from reproduction.research_env_v1.isolation import PolicyError, Worker, probe


class EnvironmentTests(unittest.TestCase):
    def setUp(self):
        self.registry=core.read_json(core.REGISTRY)
        self.job=dict(job_id='private-task:0:0',task='private-task',ids=['a','b','c'],seed=7,budget=2)
        self.bank={'a|b':dict(order=['b','a'],predicted_best_index=0,confidence=.9),
                   'a|c':dict(order=['a','c'],predicted_best_index=0,confidence=.4),
                   'b|c':dict(order=['b','c'],predicted_best_index=1,confidence=.8)}

    def test_observation_contains_only_contract(self):
        obs=Episode(self.job,self.bank).observation()
        self.assertEqual(set(obs),set(self.registry['policy']['visible_fields']))
        self.assertEqual(obs['feedback'],[])
        self.assertNotIn('private-task',json.dumps(obs))

    def test_reversed_query_is_cache_and_same_winner(self):
        env=Episode(self.job,self.bank)
        env.act(dict(action='compare',pair=['a','b']))
        env.act(dict(action='compare',pair=['b','a']))
        self.assertEqual([r['winner'] for r in env.trace],['b','b'])
        self.assertEqual(env.stats()['unique_feedback_reads'],1)
        self.assertEqual(env.stats()['cache_reads'],1)
        self.assertEqual(env.selected(),['b'])

    def test_confidence_threshold_and_invalid_index(self):
        self.assertFalse(public_feedback(self.bank,'a','c',.7)['valid'])
        self.bank['a|b']['predicted_best_index']=True
        self.assertIsNone(public_feedback(self.bank,'a','b',.7)['winner'])

    def test_unique_budget_is_enforced(self):
        env=Episode({**self.job,'budget':1},self.bank)
        env.act(dict(action='compare',pair=['a','b']))
        with self.assertRaises(PolicyError):
            env.act(dict(action='compare',pair=['a','c']))
        self.assertEqual(len(env.observed),1)

    def test_repeat_attempt_limit_is_enforced(self):
        env=Episode(self.job,self.bank,max_attempts=2)
        action=dict(action='compare',pair=['a','b'])
        env.act(action)
        env.act(action)
        with self.assertRaises(PolicyError):
            env.act(action)

    def test_malformed_actions_and_foreign_ids(self):
        for action in ([],{},dict(action='score'),dict(action='compare',pair=['a','a']),
                       dict(action='compare',pair=['a','outside']),dict(action='stop',extra=1)):
            with self.subTest(action=action),self.assertRaises(PolicyError):
                Episode(self.job,self.bank).act(action)

    def test_stop_preserves_uniform_tie(self):
        env=Episode(self.job,self.bank)
        self.assertFalse(env.act({'action':'stop'}))
        self.assertEqual(env.selected(),self.job['ids'])
        self.assertEqual(core.evaluate(self.job['ids'],env.selected(),dict(a=0,b=1,c=2)),
                         dict(regret=.5,best_hit=1/3))
        self.assertEqual(core.evaluate(['a','b'],['a','b'],dict(a=1,b=1)),dict(regret=0,best_hit=1))

    def test_independent_trace_verification_rejects_tampering(self):
        env=Episode(self.job,self.bank)
        env.act(dict(action='compare',pair=['a','b']))
        env.act({'action':'stop'})
        row=dict(selected=env.selected(),status='ok',stop_reason='policy_stop',
                 trace=env.trace,actions=env.actions,stats=env.stats())
        verify_episode(row,self.job,self.bank,self.registry)
        changed=copy.deepcopy(row)
        changed['trace'][0]['winner']='a'
        with self.assertRaises(ValueError):
            verify_episode(changed,self.job,self.bank,self.registry)
        changed=copy.deepcopy(row)
        changed['actions'].insert(0,{'action':'stop'})
        changed['stats']['attempts']+=1
        with self.assertRaises(ValueError):
            verify_episode(changed,self.job,self.bank,self.registry)

    def test_source_hash_mismatch_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'input'
            path.write_text('first')
            expected={'input':core.digest(path)}
            core.verify_files(expected,Path(directory))
            path.write_text('changed')
            with self.assertRaises(ValueError):
                core.verify_files(expected,Path(directory))

    def test_failed_episode_stays_in_score_denominator(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            registry=copy.deepcopy(self.registry)
            registry['benchmark'].update(prepared='.',protocol='protocol.json',reference_decisions='reference.gz')
            registry['paths']['protected_manifest']='protected.json'
            dump(root/'registry.json',registry)
            dump(root/'protected.json',{'sha256':{}})
            dump(root/'protocol.json',dict(bootstrap_seed=7,bootstrap_repeats=10))
            dump(root/'evaluation_labels.json',{'private-task':dict(a=0,b=1,c=2)})
            stats=dict(unique_feedback_reads=0,cache_reads=0,budget_denials=0,comparison_records=0,attempts=0)
            with gzip.open(root/'reference.gz','wt') as stream:
                stream.write(json.dumps(dict(job_id=self.job['job_id'],method='corrected_tournament',selected=['c'],stats=stats))+'\n')
            output=root/'run'
            output.mkdir()
            dump(output/'episode_plan.json',[self.job])
            (output/'policy.py').write_text('def decide(obs): raise RuntimeError()\n')
            dump(output/'run_info.json',dict(environment_id=registry['environment_id'],mode='submitted_policy',
                 jobs=1,full_population=True,registry_sha256=core.digest(root/'registry.json'),
                 protected_manifest_sha256=core.digest(root/'protected.json'),policy_sha256=core.digest(output/'policy.py')))
            row=dict(job_id=self.job['job_id'],selected=[],status='failed',error='RuntimeError',
                     stop_reason='policy_failure',trace=[],actions=[],stats=stats)
            with gzip.open(output/'decisions.jsonl.gz','wt') as stream:
                stream.write(json.dumps(row)+'\n')
            dump(output/'run_manifest.json',{p.name:core.digest(p) for p in output.iterdir()})
            with patch.object(core,'ROOT',root),patch.object(core,'REGISTRY',root/'registry.json'),patch.object(
                    core,'load_context',return_value=(registry,[self.job],{'private-task':self.bank},{})):
                result=core.evaluate_run(output)
                self.assertEqual(result,core.evaluate_run(output))
            self.assertEqual(result['planned_denominator'],1)
            self.assertEqual(result['macro']['submitted_policy']['regret'],1)
            self.assertEqual(result['macro']['submitted_policy']['best_hit'],0)
            self.assertIsNone(result['valid_only_episode_mean_regret'])

    def test_policy_path_must_be_editable(self):
        with self.assertRaises(ValueError):
            core.policy_bytes(core.REGISTRY,self.registry)


class SandboxTests(unittest.TestCase):
    def test_canary_write_and_network_probes(self):
        self.assertEqual(probe(),dict(private_read=True,outside_write=True,network=True))

    def test_actual_evaluation_file_and_credentials_hidden(self):
        path=core.ROOT/'experiments/clean-ranking-v1/prepared/evaluation_labels.json'
        source=('import os\ndef decide(obs):\n'
                '    try:\n        open('+repr(str(path))+').read()\n        blocked=False\n'
                '    except PermissionError:\n        blocked=True\n'
                '    return {"blocked":blocked,"env":sorted(os.environ)}\n').encode()
        with Worker(source) as worker:
            result=worker.request({})
        self.assertTrue(result['blocked'])
        self.assertTrue(set(result['env'])<= {'TMPDIR','LC_ALL','LC_CTYPE'})

    def test_import_time_read_is_blocked(self):
        source=('open('+repr(str(core.REGISTRY))+').read()\ndef decide(obs): return {"action":"stop"}').encode()
        with Worker(source) as worker,self.assertRaises(PolicyError):
            worker.request({})

    def test_process_state_resets_each_episode(self):
        source=b'n=0\ndef decide(obs):\n global n\n n+=1\n return {"n":n}\n'
        for _ in range(2):
            with Worker(source) as worker:
                self.assertEqual(worker.request({}),{'n':1})

    def test_response_timeout_and_blocked_input_timeout(self):
        for payload in ({},{'large':'x'*200000}):
            with Worker(b'import time\ntime.sleep(2)\ndef decide(obs): return {}',timeout=.1) as worker:
                with self.assertRaisesRegex(PolicyError,'timeout'):
                    worker.request(payload)

    def test_non_object_and_excessive_output(self):
        for source in (b'def decide(obs): return []',b'def decide(obs): return {"x":"x"*70000}'):
            with Worker(source) as worker,self.assertRaises(PolicyError):
                worker.request({})


if __name__=='__main__':
    unittest.main()
