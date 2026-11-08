"""Original-vs-C0 two-step Agent replay on identical new short-training outputs."""
import argparse
import csv
import importlib.util
import json
from pathlib import Path
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import types
from unittest.mock import patch

from .correctness import stanford_score
from .data import ROOT, dump
from .install import install


def worker(original, smoke, output):
    import pandas as pd
    output.mkdir(parents=True)
    source=output/'source-copy'
    shutil.copytree(ROOT/'phase1-reproduction/code/author',source)
    if not original:install(source)
    sys.path[:0]=[str(source/'mle-bench/agents/aide'),str(source/'mle-bench')]
    def forbidden(*args,**kwargs):raise AssertionError('Network disabled')
    with patch.object(socket.socket,'connect',forbidden),patch.object(socket,'create_connection',forbidden):
        from aide.agent import Agent
        from aide.journal import Journal,Node
        from aide.interpreter import ExecutionResult
        from aide.utils.metric import MetricValue
        import aide.world_model as wm
        wm.query=lambda **kwargs:'{"predicted_best_index":0,"confidence":0.9}'
        summary=json.loads((smoke/'summary.json').read_text())
        results={r['node']:r for r in summary['results'] if r['seed']==41}
        codes={k:(ROOT/f'phase1-reproduction/records/stanford-autodl-v2/workspaces/exp/all_nodes/node_{k}/code.py').read_text() for k in results}
        lookup={v:k for k,v in codes.items()}
        workspace=output/'workspace';workspace.mkdir()
        cfg=types.SimpleNamespace(workspace_dir=workspace,task_name='stanford-covid-vaccine',
            agent=types.SimpleNamespace(use_world_model=True,world_model_confidence_threshold=.7,
                world_model_exec_probability=1.0,improve_num_candidates=3,improve_top_k=3))
        journal=Journal();agent=Agent('Public-data before/after diagnostic',cfg,journal)
        agent.data_preview='controlled';agent.data_analysis_report='controlled';agent.update_data_preview=lambda:None
        def execute(code,reset):
            key=lookup[code]
            shutil.copyfile(smoke/f'{key}-41/validation_predictions.csv',workspace/'submission/submission.csv')
            return ExecutionResult(term_out=['controlled execution return '+key],exec_time=0,exc_type=None)
        def parse(node,exec_result):
            key=lookup[node.code];node.absorb_exec_result(exec_result)
            node.metric=MetricValue(results[key]['independent_validation_mcrmse'],maximize=False)
            node.is_buggy=False;node.analysis='New smoke predictions independently scored';return node
        agent.parse_exec_result=parse
        initial=Node(code=codes['2310e6bf'],id='initial_trans',plan='initial incumbent')
        agent._draft=lambda:initial;agent.search_policy=lambda:None
        agent.step(execute)
        candidates=[Node(code=codes[k],id=k+'later',parent=initial,plan='real archived model') for k in results]
        agent._improve_batch=lambda parent,n:list(candidates);agent.search_policy=lambda:initial
        agent.step(execute)
        info=(workspace/'best_solution/node_info.txt').read_text()
        saved=re.search(r'node_id: (\S+)',info)[1]
        with (workspace/'best_submission/submission.csv').open() as f:pred=list(csv.DictReader(f))
        with (smoke/'2310e6bf-41/validation_answers.csv').open() as f:answers=list(csv.DictReader(f))
        value=stanford_score(pred,answers)
        grader=source/'mle-bench/mlebench/competitions/stanford-covid-vaccine/grade.py'
        spec=importlib.util.spec_from_file_location('diagnostic_grade',grader);mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
        frame=pd.DataFrame(pred);truth=pd.DataFrame(answers)
        for c in ['reactivity','deg_Mg_pH10','deg_Mg_50C','deg_pH10','deg_50C']:
            frame[c]=pd.to_numeric(frame[c]);truth[c]=pd.to_numeric(truth[c])
        truth['keep']=truth['keep'].map(lambda v:str(v).lower()=='true')
        own=float(mod.grade(frame,truth));shuffled=float(mod.grade(frame.iloc[::-1].reset_index(drop=True),truth))
        result=dict(original=original,saved_node=saved,journal_best=journal.get_best_node().id,
            saved_public_mcrmse=value,journal_best_public_mcrmse=journal.get_best_node().metric.value,
            own_grader_score=own,own_grader_reordered_score=shuffled,
            same_input_predictions=True,live_model_calls=0,
            scope='Two real Agent.step calls; fixed candidates, judgments and new smoke execution returns. Component correctness, not full search performance.')
        dump(output/'result.json',result)
    # Keep the small workspace/artifacts and source hashes, not a redundant full repo.
    dump(output/'source-copy-hashes.json',{str(p.relative_to(source)):__import__('hashlib').sha256(p.read_bytes()).hexdigest() for p in source.rglob('*.py')})
    shutil.rmtree(source)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--smoke',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--worker',choices=['original','corrected'])
    a=p.parse_args();a.smoke=a.smoke.resolve();a.output=a.output.resolve()
    if a.worker:worker(a.worker=='original',a.smoke,a.output)
    else:
        if a.output.exists():raise ValueError('Preserve old diagnostics')
        a.output.mkdir(parents=True)
        for mode in ['original','corrected']:
            subprocess.run([sys.executable,'-m',__package__+'.baseline_equivalence','--worker',mode,'--smoke',str(a.smoke),'--output',str(a.output/mode)],cwd=ROOT,check=True,timeout=60)
        rows={m:json.loads((a.output/m/'result.json').read_text()) for m in ['original','corrected']}
        assert rows['corrected']['saved_node']==rows['corrected']['journal_best']
        assert abs(rows['corrected']['own_grader_score']-rows['corrected']['own_grader_reordered_score'])<1e-12
        dump(a.output/'summary.json',rows);print(json.dumps(rows,indent=2))
