"""Post-hoc audit of already saved predictions, never selects or executes a candidate."""
import csv,gzip,hashlib,json,math,re,statistics,sys
from pathlib import Path
root=Path(sys.argv[1]);ph=root/'phase1-reproduction';sys.path.insert(0,str(root));sys.dont_write_bytecode=True
from scripts.verify_online_baseline import score_by_id
private=Path(sys.argv[3])
answers=list(csv.DictReader(private.open()));j=json.loads((ph/'records/stanford-autodl-v2/logs/exp/journal.json').read_text());rows=[]
for n in j['nodes']:
 if n['is_skipped'] or n['is_buggy']:continue
 file=ph/'records/stanford-autodl-v2/workspaces/exp/all_nodes'/('node_'+n['id'][:8])/'submission.csv'
 score=score_by_id(list(csv.DictReader(file.open())),answers)
 rows.append({'id':n['id'],'validation':n['metric']['value'],'private_score':score['score'],'per_target_rmse':score['per_target_rmse'],'prediction_sha256':hashlib.sha256(file.read_bytes()).hexdigest(),'wm_rank':n['wm_predicted_rank']})
best_val=min(rows,key=lambda x:x['validation']);best_test=min(rows,key=lambda x:x['private_score'])
ns={r['id']:r for r in rows};edges=[]
for r in rows:
 parent=j['node2parent'].get(r['id'])
 if parent in ns:
  p=ns[parent];dv=r['validation']-p['validation'];dt=r['private_score']-p['private_score'];edges.append({'parent':parent,'child':r['id'],'validation_delta':dv,'private_delta':dt,'sign_agrees':(dv>0)-(dv<0)==(dt>0)-(dt<0)})
# Rank association within this dependent, selected set is descriptive.
def ranks(v):return [1+sum(x<y for x in v)+(sum(x==y for x in v)-1)/2 for y in v]
x=ranks([r['validation'] for r in rows]);y=ranks([r['private_score'] for r in rows]);rho=statistics.correlation(x,y)
# Directly expose the loss-mask mismatch on the same prediction file, with no fitting.
pred=list(csv.DictReader((ph/'records/stanford-autodl-v2/workspaces/exp/best_submission/submission.csv').open()));ans={a['id_seqpos']:a for a in answers};all_score=statistics.mean(math.sqrt(statistics.mean((float(r[c])-float(ans[r['id_seqpos']][c]))**2 for r in pred)) for c in ('reactivity','deg_Mg_pH10','deg_Mg_50C'))
result={'id':'foreagent-candidate-audit-20261108-v1','scope':'Retrospective scores of saved executed valid predictions; private labels used only by this external audit. These are dependent selected candidates. The frozen final submission and protocol are preserved.','new_model_calls':0,'new_training_runs':0,'private_answers_sha256':hashlib.sha256(private.read_bytes()).hexdigest(),'candidates':rows,'validation_selected':best_val['id'],'posthoc_private_best':best_test['id'],'posthoc_selection_gap':best_val['private_score']-best_test['private_score'],'spearman_validation_private':rho,'good_parent_child_edges':edges,'frozen_private_masked_mcrmse':best_val['private_score'],'same_frozen_predictions_all107_padded_zero_mcrmse':all_score,'padded_loss_fraction':39/107}
Path(sys.argv[2]).write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:v for k,v in result.items() if k not in ('candidates','good_parent_child_edges')},indent=2));print('candidates',[(r['id'][:8],r['validation'],round(r['private_score'],8)) for r in rows]);print('parent edges',len(edges),'agree',sum(e['sign_agrees'] for e in edges))
