"""Five-second CPU checks of archived real model/preprocessing/loss functions.

Only whitelisted definitions are executed. Full generated scripts, their
top-level IO, private test labels, API clients and historical rankings are not
executed. This is a component check, not a full ForeAgent rerun.
"""
import argparse
import ast
import csv
import hashlib
import json
import math
import os
from pathlib import Path
import random
import subprocess
import sys
import time

from .correctness import stanford_score

ROOT = Path(__file__).resolve().parents[2]
MODELS = {'2310e6bf': 'Transformer', '0cae1a47': 'LSTM', '8dce0f8c': 'CNN+LSTM'}
TARGETS = ['reactivity','deg_Mg_pH10','deg_pH10','deg_Mg_50C','deg_50C']


def worker(node, seed, output):
    import numpy as np
    import pandas as pd
    import torch
    from torch import nn
    from torch.utils.data import Dataset, DataLoader, TensorDataset
    from sklearn.metrics import mean_squared_error
    torch.set_num_threads(2)
    torch.manual_seed(seed);np.random.seed(seed);random.seed(seed)
    torch.use_deterministic_algorithms(True)
    output = Path(output);output.mkdir(parents=True)
    source = ROOT/f'phase1-reproduction/records/stanford-autodl-v2/workspaces/exp/all_nodes/node_{node}/code.py'
    raw = source.read_bytes();tree = ast.parse(raw)
    allowed = {'preprocess_data','encode_sequence','encode_features','preprocess_sequence',
               'preprocess_structure','preprocess_loop_type','get_features','RNADataset',
               'RNAModel','RNADegradationTransformer','PositionScoredMSELoss','mcrmse_loss',
               'train_epoch','validate_epoch'}
    definitions = [n for n in tree.body if isinstance(n,(ast.FunctionDef,ast.ClassDef)) and n.name in allowed]
    for definition in definitions:
        for call in ast.walk(definition):
            if isinstance(call,ast.Call):
                name = call.func.id if isinstance(call.func,ast.Name) else call.func.attr if isinstance(call.func,ast.Attribute) else ''
                dynamic = isinstance(call.func,ast.Name) and name in {'eval','exec','compile','__import__'}
                io = name in {'open','read_csv','read_json','load','save','system','popen','connect'}
                if dynamic or io:
                    raise ValueError('Definition requires review of IO: '+name)
    env = dict(np=np,pd=pd,torch=torch,nn=nn,Dataset=Dataset,
        target_cols=TARGETS,scored_targets=['reactivity','deg_Mg_pH10','deg_Mg_50C'],
        base_to_idx={'A':0,'G':1,'U':2,'C':3}, structure_to_idx={'.':0,'(':1,')':2},
        loop_type_to_idx={'S':0,'M':1,'I':2,'B':3,'H':4,'E':5,'X':6},
        SEQ_LEN=107,SCORED_LEN=68,mean_squared_error=mean_squared_error,
        tqdm=lambda iterable,**kwargs:iterable)
    exec(compile(ast.Module(definitions,type_ignores=[]),str(source),'exec'),env)
    data_file=ROOT/'phase1-reproduction/data/public/train.json'
    records=[json.loads(x) for x in data_file.read_text().splitlines()]
    records=[r for r in records if len(r['sequence'])==107 and all(
        len(r[c])==68 and all(isinstance(x,(int,float)) and math.isfinite(x) for x in r[c]) for c in TARGETS)]
    records=list({r['sequence']:r for r in reversed(records)}.values())
    random.Random(20261108094).shuffle(records)
    train,valid=records[:64],records[64:96]
    assert len(train)==64 and len(valid)==32
    assert not ({r['id'] for r in train}&{r['id'] for r in valid})
    assert not ({r['sequence'] for r in train}&{r['sequence'] for r in valid})
    frame=pd.DataFrame(train+valid)
    y=np.stack([np.stack([r[c] for c in TARGETS],axis=-1) for r in train+valid]).astype(np.float32)
    if node=='2310e6bf':
        x,_=env['preprocess_data'](frame,True);model=env['RNADegradationTransformer']()
        criterion=nn.MSELoss();optimizer=torch.optim.AdamW(model.parameters(),lr=.001,weight_decay=.01)
        y_train=y
    elif node=='0cae1a47':
        x=env['encode_features'](frame['sequence'].values,frame['structure'].values,frame['predicted_loop_type'].values)
        model=env['RNAModel']();criterion=env['PositionScoredMSELoss']()
        optimizer=torch.optim.Adam(model.parameters(),lr=.001);y_train=y
    else:
        x=np.stack([env['get_features'](r) for r in train+valid]).astype(np.float32)
        model=env['RNAModel'](input_dim=x.shape[-1]);criterion=env['mcrmse_loss']
        optimizer=torch.optim.Adam(model.parameters(),lr=.001)
        y_train=np.pad(y,((0,0),(0,39),(0,0)))
    dtype=torch.float32 if node=='8dce0f8c' else torch.long
    x=torch.tensor(x,dtype=dtype);target=torch.tensor(y_train,dtype=torch.float32)
    before=next(model.parameters()).detach().clone()
    start=time.monotonic();steps=0;losses=[]
    while time.monotonic()-start<5 or not steps:
        indices=np.random.choice(64,4,replace=False)
        batch=DataLoader(TensorDataset(x[indices],target[indices]),batch_size=4)
        if node!='8dce0f8c':
            loss=env['train_epoch'](model,batch,optimizer,criterion,torch.device('cpu'))
        else:
            model.train();optimizer.zero_grad();pred=model(x[indices]);loss=criterion(pred,target[indices])
            loss.backward();optimizer.step();loss=float(loss.detach())
        assert math.isfinite(loss)
        assert all(p.grad is None or torch.isfinite(p.grad).all() for p in model.parameters())
        losses.append(float(loss));steps+=1
    train_seconds=time.monotonic()-start
    changed=not torch.equal(before,next(model.parameters()).detach());assert changed
    model.eval()
    with torch.no_grad():pred=model(x[64:]).numpy()
    assert pred.shape==(32,107,5) and np.isfinite(pred).all()
    expected=float(np.sqrt(np.mean((pred[:,:68,[0,1,3]]-y[64:,:,[0,1,3]])**2,axis=(0,1))).mean())
    # Numpy advanced indexing above preserves sample,position,target with a final
    # axis slice; assert explicitly against one-target-at-a-time calculation.
    reference=float(np.mean([np.sqrt(np.mean((pred[:,:68,i]-y[64:,:,i])**2)) for i in [0,1,3]]))
    assert math.isclose(expected,reference,rel_tol=1e-6)
    prediction_rows=[];answer_rows=[]
    for row,prediction in zip(valid,pred):
        for position in range(107):
            identity=f"{row['id']}_{position}"
            prediction_rows.append(dict(id_seqpos=identity,**{c:float(prediction[position,i]) for i,c in enumerate(TARGETS)}))
            answer_rows.append(dict(id_seqpos=identity,keep=position<68,
                **{c:float(row[c][position]) if position<68 else 0.0 for c in TARGETS}))
    score=stanford_score(prediction_rows,answer_rows)
    assert math.isclose(score,reference,rel_tol=1e-5)
    assert math.isclose(score,stanford_score(prediction_rows[::-1],answer_rows),abs_tol=1e-12)
    native=None
    if node!='8dce0f8c':
        native=env['validate_epoch'](model,DataLoader(TensorDataset(x[64:],target[64:]),batch_size=8),criterion,torch.device('cpu'))
        if isinstance(native,tuple):
            native=[{'shape':list(a.shape),'finite':bool(np.isfinite(a).all())}
                    if isinstance(a,np.ndarray) else float(a) for a in native]
        else:
            native=float(native)
    else:
        with torch.no_grad():native=float(criterion(torch.tensor(pred),target[64:]))
    # Controlled metric checks: predictions on unscored positions must not alter
    # official MCRMSE, whereas changing scored positions must change it.
    altered=[dict(r) for r in prediction_rows]
    for r,a in zip(altered,answer_rows):
        if not a['keep']:
            for c in TARGETS:r[c]+=1000
    assert math.isclose(score,stanford_score(altered,answer_rows),abs_tol=1e-12)
    result=dict(node=node,architecture=MODELS[node],seed=seed,source_sha256=hashlib.sha256(raw).hexdigest(),
        extracted_definitions=[n.name for n in definitions],train_ids=[r['id'] for r in train],
        validation_ids=[r['id'] for r in valid],training_steps=steps,training_seconds=train_seconds,
        parameters=sum(p.numel() for p in model.parameters()),parameter_update=changed,
        first_loss=losses[0],last_loss=losses[-1],independent_validation_mcrmse=score,
        native_validation_output=native,source_native_validation_contract='recorded separately; may be batch-averaged or use padded positions',
        private_labels_accessed=False,live_api_calls=0,
        scope='Actual archived model, preprocessing and loss definitions; timed harness, fixed public-data split. Full script and full Agent not executed.')
    for name,rows in [('validation_predictions.csv',prediction_rows),('validation_answers.csv',answer_rows)]:
        with (output/name).open('w',newline='') as stream:
            writer=csv.DictWriter(stream,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    (output/'result.json').write_text(json.dumps(result,indent=2)+'\n')


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--node',choices=list(MODELS));p.add_argument('--seed',type=int);args=p.parse_args()
    if args.node:
        worker(args.node,args.seed,args.output);return
    if args.output.exists():raise ValueError('Use a new output directory')
    args.output.mkdir(parents=True)
    rows=[]
    for node in MODELS:
        for seed in (41,42):
            out=args.output/f'{node}-{seed}'
            subprocess.run([sys.executable,'-m',__package__+'.smoke','--node',node,'--seed',str(seed),'--output',str(out)],
                cwd=ROOT,env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1','OMP_NUM_THREADS':'2','MKL_NUM_THREADS':'2'},
                check=True,timeout=60)
            rows.append(json.loads((out/'result.json').read_text()));print('smoke passed',node,seed,flush=True)
    summary=dict(runs=len(rows),models=3,new_model_calls=0,gpu_used=False,
        scope='Component diagnostics on public data; five-second rankings are not final architecture results.',
        diagnostic_rankings={str(seed):[r['node'] for r in sorted([r for r in rows if r['seed']==seed],key=lambda x:x['independent_validation_mcrmse'])] for seed in (41,42)},results=rows)
    (args.output/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')


if __name__=='__main__':main()
