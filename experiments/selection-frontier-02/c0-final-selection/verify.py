"""Independently check sealed directions, selectors, scores and paired task statistics."""
import argparse
from collections import defaultdict
import gzip
import hashlib
import json
import math
from pathlib import Path
import random
import statistics

ROOT=Path(__file__).resolve().parents[3]


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def close(a,b):assert abs(a-b)<1e-11,(a,b)


def independent_top(ids,edges,allowed):
    wins={i:0 for i in ids};degrees={i:0 for i in ids}
    for a,b,w in edges:
        if w is not None:degrees[a]+=1;degrees[b]+=1;wins[w]+=1
    def key(i):return ((wins[i]/degrees[i]) if degrees[i] else .5,degrees[i])
    maximum=max(key(i) for i in allowed)
    return [i for i in allowed if key(i)==maximum]


def quantile(values,q):
    x=(len(values)-1)*q;i=math.floor(x);f=x-i
    return values[i]*(1-f)+values[min(i+1,len(values)-1)]*f


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--run',type=Path,required=True)
    args=ap.parse_args();out=args.run.resolve()
    hashes=json.loads((out/'hashes.json').read_text())
    for p,d in hashes.items():assert sha(out/p)==d,p
    seal=json.loads((out/'selection_seal.json').read_text())
    for p,d in seal['inputs'].items():assert sha(ROOT/p)==d,p
    assert sha(out/'decisions.sealed.jsonl.gz')==seal['decisions_sha256']
    assert sha(out/'experiment.snapshot.py')==seal['script_sha256']
    with gzip.open(out/'decisions.sealed.jsonl.gz','rt') as f:rows=[json.loads(x) for x in f]
    jobs={j['job_id']:j for line in (ROOT/'experiments/clean-ranking-v1/prepared/jobs.jsonl').read_text().splitlines() if (j:=json.loads(line))}
    labels=json.loads((ROOT/'experiments/clean-ranking-v1/prepared/evaluation_labels.json').read_text())
    banks={'DS':json.loads((ROOT/'experiments/clean-ranking-v1/prepared/feedback.json').read_text())}
    bm=json.loads((ROOT/'experiments/selection-frontier-02/banks/manifest.json').read_text())
    for run,meta in bm['banks'].items():banks[run]=json.loads(gzip.decompress((ROOT/meta['path']).read_bytes()))
    episodes={(e['bank'],e['job_id']):e for line in (out/'per_episode.jsonl').read_text().splitlines() if (e:=json.loads(line))}
    with gzip.open(ROOT/'experiments/clean-ranking-v1/results/decisions.jsonl.gz','rt') as f:
        frozen={r['job_id']:r for line in f if (r:=json.loads(line))['method']=='corrected_tournament'}
    grouped=defaultdict(list);checks=defaultdict(int)
    for row in rows:
        digest=row['selection_trace_sha256'];plain={k:v for k,v in row.items() if k!='selection_trace_sha256'}
        assert hashlib.sha256(json.dumps(plain,sort_keys=True,separators=(',',':')).encode()).hexdigest()==digest
        job=jobs[row['job_id']];task=job['task'];bank=banks[row['bank']][task];high=[];low=[]
        seen=set()
        for edge in row['trace']:
            a,b=edge['a'],edge['b'];pair='|'.join(sorted((a,b)));assert pair not in seen;seen.add(pair)
            item=bank[pair];idx=item['predicted_best_index']
            if type(idx) is str and idx in ('0','1'):idx=int(idx)
            if type(idx) is not int or idx not in (0,1):idx=None
            raw=item.get('confidence',.5)
            try:
                assert type(raw) is not bool
                confidence=float(raw)
                assert math.isfinite(confidence) and 0<=confidence<=1
            except (AssertionError,TypeError,ValueError):confidence=0.;idx=None
            expected=item['order'][idx] if idx is not None and confidence>=.7 else None
            assert edge['winner']==expected;close(edge['confidence'],confidence)
            assert edge['source_group_index']==item['source_group_index']
            high.append((a,b,expected));low.append((a,b,item['order'][idx] if idx is not None and confidence>=.5 else None))
        assert len(seen)==row['unique_reads']<=job['budget']
        assert row['low_evidence']==[list(x) for x in low]
        assert row['selected']['H']==independent_top(job['ids'],high,job['ids'])
        assert row['selected']['L']==independent_top(job['ids'],low,job['ids'])
        assert row['selected']['T']==independent_top(job['ids'],low,row['selected']['C'])
        checks['all_alternative_selections_independent']+=1
        if row['bank']=='DS':
            old=frozen[row['job_id']]
            assert row['selected']['C']==old['selected'] and row['trace']==old['trace'] and row['stats']==old['stats']
            checks['frozen_DS_exact']+=1
        utility=labels[task];best=max(utility[i] for i in job['ids']);worst=min(utility[i] for i in job['ids'])
        for arm,selection in row['selected'].items():
            assert selection and len(selection)==len(set(selection)) and set(selection)<=set(job['ids'])
            regret=statistics.fmean((best-utility[i])/(best-worst) if best>worst else 0. for i in selection)
            hit=sum(utility[i]==best for i in selection)/len(selection)
            metric=episodes[(row['bank'],row['job_id'])]['metrics'][arm]
            close(regret,metric['regret']);close(hit,metric['best_hit']);close(metric['unique_reads'],len(seen))
            grouped[(row['bank'],task,arm)].append(dict(regret=regret,best_hit=hit))
            checks['selection_scores_independent']+=1
    tasks=sorted(labels);arms=('C','H','L','T');gpt=[b for b in banks if b!='DS']
    per_task={bank:{task:{arm:{k:statistics.fmean(x[k] for x in grouped[(bank,task,arm)])
            for k in ('regret','best_hit')} for arm in arms} for task in tasks} for bank in banks}
    pooled={task:{arm:{k:statistics.fmean(per_task[b][task][arm][k] for b in gpt)
             for k in ('regret','best_hit')} for arm in arms} for task in tasks}
    reported=json.loads((out/'summary.json').read_text())['summaries']
    comparisons={'C_minus_L':('C','L'),'C_minus_H':('C','H'),'H_minus_L':('H','L'),'L_minus_T':('L','T'),'C_minus_T':('C','T')}
    for bank,data in list(per_task.items())+[('GPT_task_first_pooled',pooled)]:
        summary=reported[bank]
        for arm in arms:
            for k in ('regret','best_hit'):close(summary['macro'][arm][k],statistics.fmean(data[t][arm][k] for t in tasks))
        for name,(a,b) in comparisons.items():
            for key in ('regret','best_hit'):
                deltas=[(data[t][a][key]-data[t][b][key])*(1 if key=='regret' else -1) for t in tasks]
                target=summary['contrasts'][name][key];close(target['gain'],statistics.fmean(deltas))
                for i,t in enumerate(tasks):close(target['leave_one_task_out'][t],statistics.fmean(deltas[:i]+deltas[i+1:]))
                rng=random.Random(20261108093);samples=[]
                for _ in range(10000):samples.append(statistics.fmean(deltas[math.floor(rng.random()*26)] for _ in range(26)))
                samples.sort();close(target['ci95'][0],quantile(samples,.025));close(target['ci95'][1],quantile(samples,.975))
                checks['paired_task_contrasts_CI_LOO_independent']+=1
    result=dict(status='passed',checks=dict(checks),run=str(out.relative_to(ROOT)),verifier_sha256=sha(Path(__file__)),
        implementation='standalone parser, float fraction/degree selector, direct scoring and random-index bootstrap, independent of experiment functions')
    (out/'verification.json').write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')
    print(json.dumps(result))


if __name__=='__main__':main()
