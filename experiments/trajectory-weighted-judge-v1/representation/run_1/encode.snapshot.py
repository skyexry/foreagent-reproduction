"""Fixed CodeT5 encoder features; all source inputs are available before selection."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import shutil
import time

import numpy as np
import torch
from transformers import RobertaTokenizerFast, T5EncoderModel


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def encode(model_dir, out, batch_size):
    out.mkdir(parents=True, exist_ok=False)
    start = time.monotonic()
    shutil.copyfile(__file__, out/'encode.snapshot.py')
    spec = json.loads((HERE/'spec.json').read_bytes())
    files = {name:sha(model_dir/name) for name in spec['files']}
    assert files['pytorch_model.bin'] == spec['files']['pytorch_model.bin']['sha256']
    torch.set_num_threads(4)
    model, loading = T5EncoderModel.from_pretrained(str(model_dir),local_files_only=True,output_loading_info=True)
    assert not loading['missing_keys'] and not loading['mismatched_keys'] and not loading['error_msgs'], loading
    model.eval()
    tok = RobertaTokenizerFast.from_pretrained(str(model_dir), local_files_only=True)
    mapping = json.loads((ROOT/'experiments/clean-ranking-v1/prepared/code_files.json').read_bytes())
    data = ROOT/'data/reward-model/corpus-6b322cb-raw-v1/tasks'
    docs = []
    for task, codes in sorted(mapping.items()):
        for ident, name in sorted(codes.items()):
            path = ROOT/name
            assert sha(path)[:20] == ident
            docs.append(('code',task+'|'+ident,path.read_text(),{name:sha(path)}))
    for task in sorted(mapping):
        desc,report = [(next(path for key in [task.replace('-','_'), task] if
                            (path:=data/sub/(prefix+key+ext)).is_file()))
                       for sub,prefix,ext in [('description','description_','.md'),
                                               ('data_analysis/result','da_result_','.txt')]]
        body=report.read_text()
        if 'Analysis metadata' in body[:180] and '\nData loading\n' in body:
            body = 'Data loading\n' + body.split('\nData loading\n',1)[1]
        text=desc.read_text()+'\n\n'+body
        docs.append(('context',task,text,{str(p.relative_to(ROOT)):sha(p) for p in (desc,report)}))
    stats=[]
    segments=[]
    for i,(kind,key,text,source) in enumerate(docs):
        ids=tok(text,add_special_tokens=False,verbose=False)['input_ids']
        chunks=[ids[n:n+254] for n in range(0,len(ids),254)]
        assert chunks
        indexes=np.linspace(0,len(chunks)-1,min(8,len(chunks))).round().astype(int).tolist()
        assert len(indexes)==len(set(indexes))
        kept=sum(len(chunks[n]) for n in indexes)
        stats.append(dict(kind=kind,key=key,tokens=len(ids),kept=kept,chunk_indices=indexes,source=source))
        segments.extend((i,chunks[n]) for n in indexes)
    segments.sort(key=lambda item:len(item[1]))
    sums=np.zeros((len(docs),model.config.d_model),dtype=np.float64)
    device='cpu'
    with torch.inference_mode():
        for n in range(0,len(segments),batch_size):
            items=segments[n:n+batch_size]
            width=max(len(ids) for _,ids in items)+2
            tokens=torch.full((len(items),width),tok.pad_token_id,dtype=torch.long)
            mask=torch.zeros_like(tokens)
            content_mask=torch.zeros_like(tokens)
            for row,(_,ids) in enumerate(items):
                tokens[row,:len(ids)+2]=torch.tensor([tok.bos_token_id,*ids,tok.eos_token_id])
                mask[row,:len(ids)+2]=1
                content_mask[row,1:len(ids)+1]=1
            vectors=model(input_ids=tokens,attention_mask=mask).last_hidden_state
            pooled=(vectors*content_mask.unsqueeze(-1)).sum(dim=1).cpu().numpy()
            for row,(i,_) in enumerate(items):
                sums[i]+=pooled[row]
            if n==0 or n//batch_size%50==0:
                print(f'{n+len(items)}/{len(segments)} chunks; {time.monotonic()-start:.1f}s',flush=True)
    norms=np.linalg.norm(sums,axis=1,keepdims=True)
    assert np.isfinite(norms).all() and (norms>0).all()
    vectors=(sums/norms).astype(np.float32)
    output={}
    coverage={}
    for kind,key_field in [('code','code_keys'),('context','task_keys')]:
        indexes=[i for i,d in enumerate(docs) if d[0]==kind]
        output[kind]=vectors[indexes]
        output[key_field]=np.asarray([docs[i][1] for i in indexes])
        total=sum(stats[i]['tokens'] for i in indexes)
        kept=sum(stats[i]['kept'] for i in indexes)
        coverage[kind]=dict(records=len(indexes),original_tokens=total,kept_tokens=kept,
                            fraction=kept/total,docs_with_all_tokens=sum(stats[i]['tokens']==stats[i]['kept'] for i in indexes))
    # Publish a complete file for the downstream fitter.
    temp=out/'embeddings.partial.npz'
    np.savez_compressed(temp,**output)
    temp.replace(out/'embeddings.npz')
    (out/'inputs.json').write_text(json.dumps(stats,indent=2)+'\n')
    info=dict(model=spec['repo'],revision=spec['revision'],files=files,feature_sha256=sha(out/'embeddings.npz'),
              coverage=coverage,dimensions=vectors.shape[1],chunks=len(segments),device=device,batch_size=batch_size,
              torch_version=torch.__version__,seconds=time.monotonic()-start,model_training=False)
    (out/'receipt.json').write_text(json.dumps(info,indent=2)+'\n')
    print(json.dumps(info['coverage']),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('model_dir',type=Path)
    parser.add_argument('out',type=Path)
    parser.add_argument('--batch-size',type=int,default=12)
    args=parser.parse_args()
    encode(args.model_dir,args.out,args.batch_size)
