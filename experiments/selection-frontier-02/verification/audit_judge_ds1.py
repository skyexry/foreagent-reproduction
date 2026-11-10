"""Read-only independent DS1 audit of partial D/A oracle masks and actual paths."""
from collections import Counter,defaultdict
import gzip
import hashlib
import json
from pathlib import Path
import random
import statistics
import sys
import time

import numpy as np

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(Path(__file__).resolve().parent))
from audit_outputs import close,parse,sha
from reproduction.clean_ranking_v1.loader import load_world
from reproduction.clean_ranking_v1.run import select

HERE=Path(__file__).resolve().parent;E=HERE.parent


def main():
    start=time.monotonic();run=E/'judge-intervention/run_1';checks=Counter();prefix=hashlib.sha256();rows={}
    with gzip.open(run/'decisions.oracle.jsonl.gz','rt') as f:
        for line in f:
            row=json.loads(line)
            if row['bank']!='DS1':break
            prefix.update(line.encode())
            digest=row['decision_sha256'];plain={k:v for k,v in row.items() if k!='decision_sha256'}
            assert hashlib.sha256(json.dumps(plain,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()==digest
            rows[(row['job_id'],row['arm'],row['fold'])]=row
    assert len(rows)==850*9
    scores={}
    with gzip.open(run/'per_fold_scores.jsonl.gz','rt') as f:
        for line in f:
            row=json.loads(line)
            if row['bank']!='DS1':break
            scores[(row['job_id'],row['arm'],row['fold'])]=row
    assert len(scores)==len(rows)
    prepared=ROOT/'experiments/clean-ranking-v1/prepared'
    bank=json.loads((prepared/'feedback.json').read_text());labels=json.loads((prepared/'evaluation_labels.json').read_text())
    jobs={j['job_id']:j for line in (prepared/'jobs.jsonl').read_text().splitlines() if (j:=json.loads(line))}
    code={task:{i:(ROOT/p).read_text() for i,p in files.items()} for task,files in json.loads((prepared/'code_files.json').read_text()).items()}
    frozen={}
    with gzip.open(ROOT/'experiments/clean-ranking-v1/results/decisions.jsonl.gz','rt') as f:
        for line in f:
            row=json.loads(line)
            if row['method']=='corrected_tournament':frozen[row['job_id']]=row
    model=load_world();all_metrics={};opportunity={}
    # Controls are independently replayed and checked against original frozen C0.
    for key,job in jobs.items():
        row=rows[(key,'O',None)]
        selected,trace,stats=select(model,job,bank[job['task']],{i:code[job['task']][i] for i in job['ids']},'corrected_tournament',.7)
        assert row['selected']==selected==frozen[key]['selected']
        assert row['trace']==trace==frozen[key]['trace'] and row['stats']==stats==frozen[key]['stats']
        checks['DS1_actual_control_exact_original']+=1
    print('DS1 all 850 original controls replayed exactly',flush=True)
    for fold in range(4):
        for arm in ('D','A'):
            changed_bank={};metadata={};counts=Counter()
            for task,table in bank.items():
                changed_bank[task]={};metadata[task]={}
                for pair,item in table.items():
                    eligible=int(hashlib.sha256((task+'\x1f'+pair).encode()).hexdigest(),16)%4==fold
                    a,b=item['order'];strict=labels[task][a]!=labels[task][b]
                    truth=a if labels[task][a]>labels[task][b] else b if strict else None
                    old,confidence=parse(item);accepted=old if confidence>=.7 else None
                    target=eligible and strict and ((accepted is not None) if arm=='D' else (accepted is None))
                    updated=dict(item)
                    if target and accepted!=truth:
                        updated['predicted_best_index']=item['order'].index(truth)
                        if arm=='A':updated['confidence']=.7
                    altered=updated!=item
                    assert altered==(target and accepted!=truth)
                    assert eligible or updated==item
                    assert strict or updated==item
                    if arm=='D':assert updated['confidence']==item['confidence']
                    if altered:
                        raw_new,new_c=parse(updated);assert raw_new==truth and new_c>=.7
                    changed_bank[task][pair]=updated;metadata[task][pair]=(eligible,target,altered)
                    counts['eligible']+=eligible;counts['target']+=target;counts['altered']+=altered
                    checks['DS1_full_bank_oracle_gate_checks']+=1
            opportunity[arm+str(fold)]=dict(counts)
            for key,job in jobs.items():
                row=rows[(key,arm,fold)]
                selected,trace,stats=select(model,job,changed_bank[job['task']],{i:code[job['task']][i] for i in job['ids']},'corrected_tournament',.7)
                assert row['selected']==selected and row['trace']==trace and row['stats']==stats
                exposure=Counter()
                for edge in trace:
                    pair='|'.join(sorted((edge['a'],edge['b'])));eligible,target,altered=metadata[job['task']][pair]
                    w,c=parse(changed_bank[job['task']][pair]);expected=w if c>=.7 else None
                    assert edge['winner']==expected and edge['confidence']==c
                    exposure['eligible_queried']+=eligible;exposure['target_queried']+=target;exposure['altered_queried']+=altered
                    exposure['accepted_queried']+=expected is not None
                assert dict(exposure)==row['exposure']
                checks['DS1_oracle_actual_paths_and_exposure_exact']+=1
            print('DS1 replayed',arm,fold,flush=True)
    # Directly recalculate every fold score, then average folds within job before task.
    grouped=defaultdict(list)
    for (key,arm,fold),row in rows.items():
        job=jobs[key];u=labels[job['task']];hi=max(u[i] for i in job['ids']);lo=min(u[i] for i in job['ids'])
        selected=row['selected']
        regret=statistics.fmean((hi-u[i])/(hi-lo) if hi>lo else 0. for i in selected)
        hit=sum(u[i]==hi for i in selected)/len(selected)
        actual=scores[(key,arm,fold)]['metrics'];close(regret,actual['regret']);close(hit,actual['best_hit'])
        metric=dict(regret=regret,best_hit=hit,**row['stats'],selected_size=len(selected))
        metric.update({k:row['exposure'][k] for k in ('eligible_queried','target_queried','altered_queried')})
        for name,value in metric.items():close(value,actual[name])
        all_metrics[(key,arm,fold)]=metric;checks['DS1_fold_scores_independent']+=1
    per_task={};tasks=sorted(labels)
    for task in tasks:
        per_task[task]={}
        keys=[key for key,job in jobs.items() if job['task']==task]
        for arm in ('O','D','A'):
            job_metrics=[]
            for key in keys:
                folds=[None] if arm=='O' else list(range(4))
                metrics=[all_metrics[(key,arm,f)] for f in folds]
                job_metrics.append({m:statistics.fmean(r[m] for r in metrics) for m in metrics[0]})
            per_task[task][arm]={m:statistics.fmean(r[m] for r in job_metrics) for m in job_metrics[0]}
    stage=json.loads((run/'stage_DS1.json').read_text())
    for arm in ('O','D','A'):
        for m in stage['macro'][arm]:close(statistics.fmean(per_task[t][arm][m] for t in tasks),stage['macro'][arm][m])
    rng=random.Random(20261108093);draws=np.array([rng.choices(range(26),k=26) for _ in range(10000)])
    for name,(left,right) in {'O_minus_D':('O','D'),'O_minus_A':('O','A'),'A_minus_D':('A','D')}.items():
        for m in ('regret','best_hit'):
            values=np.array([(per_task[t][left][m]-per_task[t][right][m])*(1 if m=='regret' else -1) for t in tasks])
            target=stage['contrasts'][name][m];close(float(values.mean()),target['gain'])
            expected=np.quantile(values[draws].mean(axis=1),[.025,.975])
            for a,b in zip(expected,target['ci95']):close(float(a),b)
            for i,t in enumerate(tasks):close(float(np.delete(values,i).mean()),target['leave_one_task_out'][t])
            checks['DS1_primary_contrasts_CI_LOO_independent']+=1
    for arm in ('D','A'):assert sum(opportunity[arm+str(f)]['eligible'] for f in range(4))==17877
    result=dict(status='passed',checks=dict(checks),opportunity=opportunity,DS1_sealed_prefix_sha256=prefix.hexdigest(),
        stage_DS1_sha256=sha(run/'stage_DS1.json'),protocol_sha256=sha(run/'protocol.snapshot.json'),bank_sha256=sha(prepared/'feedback.json'),
        script_sha256=sha(Path(__file__)),wall_seconds=time.monotonic()-start,
        scope='DS1 only; all controls and eight oracle paths per job reproduced from independent mask/bank construction, frozen original tournament, sealed outputs read-only')
    (HERE/'judge_DS1_receipt.json').write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')
    print(json.dumps(result),flush=True)


if __name__=='__main__':main()
