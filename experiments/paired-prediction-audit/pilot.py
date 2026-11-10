"""Estimate slot time from historical sibling jobs and list score-blind pilot selections."""
import argparse
import hashlib
import json
import statistics
from pathlib import Path

from inventory import LOCAL

TASKS={'stanford-covid-vaccine':30, 'statoil-iceberg-classifier-challenge':10}


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('inventory',type=Path)
    ap.add_argument('output',type=Path)
    a=ap.parse_args()
    pairs=json.loads((a.inventory/'pairs.json').read_text())
    runtime=json.loads((a.inventory/'runtime.json').read_text())
    per_task={}
    matched=[]
    reuse=[]
    for task,limit in TASKS.items():
        all_times=runtime[task]
        vals=[v['seconds'] for v in all_times if v['valid']]
        per_task[task]=dict(executed=len(all_times),successful=len(vals),median_s=statistics.median(vals),
                            upper_quartile_s=statistics.quantiles(vals,method='inclusive')[2],
                            max_s=max(vals),pilot_arm_cap_minutes=limit)
        runs=sorted({r['run'] for r in pairs if r['task']==task and r['run']!=LOCAL})
        for run in runs:
            group=[r for r in pairs if r['run']==run and r['disjoint']]
            def order(r):
                return hashlib.sha256(f"paired-prediction-audit|{run}|{r['first_log_line']}".encode()).digest()
            for target,eligible in [(matched,group), (reuse,[r for r in group if any(r[a]['predictions'] for a in ('c0','memory'))])]:
                r=min(eligible,key=order)
                saved=next((a for a in ('c0','memory') if r[a]['predictions']),None)
                target.append(dict(task=task,run=run,first_log_line=r['first_log_line'],
                                   c0=r['c0']['id'],memory=r['memory']['id'],saved_arm=saved,
                                   saved_arm_seconds=r[saved]['exec_seconds'] if saved else None))
    assert len(reuse)==len(matched)==6 and all(r['saved_arm'] for r in reuse)
    per_arm={k:sum(3*p[k] for p in per_task.values())/3600 for k in ('median_s','upper_quartile_s')}
    cap=sum(3*v for v in TASKS.values())/60
    scenarios={name:dict(new_runs=6*arms,median_based_hours=arms*per_arm['median_s'],
                         upper_quartile_based_hours=arms*per_arm['upper_quartile_s'],
                         training_cap_hours=arms*cap,one_time_setup_allowance_hours=.5)
               for name,arms in [('reuse_archived_side',1),('fresh_matched',2)]}
    result=dict(per_task=per_task,scenarios=scenarios,six_archived_arms_actual_hours=
                sum(r['saved_arm_seconds'] for r in reuse)/3600,
                score_blind_one_archive_each=reuse,score_blind_fresh_sample=matched)
    a.output.write_text(json.dumps(result,indent=2)+'\n')


if __name__=='__main__':
    main()
