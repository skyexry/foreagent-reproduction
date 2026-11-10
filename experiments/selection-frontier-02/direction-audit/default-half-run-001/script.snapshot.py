"""Source-informed sensitivity: drop every exact-.5 added edge, retain all high.
This is a labelled post-main-audit diagnostic, never a candidate promotion.
"""
from collections import Counter,defaultdict
import gzip
import json
from pathlib import Path
import statistics
import sys
import time

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(Path(__file__).resolve().parent))
import audit as a


def main():
    out=a.HERE/'default-half-run-001';assert not out.exists();out.mkdir()
    start=time.monotonic()
    a.dump(out/'protocol.json',{'id':'direction-default-half-sensitivity-v1','stage':'Source-informed post-main-audit sensitivity; main C/H/L/E/N32 results already inspected.',
        'purpose':'The upstream parser default is exactly .5. Conservatively drop all added confidence==.5 edges, including genuinely explicit .5, to bound dependence on that ambiguity. Keep .7+ unchanged and all .5<conf<.7 directions. Explanation only; no method promotion or threshold search.',
        'source':'direction-audit/run-003 sealed audit and actual per-bank C0 traces','scoring':'seal V choices before separate label access; compare original C/H/L and paired task macro/bootstrap/leave-one with seed20261108093,10000 draws.','limits':'CPU only; zero models/training/GPU;600s'})
    (out/'script.snapshot.py').write_bytes(Path(__file__).read_bytes())
    rows=a.gzread(a.F/'c0-final-selection/run-001/decisions.sealed.jsonl.gz')
    banks={'DS':a.read(ROOT/'experiments/clean-ranking-v1/prepared/feedback.json')};bm=a.read(a.F/'banks/manifest.json')
    for b,m in bm['banks'].items():banks[b]=json.loads(gzip.decompress((ROOT/m['path']).read_bytes()))
    jobs={x['job_id']:x for x in [json.loads(r) for r in (ROOT/'experiments/clean-ranking-v1/prepared/jobs.jsonl').read_text().splitlines()]}
    a.TASKS=sorted({j['task'] for j in jobs.values()})
    source=a.gzread(a.HERE/'run-003/source_audit.sealed.jsonl.gz')
    unique_counts=defaultdict(Counter);trace_counts=defaultdict(Counter)
    for r in source:
        if r['band']=='low_added':
            c=unique_counts[r['bank']];c['low_added_unique']+=1;c['exact_half']+=r['parsed_confidence']==.5;c['above_half']+=r['parsed_confidence']>.5
            c['exact_half_raw_proven']+=r['parsed_confidence']==.5 and r['raw_explicit_eligible']
            c['reasoning_mismatch_auxiliary']+=r['reasoning_vs_archive_mismatch']
    sealed=[]
    for r in rows:
        b,t,j=r['bank'],r['task'],r['job_id'];edges=[]
        for e in r['trace']:
            item=banks[b][t]['|'.join(sorted((e['a'],e['b'])))];idx,conf=a.response_values(item)
            low=idx is not None and .5<=conf<.7
            if low:
                trace_counts[b]['low_edge_episodes']+=1;trace_counts[b]['exact_half']+=conf==.5;trace_counts[b]['above_half']+=conf>.5
            winner=item['order'][idx] if idx is not None and conf>.5 else None
            edges.append((e['a'],e['b'],winner))
        sealed.append({'bank':b,'task':t,'job_id':j,'selected':a.top(jobs[j]['ids'],edges),'retained_low_count':sum(.5<a.response_values(banks[b][t]['|'.join(sorted((e['a'],e['b'])))])[1]<.7 and a.response_values(banks[b][t]['|'.join(sorted((e['a'],e['b'])))])[0] is not None for e in r['trace'])})
    dest=out/'decisions.sealed.jsonl.gz';dest.write_bytes(gzip.compress(''.join(json.dumps(r,sort_keys=True)+'\n' for r in sealed).encode(),mtime=0))
    a.dump(out/'selection_seal.json',{'sha256':a.sha(dest),'labels_loaded':False,'jobs':3400,'source_script_sha256':a.sha(Path(__file__)),'protocol_sha256':a.sha(out/'protocol.json')})
    labels=a.read(ROOT/'experiments/clean-ranking-v1/prepared/evaluation_labels.json')
    grouped=defaultdict(list)
    for r in sealed:
        grouped[(r['bank'],r['task'])].append(a.score(jobs[r['job_id']]['ids'],r['selected'],labels[r['task']]))
    prior=a.read(a.HERE/'run-003/per_task.json');data={}
    for b in banks:
        data[b]={t:{k:statistics.fmean(r[k] for r in grouped[(b,t)]) for k in ('regret','best_hit')} for t in a.TASKS}
    gpt=[b for b in banks if b!='DS'];data['GPT_task_first_pooled']={t:{k:statistics.fmean(data[b][t][k] for b in gpt) for k in ('regret','best_hit')} for t in a.TASKS}
    results={}
    for b,d in data.items():
        results[b]={'V_macro':{k:statistics.fmean(d[t][k] for t in a.TASKS) for k in ('regret','best_hit')},
                    'contrasts':{f'{arm}-V':{k:a.infer([(prior[b][t][arm][k]-d[t][k])*(1 if k=='regret' else -1) for t in a.TASKS]) for k in ('regret','best_hit')} for arm in ('C','H','L')}}
    a.dump(out/'summary.json',results);a.dump(out/'source_confidence_counts.json',{'all_bank_unique_pairs':{b:dict(c) for b,c in unique_counts.items()},'actual_C0_trace_edge_episodes':{b:dict(c) for b,c in trace_counts.items()},'interpretation':'Exact .5 may be explicit or default; counts alone identify neither. Greater than .5 differs from documented fallback value, conditional on source-parser semantics.'})
    a.dump(out/'per_task.json',data);a.dump(out/'verification.json',{'elapsed_seconds':time.monotonic()-start,'new_model_calls':0,'new_training_runs':0,'scope':'post-main source-informed conservative sensitivity'})
    a.dump(out/'output_sha256.json',{p.name:a.sha(p) for p in out.iterdir() if p.is_file() and p.name!='output_sha256.json'})
    print({b:{'V':r['V_macro']['regret'],'C-V':r['contrasts']['C-V']['regret']['gain'],'L-V':r['contrasts']['L-V']['regret']['gain']} for b,r in results.items()})

if __name__=='__main__':main()
