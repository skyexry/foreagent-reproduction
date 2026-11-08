"""Load the new checksum-verified overlay without API dependency imports."""
import ast
import hashlib
import json
import logging
from pathlib import Path
import sys
import types

from .correctness import response_values, prepare_submission, submission_problem, save_checkpoint
from .ranking import rank_candidates

HERE = Path(__file__).resolve().parent


def load_world(original=False):
    manifest = json.loads((HERE/'manifest.json').read_text())
    path = (HERE.parents[1]/'phase1-reproduction/code/author/mle-bench/agents/aide/aide/world_model.py'
            if original else HERE/'overlay/world_model.py')
    raw = path.read_bytes()
    expected = manifest['source_sha256'][path.name] if original else manifest['overlay_sha256'][path.name]
    if hashlib.sha256(raw).hexdigest() != expected:
        raise ValueError('Corrected world-model snapshot changed')
    tree = ast.parse(raw)
    tree.body = [n for n in tree.body if not (isinstance(n, ast.ImportFrom) and n.level)]
    module = types.ModuleType('_clean_ranking_world_v1')
    sys.modules[module.__name__] = module
    def disabled(**kwargs):
        raise RuntimeError('Live model backend disabled in offline loader')
    module.__dict__.update(Node=types.SimpleNamespace, query=disabled,
                           response_values=response_values, rank_candidates=rank_candidates)
    exec(compile(tree, str(path), 'exec'), module.__dict__)
    module.logger.setLevel(logging.CRITICAL)
    return module


def agent_methods(names):
    path = HERE/'overlay/agent.py'
    tree = ast.parse(path.read_text())
    cl = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'Agent')
    methods = [n for n in cl.body if isinstance(n, ast.FunctionDef) and n.name in names]
    if len(methods) != len(names):
        raise ValueError('Requested corrected Agent methods missing')
    import shutil
    env = dict(Path=Path, Node=types.SimpleNamespace, ExecCallbackType=object,
               ExecutionResult=object, shutil=shutil, prepare_submission=prepare_submission,
               submission_problem=submission_problem, save_checkpoint=save_checkpoint,
               logger=logging.getLogger('clean-agent'), WorstMetricValue=lambda:float('inf'))
    exec(compile(ast.Module(methods, type_ignores=[]), str(path), 'exec'), env)
    return env
