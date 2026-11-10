"""Source-audit low-confidence directions and fixed-C0 negative controls.

Usage: python3 -B experiments/selection-frontier-02/direction-audit/audit.py --output NEW_DIR
CPU only; all selections sealed before first evaluation-label access.
"""
import argparse
from collections import Counter, defaultdict
from fractions import Fraction
import gzip
import hashlib
import json
import math
from pathlib import Path
import random
import re
import statistics
import sys
import time

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT))
from reproduction.clean_ranking_v1.correctness import response_values
from reproduction.round08.data import verify_source
HERE=Path(__file__).resolve().parent
F=HERE.parent
SEED=20261108093
ARMS=('C','H','L','E','E_archive','N32')
CONTRASTS={'C-H':('C','H'),'C-L':('C','L'),'H-L':('H','L'),'C-E':('C','E'),
           'L-E':('L','E'),'H-N32':('H','N32'),'L-N32':('L','N32'),
           'E-N32':('E','N32'),'C-N32':('C','N32'),'C-E_archive':('C','E_archive')}


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def objsha(v):return hashlib.sha256(json.dumps(v,sort_keys=True,separators=(',',':')).encode()).hexdigest()
def dump(p,v):p.write_text(json.dumps(v,indent=2,sort_keys=True,allow_nan=False)+'\n')
def read(p):return json.loads(p.read_text())
def gzread(p):return [json.loads(x) for x in gzip.decompress(p.read_bytes()).decode().splitlines()]
def percentile(v,q):
    v=sorted(v);k=(len(v)-1)*q;i=int(k);j=min(i+1,len(v)-1)
    return v[i]*(j-k)+v[j]*(k-i) if i!=j else v[i]


def legal_index(v):return type(v) is int and v in (0,1)
def legal_conf(v):return type(v) in (float,int) and math.isfinite(v) and 0<=v<=1

def explicit_json(text):
    """Last index-bearing flat JSON; partial retained reasoning is labelled apart."""
    if not isinstance(text,str):return None
    found=[]
    for s in re.findall(r'\{[^{}]{0,2000}\}',text):
        try:
            x=json.loads(s)
        except (ValueError,TypeError):continue
        if isinstance(x,dict) and ('predicted_best_index' in x or 'best_index' in x):found.append(x)
    return found[-1] if found else None


def fallback_flags(*objects):
    result=[]
    for level,obj in enumerate(objects):
        if not isinstance(obj,dict):continue
        for k,v in obj.items():
            if ('error' in k.lower() and v not in (None,False,'',[],{})) or ('fallback' in k.lower() and bool(v)):
                result.append(f'{level}:{k}')
    return result


def source_meta(pred,backup,bank_item,path,rowindex,recovered=False):
    pred=pred if isinstance(pred,dict) else {}
    i,c=response_values(bank_item)
    pi=pred.get('best_index');pc=pred.get('confidence')
    flags=fallback_flags(pred, backup.get('parsed') if backup else None)
    archive_explicit=legal_index(pi) and legal_conf(pc) and not flags
    rawtext=None
    if backup:
        rawtext=backup.get('raw_response')
        if not isinstance(rawtext,str):
            texts=backup.get('raw_responses')
            if isinstance(texts,list) and texts and isinstance(texts[-1],str):rawtext=texts[-1]
    rawjson=explicit_json(rawtext)
    reasoningjson=explicit_json(pred.get('reasoning'))
    candidate=rawjson if isinstance(rawtext,str) else reasoningjson
    def match(obj):
        if obj is None:return False
        ix=obj.get('predicted_best_index',obj.get('best_index'))
        cf=obj.get('confidence')
        return legal_index(ix) and legal_conf(cf) and ix==i and abs(cf-c)<1e-12
    raw_ok=match(rawjson)
    reasoning_ok=match(reasoningjson)
    # Existing raw text takes precedence: partial reasoning cannot override it.
    proven=(raw_ok if isinstance(rawtext,str) else reasoning_ok) and not flags
    ev='full_raw_json_match' if raw_ok else 'full_raw_available_without_matching_explicit_json' if isinstance(rawtext,str) else 'retained_reasoning_explicit_json_match' if reasoning_ok else 'archive_prediction_only'
    return {'source_file':path,'source_row':rowindex,'recovered_failure':recovered,
            'prediction_index_present':'best_index' in pred,'prediction_index_type':type(pi).__name__,
            'prediction_confidence_present':'confidence' in pred,'prediction_confidence_type':type(pc).__name__,
            'prediction_confidence_value':pc,'prediction_index_value':pi,
            'index_legal_explicit':legal_index(pi),'confidence_legal_explicit':legal_conf(pc),
            'archive_explicit_eligible':archive_explicit,'raw_explicit_eligible':proven,
            'source_evidence_level':ev,'has_full_raw_text':isinstance(rawtext,str),
            'has_retained_reasoning':isinstance(pred.get('reasoning'),str),
            'raw_last_json_present':rawjson is not None,'reasoning_last_json_present':reasoningjson is not None,
            'recorded_error_fallback_flags':flags,
            'raw_last_json_index':None if rawjson is None else rawjson.get('predicted_best_index',rawjson.get('best_index')),
            'raw_last_json_confidence':None if rawjson is None else rawjson.get('confidence'),
            'raw_vs_archive_mismatch':rawjson is not None and not raw_ok,
            'reasoning_vs_archive_mismatch':reasoningjson is not None and not reasoning_ok}


def top(ids,edges):
    d=dict.fromkeys(ids,0);w=dict.fromkeys(ids,0)
    for a,b,c in edges:
        if c is not None:d[a]+=1;d[b]+=1;w[c]+=1
    keys={i:(Fraction(w[i],d[i]) if d[i] else Fraction(1,2),d[i]) for i in ids}
    best=max(keys.values())
    return [i for i in ids if keys[i]==best]


def score(ids,chosen,utility):
    mx=max(utility[i] for i in ids);mn=min(utility[i] for i in ids)
    regret=sum((mx-utility[i])/(mx-mn) if mx!=mn else 0 for i in chosen)/len(chosen)
    hit=sum(utility[i]==mx for i in chosen)/len(chosen)
    alt=(mx-statistics.fmean(utility[i] for i in chosen))/(mx-mn) if mx!=mn else 0
    assert abs(regret-alt)<1e-10
    return {'regret':regret,'best_hit':hit}


def infer(v):
    rng=random.Random(SEED)
    samples=[sum(rng.choices(v,k=len(v)))/len(v) for _ in range(10000)]
    loo=[(sum(v)-x)/(len(v)-1) for x in v]
    return {'gain':statistics.fmean(v),'ci95':[percentile(samples,.025),percentile(samples,.975)],
            'tasks_positive':sum(x>1e-12 for x in v),'tasks_zero':sum(abs(x)<=1e-12 for x in v),'tasks_negative':sum(x < -1e-12 for x in v),
            'leave_one_task_out':dict(zip(TASKS,loo)),'leave_one_min':min(loo),'leave_one_max':max(loo)}


def main():
    global TASKS
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--output',type=Path,required=True);args=ap.parse_args()
    out=args.output.resolve();assert not out.exists();out.mkdir(parents=True)
    start=time.monotonic()
    for name in ('protocol.json','schema_supplement.json'):(out/name).write_bytes((HERE/name).read_bytes())
    (out/'audit.snapshot.py').write_bytes(Path(__file__).read_bytes())
    assert sha(HERE/'protocol.json')=='a917d39958175ae06ae55b1719ca9d71209f8658eeb22db7fa383140950d9d6a'
    bm=read(F/'banks/manifest.json');source_root=Path(bm['source_root'])
    source_manifest=read(ROOT/'experiments/clean-ranking-v1/prepared/source_manifest.json')['sha256']
    jobs=[json.loads(x) for x in (ROOT/'experiments/clean-ranking-v1/prepared/jobs.jsonl').read_text().splitlines()]
    byjob={j['job_id']:j for j in jobs};TASKS=sorted({j['task'] for j in jobs})
    paths=read(ROOT/'experiments/clean-ranking-v1/prepared/code_files.json')
    name_to_id={t:{Path(p).name:cid for cid,p in files.items()} for t,files in paths.items()}
    suffix_to_id={t:{Path(p).name[-7:]:cid for cid,p in files.items()} for t,files in paths.items()}
    assert all(len(suffix_to_id[t])==len(paths[t]) for t in TASKS)
    banks={'DS':read(ROOT/'experiments/clean-ranking-v1/prepared/feedback.json')}
    used={}
    for b,meta in bm['banks'].items():
        p=ROOT/meta['path'];assert sha(p)==meta['sha256'];used[str(p)]=sha(p)
        banks[b]=json.loads(gzip.decompress(p.read_bytes()))
    # Source join reads paths and prediction/response fields, never correctness or scores.
    recovery_entries=read(ROOT/'experiments/round-08/recovery_sources.json')['files']
    backups={}
    for e in recovery_entries:
        p=source_root/e['target'];h=verify_source(e,p);assert h==e['sha256'];used[str(p)]=h
        raw=read(p)[e['task']][f"groups_{e['task']}_n2.json"]
        table={}
        for row in raw:
            ids=[suffix_to_id[e['task']].get(Path(x).name[-7:]) for x in row['paths']]
            if None not in ids:table['|'.join(sorted(ids))]=row
        backups[(e['feedback_run'],e['task'])]=table
    recovered=read(ROOT/'experiments/round-08/recovered_feedback.json')['records']
    source_entries={('DS',t):(ROOT/'data/author_reference'/f'{t}.json') for t in TASKS}
    e_by={}
    for e in read(ROOT/'experiments/round-08/data_manifest.json')['files']:
        source_entries[(e['feedback_run'],e['task'])]=source_root/e['target'];e_by[(e['feedback_run'],e['task'])]=e
    metadata={};source_counts={};source_rows=[]
    for b,bank in banks.items():
        counts=Counter()
        metadata[b]={}
        for t in TASKS:
            p=source_entries[(b,t)];h=sha(p);used[str(p)]=h
            if b=='DS':assert h==source_manifest[str(p.relative_to(ROOT))]
            else:assert h==verify_source(e_by[(b,t)],p)
            raw=read(p)['results'];table={}
            for rownum,row in enumerate(raw):
                ids=[suffix_to_id[t].get(Path(s['path']).name[-7:]) for s in row.get('solutions',[])]
                if len(ids)!=2 or None in ids:continue
                pair='|'.join(sorted(ids))
                if pair not in bank[t]:continue
                assert pair not in table
                item=bank[t][pair];assert ids==item['order']
                pred=row.get('prediction');pred=pred if isinstance(pred,dict) else {}
                assert item['predicted_best_index']==pred.get('best_index') and item['confidence']==pred.get('confidence',.5)
                table[pair]=source_meta(pred,backups.get((b,t),{}).get(pair),item,str(p),rownum)
            for rec in recovered:
                if rec['feedback_run']!=b or rec['task']!=t:continue
                ids=[suffix_to_id[t].get(Path(s).name[-7:]) for s in rec['paths_order']]
                if None in ids:continue
                pair='|'.join(sorted(ids))
                if pair not in bank[t]:continue
                assert pair not in table and bank[t][pair]['predicted_best_index'] is None
                table[pair]=source_meta({},backups.get((b,t),{}).get(pair),bank[t][pair],str(p),None,True)
            assert set(table)==set(bank[t]),(b,t,len(table),len(bank[t]))
            metadata[b][t]=table
            for pair,m in table.items():
                idx,conf=response_values(bank[t][pair]);band='high' if idx is not None and conf>=.7 else 'low_added' if idx is not None and conf>=.5 else 'abstained'
                counts[f'{band}:pairs']+=1
                for key in ('archive_explicit_eligible','raw_explicit_eligible','has_full_raw_text','has_retained_reasoning','prediction_confidence_present','confidence_legal_explicit','raw_vs_archive_mismatch','reasoning_vs_archive_mismatch'):
                    counts[f'{band}:{key}']+=bool(m[key])
                counts[f"{band}:evidence:{m['source_evidence_level']}"]+=1
                counts[f'{band}:recorded_error_fallback']+=bool(m['recorded_error_fallback_flags'])
                source_rows.append(dict(bank=b,task=t,pair=pair,parsed_index=idx,parsed_confidence=conf,band=band,**m))
        source_counts[b]=dict(counts)
    src=out/'source_audit.sealed.jsonl.gz';src.write_bytes(gzip.compress(''.join(json.dumps(r,sort_keys=True)+'\n' for r in source_rows).encode(),mtime=0))
    dump(out/'source_counts.json',source_counts)
    print('Source audit sealed',len(source_rows),flush=True)
    c0path=F/'c0-final-selection/run-001/decisions.sealed.jsonl.gz'
    c0seal=read(F/'c0-final-selection/run-001/selection_seal.json')
    assert sha(c0path)==c0seal['decisions_sha256']
    rows=gzread(c0path);assert len(rows)==3400
    sealed=[];trace_counts=defaultdict(Counter);checks=Counter()
    for row in rows:
        assert time.monotonic()-start<600
        b,t,jid=row['bank'],row['task'],row['job_id'];job=byjob[jid];ids=job['ids']
        trace=row['trace'];assert len(trace)==row['stats']['unique_feedback_reads']
        assert len({tuple(sorted((e['a'],e['b']))) for e in trace})==len(trace)
        edges={a:[] for a in ('H','L','E','E_archive')};negative=[[] for _ in range(32)];added=[]
        for event in trace:
            a,c=event['a'],event['b'];pair='|'.join(sorted((a,c)));item=banks[b][t][pair];idx,conf=response_values(item);m=metadata[b][t][pair]
            high=item['order'][idx] if idx is not None and conf>=.7 else None
            low=item['order'][idx] if idx is not None and .5<=conf<.7 else None
            assert event['winner']==high
            win=high if high is not None else low
            edges['H'].append((a,c,high));edges['L'].append((a,c,win))
            edges['E'].append((a,c,high if high is not None else low if m['raw_explicit_eligible'] else None))
            edges['E_archive'].append((a,c,high if high is not None else low if m['archive_explicit_eligible'] else None))
            if low is not None:
                added.append({'a':a,'b':c,'winner':low,'confidence':conf,'source_evidence_level':m['source_evidence_level'],
                              'raw_explicit_eligible':m['raw_explicit_eligible'],'archive_explicit_eligible':m['archive_explicit_eligible']})
                trace_counts[b]['low_added_edge_episodes']+=1
                trace_counts[b]['low_added_explicit_raw']+=m['raw_explicit_eligible']
                trace_counts[b]['low_added_explicit_archive']+=m['archive_explicit_eligible']
                trace_counts[b][f"low_added_evidence:{m['source_evidence_level']}"]+=1
                trace_counts[b]['low_missing_confidence']+=not m['prediction_confidence_present']
                trace_counts[b]['low_recorded_error_fallback']+=bool(m['recorded_error_fallback_flags'])
            for r in range(32):
                nw=high
                if low is not None:
                    pairids=sorted((a,c));seed=int.from_bytes(hashlib.sha256(json.dumps(['direction-audit-v1',r,jid,*pairids],separators=(',',':')).encode()).digest()[:8],'big')
                    nw=pairids[random.Random(seed).randrange(2)]
                negative[r].append((a,c,nw))
        selected={'C':row['selected']['C'],**{a:top(ids,e) for a,e in edges.items()}}
        assert selected['H']==row['selected']['H'] and selected['L']==row['selected']['L']
        assert edges['L']==[tuple(x) for x in row['low_evidence']]
        ns=[top(ids,e) for e in negative]
        sealed.append({'bank':b,'task':t,'job_id':jid,'n':len(ids),'C0_tied':row['C0_tied'],
                       'selected':selected,'negative_selections':ns,'added_low_edges':added,'unique_reads':len(trace),
                       'H_valid':sum(w is not None for a,c,w in edges['H']),
                       'L_valid':sum(w is not None for a,c,w in edges['L']),
                       'E_valid':sum(w is not None for a,c,w in edges['E']),
                       'E_archive_valid':sum(w is not None for a,c,w in edges['E_archive'])})
        checks['C0_rows_verified']+=1;checks['H_L_sealed_matches']+=1;checks['unique_same_schedule_and_cost']+=1
    dest=out/'decisions.sealed.jsonl.gz';dest.write_bytes(gzip.compress(''.join(json.dumps(r,sort_keys=True)+'\n' for r in sealed).encode(),mtime=0))
    dump(out/'selection_seal.json',{'sha256':sha(dest),'source_audit_sha256':sha(src),'labels_loaded':False,
         'jobs':3400,'banks':4,'N_replicates':32,'protocol_sha256':sha(HERE/'protocol.json'),'supplement_sha256':sha(HERE/'schema_supplement.json'),
         'script_sha256':sha(Path(__file__)),'original_C0_selection_seal_sha256':sha(F/'c0-final-selection/run-001/selection_seal.json'),
         'original_C0_sealed_decisions_sha256':sha(c0path),'checks':dict(checks)})
    dump(out/'source_trace_counts.json',{b:dict(x) for b,x in trace_counts.items()})
    print('All audit selections sealed before scoring',sha(dest),flush=True)
    # First utility-label access. Source files above were restricted to identity/prediction/response fields.
    labels=read(ROOT/'experiments/clean-ranking-v1/prepared/evaluation_labels.json')
    grouped=defaultdict(list);repgroup=defaultdict(list);episode=[];accuracy=defaultdict(Counter);subgroup=defaultdict(list)
    for row in sealed:
        b,t,jid=row['bank'],row['task'],row['job_id'];ids=byjob[jid]['ids'];u=labels[t]
        scored={a:score(ids,s,u) for a,s in row['selected'].items()}
        nn=[score(ids,s,u) for s in row['negative_selections']]
        scored['N32']={k:statistics.fmean(x[k] for x in nn) for k in ('regret','best_hit')}
        for a,m in scored.items():grouped[(b,t,a)].append(m)
        for i,m in enumerate(nn):repgroup[(b,t,i)].append(m)
        for e in row['added_low_edges']:
            if u[e['a']]==u[e['b']]:accuracy[(b,t)]['ties']+=1
            else:
                accuracy[(b,t)]['strict_total']+=1
                accuracy[(b,t)]['strict_correct']+=u[e['winner']]==max(u[e['a']],u[e['b']])
                if e['raw_explicit_eligible']:
                    accuracy[(b,t)]['explicit_strict_total']+=1
                    accuracy[(b,t)]['explicit_strict_correct']+=u[e['winner']]==max(u[e['a']],u[e['b']])
        for g in ('n=10' if row['n']==10 else 'n<10','C_tied' if row['C0_tied'] else 'C_singleton'):
            subgroup[(b,g,t)].append(scored)
        episode.append({**{k:row[k] for k in ('bank','task','job_id','n','C0_tied','unique_reads','H_valid','L_valid','E_valid','E_archive_valid')},
                        'scores':scored,'negative_rep_scores':nn})
    (out/'per_episode.jsonl').write_text(''.join(json.dumps(x,sort_keys=True)+'\n' for x in episode))
    per_task={b:{t:{a:{k:statistics.fmean(r[k] for r in grouped[(b,t,a)]) for k in ('regret','best_hit')} for a in ARMS} for t in TASKS} for b in banks}
    reps={b:{t:{i:{k:statistics.fmean(r[k] for r in repgroup[(b,t,i)]) for k in ('regret','best_hit')} for i in range(32)} for t in TASKS} for b in banks}
    gpt=[b for b in banks if b!='DS'];pool='GPT_task_first_pooled'
    per_task[pool]={t:{a:{k:statistics.fmean(per_task[b][t][a][k] for b in gpt) for k in ('regret','best_hit')} for a in ARMS} for t in TASKS}
    reps[pool]={t:{i:{k:statistics.fmean(reps[b][t][i][k] for b in gpt) for k in ('regret','best_hit')} for i in range(32)} for t in TASKS}
    dump(out/'per_task.json',per_task)
    results={}
    for b,data in per_task.items():
        macro={a:{k:statistics.fmean(data[t][a][k] for t in TASKS) for k in ('regret','best_hit')} for a in ARMS}
        contrast={}
        for name,(a,c) in CONTRASTS.items():
            contrast[name]={k:infer([(data[t][a][k]-data[t][c][k])*(1 if k=='regret' else -1) for t in TASKS]) for k in ('regret','best_hit')}
        replicate=[]
        for i in range(32):
            rr={k:statistics.fmean(reps[b][t][i][k] for t in TASKS) for k in ('regret','best_hit')}
            replicate.append({'replicate':i,**rr,'C_minus_N_regret':macro['C']['regret']-rr['regret'],'H_minus_N_regret':macro['H']['regret']-rr['regret'],'L_minus_N_regret':macro['L']['regret']-rr['regret']})
        repl_summary={k:{'mean':statistics.fmean(r[k] for r in replicate),'min':min(r[k] for r in replicate),'max':max(r[k] for r in replicate),
                          'sd':statistics.stdev(r[k] for r in replicate),'q025':percentile([r[k] for r in replicate],.025),'q975':percentile([r[k] for r in replicate],.975)} for k in ('C_minus_N_regret','H_minus_N_regret','L_minus_N_regret')}
        results[b]={'macro':macro,'contrasts':contrast,'negative_replicates':replicate,'negative_replicate_sensitivity':repl_summary}
    # Independently check the previously sealed C/H/L source aggregation only after own scoring.
    prior=read(F/'c0-final-selection/run-001/per_task.json')
    for b in banks:
        for t in TASKS:
            for a in ('C','H','L'):
                for k in ('regret','best_hit'):assert abs(prior[b][t][a][k]-per_task[b][t][a][k])<1e-12
    checks['independent_C_H_L_task_metric_matches']=4*26*3*2
    accuracy_summary={}
    for b in banks:
        totals=Counter()
        for t in TASKS:totals.update(accuracy[(b,t)])
        vals=[accuracy[(b,t)]['strict_correct']/accuracy[(b,t)]['strict_total'] for t in TASKS if accuracy[(b,t)]['strict_total']]
        accuracy_summary[b]={'counts':dict(totals),'micro_strict_accuracy':totals['strict_correct']/totals['strict_total'] if totals['strict_total'] else None,
                             'task_macro_strict_accuracy_nonempty_tasks':statistics.fmean(vals),'nonempty_tasks':len(vals)}
    groups={}
    for b in banks:
        groups[b]={}
        for g in ('n=10','n<10','C_tied','C_singleton'):
            taskdata={t:subgroup[(b,g,t)] for t in TASKS if subgroup[(b,g,t)]}
            groups[b][g]={'episodes':sum(map(len,taskdata.values())),'tasks':len(taskdata)}
            for cname in ('C-L','H-L','L-N32','C-E'):
                a,c=CONTRASTS[cname]
                vv={t:statistics.fmean(r[a]['regret']-r[c]['regret'] for r in rr) for t,rr in taskdata.items()}
                groups[b][g][cname]={'conditional_task_macro_gain':statistics.fmean(vv.values()),
                    'full_task_macro_contribution':sum(sum(r[a]['regret']-r[c]['regret'] for r in rr)/len(grouped[(b,t,'C')])/26 for t,rr in taskdata.items())}
    dump(out/'source_accuracy.json',accuracy_summary);dump(out/'subgroups.json',groups)
    dump(out/'summary.json',results)
    dump(out/'verification.json',dict(checks=dict(checks),selection_first=True,source_rows=len(source_rows),decision_rows=len(sealed),
        new_model_calls=0,new_training_runs=0,new_gpu_rentals=0,elapsed_seconds=time.monotonic()-start,
        scope='Explanatory retrospective development audit; additional arms never promoted',same_schedule='each bank own actual C0 trace, all arms fixed within bank'))
    for p in (HERE/'protocol.json',HERE/'schema_supplement.json',Path(__file__),c0path,F/'c0-final-selection/run-001/selection_seal.json',ROOT/'experiments/clean-ranking-v1/prepared/evaluation_labels.json'):
        used[str(p)]=sha(p)
    dump(out/'input_sha256.json',used)
    dump(out/'output_sha256.json',{p.name:sha(p) for p in out.iterdir() if p.is_file() and p.name!='output_sha256.json'})
    print(json.dumps({b:{'macro':r['macro'],'C-L':r['contrasts']['C-L']['regret'],'L-N32':r['contrasts']['L-N32']['regret']} for b,r in results.items()},indent=2))

if __name__=='__main__':main()
