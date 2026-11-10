#!/usr/bin/env python3
"""Standalone verification of partial-oracle gates, fold averaging and inference."""
from collections import Counter,defaultdict
import gzip
import hashlib
import json
import math
from pathlib import Path
import random
import shutil
import sys
import time

HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
OUT=HERE/sys.argv[1];DEST=OUT/('verification_'+sys.argv[2]);assert not DEST.exists();DEST.mkdir()
shutil.copyfile(__file__,DEST/'verify.snapshot.py');start=time.monotonic();checks=Counter()
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
load=lambda p:json.loads(Path(p).read_text())
def near(a,b):assert math.isclose(a,b,abs_tol=1e-11,rel_tol=1e-11),(a,b)
for p,h in load(OUT/'hashes.json').items():assert sha(OUT/p)==h,p
for p,h in load(OUT/'input_sha256.json').items():assert sha(ROOT/p)==h,p
protocol=load(OUT/'protocol.snapshot.json');summary=load(OUT/'summary.json')
assert sha(HERE/'protocol.json')==summary['protocol_sha256']
receipt=load(OUT/'selection_receipt.json')
assert not receipt['frozen_C0_direct_label_access_attempts']
assert sha(OUT/'decisions.oracle.jsonl.gz')==receipt['decisions_sha256']
banks={'DS1':load(ROOT/'experiments/clean-ranking-v1/prepared/feedback.json')}
gpt=load(HERE.parent/'banks/manifest.json')['banks'];ds0=load(HERE.parent/'deepseek-transfer/banks_1/manifest.json')['banks']
for n,m in {**gpt,**ds0}.items():banks[n]=json.loads(gzip.decompress((ROOT/m['path']).read_bytes()))
jobs={j['job_id']:j for line in (ROOT/'experiments/clean-ranking-v1/prepared/jobs.jsonl').read_text().splitlines() if (j:=json.loads(line))}
paths=load(ROOT/'experiments/clean-ranking-v1/prepared/code_files.json')
for task,table in paths.items():
    for cid,p in table.items():assert sha(ROOT/p)[:20]==cid;checks['candidate_code_identity_sha_checks']+=1
labels=load(ROOT/'experiments/clean-ranking-v1/prepared/evaluation_labels.json')
def parse(item):
    index=item.get('predicted_best_index')
    if type(index) is str and index in ('0','1'):index=int(index)
    if type(index) is not int or index not in (0,1):index=None
    try:
        raw=item.get('confidence',.5);assert type(raw) is not bool
        c=float(raw);assert math.isfinite(c) and 0<=c<=1
    except (AssertionError,TypeError,ValueError):c=0.;index=None
    return (item['order'][index] if index is not None and c>=.7 else None),c
def fold(task,pair):return hashlib.sha256((task+'\x1f'+pair).encode()).digest()[-1]%4
opportunity=load(OUT/'fold_opportunity.json')
for n,bank in banks.items():
    counts={a+str(f):Counter() for a in ('D','A') for f in range(4)}
    for task,table in bank.items():
        for pair,item in table.items():
            a,b=item['order'];ow,oc=parse(item);strict=labels[task][a]!=labels[task][b]
            truth=(a if labels[task][a]>labels[task][b] else b) if strict else None
            for arm in ('D','A'):
                for f in range(4):
                    c=counts[arm+str(f)];eligible=fold(task,pair)==f
                    target=eligible and strict and ((ow is not None) if arm=='D' else ow is None)
                    c['all_pair_addresses']+=1;c['eligible_addresses']+=eligible
                    c['eligible_target_addresses']+=target;c['altered_addresses']+=target and ow!=truth
                    c['eligible_true_tie_addresses']+=eligible and not strict
            checks['independent_label_free_fold_and_opportunity_pairs']+=1
    for key,c in counts.items():assert dict(c)==opportunity[n][key]
original={}
with gzip.open(ROOT/'experiments/clean-ranking-v1/results/decisions.jsonl.gz','rt') as stream:
    for line in stream:
        r=json.loads(line)
        if r['method']=='corrected_tournament':original[('DS1',r['job_id'])]={k:r[k] for k in ('selected','trace','stats')}
for p in (HERE.parent/'c0-final-selection/run-002/decisions.sealed.jsonl.gz',HERE.parent/'deepseek-transfer/run_1/decisions.sealed.jsonl.gz'):
    with gzip.open(p,'rt') as stream:
        for line in stream:
            r=json.loads(line)
            if r['bank']=='DS':continue
            original[(r['bank'],r['job_id'])]={'selected':r['selected']['C'],'trace':r['trace'],'stats':r['stats']}
scores={}
with gzip.open(OUT/'per_fold_scores.jsonl.gz','rt') as stream:
    for line in stream:
        r=json.loads(line);scores[(r['bank'],r['job_id'],r['arm'],r['fold'])]=r['metrics']
byjob=defaultdict(dict);bank_hash={n:hashlib.sha256() for n in banks};costs=defaultdict(Counter)
with gzip.open(OUT/'decisions.oracle.jsonl.gz','rt') as stream:
    for line in stream:
        r=json.loads(line);n=r['bank'];job=jobs[r['job_id']];task=job['task'];arm=r['arm'];f=r['fold']
        bank_hash[n].update(line.encode())
        raw={k:v for k,v in r.items() if k!='decision_sha256'}
        assert hashlib.sha256(json.dumps(raw,sort_keys=True,separators=(',',':')).encode()).hexdigest()==r['decision_sha256']
        exposure=Counter();seen=set()
        for e in r['trace']:
            a,b=e['a'],e['b'];pair='|'.join(sorted((a,b)));assert pair not in seen;seen.add(pair)
            item=banks[n][task][pair];ow,oc=parse(item);ew,ec=ow,oc
            if arm!='O':
                eligible=fold(task,pair)==f;strict=labels[task][a]!=labels[task][b]
                truth=(a if labels[task][a]>labels[task][b] else b) if strict else None
                target=eligible and strict and ((ow is not None) if arm=='D' else ow is None)
                changed=target and ow!=truth
                if changed:ew=truth;ec=oc if arm=='D' else .7
                exposure['eligible_queried']+=eligible;exposure['target_queried']+=target
                exposure['altered_queried']+=changed;exposure['accepted_queried']+=ew is not None
            assert e['winner']==ew;near(e['confidence'],ec)
            assert e['source_group_index']==item['source_group_index']
            checks['independent_oracle_queried_direction_confidence']+=1
        assert len(seen)==r['stats']['unique_feedback_reads']<=job['budget']
        if arm=='O':
            old=original[(n,r['job_id'])]
            assert all(r[k]==old[k] for k in ('selected','trace','stats'))
            checks['original_control_exact']+=1
        else:
            for k,v in exposure.items():assert v==r['exposure'][k]
        gold=labels[task];hi=max(gold[i] for i in job['ids']);lo=min(gold[i] for i in job['ids'])
        regret=0 if hi==lo else sum((hi-gold[i])/(hi-lo) for i in r['selected'])/len(r['selected'])
        hit=sum(gold[i]==hi for i in r['selected'])/len(r['selected'])
        target=scores[(n,r['job_id'],arm,f)];near(regret,target['regret']);near(hit,target['best_hit'])
        for k,v in r['stats'].items():near(v,target[k])
        for k in ('eligible_queried','target_queried','altered_queried'):near(exposure[k],target[k])
        byjob[(n,r['job_id'])][(arm,f)]=target
        costs[(n,arm)].update(r['stats']);costs[(n,arm)]['selection_runs']+=1
        costs[(n,arm)]['altered_queried']+=exposure['altered_queried']
        checks['independent_selection_scores']+=1
for n,h in bank_hash.items():assert h.hexdigest()==receipt['bank_decision_sha256'][n]
reported={}
for line in (OUT/'per_episode_fold_averaged.jsonl').read_text().splitlines():
    r=json.loads(line);reported[(r['bank'],r['job_id'])]=r
grouped=defaultdict(list)
for (n,jid),table in byjob.items():
    expected={('O',None)}|{(a,f) for a in ('D','A') for f in range(4)};assert set(table)==expected
    task=jobs[jid]['task'];r=reported[(n,jid)];metrics={}
    for arm in ('O','D','A'):
        records=[table[(arm,f)] for f in ([None] if arm=='O' else range(4))]
        mean={m:math.fsum(v[m] for v in records)/len(records) for m in records[0]}
        for m,v in mean.items():near(v,r['metrics'][arm][m])
        metrics[arm]=mean;grouped[(n,task,arm)].append(mean)
    near(metrics['O']['regret']-metrics['D']['regret'],r['g_D'])
    near(metrics['O']['regret']-metrics['A']['regret'],r['g_A'])
    near(metrics['A']['regret']-metrics['D']['regret'],r['g_D_minus_g_A'])
    checks['four_fold_job_averages']+=1
taskdata={n:{t:{a:{m:math.fsum(v[m] for v in grouped[(n,t,a)])/len(grouped[(n,t,a)]) for m in grouped[(n,t,a)][0]}
                   for a in ('O','D','A')} for t in sorted(bank)} for n,bank in banks.items()}
saved=load(OUT/'per_task.json')
for n,data in taskdata.items():
    for t in data:
        for a in data[t]:
            for m,v in data[t][a].items():near(v,saved['by_bank'][n][t][a][m]);checks['task_metrics']+=1
fulltasks=sorted(banks['DS1']);common=summary['common_tasks']
def pooled(names,tasks):return {t:{a:{m:math.fsum(taskdata[n][t][a][m] for n in names)/len(names) for m in taskdata[names[0]][t][a]}
                                 for a in ('O','D','A')} for t in tasks}
full={**taskdata,'GPT_task_first_pooled':pooled(list(gpt),fulltasks)}
common_data={n:{t:data[t] for t in common} for n,data in full.items()}
common_data['DS0_task_first_pooled']=pooled(list(ds0),common)
def quantile(samples,q):
    x=(len(samples)-1)*q;l=int(x);f=x-l
    return samples[l]*(1-f)+samples[min(l+1,len(samples)-1)]*f
for group,data in [('summaries',full),('common_10_summaries',common_data)]:
    for n,table in data.items():
        tasks=sorted(table);target=summary[group][n];nt=len(tasks)
        for a in ('O','D','A'):
            for m in table[tasks[0]][a]:near(math.fsum(table[t][a][m] for t in tasks)/nt,target['macro'][a][m])
        for name,(a,b) in {'O_minus_D':('O','D'),'O_minus_A':('O','A'),'A_minus_D':('A','D')}.items():
            for m in ('regret','best_hit'):
                values=[(table[t][a][m]-table[t][b][m])*(1 if m=='regret' else -1) for t in tasks]
                result=target['contrasts'][name][m];near(math.fsum(values)/nt,result['gain'])
                for i,t in enumerate(tasks):near((math.fsum(values)-values[i])/(nt-1),result['leave_one_task_out'][t])
                rng=random.Random(20261108093)
                samples=sorted(math.fsum(values[int(rng.random()*nt)] for _ in range(nt))/nt for _ in range(10000))
                for q,v in zip((.025,.975),result['ci95']):near(quantile(samples,q),v)
                checks['independent_task_bootstrap_leave_one_contrasts']+=1
result={'status':'passed','checks':dict(checks),'summary_sha256':sha(OUT/'summary.json'),
        'script_sha256':sha(__file__),'elapsed_seconds':time.monotonic()-start,
        'method':'independent raw parser, digest-byte fold, oracle eligibility and direction reconstruction, direct scoring, fold-first/task-first averaging and random-index bootstrap',
        'oracle_boundary':'No deployment claim; gold is explicitly evaluator-side. Frozen C0 label file access was denied during main select calls.'}
(DEST/'actual_total_costs.json').write_text(json.dumps({n:{a:dict(costs[(n,a)]) for a in ('O','D','A')} for n in banks},indent=2)+'\n')
(DEST/'receipt.json').write_text(json.dumps(result,indent=2)+'\n')
(DEST/'hashes.json').write_text(json.dumps({p.name:sha(p) for p in DEST.iterdir() if p.is_file() and p.name!='hashes.json'},indent=2)+'\n')
print(json.dumps(result,indent=2))
