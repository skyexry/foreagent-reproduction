#!/usr/bin/env python3
"""Materialize paired per-episode gains from the already sealed factorial outputs."""
from collections import defaultdict
import gzip
import hashlib
import json
import math
from pathlib import Path
import shutil

HERE=Path(__file__).resolve().parent
SRC=HERE/'all_banks_run_2'
OUT=HERE/'paired_differences_1'
assert not OUT.exists()
OUT.mkdir()
shutil.copyfile(__file__,OUT/'script.snapshot.py')
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
summary=json.loads((SRC/'summary.json').read_text())
episodes={}
for line in (SRC/'per_episode.jsonl').read_text().splitlines():
    row=json.loads(line)
    episodes[(row['bank'],row['schedule'],row['arm'],row['job_id'])]=row
gpt=[n for n in summary['banks'] if n!='DeepSeek']
job_ids=sorted({k[3] for k in episodes})
for arm in ('g70_raw','g50_raw','g70_smooth','g50_smooth'):
    for jid in job_ids:
        rows=[episodes[(b,'coverage_random',arm,jid)] for b in gpt]
        episodes[('GPT_task_first_mean','coverage_random',arm,jid)]={
            'task':rows[0]['task'],'metrics':{m:sum(r['metrics'][m] for r in rows)/3 for m in ('regret','best_hit')},
            'stats':{m:sum(r['stats'][m] for r in rows)/3 for m in rows[0]['stats']}}
leave={}
counts={}
with gzip.open(OUT/'per_episode_paired.jsonl.gz','wt') as stream:
    for name,c in summary['contrasts'].items():
        tasks=defaultdict(list)
        outcomes=defaultdict(int)
        for jid in job_ids:
            if 'baseline' in c:
                left=episodes[(*c['baseline'],jid)];right=episodes[(*c['intervention'],jid)]
                gain=left['metrics']['regret']-right['metrics']['regret']
                hit=right['metrics']['best_hit']-left['metrics']['best_hit']
                reads=right['stats']['unique_feedback_reads']-left['stats']['unique_feedback_reads']
                task=left['task']
            else:
                bank=name.split('/')[0]
                rows={arm:episodes[(bank,'coverage_random',arm,jid)] for arm in ('g70_raw','g50_raw','g70_smooth','g50_smooth')}
                v={a:r['metrics']['regret'] for a,r in rows.items()}
                gain=v['g50_raw']-v['g50_smooth']-v['g70_raw']+v['g70_smooth']
                hit=None;reads=0;task=rows['g70_raw']['task']
            outcome='improved' if gain>1e-12 else 'worsened' if gain < -1e-12 else 'equal'
            outcomes[outcome]+=1;tasks[task].append(gain)
            stream.write(json.dumps({'contrast':name,'job_id':jid,'task':task,'regret_gain':gain,
                                     'hit_gain':hit,'unique_read_difference':reads,'outcome':outcome})+'\n')
        tmeans={t:sum(v)/len(v) for t,v in tasks.items()}
        macro=sum(tmeans.values())/26
        assert math.isclose(macro,c['regret_gain']['mean'],abs_tol=1e-12)
        leave[name]={t:(sum(tmeans.values())-v)/25 for t,v in tmeans.items()}
        counts[name]=dict(outcomes)
(OUT/'leave_one_task_out_all_contrasts.json').write_text(json.dumps(leave,indent=2)+'\n')
(OUT/'episode_outcome_counts.json').write_text(json.dumps(counts,indent=2)+'\n')
(OUT/'receipt.json').write_text(json.dumps({'status':'passed','input_summary_sha256':sha(SRC/'summary.json'),
    'input_episode_sha256':sha(SRC/'per_episode.jsonl'),'contrasts':len(counts),'jobs_per_contrast':850,
    'paired_episode_records':len(counts)*850,'all_task_macro_gains_match_main_summary':True},indent=2)+'\n')
(OUT/'output_sha256.json').write_text(json.dumps({p.name:sha(p) for p in sorted(OUT.iterdir()) if p.is_file() and p.name!='output_sha256.json'},indent=2)+'\n')
print('paired differences verified:',len(counts),'contrasts')
