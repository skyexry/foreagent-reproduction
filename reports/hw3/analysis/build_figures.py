"""Read archived online runs; derive proposal figures without model or training calls."""
from pathlib import Path
import json,gzip,re,datetime,collections,statistics
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
ROOT=Path(__file__).resolve().parents[3]; OUT=ROOT/'reports/hw3/figures'
D=ROOT/'phase1-reproduction/records/stanford-autodl-v2/logs/exp'
j=json.loads((D/'journal.json').read_text()); ns=j['nodes'];log=(D/'aide.log').read_text()
pat=re.compile(r'^\[([\d-]+ [\d:,]+)\] (?:INFO|WARNING|ERROR): (.*)$',re.M)
ev=[(datetime.datetime.strptime(t,'%Y-%m-%d %H:%M:%S,%f'),msg) for t,msg in pat.findall(log)]
t0=ev[0][0]; sec=lambda t:(t-t0).total_seconds();B=43200
ev=[(t,msg) for t,msg in ev if 0<=sec(t)<=B]
# Completion timestamps for feedback, not node creation timestamps.
parsed={};model=None;queries=[];pending_start=None
for t,msg in ev:
 if sec(t)>B:break
 m=re.search(r"Querying model '([^']+)'",msg)
 if m:model=m[1];pending_start=sec(t)
 m=re.search(r'Query completed in ([\d.]+)s',msg)
 if m:
  duration=float(m[1]); queries.append({'role':model,'start':sec(t)-duration,'end':sec(t),'seconds':duration});pending_start=None
 m=re.search(r'Parsed results: Node ([0-9a-f]+) is',msg)
 if m:parsed[m[1]]=sec(t)
if pending_start is not None and model=='DeepSeek-V3.2':queries.append({'role':'unfinished generation','start':pending_start,'end':B,'seconds':B-pending_start})
executed=[n for n in ns if not n['is_skipped']];good=[n for n in executed if not n['is_buggy'] and n['metric']['value'] is not None]
traj=sorted([(parsed[n['id']],n['metric']['value'],n['id']) for n in good]);best=min(v for _,v,_ in traj);peak=min(t for t,v,_ in traj if v==best)
groups={}
for n in ns:
 if n.get('wm_comparison_results'):groups.setdefault(json.dumps(n['wm_comparison_results'],sort_keys=True),[]).append(n)
comps=[c for k in groups for c in json.loads(k)]
bs=[]
for k,g in groups.items():bs.append({'records':len(json.loads(k)),'top_ties':sum(n['wm_predicted_rank']==0 for n in g),'executed':sum(not n['is_skipped'] for n in g),'failed':sum(not n['is_skipped'] and n['is_buggy'] for n in g)})
long=max((q for q in queries if q['role']=='gpt-4o-mini-2024-07-18'),key=lambda q:q['seconds'])
tournament=sum(float(re.search(r'completed in ([\d.]+)s',msg)[1]) for _,msg in ev if msg.startswith('World Model prediction completed'))
last_done=max(sec(t) for t,msg in ev if msg.startswith('World Model prediction completed'))
unfinished_start=min(sec(t) for t,msg in ev if sec(t)>last_done and "Querying model 'DeepSeek-V3.2-Thinking'" in msg)
tournament+=B-unfinished_start
completed_ev=[(t,msg) for t,msg in ev if sec(t)<=last_done]
generation=sum(q['seconds'] for q in queries if q['role'] in ('DeepSeek-V3.2','unfinished generation'))
feedback=sum(q['seconds'] for q in queries if q['role']=='gpt-4o-mini-2024-07-18')
execution=sum(n['exec_time'] for n in executed)
times={'Generation/API':generation,'Tournament/API':tournament,'Execution runtime':execution,'Other feedback/API':feedback-long['seconds'],'Long feedback request':long['seconds']}
times['Other overhead']=B-sum(times.values());assert times['Other overhead']>=0
refs=json.loads((ROOT/'phase1-reproduction/experiments/online-stanford-v2/author-final-reference.json').read_text())['runs'];authors=[]
for ref in refs:
 p=ROOT/'data/historical/source_records'/ref['run'];nodes=json.loads(gzip.open(p/'journal.json.gz','rt').read())['nodes'];al=gzip.open(p/'aide.log.gz','rt').read();start=datetime.datetime.strptime(pat.findall(al)[0][0],'%Y-%m-%d %H:%M:%S,%f').replace(tzinfo=datetime.timezone.utc).timestamp()
 authors.append({'id':ref['run'].split('_')[1][:8],'nodes':len(nodes),'executed':sum(not n.get('is_skipped',False) for n in nodes),'creation_hours':sorted((n['ctime']-start)/3600 for n in nodes),'score':ref['official_score'],'selected_time_h':ref['selection']['elapsed_seconds']/3600})
summary={'nodes':len(ns),'executed':len(executed),'failed':sum(n['is_buggy'] for n in executed),'valid':len(good),'batches':bs,'comparison_records':len(comps),'valid_records':sum(c['valid'] for c in comps),'confidence_ge_threshold':sum(c['confidence']>=.7 for c in comps),'cache_hits':sum('Cache hit for pair' in msg for _,msg in completed_ev),'pending_entries':2*sum(bool(re.match(r'Round \d+: Node .* inconclusive',msg)) for _,msg in completed_ev),'round_caps':sum('Tournament exceeded maximum' in msg for _,msg in ev),'top_tied_batches':sum(b['top_ties']>1 for b in bs),'calls_by_role':dict(collections.Counter(q['role'] for q in queries)),'best_internal_metric':best,'best_available_h':peak/3600,'long_request':long,'time_seconds':times,'author_runs':authors,'author_score_mean':statistics.mean(a['score'] for a in authors),'author_score_sample_sd':statistics.stdev(a['score'] for a in authors),'trajectory':traj}
(OUT/'online_analysis.json').write_text(json.dumps(summary,indent=2))
plt.rcParams.update({'font.size':9,'axes.spines.top':False,'axes.spines.right':False,'pdf.fonttype':42})
fig,axs=plt.subplots(1,2,figsize=(7,2.55),layout='constrained')
a=axs[0];ts=[t/3600 for t,_,_ in traj];vals=[v for _,v,_ in traj];bv=[];cur=float('inf')
for v in vals:cur=min(cur,v);bv.append(cur)

for stage,marker,color in [('debug','o','#317e96'),('improve','^','#b67f31')]:
 selected=[(t,v) for t,v,nid in traj if ('improve' if next(n for n in ns if n['id']==nid).get('wm_comparison_results') else 'debug')==stage]
 a.scatter([t/3600 for t,v in selected],[v for t,v in selected],s=19,marker=marker,color=color,label=stage.capitalize())
a.step(ts+[12],bv+[bv[-1]],where='post',color='#126782',label='Best validation');a.axvspan(long['start']/3600,long['end']/3600,color='#e8b45a',alpha=.3);a.axvline(peak/3600,color='#126782',ls=':',lw=1);a.set(xlabel='Wall-clock time (hours)',ylabel='Reported validation error',xlim=(0,12),title='(a) Reproduction search trajectory');a.legend(fontsize=7,loc='upper right')
for n in executed:
 if n['is_buggy']:a.plot(parsed[n['id']]/3600,.02,'x',transform=a.get_xaxis_transform(),color='#a24747',markersize=3)
a.annotate(f'Best at {peak/3600:.2f} h',xy=(peak/3600,best),xytext=(4.5,best+.07),fontsize=7,arrowprops={'arrowstyle':'->','lw':.7})
a=axs[1]
for z in authors:a.step(z['creation_hours']+[12],list(range(1,z['nodes']+1))+[z['nodes']],where='post',lw=1,alpha=.7,label='Author '+z['id'])
start=t0.replace(tzinfo=datetime.timezone(datetime.timedelta(hours=8))).timestamp();ts=sorted((n['ctime']-start)/3600 for n in ns);a.step(ts+[12],list(range(1,len(ns)+1))+[len(ns)],where='post',lw=2,color='#126782',label='Reproduction');a.axvspan(long['start']/3600,long['end']/3600,color='#e8b45a',alpha=.3);a.set(xlim=(0,12),xlabel='Wall-clock time (hours)',ylabel='Retained generated nodes',title='(b) Search breadth');a.legend(fontsize=6.6,loc='upper left')
fig.savefig(OUT/'search_trajectory.pdf');plt.close(fig)
fig,ax=plt.subplots(figsize=(7,1.5),layout='constrained');left=0;colors=['#7eadd2','#4c819e','#63a88c','#b5a6d4','#e5af52','#c8c8c8']
for (name,s),color in zip(times.items(),colors):ax.barh(0,s/3600,left=left,color=color,label=f'{name}: {s/3600:.2f} h');left+=s/3600
ax.set(xlim=(0,12),xlabel='Wall-clock budget (hours)',yticks=[]);ax.legend(loc='upper center',bbox_to_anchor=(.5,-.55),ncol=3,fontsize=7,frameon=False);ax.spines['left'].set_visible(False);fig.savefig(OUT/'time_allocation.pdf',bbox_inches='tight');plt.close(fig)
print(json.dumps({k:v for k,v in summary.items() if k not in ('trajectory','author_runs')},indent=2));print('authors',[(a['id'],a['nodes'],a['selected_time_h']) for a in authors])
