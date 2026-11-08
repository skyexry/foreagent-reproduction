"""Matched-label and Python-access probes; a bounded diagnostic, not an OS sandbox."""
import ast
import hashlib
import inspect
import json
from pathlib import Path
import socket
import sys
from unittest.mock import patch

from . import smoke
from .data import ROOT, dump


def run(output):
    import torch
    import pandas
    import sklearn.metrics
    output=Path(output)
    if output.exists():raise ValueError('Preserve previous controls')
    output.mkdir(parents=True)
    denied=[]
    def guard(event,args):
        if event in ('socket.connect','subprocess.Popen','os.system'):
            denied.append(event);raise PermissionError('Diagnostic access guard: '+event)
        if event=='open' and isinstance(args[0],(str,bytes)):
            path=Path(args[0]).resolve()
            if ('ground_truth' in path.parts or ROOT/'reports' in path.parents
                or path==ROOT/'experiments/clean-ranking-v1/prepared/evaluation_labels.json'
                or ('private' in path.parts and path.suffix in ('.csv','.json','.jsonl'))):
                denied.append('open:'+str(path));raise PermissionError('Private/evaluation input blocked')
    sys.addaudithook(guard)
    ground=next((ROOT/'data/reward-model/corpus-6b322cb-raw-v1/solutions_subset_50').glob('*/ground_truth/*n2.json'))
    try:ground.read_text();raise AssertionError('Ground truth probe should be blocked')
    except PermissionError:pass
    try:
        with socket.socket() as sock:sock.connect(('127.0.0.1',9))
        raise AssertionError('Network probe should be blocked')
    except PermissionError:pass
    # Reuse the exact checked worker; only replace its clock-based stop by 20
    # updates so the two label conditions have identical optimization budgets.
    tree=ast.parse(inspect.getsource(smoke.worker))
    loops=[n for n in ast.walk(tree) if isinstance(n,ast.While)]
    assert len(loops)==1
    loops[0].test=ast.Compare(left=ast.Name(id='steps',ctx=ast.Load()),ops=[ast.Lt()],comparators=[ast.Constant(20)])
    ast.fix_missing_locations(tree);namespace=dict(smoke.__dict__)
    exec(compile(tree,'fixed-step-public-diagnostic','exec'),namespace)
    real_loader=torch.utils.data.DataLoader
    shifted=[0]
    def shuffled_loader(dataset,*args,**kwargs):
        if isinstance(dataset,torch.utils.data.TensorDataset) and len(dataset)==4:
            x,y=dataset.tensors
            dataset=torch.utils.data.TensorDataset(x,torch.roll(y,1,0));shifted[0]+=1
        return real_loader(dataset,*args,**kwargs)
    namespace['worker']('0cae1a47',43,output/'normal')
    with patch.object(torch.utils.data,'DataLoader',shuffled_loader):
        namespace['worker']('0cae1a47',43,output/'shuffled')
    normal=json.loads((output/'normal/result.json').read_text());shuffled=json.loads((output/'shuffled/result.json').read_text())
    assert shifted[0]==20 and normal['training_steps']==shuffled['training_steps']==20
    assert normal['train_ids']==shuffled['train_ids'] and normal['validation_ids']==shuffled['validation_ids']
    assert (output/'normal/validation_answers.csv').read_bytes()==(output/'shuffled/validation_answers.csv').read_bytes()
    assert (output/'normal/validation_predictions.csv').read_bytes()!=(output/'shuffled/validation_predictions.csv').read_bytes()
    result=dict(status='passed',matched_steps=20,training_label_permutation_batches=shifted[0],
        unchanged_validation_labels=True,predictions_respond_to_training_labels=True,
        normal_public_mcrmse=normal['independent_validation_mcrmse'],
        shuffled_public_mcrmse=shuffled['independent_validation_mcrmse'],
        blocked_access_probes=denied,successful_extra_training_runs=2,
        scope='LSTM public-data matched-update label-flow check and Python audit probes. This is not an OS sandbox or evidence of final model generalization.')
    dump(output/'summary.json',result);return result


if __name__=='__main__':
    print(json.dumps(run(ROOT/'experiments/clean-ranking-v1/negative-controls'),indent=2))
