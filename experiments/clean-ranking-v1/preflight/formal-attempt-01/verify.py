"""Independent ledger, decision-sensitivity and metric audit of the new results."""
import argparse
from collections import defaultdict
import gzip
import itertools
import json
import math
from pathlib import Path
import random
import statistics

from .data import ROOT, digest, dump


def independent_top(ids, trace):
    wins = dict.fromkeys(ids, 0); degree = dict.fromkeys(ids, 0)
    for r in trace:
        if r['winner'] is not None:
            degree[r['a']] += 1; degree[r['b']] += 1; wins[r['winner']] += 1
    def greater(a, b):
        wa, da = (wins[a], degree[a]) if degree[a] else (1, 2)
        wb, db = (wins[b], degree[b]) if degree[b] else (1, 2)
        return wa*db > wb*da or (wa*db == wb*da and degree[a] > degree[b])
    best = ids[0]
    for i in ids:
        if greater(i, best):best=i
    return {i for i in ids if not greater(best,i) and not greater(i,best)}


def expected_winner(item, threshold):
    raw=item['predicted_best_index']
    if isinstance(raw,str) and raw in ('0','1'):raw=int(raw)
    confidence=item['confidence']
    try:
        confidence=float(confidence) if not isinstance(confidence,bool) else float('nan')
    except (ValueError,TypeError):confidence=float('nan')
    valid=type(raw) is int and raw in (0,1) and math.isfinite(confidence) and 0<=confidence<=1
    return item['order'][raw] if valid and confidence>=threshold else None


def verify(prepared, output):
    prepared, output=Path(prepared),Path(output)
    protocol=json.loads((ROOT/'experiments/clean-ranking-v1/protocol.json').read_text())
    lock=json.loads((ROOT/'experiments/clean-ranking-v1/implementation-lock.json').read_text())
    for p,h in lock['sha256'].items():assert digest(ROOT/p)==h,p
    sources=json.loads((prepared/'source_manifest.json').read_text())
    for p,h in sources['sha256'].items():assert digest(ROOT/p)==h,p
    assert not sources['historical_R6_R8_artifacts_used']
    jobs={j['job_id']:j for j in map(json.loads,(prepared/'jobs.jsonl').read_text().splitlines())}
    bank=json.loads((prepared/'feedback.json').read_text())
    labels=json.loads((prepared/'evaluation_labels.json').read_text())
    summary=json.loads((output/'summary.json').read_text())
    grouped=defaultdict(list);seen=set();active_checks=0;initial={}
    with gzip.open(output/'decisions.jsonl.gz','rt') as stream:
        for line in stream:
            r=json.loads(line);j=jobs[r['job_id']];ids=j['ids'];trace=r['trace']
            key=(r['job_id'],r['method']);assert key not in seen;seen.add(key)
            assert set(r['selected'])<=set(ids) and r['selected']
            assert len(trace)<=j['budget'];edges=[tuple(sorted((x['a'],x['b']))) for x in trace]
            assert len(set(edges))==len(edges)
            for t in trace:
                expected=bank[j['task']]['|'.join(sorted((t['a'],t['b'])))]
                assert t['winner']==expected_winner(expected,protocol['confidence_threshold'])
                assert t['source_group_index']==expected['source_group_index']
            if r['method']!='corrected_tournament':
                assert len(trace)==j['budget']
                assert set(r['selected'])==independent_top(ids,trace)
            if r['method'].startswith('coverage_'):
                chain=list(ids);random.Random(j['seed']).shuffle(chain)
                prefix=[tuple(sorted(e)) for e in zip(chain,chain[1:])]
                assert edges[:len(prefix)]==prefix
                initial[key]=edges[:len(prefix)]
            if r['method']=='coverage_decision_sensitive':
                remaining={tuple(sorted(e)) for e in itertools.combinations(ids,2)}
                history=[]
                for step,t in enumerate(trace):
                    chosen=edges[step]
                    if step>=len(ids)-1:
                        current=independent_top(ids,history)
                        deg={i:sum(i in (x['a'],x['b']) and x['winner'] is not None for x in history) for i in ids}
                        def priority(edge):
                            a,b=edge
                            p=independent_top(ids,history+[dict(a=a,b=b,winner=a)])
                            q=independent_top(ids,history+[dict(a=a,b=b,winner=b)])
                            tv=sum(abs((1/len(p) if i in p else 0)-(1/len(q) if i in q else 0)) for i in ids)/2
                            return round(tv,12),int(a in current or b in current),-(deg[a]+deg[b])
                        assert priority(chosen)==max(map(priority,remaining))
                        active_checks+=1
                    remaining.remove(chosen);history.append(t)
            utility=labels[r['task']];best=max(utility[i] for i in ids);worst=min(utility[i] for i in ids)
            regret=sum((best-utility[i])/(best-worst) if best>worst else 0 for i in r['selected'])/len(r['selected'])
            hit=sum(utility[i]==best for i in r['selected'])/len(r['selected'])
            assert math.isclose(regret,r['metrics']['regret'],abs_tol=1e-12)
            assert math.isclose(hit,r['metrics']['best_hit'],abs_tol=1e-12)
            assert r['metrics']['unique_feedback_reads']==len(trace)
            grouped[(r['task'],r['method'])].append(dict(regret=regret,best_hit=hit))
    assert len(seen)==len(jobs)*len(protocol['methods'])
    for job_id in jobs:
        assert initial[(job_id,'coverage_random')]==initial[(job_id,'coverage_decision_sensitive')]
    tasks=sorted({j['task'] for j in jobs.values()})
    for method in protocol['methods']:
        for metric in ('regret','best_hit'):
            macro=statistics.fmean(statistics.fmean(x[metric] for x in grouped[(t,method)]) for t in tasks)
            assert math.isclose(macro,summary['macro'][method][metric],abs_tol=1e-12)
    result=dict(status='passed',jobs=len(jobs),selections=len(seen),source_hashes=len(sources['sha256']),
        active_decision_priority_checks=active_checks,labels_used_only_for_scoring=True,
        historical_R6_R8_artifacts_used=False,summary_sha256=digest(output/'summary.json'),
        decisions_sha256=digest(output/'decisions.jsonl.gz'),
        scope='Independent feedback/priority/metric reconstruction; frozen author responses and development tasks only.')
    dump(output/'verification.json',result)
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--prepared',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    args=p.parse_args();print(json.dumps(verify(args.prepared,args.output),indent=2))
