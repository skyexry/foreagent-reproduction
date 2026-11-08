"""Explicitly posthoc diagnostics; never modifies the locked methods or main result."""
from collections import defaultdict
import gzip
import json
from pathlib import Path
import statistics

from .data import ROOT, dump


def diagnose(experiment):
    e=Path(experiment)
    labels=json.loads((e/'prepared/evaluation_labels.json').read_text())
    jobs={j['job_id']:j for j in map(json.loads,(e/'prepared/jobs.jsonl').read_text().splitlines())}
    summary=json.loads((e/'results/summary.json').read_text())
    counts=defaultdict(lambda:dict(reads=0,valid=0,correct_valid=0,extra_reads=0,extra_valid=0,extra_correct=0))
    petfinder=[]
    with gzip.open(e/'results/decisions.jsonl.gz','rt') as stream:
        for line in stream:
            r=json.loads(line);j=jobs[r['job_id']];y=labels[r['task']];c=counts[r['method']]
            for index,t in enumerate(r['trace']):
                c['reads']+=1
                valid=t['winner'] is not None
                correct=valid and y[t['winner']]==max(y[t['a']],y[t['b']])
                c['valid']+=valid;c['correct_valid']+=correct
                if r['method'].startswith('coverage_') and index>=len(j['ids'])-1:
                    c['extra_reads']+=1;c['extra_valid']+=valid;c['extra_correct']+=correct
            if r['task']=='petfinder-pawpularity-score':
                petfinder.append(dict(method=r['method'],job=r['job_id'],selected=r['selected'],
                    regret=r['metrics']['regret'],best_hit=r['metrics']['best_hit'],trace=r['trace']))
    for c in counts.values():
        c['valid_feedback_accuracy']=c['correct_valid']/c['valid'] if c['valid'] else None
        c['extra_valid_accuracy']=c['extra_correct']/c['extra_valid'] if c['extra_valid'] else None
    deltas={t:v['coverage_decision_sensitive']['regret']-v['corrected_tournament']['regret']
            for t,v in summary['per_task'].items()}
    meta=json.loads((e/'prepared/source_manifest.json').read_text())['exclusions']
    ten=[t for t in deltas if meta[t]['candidate_count']==10]
    result=dict(scope='Posthoc mechanism and sensitivity diagnostics; retain all 26 tasks as the primary result.',
        pooled_read_statistics=dict(counts),note='Reads share pairs, candidates and tasks; counts are not independent observations.',
        task_regret_deltas=deltas,
        largest_increases=sorted(deltas.items(),key=lambda x:x[1],reverse=True)[:5],
        leave_petfinder_out_delta=statistics.fmean(v for t,v in deltas.items() if t!='petfinder-pawpularity-score'),
        ten_candidate_task_count=len(ten),ten_candidate_only_delta=statistics.fmean(deltas[t] for t in ten),
        petfinder=petfinder,
        hypotheses=['Decision sensitivity need not imply expected utility gain.',
                    'Adaptive opponent/degree selection may bias raw win-rate aggregation.',
                    'One admitted Petfinder pool has high task-macro influence; broader coverage is needed.'],
        confirmed_causal_explanation=False)
    dump(e/'results/diagnostics.json',result)
    return result


if __name__=='__main__':
    r=diagnose(ROOT/'experiments/clean-ranking-v1')
    print(json.dumps({k:r[k] for k in ['pooled_read_statistics','largest_increases','leave_petfinder_out_delta','ten_candidate_task_count','ten_candidate_only_delta']},indent=2))
