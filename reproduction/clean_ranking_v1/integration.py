"""Real corrected Agent.step with controlled generation/judging and new smoke outputs.

This is an API-free integration replay, not a fresh LLM-generated end-to-end run.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import socket
import sys
import tempfile
import types
from unittest.mock import patch

from .data import ROOT, dump
from .install import install


def run(smoke, output):
    smoke, output=Path(smoke).resolve(),Path(output).resolve()
    if output.exists():raise ValueError('Preserve previous integration output')
    output.mkdir(parents=True)
    summary=json.loads((smoke/'summary.json').read_text())
    by_node={r['node']:r for r in summary['results'] if r['seed']==41}
    outcomes=[]
    with tempfile.TemporaryDirectory(prefix='clean-foreagent-') as td:
        source=Path(td)/'author'
        shutil.copytree(ROOT/'phase1-reproduction/code/author',source)
        install(source)
        sys.path.insert(0,str(source/'mle-bench/agents/aide'))
        def forbidden(*args,**kwargs):raise AssertionError('Network disabled for integration replay')
        with patch.object(socket.socket,'connect',forbidden),patch.object(socket,'create_connection',forbidden):
            from aide.agent import Agent
            from aide.journal import Journal,Node
            from aide.interpreter import ExecutionResult
            from aide.utils.metric import MetricValue
            from aide.correctness import verify_checkpoint
            import aide.world_model as wm
            wm.query=lambda **kwargs:'{"predicted_best_index":0,"confidence":0.9}'
            for policy in ['original','coverage_decision_sensitive']:
                workspace=output/policy;workspace.mkdir()
                cfg=types.SimpleNamespace(workspace_dir=workspace,task_name='stanford-covid-vaccine',
                    agent=types.SimpleNamespace(use_world_model=True,world_model_confidence_threshold=.7,
                        world_model_exec_probability=1.0,improve_num_candidates=3,improve_top_k=3,
                        ranking_policy=policy,ranking_comparison_budget=3,ranking_seed=91))
                journal=Journal();agent=Agent('Public-data integration check',cfg,journal)
                agent.data_preview='controlled public input';agent.data_analysis_report='controlled report'
                agent.update_data_preview=lambda:None
                parent=Node(code='parent fixture',plan='controlled parent',is_buggy=False)
                agent.search_policy=lambda:parent
                nodes=[];lookup={}
                for key in by_node:
                    code=(ROOT/f'phase1-reproduction/records/stanford-autodl-v2/workspaces/exp/all_nodes/node_{key}/code.py').read_text()
                    node=Node(code=code,id=key+'debug',plan='archived real candidate',parent=parent)
                    nodes.append(node);lookup[hashlib.sha256(code.encode()).hexdigest()]=key
                agent._improve_batch=lambda parent,n:list(nodes)
                events=[]
                def execute(code,reset):
                    key=lookup[hashlib.sha256(code.encode()).hexdigest()]
                    assert not (workspace/'submission/submission.csv').exists()
                    shutil.copyfile(smoke/f'{key}-41/validation_predictions.csv',workspace/'submission/submission.csv')
                    events.append(key)
                    return ExecutionResult(term_out=['new short-training artifact '+key],
                        exec_time=by_node[key]['training_seconds'],exc_type=None)
                def parse(node,exec_result):
                    key=lookup[hashlib.sha256(node.code.encode()).hexdigest()]
                    node.absorb_exec_result(exec_result)
                    node.metric=MetricValue(by_node[key]['independent_validation_mcrmse'],maximize=False)
                    node.is_buggy=False;node.analysis='Independent public holdout score; controlled parser'
                    return node
                agent.parse_exec_result=parse
                agent.step(execute)
                assert len(events)==3 and len(journal.good_nodes)==3
                manifest=verify_checkpoint(workspace)
                best=journal.get_best_node()
                assert manifest['node_id']==best.id
                outcomes.append(dict(policy=policy,executed_candidates=events,
                    best_node=best.id,best_public_metric=best.metric.value,checkpoint=manifest,
                    live_model_calls=0))
    result=dict(status='passed',policies=outcomes,actual_Agent_step_executed=True,
        fixture_generation=True,fixture_judgments=True,execution_returns='new six-run smoke artifacts',
        new_candidate_training_in_this_replay=0,new_live_model_calls=0,
        scope='Full corrected Agent class imported from installed overlay; controlled short-chain replay, not live full Agent.')
    dump(output/'summary.json',result);return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--smoke',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();print(json.dumps(run(a.smoke,a.output),indent=2))
