"""Read-only ForeAgent audit: execute pinned methods with controlled responses; inspect saved artifacts.
No model API, candidate execution, SSH, package installation, or baseline writes.
Usage: python diagnostics.py ROOT OUTPUT.json
"""
import ast, collections, csv, gzip, hashlib, json, logging, math, re, shutil, statistics, subprocess, sys, tempfile, types
from pathlib import Path
from unittest.mock import patch
ROOT=Path(sys.argv[1]).resolve(); OUT=Path(sys.argv[2]).resolve()
PH=ROOT/'phase1-reproduction'; AUTH=PH/'code/author'
sys.dont_write_bytecode=True
# Import exact source without importing the agent/API dependency stack.
source=AUTH/'mle-bench/agents/aide/aide/world_model.py'
tree=ast.parse(source.read_text());tree.body=[x for x in tree.body if not(isinstance(x,ast.ImportFrom) and x.level)]
wm=types.ModuleType('_audit_pinned_world');sys.modules[wm.__name__]=wm
wm.__dict__.update(Node=types.SimpleNamespace,query=lambda **kw:(_ for _ in ()).throw(AssertionError('live backend disabled')))
exec(compile(tree,str(source),'exec'),wm.__dict__);wm.logger.setLevel(logging.CRITICAL)
result={'audit':'foreagent-review-20261108-v1','root':str(ROOT),'new_model_calls':0,'candidate_training_runs':0,'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest()}
a,b=[types.SimpleNamespace(id=k,code='code-'+k) for k in ('A','B')]
with patch.object(wm.WorldModel,'_comparison_cache',{}),patch.object(wm,'query',return_value='{"predicted_best_index":0,"confidence":0.9}') as q:
 w=wm.WorldModel('task','report',config=wm.WorldModelConfig(confidence_threshold=.7))
 ab=w.predict_pairwise(a,b);ba=w.predict_pairwise(b,a)
 result['cache_reversal']={'first_winner':(a,b)[ab.winner_idx].id,'reversed_winner':(b,a)[ba.winner_idx].id,'backend_calls':q.call_count}
 assert result['cache_reversal']=={'first_winner':'A','reversed_winner':'B','backend_calls':1}
with patch.object(wm.WorldModel,'_comparison_cache',{}),patch.object(wm,'query',return_value='{"predicted_best_index":0,"confidence":0.65}') as q:
 w1=wm.WorldModel('task1','report1',config=wm.WorldModelConfig(confidence_threshold=.6));w2=wm.WorldModel('task2','report2',config=wm.WorldModelConfig(confidence_threshold=.7))
 w1.predict_pairwise(a,b);r=w2.predict_pairwise(a,b)
 result['cross_context_cache']={'second_valid':r.is_valid,'second_confidence':r.confidence,'second_threshold':.7,'backend_calls':q.call_count};assert r.is_valid and q.call_count==1
with patch.object(wm.WorldModel,'_comparison_cache',{}),patch.object(wm,'query',return_value='{"predicted_best_index":0,"confidence":0.6}') as q:
 w=wm.WorldModel('task','report',config=wm.WorldModelConfig(confidence_threshold=.7,max_concurrent_requests=1))
 ns=[types.SimpleNamespace(id=str(i),code='code-'+str(i)) for i in range(10)]
 ranked,cs,ranks=w.tournament_rank(ns)
 result['all_low_confidence']={'records':len(cs),'backend_calls':q.call_count,'round':max(r['round'] for r in ranks.values()),'rank_zero_size':sum(r['rank']==0 for r in ranks.values())}
 assert result['all_low_confidence']=={'records':294,'backend_calls':13,'round':21,'rank_zero_size':10}
# Execute two exact Agent methods in a disposable workspace.
ap=AUTH/'mle-bench/agents/aide/aide/agent.py';at=ast.parse(ap.read_text());cl=next(x for x in at.body if isinstance(x,ast.ClassDef) and x.name=='Agent')
methods=[x for x in cl.body if isinstance(x,ast.FunctionDef) and x.name in ('_update_best_solution','_post_process_node')]
env={'Node':types.SimpleNamespace,'Path':Path,'shutil':shutil,'logger':wm.logger,'WorstMetricValue':lambda:None}
exec(compile(ast.Module(body=methods,type_ignores=[]),str(ap),'exec'),env)
with tempfile.TemporaryDirectory(prefix='foreagent-audit-') as td:
 p=Path(td);(p/'submission').mkdir();(p/'best_solution').mkdir();(p/'best_submission').mkdir()
 (p/'submission/submission.csv').write_text('predictions-B');(p/'best_solution/solution.py').write_text('incumbent-code');(p/'best_submission/submission.csv').write_text('incumbent-predictions')
 aa=types.SimpleNamespace(id='A',code='code-A',plan='',metric=.1,is_skipped=False)
 bb=types.SimpleNamespace(id='B',code='code-B',plan='',metric=.2,is_skipped=False)
 owner=types.SimpleNamespace(journal=types.SimpleNamespace(nodes=[aa,bb],get_best_node=lambda:aa),cfg=types.SimpleNamespace(workspace_dir=p))
 env['_update_best_solution'](owner)
 result['earlier_batch_best']={'journal_best':'A','last_executed':'B','saved_code':(p/'best_solution/solution.py').read_text(),'saved_predictions':(p/'best_submission/submission.csv').read_text()}
 assert result['earlier_batch_best']['saved_code']=='incumbent-code'
 # A candidate that produced no CSV inherits the previous candidate's existing file.
 c=types.SimpleNamespace(id='C',is_buggy=False,is_skipped=False,metric=.2)
 env['_post_process_node'](owner,c)
 result['stale_submission_presence']={'candidate_wrote_csv':False,'previous_csv_present':True,'postprocess_marks_buggy':c.is_buggy}
 assert c.is_buggy is False
# Confirm metric helper semantics and success-only aggregation with controlled input.
rp=AUTH/'grade/util/report.py';rt=ast.parse(rp.read_text());f=next(x for x in rt.body if isinstance(x,ast.FunctionDef) and x.name=='aggregate_metrics');renv={'List':list,'Dict':dict,'Any':object};exec(compile(ast.Module(body=[f],type_ignores=[]),str(rp),'exec'),renv)
result['failed_prediction_denominator']=renv['aggregate_metrics']([{'n':2,'accuracy':1},{'n':2,'parsed':{'error':'failure'}}]);assert result['failed_prediction_denominator']['accuracy_avg']==1
# Parse the run without executing generated code.
run=PH/'records/stanford-autodl-v2';raw=json.loads((run/'logs/exp/journal.json').read_text());ns=raw['nodes'];executed=[n for n in ns if not n['is_skipped']];good=[n for n in executed if not n['is_buggy']]
byid={n['id']:n for n in ns};best=min(good,key=lambda n:n['metric']['value'])
result['live_run']={'nodes':len(ns),'executed':len(executed),'good':len(good),'buggy':len(executed)-len(good),'execution_seconds_sum':sum(n['exec_time'] for n in executed),'best':best['id'],'best_metric':best['metric'],'saved_code_equals_best':(run/'workspaces/exp/best_solution/solution.py').read_text()==best['code']}
labels=list(re.finditer(r'(?m)^\[[^\]]+\] INFO: Step (\d+)/5000$',(run/'logs/exp/aide.log').read_text()))
log=(run/'logs/exp/aide.log').read_text();batches=[]
for i,l in enumerate(labels):
 lo=int(l[1])-1;hi=int(labels[i+1][1])-1 if i+1<len(labels) else len(ns);part=ns[lo:hi]
 if len(part)!=10 or not all(n['wm_predicted_rank'] is not None for n in part):continue
 txt=log[l.start():labels[i+1].start() if i+1<len(labels) else len(log)]
 ex=[n for n in part if not n['is_skipped']]
 batches.append({'iteration':i+1,'records':len(part[0]['wm_comparison_results']),'cache_reads':txt.count('INFO: Cache hit for pair:'),'top_group_size':sum(n['wm_predicted_rank']==0 for n in part),'executed':[n['id'] for n in ex],'executed_metric_values':[n['metric']['value'] for n in ex],'all_inconclusive':all(not c['valid'] for c in part[0]['wm_comparison_results'])})
result['live_run']['batches']=batches
# Independent source-data separation and exact sequence overlap.
train=[json.loads(l) for l in (PH/'data/public/train.json').read_text().splitlines()];test=[json.loads(l) for l in (PH/'data/public/test.json').read_text().splitlines()]
result['data']={'train':len(train),'test':len(test),'id_overlap':len({r['id'] for r in train}&{r['id'] for r in test}),'exact_sequence_overlap':len({r['sequence'] for r in train}&{r['sequence'] for r in test}),'test_columns':sorted(test[0]),'train_target_lengths':dict(collections.Counter(len(r['reactivity']) for r in train)),'train_sequence_lengths':dict(collections.Counter(len(r['sequence']) for r in train)),'train_sn_filter':dict(collections.Counter(r['SN_filter'] for r in train))}
# Position prior and confidence from saved pairwise evidence, without a new query.
pair=json.loads((PH/'experiments/supporting/pairwise-246.json').read_text());rows=pair['adopted_results']
result['pairwise']={'n':len(rows),'correct':sum(r['correct'] for r in rows),'always_zero_correct':sum(r['best_index']==0 for r in rows),'always_one_correct':sum(r['best_index']==1 for r in rows),'explicit_confidence_ge_07_n':sum(r['parsed'].get('confidence',.5)>=.7 for r in rows),'known_cost_cny':pair['known_cost_cny'],'unknown_cost_calls':pair['unknown_cost_calls']}
# Saved comparison confidence is repeated on every node: count each batch once.
counts=collections.Counter();unique_queries=0
for batch in batches:
 counts[batch['records']]+=1;unique_queries+=batch['records']-batch['cache_reads']
result['live_run'].update(complete_batch_records=sum(b['records'] for b in batches),cache_reads=sum(b['cache_reads'] for b in batches),unique_comparison_requests=unique_queries,safety_exits=sum(1 for b in batches if max(n['wm_round'] for n in ns if n['id'] in b['executed'])==21))
# Source/version inventory: working copy must match pinned Git blobs.
manifest=json.loads((PH/'SOURCES.json').read_text());checkout=Path(manifest['source_roots']['author_checkout']);commit=manifest['author_commit'];entries=subprocess.check_output(['git','-C',str(checkout),'ls-tree','-r',commit],text=True).splitlines();checked=0
for entry in entries:
 header,name=entry.split('\t');mode,kind,oid=header.split()
 if kind!='blob':continue
 path=AUTH/(str(Path(name).with_name('.gitattributes.upstream')) if Path(name).name=='.gitattributes' else name);data=path.read_bytes();actual=hashlib.sha1(('blob '+str(len(data))+'\0').encode()+data).hexdigest();assert oid==actual,name;checked+=1
result['versions']={'author_commit':commit,'author_blobs_verified':checked,'reproduction_head':subprocess.check_output(['git','-C',str(ROOT),'rev-parse','HEAD'],text=True).strip(),'phase1_tracked_files':len(subprocess.check_output(['git','-C',str(ROOT),'ls-files','phase1-reproduction'],text=True).splitlines()),'source_manifest_sha256':hashlib.sha256((PH/'SOURCES.json').read_bytes()).hexdigest()}
# Simulate saved-journal selection decisions for every completed historical batch.
hist=[]
for folder in sorted((ROOT/'data/historical/source_records').iterdir()):
 jp=folder/'journal.json.gz';lp=folder/'aide.log.gz'
 if not jp.is_file():continue
 nn=json.loads(gzip.decompress(jp.read_bytes()))['nodes'];ll=gzip.decompress(lp.read_bytes()).decode();ls=list(re.finditer(r'(?m)^\[[^\]]+\] INFO: Step (\d+)/5000$',ll));miss=[]
 for i,l in enumerate(ls):
  lo=int(l[1])-1;hi=int(ls[i+1][1])-1 if i+1<len(ls) else len(nn);pn=nn[lo:hi]
  if len(pn)!=10 or not all(n.get('wm_predicted_rank') is not None for n in pn):continue
  valid=[n for n in nn[:hi] if not n['is_skipped'] and not n['is_buggy'] and n.get('metric',{}).get('value') is not None];ex=[n for n in nn[:hi] if not n['is_skipped']]
  if not valid or not ex:continue
  maximize=valid[0]['metric']['maximize'];bn=(max if maximize else min)(valid,key=lambda n:n['metric']['value']);current=[n['id'] for n in pn]
  if bn['id'] in current and bn['id']!=ex[-1]['id']:miss.append({'iteration':i+1,'best':bn['id'],'last_executed':ex[-1]['id'],'best_metric':bn['metric']['value']})
 hist.append({'run':folder.name,'earlier_batch_best_update_miss_conditions':miss})
result['historical_checkpoint_scan']=hist
for item in result['historical_checkpoint_scan']:
 folder=ROOT/'data/historical/source_records'/item['run']
 raw_nodes=json.loads(gzip.decompress((folder/'journal.json.gz').read_bytes()))['nodes']
 good_nodes=[n for n in raw_nodes if not n['is_skipped'] and not n['is_buggy'] and n['metric']['value'] is not None]
 if not good_nodes:continue
 bn=(max if good_nodes[0]['metric']['maximize'] else min)(good_nodes,key=lambda n:n['metric']['value'])
 log_bytes=gzip.decompress((folder/'aide.log.gz').read_bytes());log_lines=log_bytes.decode().splitlines()
 updates=[(i,l) for i,l in enumerate(log_lines,1) if re.search(r'Node [0-9a-f]{32} is the best node so far',l)]
 saved=re.search(r'Node ([0-9a-f]{32}) is',updates[-1][1])[1] if updates else None
 item.update(journal_best=bn['id'],journal_best_metric=bn['metric']['value'],last_logged_saved_best=saved,last_saved_log_line=updates[-1][0] if updates else None,final_best_identity_mismatch=saved!=bn['id'])
 if saved!=bn['id']:
  item['last_saved_metric']=next(n['metric']['value'] for n in raw_nodes if n['id']==saved)
  item['best_execution_evidence']=[{'line':i,'text':l} for i,l in enumerate(log_lines,1) if (bn['id'][:8] in l and 'Executing candidate' in l) or (bn['id'] in l and 'not buggy' in l)]
  item['log_sha256_decompressed']=hashlib.sha256(log_bytes).hexdigest()
result['notes']={'historical_checkpoint_scan':'Step-boundary scan is a diagnostic screen. Final mismatch additionally verifies the minimum/maximum over good journal nodes and last saved-best log event. The published Stanford final identity is independently available in author-final-reference.json.','all_low_confidence':'Native WorldModel with deterministic constant replies; cached reads are not extra model requests.','stale_submission_presence':'Native postprocessing check with a previous candidate file; actual occurrence requires artifact tracing.'}
OUT.write_text(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
print(json.dumps({k:v for k,v in result.items() if k not in ('historical_checkpoint_scan','live_run')},ensure_ascii=False));print('live_run',json.dumps(result['live_run']));print('historical_miss_conditions',sum(len(r['earlier_batch_best_update_miss_conditions']) for r in hist),'in',len(hist),'runs');print('wrote',str(OUT))
