import gzip,json,hashlib,random,re,time,collections,statistics,sys
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[2]; OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT))
from reproduction.clean_ranking_v1.correctness import response_values
start=time.monotonic(); cpu=time.process_time()
def read(p):return json.loads(Path(p).read_bytes())
def dump(p,x):Path(p).write_text(json.dumps(x,sort_keys=True,indent=2,allow_nan=False)+'\n')
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def rows(p):return [json.loads(x) for x in gzip.open(p,'rt')]
def gzwrite(p,data):
 with gzip.GzipFile(filename=str(p),mode='wb',mtime=0) as f:
  for x in data:f.write((json.dumps(x,sort_keys=True)+'\n').encode())
def strict(x):return type(x)is int and x in (0,1)
def extract(s):
 found=[]
 if isinstance(s,str):
  for x in re.findall(r'\{[^{}]{0,2000}\}',s):
   try:z=json.loads(x)
   except (ValueError,TypeError):continue
   if isinstance(z,dict) and ('predicted_best_index'in z or 'best_index'in z):found.append(z)
 return found[-1] if found else None
P=ROOT/'experiments/clean-ranking-v1/prepared'; F=ROOT/'experiments/selection-frontier-02'
auditpath=F/'direction-audit/run-003/source_audit.sealed.jsonl.gz'
decpath=ROOT/'experiments/trajectory-weighted-judge-v1/evaluation/run_1/decisions.sealed.jsonl.gz'
refpath=F/'c0-final-selection/run-002/decisions.sealed.jsonl.gz'
jobs={x['job_id']:x for x in map(json.loads,(P/'jobs.jsonl').read_text().splitlines())}
paths=read(P/'code_files.json'); suffix={t:{Path(p).name[-7:]:cid for cid,p in d.items()} for t,d in paths.items()}
manifest=read(F/'banks/manifest.json'); banks={'DS':read(P/'feedback.json')}
for b,v in manifest['banks'].items():
 assert sha(ROOT/v['path'])==v['sha256'];banks[b]=json.loads(gzip.decompress((ROOT/v['path']).read_bytes()))
audit=rows(auditpath); meta={}; sources={}; flags=[]
source_hashes=read(F/'direction-audit/run-003/input_sha256.json')
# Frozen source audit output contains the original input hashes under its seal/manifest.
for a in audit:
 key=(a['bank'],a['task'],a['pair']);p=a['source_file']
 if p not in sources:
  assert sha(p)==source_hashes[p]
  sources[p]=read(p)['results']
 item=banks[a['bank']][a['task']][a['pair']];ix,conf=response_values(item)
 if a['source_row'] is None:
  obj=None;assert not a['has_retained_reasoning']
 else:
  src=sources[p][a['source_row']];ids=[suffix[a['task']][Path(s['path']).name[-7:]] for s in src['solutions']]
  assert ids==item['order'] and '|'.join(sorted(ids))==a['pair']
  pred=src.get('prediction') or {};assert pred.get('best_index')==a['prediction_index_value']
  assert pred.get('confidence')==a['prediction_confidence_value']
  obj=extract(pred.get('reasoning'))
  assert isinstance(pred.get('reasoning'),str)==a['has_retained_reasoning']
 assert (obj is not None)==a['reasoning_last_json_present']
 ri=None if obj is None else obj.get('predicted_best_index',obj.get('best_index'))
 usable=a['has_retained_reasoning'] and strict(ri) and strict(ix)
 flag=bool(usable and ri!=ix)
 if obj is not None:
  cf=obj.get('confidence');cfok=type(cf)in(int,float) and 0<=cf<=1
  oldok=strict(ri) and cfok and ri==ix and abs(cf-conf)<1e-12
  assert (not oldok)==a['reasoning_vs_archive_mismatch']
 r={'bank':a['bank'],'task':a['task'],'pair':a['pair'],'usable_explicit_direction':bool(usable),'direction_mismatch':flag,'reasoning_last_json_index':ri,'parsed_index':ix,'source_file':p,'source_row':a['source_row']}
 meta[key]=r;flags.append(r)
del sources
gzwrite(OUT/'flags.sealed.jsonl.gz',flags)
reference={(x['bank'],x['job_id']):x for x in rows(refpath)}
controls=[x for x in rows(decpath) if x['arm']=='C0'];assert len(controls)==3400
selected=[];unique={};counts=collections.defaultdict(collections.Counter)
def choose(base,edges,flagpos):
 if len(base)<2 or not flagpos:return base
 penalty=dict.fromkeys(base,0);touch=False
 for i in flagpos:
  e=edges[i];w=e['winner'];l=e['b'] if w==e['a'] else e['a']
  if w in penalty:penalty[w]+=1;touch=True
  if l in penalty:penalty[l]-=1;touch=True
 if not touch:return base
 m=min(penalty.values());return [x for x in base if penalty[x]==m]
for x in controls:
 b,t,j=x['bank'],x['task'],x['job_id'];base=x['selected'];old=reference[(b,j)]
 assert base==old['selected']['C'] and x['trace']==old['trace']
 assert set(base)<=set(jobs[j]['ids']);accepted=[];seen=set()
 for e in x['trace']:
  pair='|'.join(sorted((e['a'],e['b'])));assert pair not in seen;seen.add(pair)
  it=banks[b][t][pair];ix,cf=response_values(it)
  winner=it['order'][ix] if ix is not None and cf>=.7 else None
  assert (e['winner'],e['confidence'],e['source_group_index'])==(winner,cf,it['source_group_index'])
  if winner is not None:accepted.append(e);unique[(b,t,pair)]=e
 pos=[i for i,e in enumerate(accepted) if meta[(b,t,'|'.join(sorted((e['a'],e['b']))))]['direction_mismatch']]
 text=choose(base,accepted,pos);shams=[]
 for k in range(32):
  seed=int(hashlib.sha256(f'rationale-tiebreak-v1:{b}:{j}:{k}'.encode()).hexdigest(),16)
  shuffled=random.Random(seed).sample(range(len(accepted)),len(pos));shams.append(choose(base,accepted,shuffled))
 counts[b]['episodes']+=1;counts[b]['tied_episodes']+=len(base)>1;counts[b]['changed_episodes']+=text!=base
 counts[b]['episodes_with_accepted_flag']+=bool(pos)
 selected.append({'bank':b,'task':t,'job_id':j,'C0':base,'text':text,'sham':shams})
for (b,t,p),e in unique.items():
 counts[b]['unique_accepted_pairs']+=1
 counts[b]['unique_accepted_with_usable_explicit_direction']+=meta[(b,t,p)]['usable_explicit_direction']
 counts[b]['unique_accepted_with_direction_mismatch']+=meta[(b,t,p)]['direction_mismatch']
gzwrite(OUT/'selections.sealed.jsonl.gz',selected)
inputfiles=[auditpath,decpath,refpath,P/'jobs.jsonl',P/'feedback.json',P/'code_files.json',OUT/'protocol.json']
# Input audit verifies all source hashes in its own immutable source-manifest artifact below.
inputhash={str(p):sha(p) for p in inputfiles};sourcehash={p:sha(p) for p in set(a['source_file'] for a in audit)}
dump(OUT/'selection_seal.json',{'labels_opened':False,'inputs':inputhash,'source_sha256':sourcehash,'flags_sha256':sha(OUT/'flags.sealed.jsonl.gz'),'selections_sha256':sha(OUT/'selections.sealed.jsonl.gz'),'controls_exact':3400,'trace_source_order_and_gate_verified':True,'source_rows_verified':len(audit),'audit_missing_reasoning_index_rows':sum('reasoning_last_json_index'not in a for a in audit)})
# Gold is opened only after all selected sets and extracted metadata are sealed.
labels=read(P/'evaluation_labels.json');tasks=sorted(labels)
def score(job,sel):
 u=labels[job['task']];v=[u[i] for i in job['ids']];hi,lo=max(v),min(v)
 return [(hi-statistics.fmean(u[i] for i in sel))/(hi-lo) if hi>lo else 0.,sum(u[i]==hi for i in sel)/len(sel)]
data=collections.defaultdict(list);per=[]
for x in selected:
 j=jobs[x['job_id']];base=score(j,x['C0']);text=score(j,x['text']);sham=[score(j,s) for s in x['sham']]
 data[(x['bank'],x['task'])].append(np.array([base,text,*sham]));per.append(dict(bank=x['bank'],task=x['task'],job_id=x['job_id'],C0=base,text=text,sham=sham))
gzwrite(OUT/'scores.jsonl.gz',per)
means={b:np.stack([np.mean(data[(b,t)],axis=0) for t in tasks]) for b in banks}
means['GPT_task_first_pooled']=np.mean([v for b,v in means.items() if b!='DS'],axis=0)
rng=np.random.default_rng(812808);idx=rng.integers(0,26,(10000,26));summary={};pt=[]
def contrast(v):
 avg=float(v.mean());boot=v[idx].mean(axis=1);leave=(v.sum()-v)/25
 return {'mean':avg,'ci95':np.quantile(boot,[.025,.975]).tolist(),'leave_one_task_out_range':[float(leave.min()),float(leave.max())],'all_leave_one_task_out_positive':bool(np.all(leave>0))}
for b,v in means.items():
 report={'C0':v[:,0,:].mean(axis=0).tolist(),'text':v[:,1,:].mean(axis=0).tolist(),'sham_mean':v[:,2:,:].mean(axis=(0,1)).tolist()}
 report['regret_gain_C0_minus_text']=contrast(v[:,0,0]-v[:,1,0]);report['regret_gain_sham_minus_text']=contrast(v[:,2:,0].mean(axis=1)-v[:,1,0]);report['hit_gain_text_minus_C0']=contrast(v[:,1,1]-v[:,0,1]);report['hit_gain_text_minus_sham']=contrast(v[:,1,1]-v[:,2:,1].mean(axis=1))
 report['sham_replicate_regret_gains_C0_minus_sham']=(v[:,0,0].mean()-v[:,2:,0].mean(axis=0)).tolist();summary[b]=report
 for i,t in enumerate(tasks):pt.append({'bank':b,'task':t,'C0':v[i,0,:].tolist(),'text':v[i,1,:].tolist(),'sham':v[i,2:,:].mean(axis=0).tolist()})
def stable(b):
 s=summary[b];return all(s[k]['ci95'][0]>0 and s[k]['all_leave_one_task_out_positive'] for k in ['regret_gain_C0_minus_text','regret_gain_sham_minus_text'])
gate=summary['DS']['regret_gain_C0_minus_text']['mean']>=.01 and summary['GPT_task_first_pooled']['regret_gain_C0_minus_text']['mean']>0 and stable('DS') and stable('GPT_task_first_pooled')
diag=collections.defaultdict(collections.Counter)
for (b,t,p),e in unique.items():
 m=meta[(b,t,p)];a,c=p.split('|');u=labels[t]
 if not m['usable_explicit_direction'] or u[a]==u[c]:continue
 status='mismatch' if m['direction_mismatch'] else 'match';cf=e['confidence'];band='[0.7,0.8)' if cf<.8 else '[0.8,0.9)' if cf<.9 else '[0.9,1]'
 correct=u[e['winner']]==max(u[a],u[c])
 for gran,key in [('bank',b),('task',b+'|'+t),('confidence',b+'|'+band)]:
  d=diag[(gran,key,status)];d['n']+=1;d['correct']+=correct
diagnostics=[dict(granularity=g,group=k,direction=s,**v,accuracy=v['correct']/v['n']) for (g,k,s),v in sorted(diag.items())]
dump(OUT/'diagnostics.json',{'interpretation':'Raw conditioning on unique accepted strict pairs with explicit retained reasoning JSON. Intermediate JSON may flag correctly parsed outcomes; mismatch is not truth. Bank/task/confidence strata are descriptive.','rows':diagnostics})
dump(OUT/'per_task.json',pt)
result={'experiment':'rationale-tiebreak-v1','metric_vector':['normalized_regret','uniform_tie_best_hit'],'tasks':26,'episodes':3400,'exposure':dict(counts),'metrics':summary,'gate_passed':bool(gate),'decision':'retain C0; close this exact retained-reasoning direction mismatch tie-break signal' if not gate else 'gate passed on development data; independent confirmation required','source_disclosure':'All audit rows lacked extracted reasoning index; recovered from frozen raw prediction.reasoning using same last-flat-JSON extractor and verified every candidate order, parsed prediction and audit presence/mixed mismatch. Reasoning may contain intermediate JSON; flags carry uncertainty.','cost':{'new_model_calls':0,'training_runs':0,'gpu_hours':0,'paid_cost_usd':0,'wall_seconds':time.monotonic()-start,'cpu_seconds':time.process_time()-cpu},'selection_seal_sha256':sha(OUT/'selection_seal.json'),'labels_sha256':sha(P/'evaluation_labels.json')}
dump(OUT/'summary.json',result)
print(json.dumps({'gate':gate,'exposure':dict(counts),'DS':summary['DS'],'GPT':summary['GPT_task_first_pooled'],'cost':result['cost']},indent=2))
