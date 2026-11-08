"""Run the pinned author's exact execution-policy AST with local recording callbacks."""
import ast
import copy
import hashlib
import logging
from pathlib import Path
import types

SOURCE=Path(__file__).resolve().parents[2]/'vendor/foreagent_upstream/mle-bench/agents/aide/aide/agent.py'
EXPECTED='81cf3ddb60eea401f41eb1ccb0a069b3e28ee01debceeb224a6292f6f75063de'


def load_policy():
    assert hashlib.sha256(SOURCE.read_bytes()).hexdigest()==EXPECTED
    tree=ast.parse(SOURCE.read_text())
    method=next(n for n in ast.walk(tree) if isinstance(n,ast.FunctionDef) and n.name=='_improve_with_world_model')
    start=next(i for i,n in enumerate(method.body) if isinstance(n,ast.Assign)
               and any(isinstance(t,ast.Name) and t.id=='executed_count' for t in n.targets))
    statements=method.body[start:]
    assert len(statements)==3 and isinstance(statements[-1],ast.If)
    assert statements[0].lineno==700 and statements[-1].end_lineno==767
    function=ast.parse('def execute_policy(self, ranked_candidates, world_model, exec_callback):\n    pass').body[0]
    function.body=copy.deepcopy(statements)
    compiled=ast.fix_missing_locations(ast.Module(body=[function],type_ignores=[]))
    logger=logging.getLogger('offline_execution_policy')
    logger.setLevel(logging.CRITICAL)
    namespace={'logger':logger}
    exec(compile(compiled,str(SOURCE),'exec'),namespace)
    # The executable policy statements are bytecode-compiled from the source
    # AST as-is; only training, journal and filesystem side effects are stubbed.
    assert ast.dump(ast.Module(body=function.body,type_ignores=[]))==ast.dump(ast.Module(body=statements,type_ignores=[]))
    return namespace['execute_policy']


AUTHOR_POLICY=load_policy()


def apply_execution_policy(ranked, rank_meta, world_model):
    nodes=[types.SimpleNamespace(id=node.id,code=node.id,
                                wm_predicted_rank=rank_meta[node.id]['rank'],
                                wm_round=rank_meta[node.id]['round'],is_skipped=False)
           for node in ranked]
    saved=[];executed=[];events=[]
    class Journal:
        def __init__(self): self.nodes=[]
        def append(self,node): self.nodes.append(node)
    agent=types.SimpleNamespace(improve_top_k=1,journal=Journal(),all_nodes_dir=Path('.'),
                                parse_exec_result=lambda node,exec_result:node,
                                _post_process_node=lambda node:None,
                                _save_node_artifacts=lambda node,path:saved.append(node.id))
    def callback(code,reset_session):
        assert reset_session is True
        phase='forced_fallback' if len(saved)>=len(nodes) else 'probability'
        executed.append(code);events.append({'candidate':code,'phase':phase})
        return None
    AUTHOR_POLICY(agent,nodes,world_model,callback)
    forced=len(saved)>len(nodes)
    probability=[e['candidate'] for e in events if e['phase']=='probability']
    assert forced==bool(nodes and not probability)
    assert len(saved)==len(nodes)+int(forced)
    assert len(executed)==len(set(executed))
    assert all(rank_meta[x]['rank']==0 for x in executed)
    if nodes:
        assert executed
    if forced:
        assert executed==[next(node.id for node in nodes if node.wm_predicted_rank==0)]
    return {'final_executed':executed,'probability_executed':probability,
            'forced_fallback':forced,'execution_events':events}


def verify_execution_policy():
    nodes=[types.SimpleNamespace(id=x) for x in 'ABC']
    meta={'A':{'rank':0,'round':1},'B':{'rank':0,'round':1},'C':{'rank':1,'round':1}}
    checked=[]
    for outcomes,expected,forced in [([False,False],['A'],True),
                                     ([True,False],['A'],False),
                                     ([False,True],['B'],False),
                                     ([True,True],['A','B'],False)]:
        sequence=iter(outcomes);calls=[]
        def should_execute():
            value=next(sequence);calls.append(value);return value
        result=apply_execution_policy(nodes,meta,types.SimpleNamespace(should_execute=should_execute))
        assert result['final_executed']==expected and result['forced_fallback']==forced
        assert len(calls)==2
        checked.append('passed')
    return {'author_policy_ast_exact':True,'policy_source_lines':[700,767],
            'two_tied_candidates_all_four_probability_outcomes_passed':len(checked),
            'rank_outside_top_group_never_sampled':True,
            'fallback_uses_first_rank_zero_without_extra_random_draw':True}
