#!/usr/bin/env python3
"""Descriptive paired-outcome and realized-cost tables; no new interventions."""
from collections import Counter,defaultdict
import hashlib
import json
from pathlib import Path
import shutil

HERE=Path(__file__).resolve().parent;SRC=HERE/'run_1';OUT=HERE/'report_1';assert not OUT.exists();OUT.mkdir()
shutil.copyfile(__file__,OUT/'report.snapshot.py')
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
summary=json.loads((SRC/'summary.json').read_text())
outcomes=defaultdict(Counter)
for line in (SRC/'per_episode_fold_averaged.jsonl').read_text().splitlines():
    r=json.loads(line)
    for name in ('g_D','g_A','g_D_minus_g_A'):
        value=r[name];outcomes[(r['bank'],name)]['improved' if value>1e-12 else 'worsened' if value < -1e-12 else 'unchanged']+=1
table={}
for n,s in summary['summaries'].items():
    table[n]={'tasks':s['tasks'],'contrasts':{k:{'gain':v['regret']['gain'],'ci95':v['regret']['ci95'],
            'hit_gain':v['best_hit']['gain'],'leave_one_range':[v['regret']['leave_one_min'],v['regret']['leave_one_max']]}
            for k,v in s['contrasts'].items()},
            'cost_and_exposure_task_macro':{a:{k:s['macro'][a][k] for k in ('unique_feedback_reads','cache_reads','budget_denials','altered_queried','eligible_queried','target_queried')} for a in ('O','D','A')},
            'fold_averaged_episode_outcomes':{k:dict(outcomes[(n,k)]) for k in ('g_D','g_A','g_D_minus_g_A')} if n!='GPT_task_first_pooled' else None}
(OUT/'tables.json').write_text(json.dumps(table,indent=2)+'\n')
(OUT/'receipt.json').write_text(json.dumps({'status':'complete','source_summary_sha256':sha(SRC/'summary.json'),
    'source_episode_sha256':sha(SRC/'per_episode_fold_averaged.jsonl'),'interventions_added':0,'oracle_replays_added':0},indent=2)+'\n')
(OUT/'hashes.json').write_text(json.dumps({p.name:sha(p) for p in OUT.iterdir() if p.is_file() and p.name!='hashes.json'},indent=2)+'\n')
print('Descriptive tables written')
