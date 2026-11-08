"""Validate released pair labels and quantify finite-score-only sensitivity for one saved author run.
Usage: python corpus_labels.py ROOT OUTPUT.json
"""
import json,math,sys
from pathlib import Path
root=Path(sys.argv[1]);n=correct=bad=bc=bn=0;affected=[]
for p in sorted((root/'data/coverage/solutions_subset_50').glob('*/ground_truth/*n2.json')):
 task=p.parent.parent.name;gs=json.loads(p.read_text());rs=json.loads((root/'data/author_reference'/(task+'.json')).read_text())['results'];assert len(rs)==len(gs)
 for i,(g,r) in enumerate(zip(gs,rs)):
  assert [Path(x).stem[-4:]+'.py' for x in g['paths']]==[s['path'] for s in r['solutions']]
  assert g['best_index']==r['groundtruth']['best_index']
  c=int(r['prediction']['best_index']==g['best_index']);n+=1;correct+=c
  if any(not math.isfinite(x) for x in g['scores']):
   bad+=1;bc+=c;bn+=not math.isfinite(g['scores'][g['best_index']])
   affected.append({'task':task,'group_index':i,'labelled_best_is_nonfinite':not math.isfinite(g['scores'][g['best_index']]),'correct_on_saved_label':bool(c)})
assert n==18438
valid_n=n-bad
d={'author_saved_run':{'n':n,'correct':correct,'accuracy':correct/n},'nonfinite_score_pairs':bad,'nonfinite_labelled_winners':bn,'correct_on_invalid_pairs':bc,'finite_pairs_only':{'n':valid_n,'correct':correct-bc,'accuracy':(correct-bc)/valid_n},'change_pp':100*((correct-bc)/valid_n-correct/n),'affected_groups':affected}
sub=json.loads((root/'experiments/coverage_retry_results.json').read_text())['adopted_results'];d['reproduction246_affected_indices']=[r['index'] for r in sub if any(a['task']==r['task'] and a['group_index']==r['source_group_index'] for a in affected)]
Path(sys.argv[2]).write_text(json.dumps(d,indent=2)+'\n')
print({k:v for k,v in d.items() if k!='affected_groups'})
