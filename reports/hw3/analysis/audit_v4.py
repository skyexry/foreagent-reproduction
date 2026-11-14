"""Additional read-only audits of archived live trajectories and saved submissions."""
from pathlib import Path
import json,gzip,re,datetime,statistics,hashlib,argparse
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
ROOT=Path(__file__).resolve().parents[3];OUT=ROOT/'reports/hw3/figures';R=ROOT/'phase1-reproduction/records/stanford-autodl-v2'
p=argparse.ArgumentParser();p.add_argument('--answers',required=True);p.add_argument('--leaderboard',required=True);args=p.parse_args()
summary=json.loads((OUT/'online_analysis.json').read_text());j=json.loads((R/'logs/exp/journal.json').read_text());nodes=j['nodes'];start=summary['long_request']['start'];end=summary['long_request']['end']
pattern=re.compile(r'^\[([\d-]+ [\d:,]+)\] (?:INFO|WARNING|ERROR): (.*)$',re.M)
def events(log):return [(datetime.datetime.strptime(t,'%Y-%m-%d %H:%M:%S,%f'),msg) for t,msg in pattern.findall(log)]
def audit_run(name,j,log,offset):
 ev=events(log);t0=ev[0][0];sec=lambda t:(t-t0).total_seconds();ev=[(t,msg) for t,msg in ev if 0<=sec(t)<=43200]
 ns=j['nodes'];ct=[n['ctime']-t0.replace(tzinfo=datetime.timezone(datetime.timedelta(hours=offset))).timestamp() for n in ns]
 groups={}
 for n in ns:
  if n.get('wm_comparison_results'):groups.setdefault(json.dumps(n['wm_comparison_results'],sort_keys=True),[]).append(n)
 # Verify first-round records against completed batches, with no cache access between generation and their first results.
 first=[];checks=[]
 for cs,group in groups.items():
  ids={n['id'][:8] for n in group};indices=[i for i,(_,m) in enumerate(ev) if re.match(r'Round 1: Node ',m) and len(ids.intersection(re.findall(r'\b[0-9a-f]{8}\b',m)))==2]
  assert len(indices)==5,(name,len(indices))
  first_idx=indices[0];gidx=max(i for i in range(first_idx) if 'Generated improvement candidate 10/10' in ev[i][1]);pre=[m for _,m in ev[gidx+1:first_idx]]
  assert sum('Cache hit for pair' in m for m in pre)==0
  assert sum("Querying model 'DeepSeek-V3.2-Thinking'" in m for m in pre)==5
  first.extend(json.loads(cs)[:5]);checks.append({'first_round_fresh':5,'cache_hits':0})
 # Elimination identity is explicitly logged even when revival opponent identity is absent.
 eliminated=set(re.findall(r'Round \d+: Node [0-9a-f]+ beats ([0-9a-f]+)',log))|set(re.findall(r'Round \d+ \(Re-match\): Node ([0-9a-f]+) lost',log))
 tops=[n for n in ns if n.get('wm_predicted_rank')==0]
 # Request elapsed duration + output size; do not substitute node timestamp spacing for generation latency.
 role=None;requests=[]
 for t,m in ev:
  match=re.search(r"Querying model '([^']+)'",m)
  if match:role=match[1]
  match=re.search(r'Query completed in ([\d.]+)s. Input tokens: (\d+), output tokens: (\d+)',m)
  if match and role=='DeepSeek-V3.2':requests.append({'end':sec(t),'seconds':float(match[1]),'output_tokens':int(match[3])})
 phases={}
 for label,q in [('before_wait',[q for q in requests if q['end']<=start]),('after_wait',[q for q in requests if q['end']>=end]),('all',requests)]:
  phases[label]={'count':len(q),'mean_seconds':statistics.mean(v['seconds'] for v in q) if q else None,'mean_output_tokens':statistics.mean(v['output_tokens'] for v in q) if q else None}
 return {'name':name,'counts_at_wait_start_end_cutoff':[sum(t<=h for t in ct) for h in [start,end,43200]],'first_round_fresh_calls':len(first),'first_round_high_confidence':sum(c['confidence']>=.7 for c in first),'rank_zero_candidates':len(tops),'rank_zero_eliminated':sum(n['id'][:8] in eliminated for n in tops),'generation_requests':phases,'fresh_round_checks':checks}
ours=audit_run('reproduction',j,(R/'logs/exp/aide.log').read_text(),8);authors=[]
for ref in summary['author_runs']:
 folder=next((ROOT/'data/historical/source_records').glob('stanford*_'+ref['id']+'*'));authors.append(audit_run(ref['id'],json.loads(gzip.open(folder/'journal.json.gz','rt').read()),gzip.open(folder/'aide.log.gz','rt').read(),0))
# Read existing outputs only: no retraining or new candidate selection using private labels.
y=pd.read_csv(args.answers).set_index('id_seqpos');cols=['reactivity','deg_Mg_pH10','deg_Mg_50C'];mask=y['keep'].astype(bool);assert mask.sum()==16320
lb=pd.read_csv(args.leaderboard)['score'].dropna().to_numpy();assert len(lb)>0
parsed=dict((nid,t) for t,_,nid in summary['trajectory']);scores=[]
for n in nodes:
 if n['is_skipped'] or n['is_buggy']:continue
 folder=R/'workspaces/exp/all_nodes'/('node_'+n['id'][:8]);assert json.loads((folder/'metadata.json').read_text())['node_id']==n['id'];assert (folder/'code.py').read_text()==n['code']
 # Verify each saved output against its execution task's recorded submission digest.
 digest=hashlib.sha256((folder/'submission.csv').read_bytes()).hexdigest();matches=[]
 for q in (R/'tasks').glob('*/request.json'):
  request=json.loads(q.read_text())
  if request['code']==n['code'] and (q.parent/'submission.sha256').exists():matches.append((q.parent/'submission.sha256').read_text().split()[0])
 assert digest in matches,(n['id'],'submission provenance mismatch')
 pred=pd.read_csv(folder/'submission.csv').set_index('id_seqpos');assert pred.index.is_unique and set(pred.index)==set(y.index);a=pred.loc[y.index,cols].to_numpy();assert np.isfinite(a).all();diff=a[mask]-y.loc[mask,cols].to_numpy();score=float(np.sqrt((diff**2).mean(axis=0)).mean());br=float((lb>score).mean())
 scores.append({'id':n['id'],'hours':parsed[n['id']]/3600,'stage':'improve' if n.get('wm_comparison_results') else 'debug','validation':n['metric']['value'],'private_mcrmse':score,'beat_ratio':br})
scores.sort(key=lambda d:d['hours']);assert abs(next(s['private_mcrmse'] for s in scores if s['id'].startswith('84c79a8d'))-.2663989312)<1e-8
out={'ours':ours,'authors':authors,'test_scores':scores,'leaderboard_teams':len(lb),'cache_order_audit':'Exact reversal counts not identifiable: cache-hit events expose unordered code hashes but omit ordered candidate identities; revival opponent identities and response bodies are not fully recorded.'}
(OUT/'audit_v4.json').write_text(json.dumps(out,indent=2))
plt.rcParams.update({'font.size':9,'axes.spines.top':False,'axes.spines.right':False,'pdf.fonttype':42})
fig,axs=plt.subplots(1,2,figsize=(7,2.5),layout='constrained');a=axs[0]
for stage,marker,color in [('debug','o','#317e96'),('improve','^','#b67f31')]:
 ss=[s for s in scores if s['stage']==stage];a.scatter([s['hours'] for s in ss],[s['private_mcrmse'] for s in ss],marker=marker,color=color,label=stage.capitalize(),s=20)
vals=np.minimum.accumulate([s['private_mcrmse'] for s in scores]);a.step([s['hours'] for s in scores]+[12],list(vals)+[vals[-1]],where='post',color='#555',lw=1,label='Best observed test score');a.set(xlim=(0,12),xlabel='Wall-clock time (hours)',ylabel='Private MCRMSE',title='(a) Retrospective private scores');a.legend(fontsize=7)
a=axs[1];br=np.maximum.accumulate([s['beat_ratio']*100 for s in scores]);a.step([0]+[s['hours'] for s in scores]+[12],[0]+list(br)+[br[-1]],where='post',color='#317e96',label='Best observed Beat Ratio');a.set(xlim=(0,12),ylim=(0,103),xlabel='Wall-clock time (hours)',ylabel='Beat Ratio (%)',title='(b) Leaderboard-relative trajectory');a.legend(fontsize=7,loc='lower right')
for a in axs:a.axvspan(start/3600,end/3600,color='#e8b45a',alpha=.2)
fig.savefig(OUT/'private_trajectory.pdf');plt.close(fig)
print(json.dumps({'ours':ours,'authors':[{k:v for k,v in a.items() if k!='fresh_round_checks'} for a in authors],'test_scores':scores,'leaderboard_teams':len(lb)},indent=2))
