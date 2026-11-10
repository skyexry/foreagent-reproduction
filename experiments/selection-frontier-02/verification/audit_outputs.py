"""Independent output audit of opponents, second opinion and actual-C0 budget."""
from collections import Counter, defaultdict
from fractions import Fraction
import gzip
import hashlib
import itertools
import json
import math
from pathlib import Path
import random
import statistics
import sys
import time

import numpy as np

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT))
from reproduction.clean_ranking_v1.loader import load_world
from reproduction.clean_ranking_v1.run import select

HERE=Path(__file__).resolve().parent
E=HERE.parent


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def read(p):return json.loads(p.read_text())


def gzlines(p):
    with gzip.open(p,'rt') as f:return [json.loads(x) for x in f]


def close(a,b):assert abs(a-b)<1e-10,(a,b)


def parse(item):
    i=item.get('predicted_best_index')
    if type(i) is str and i in ('0','1'):i=int(i)
    if type(i) is not int or i not in (0,1):i=None
    raw=item.get('confidence',.5)
    try:
        assert type(raw) is not bool
        c=float(raw);assert math.isfinite(c) and 0<=c<=1
    except (AssertionError,ValueError,TypeError):i,c=None,0.
    return item['order'][i] if i is not None else None,c


def legacy(ids,feedback):
    wins=dict.fromkeys(ids,0);degree=dict.fromkeys(ids,0)
    for a,b,w in feedback:
        if w is not None:wins[w]+=1;degree[a]+=1;degree[b]+=1
    keys={i:((Fraction(wins[i],degree[i]) if degree[i] else Fraction(1,2)),degree[i]) for i in ids}
    best=max(keys.values());return [i for i in ids if keys[i]==best]


def gaussian(matrix,rhs):
    a=[list(row)+[v] for row,v in zip(matrix,rhs)];n=len(rhs)
    for k in range(n):
        pivot=max(range(k,n),key=lambda i:abs(a[i][k]));a[k],a[pivot]=a[pivot],a[k]
        for i in range(k+1,n):
            q=a[i][k]/a[k][k]
            for j in range(k,n+1):a[i][j]-=q*a[k][j]
    answer=[0 for _ in rhs]
    for k in range(n-1,-1,-1):answer[k]=(a[k][n]-sum(a[k][j]*answer[j] for j in range(k+1,n)))/a[k][k]
    return answer


def ranks(ids,edges,bank,exact=False):
    index={x:i for i,x in enumerate(ids)};n=len(ids);parsed=[];hard=[]
    for a,b in edges:
        winner,c=parse(bank['|'.join(sorted((a,b)))])
        hard.append((a,b,winner if c>=.7 else None))
        if winner is not None:parsed.append((winner,b if winner==a else a,c))
    selections={'legacy':legacy(ids,hard)};scores_out={}
    for setting in ('hard','soft'):
        weights=[[Fraction(0) if exact else 0. for _ in ids] for _ in ids]
        for winner,loser,c in parsed:
            weight=int(c>=.7) if setting=='hard' else max(Fraction(0),2*Fraction(str(c))-1) if exact else max(0.,2*c-1)
            weights[index[winner]][index[loser]]+=weight
        both=[[weights[i][j]+weights[j][i] for j in range(n)] for i in range(n)]
        total=[sum(row) for row in both];wins=[sum(row) for row in weights]
        degree=[sum(x>0 for x in row) for row in both]
        matrix=[[(2+total[i]) if i==j else -both[i][j] for j in range(n)] for i in range(n)]
        rhs=[1+wins[i]-total[i]/2 for i in range(n)]
        if exact:rhs=[Fraction(1)+wins[i]-total[i]/2 for i in range(n)]
        colley=gaussian(matrix,rhs)
        shrink=[(1+wins[i])/(2+total[i]) for i in range(n)]
        for name,scores in [('shrink',shrink),('colley',colley)]:
            top=max(scores);tied=[i for i in range(n) if abs(float(scores[i]-top))<=1e-12]
            best_degree=max(degree[i] for i in tied)
            selections[setting+'_'+name]=[ids[i] for i in tied if degree[i]==best_degree]
            scores_out[setting+'_'+name]=[float(s) for s in scores]
        for i in range(n):close(float(sum(matrix[i][j]*colley[j] for j in range(n))),float(rhs[i]))
    return selections,scores_out


def score(job,selected,labels):
    u=labels[job['task']];hi=max(u[i] for i in job['ids']);lo=min(u[i] for i in job['ids'])
    return [statistics.fmean((hi-u[i])/(hi-lo) if hi>lo else 0. for i in selected),sum(u[i]==hi for i in selected)/len(selected)]


def describe(values,target,draws):
    values=np.array(values);close(float(values.mean()),target['gain'])
    boot=np.mean(values[draws],axis=1)
    for computed,reported in zip(np.quantile(boot,[.025,.975]),target['ci95']):close(float(computed),reported)
    if 'min_leave_one' in target:close(float(((values.sum()-values)/(len(values)-1)).min()),target['min_leave_one'])


def main():
    start=time.monotonic();checks=Counter();sources={};bank_paths={'DS':ROOT/'experiments/clean-ranking-v1/prepared/feedback.json'}
    for manifest in [E/'banks/manifest.json',E/'deepseek-transfer/banks_1/manifest.json']:
        for name,meta in read(manifest)['banks'].items():
            p=ROOT/meta['path'];assert sha(p)==meta['sha256'];bank_paths[name]=p
    banks={}
    ds=read(bank_paths['DS'])
    for name,p in bank_paths.items():
        data=json.loads(gzip.decompress(p.read_bytes())) if p.suffix=='.gz' else read(p)
        for task,pairs in data.items():
            assert set(pairs)==set(ds[task])
            for key,item in pairs.items():
                assert sorted(item['order'])==key.split('|')
                assert {'order','predicted_best_index','confidence','source_group_index'}<=set(item)
                assert set(item)<={'order','predicted_best_index','confidence','source_group_index','source_row','missing_source_pair'}
                assert item.get('missing_source_pair',False) is False
                assert item['source_group_index']==ds[task][key]['source_group_index']
                checks['bank_records_schema_order_pair_checked']+=1
        banks[name]=data;sources[str(p.relative_to(ROOT))]=sha(p)
    assert len(banks)==6
    prepared=ROOT/'experiments/clean-ranking-v1/prepared'
    jobs={j['job_id']:j for line in (prepared/'jobs.jsonl').read_text().splitlines() if (j:=json.loads(line))}
    labels=read(prepared/'evaluation_labels.json');tasks=sorted(labels)
    history=gzlines(ROOT/'experiments/clean-ranking-v1/results/decisions.jsonl.gz')
    schedules={(r['method'],r['job_id']):[(e['a'],e['b']) for e in r['trace']] for r in history}
    old_choices={(r['method'],r['job_id']):r['selected'] for r in history}
    full={}
    for path in [E/'c0-final-selection/run-002/decisions.sealed.jsonl.gz',E/'deepseek-transfer/run_1/decisions.sealed.jsonl.gz']:
        for row in gzlines(path):full[(row['bank'],row['job_id'])]=row
        sources[str(path.relative_to(ROOT))]=sha(path)
    for key,job in jobs.items():
        rng=random.Random(job['seed']);chain=list(job['ids']);rng.shuffle(chain)
        chain=[tuple(sorted(p)) for p in zip(chain,chain[1:])]
        unseen=set(tuple(sorted(p)) for p in itertools.combinations(job['ids'],2));edges=[]
        for step in range(job['budget']):
            edge=chain[step] if step<len(chain) else rng.choice(sorted(unseen))
            edges.append(edge);unseen.remove(edge)
        assert edges==[tuple(p) for p in schedules[('coverage_random',key)]]
        checks['label_free_full_control_schedule_rebuilt']+=1
    rng=random.Random(20261108093);draws=np.array([rng.choices(range(26),k=26) for _ in range(10000)])
    print('banks and all control schedules verified',flush=True)
    # Opponent adjustment: independent pure-Python Gaussian solver on every graph,
    # plus exact rational arithmetic for a small predetermined sample.
    run=E/'opponents/run_1';seal=read(run/'seal.json');assert sha(run/'sealed.jsonl.gz')==seal['hash']
    assert sha(run/'experiment.snapshot.py')==seal['script'];assert sha(E/'opponents/protocol.json')==seal['protocol']
    for name,digest in seal['banks'].items():assert sha(bank_paths[name])==digest
    rows=gzlines(run/'sealed.jsonl.gz');grouped=defaultdict(list);exact_samples=[]
    sample_jobs=set(list(jobs)[:2])
    for name,schedule,key,reads,selected in rows:
        job=jobs[key];edges=schedules[(schedule,key)]
        assert reads==len(edges)==len(set(tuple(sorted(p)) for p in edges))<=job['budget']
        actual,values=ranks(job['ids'],edges,banks[name][job['task']])
        assert actual==selected,(name,schedule,key,actual,selected)
        checks['opponent_all_rankers_independently_rebuilt']+=1
        if key in sample_jobs:
            rational,exact_values=ranks(job['ids'],edges,banks[name][job['task']],exact=True)
            assert rational==selected
            for method,scores in values.items():
                for x,y in zip(scores,exact_values[method]):close(x,y)
            exact_samples.append(dict(bank=name,schedule=schedule,job_id=key,scores=exact_values))
        if name=='DS' and schedule!='corrected_tournament':assert selected['legacy']==old_choices[(schedule,key)]
        for method,picked in selected.items():grouped[(name,schedule,method,job['task'])].append(score(job,picked,labels))
        grouped[(name,schedule,'actual_c0',job['task'])].append(score(job,old_choices[('corrected_tournament',key)],labels))
    means={key:np.mean(value,axis=0) for key,value in grouped.items()}
    results=read(run/'final_info.json')['results']
    methods=['legacy','hard_shrink','hard_colley','soft_shrink','soft_colley']
    contrasts=[('hard_shrink','hard_colley'),('legacy','hard_colley'),('hard_colley','soft_colley'),
        ('legacy','soft_colley'),('soft_shrink','soft_colley'),('hard_shrink','soft_shrink'),('actual_c0','hard_colley'),('actual_c0','soft_colley')]
    for group,value in results.items():
        name,schedule=group.split('/');members=[b for b in banks if b.startswith('gpt')] if name=='GPT_pooled' else [name]
        def metric(method,task,i):return statistics.fmean(means[(b,schedule,method,task)][i] for b in members)
        for method in methods:
            close(statistics.fmean(metric(method,t,0) for t in tasks),value['means'][method]['regret'])
            close(statistics.fmean(metric(method,t,1) for t in tasks),value['means'][method]['hit'])
        for old,new in contrasts:
            target=value['gains'].get(new+'_over_'+old)
            if target is None:continue
            describe([metric(old,t,0)-metric(new,t,0) for t in tasks],target,draws);checks['opponent_effect_and_CI_recomputed']+=1
        describe([(metric('soft_shrink',t,0)-metric('soft_colley',t,0))-(metric('hard_shrink',t,0)-metric('hard_colley',t,0)) for t in tasks],value['gains']['interaction'],draws)
        checks['opponent_effect_and_CI_recomputed']+=1
    sources[str((run/'sealed.jsonl.gz').relative_to(ROOT))]=sha(run/'sealed.jsonl.gz')
    print('all opponent ranks, exact samples, scores and intervals verified',flush=True)
    # Second opinion: reconstruct each primary/backup call and the sacrificed
    # novel suffix explicitly; source-bank identity makes revisits real evidence.
    run=E/'second-opinion/run_1';seal=read(run/'seal.json');assert sha(run/'selections.jsonl.gz')==seal['sha256']
    assert sha(run/'experiment.snapshot.py')==seal['script'];grouped=defaultdict(list);call_totals=Counter()
    for first,backup,key,selected,revisits,rescued in gzlines(run/'selections.jsonl.gz'):
        job=jobs[key];edges=schedules[('coverage_random',key)];split=len(job['ids'])-1;B=job['budget']
        answers=[]
        for a,b in edges:
            w,c=parse(banks[first][job['task']]['|'.join(sorted((a,b)))]);answers.append(w if c>=.7 else None)
        planned=[i for i in range(split) if answers[i] is None][:B-split]
        keep=B-len(planned);assert keep>=split
        assert len(planned)==revisits and first!=backup
        used=[(first,tuple(sorted(p))) for p in edges[:keep]]
        repaired=answers[:keep];sham=answers[:keep]
        for i in planned:
            edge=edges[i];used.append((backup,tuple(sorted(edge))))
            w,c=parse(banks[backup][job['task']]['|'.join(sorted(edge))]);repaired[i]=w if c>=.7 else None
        assert len(used)==len(set(used))==B
        assert sum(repaired[i] is not None for i in planned)==rescued
        choices={'new':legacy(job['ids'],[(a,b,w) for (a,b),w in zip(edges,answers)]),
                 'sham':legacy(job['ids'],[(a,b,w) for (a,b),w in zip(edges,sham)]),
                 'backup':legacy(job['ids'],[(a,b,w) for (a,b),w in zip(edges,repaired)])}
        assert selected==choices
        if first=='DS':assert selected['new']==old_choices[('coverage_random',key)]
        for arm,picked in choices.items():
            for group in [first+'+'+backup,'DS_first' if first=='DS' else 'GPT_first']:
                grouped[(group,job['task'],arm)].append(score(job,picked,labels)+[revisits,rescued,B])
        checks['second_opinion_full_call_selection_reconstruction']+=1
        call_totals['backup_reads']+=revisits;call_totals['sacrificed_novel_pairs']+=B-keep
        call_totals['rescued_primary_abstentions']+=rescued;call_totals['total_logical_reads']+=B
    reported=read(run/'final_info.json')['comparisons']
    for name,value in reported.items():
        arrays={arm:np.stack([np.mean(grouped[(name,t,arm)],axis=0) for t in tasks]) for arm in ['new','sham','backup']}
        for arm in arrays:
            for i,metric in enumerate(['regret','hit','planned_revisits','rescued','total_calls']):close(float(arrays[arm][:,i].mean()),value['means'][arm][metric])
        for old,new in [('new','backup'),('new','sham'),('sham','backup')]:
            describe(arrays[old][:,0]-arrays[new][:,0],value[new+'_over_'+old],draws);checks['second_opinion_effect_and_CI_recomputed']+=1
    sources[str((run/'selections.jsonl.gz').relative_to(ROOT))]=sha(run/'selections.jsonl.gz')
    print('second-opinion calls, sacrifices, outcomes and intervals verified',flush=True)
    # Budget: fresh original-C0 replay of every short cap, then exact prefix check.
    run=E/'c0-budget/run_1';seal=read(run/'seal.json');assert sha(run/'selections.jsonl.gz')==seal['hash']
    assert sha(run/'experiment.snapshot.py')==seal['script'];grouped=defaultdict(lambda:defaultdict(list));module=load_world()
    code={t:{i:(ROOT/p).read_text() for i,p in files.items()} for t,files in read(prepared/'code_files.json').items()}
    population=Counter()
    for bank,key,short,full_choice,short_count,full_count in gzlines(run/'selections.jsonl.gz'):
        job=jobs[key];reduced=dict(job,budget=min(job['budget'],len(job['ids'])-1))
        fullrow=full[(bank,key)];assert full_choice==fullrow['selected']['C'] and full_count==len(fullrow['trace'])
        selected,trace,stats=select(module,reduced,banks[bank][job['task']],{i:code[job['task']][i] for i in job['ids']},'corrected_tournament',.7)
        assert short==selected and short_count==len(trace)<=reduced['budget']
        assert trace==fullrow['trace'][:len(trace)]
        assert len(trace)==len({tuple(sorted((r['a'],r['b']))) for r in trace})
        a=score(job,short,labels);b=score(job,full_choice,labels)
        vector=[a[0]-b[0],full_count-short_count,a[1]-b[1],a[0],b[0],short_count,full_count]
        grouped[bank][job['task']].append(vector)
        if bank.startswith('gpt'):grouped['GPT_pooled'][job['task']].append(vector)
        population[bank]+=1;checks['short_C0_replay_and_prefix_exact']+=1
    result=read(run/'final_info.json')['banks'];metrics=['regret_deterioration','read_savings','hit_change','short_regret','full_regret','short_reads','full_reads']
    for bank,by_task in grouped.items():
        names=sorted(by_task);values=np.stack([np.mean(by_task[t],axis=0) for t in names]);rng=random.Random(20261108093)
        samples=np.array([rng.choices(range(len(names)),k=len(names)) for _ in range(10000)])
        expected=np.quantile(values[samples].mean(axis=1),[.025,.975],axis=0)
        for i,metric in enumerate(metrics):
            close(float(values[:,i].mean()),result[bank][metric]['mean'])
            for a,b in zip(expected[:,i],result[bank][metric]['ci']):close(float(a),b)
            checks['budget_effect_and_CI_recomputed']+=1
    sources[str((run/'selections.jsonl.gz').relative_to(ROOT))]=sha(run/'selections.jsonl.gz')
    print('all six-bank short-C0 executions and intervals verified',flush=True)
    payload=dict(status='passed',checks=dict(checks),bank_population=dict(population),second_opinion_logical_calls=dict(call_totals),
        exact_colley_samples=exact_samples,input_sha256=sources,script_sha256=sha(Path(__file__)),wall_seconds=time.monotonic()-start,
        scope='read-only audit of sealed outputs and six feedback banks; no hypothesis, method, labels or experiment files changed; sham matched calls are nominal attribution costs as registered')
    (HERE/'receipt.json').write_text(json.dumps(payload,sort_keys=True,indent=2)+'\n')
    print(json.dumps({k:v for k,v in payload.items() if k not in ['input_sha256','exact_colley_samples']}),flush=True)


if __name__=='__main__':main()
