"""Independent source-order check and prespecified pool-size sensitivity summary."""
from collections import Counter,defaultdict
import gzip
import json
from pathlib import Path
import statistics
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
import audit as a

p=a.HERE/'run-003';m=a.read(a.F/'banks/manifest.json');src=Path(m['source_root'])
paths=a.read(a.ROOT/'experiments/clean-ranking-v1/prepared/code_files.json')
suffix={t:{Path(f).name[-7:]:cid for cid,f in x.items()} for t,x in paths.items()}
count=Counter()
for e in a.read(a.ROOT/'experiments/round-08/recovery_sources.json')['files']:
    bank=json.loads(gzip.decompress((a.ROOT/m['banks'][e['feedback_run']]['path']).read_bytes()))
    raw=a.read(src/e['target'])[e['task']][f"groups_{e['task']}_n2.json"]
    for r in raw:
        ids=[suffix[e['task']].get(Path(x).name[-7:]) for x in r['paths']]
        if None in ids:continue
        pair='|'.join(sorted(ids))
        if pair in bank[e['task']]:
            count['backup_admitted_pairs']+=1;count['same_endpoint_order']+=ids==bank[e['task']][pair]['order']
assert count['backup_admitted_pairs']==count['same_endpoint_order']==5013
rows=[json.loads(x) for x in (p/'per_episode.jsonl').read_text().splitlines()]
g=defaultdict(list)
for r in rows:g[(r['bank'],'n10' if r['n']==10 else 'small',r['task'])].append(r['scores'])
banks=sorted({r['bank'] for r in rows});gpt=[b for b in banks if b!='DS']
result={}
for group in ('n10','small'):
    tasks=sorted({t for b,s,t in g if s==group});a.TASKS=tasks
    data={b:{t:{arm:{k:statistics.fmean(r[arm][k] for r in g[(b,group,t)]) for k in ('regret','best_hit')} for arm in a.ARMS} for t in tasks} for b in banks}
    data['GPT_task_first_pooled']={t:{arm:{k:statistics.fmean(data[b][t][arm][k] for b in gpt) for k in ('regret','best_hit')} for arm in a.ARMS} for t in tasks}
    result[group]={'tasks':tasks,'tasks_count':len(tasks),'episodes_per_bank':sum(len(g[(banks[0],group,t)]) for t in tasks),'banks':{}}
    for b,d in data.items():
        result[group]['banks'][b]={'C_minus_L':a.infer([d[t]['C']['regret']-d[t]['L']['regret'] for t in tasks]),
                                  'direction_advantage_N32_minus_L':a.infer([d[t]['N32']['regret']-d[t]['L']['regret'] for t in tasks])}
a.dump(a.HERE/'pool_size_sensitivity.json',result)
summary=a.read(p/'summary.json')
rep={b:{'actual_L_better_than_fair_replicates':sum(r['L_minus_N_regret']<0 for r in x['negative_replicates']),'replicates':32} for b,x in summary.items()}
a.dump(a.HERE/'final_checks.json',dict(source_order_check=dict(count),negative_replicates=rep,
    C_H_L_independent_task_numeric_checks=624,sealed_rows=3400,sealed_source_pairs=71508,
    reasoning_json='auxiliary only; strict E requires full response explicit JSON',
    fallback_interpretation='confidence defaults documented in local code; archival field presence verified, full author parse history partly observed',
    new_model_calls=0,new_training_runs=0))
print({g:{b:{k:{kk:vv for kk,vv in x.items() if kk in ('gain','ci95','leave_one_min','leave_one_max')} for k,x in z.items()} for b,z in r['banks'].items() if b in ('DS','GPT_task_first_pooled')} for g,r in result.items()})
