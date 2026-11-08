"""Fresh fixed-feedback comparison. Reads no historical experiment artifacts."""
import argparse
from collections import defaultdict
import csv
import gzip
import hashlib
import json
import math
from pathlib import Path
import random
import statistics
import time
import types

from .correctness import response_values
from .data import ROOT, dump, digest
from .loader import load_world

EXPERIMENT = ROOT/'experiments/clean-ranking-v1'


class ReplayBank:
    def __init__(self, bank, budget, threshold):
        self.bank, self.budget, self.threshold = bank, budget, threshold
        self.ledger = []
        self.denied = 0
    def query(self, **kwargs):
        a, b = json.loads(kwargs['user_message'])
        if len(self.ledger) >= self.budget:
            self.denied += 1
            return '{"predicted_best_index":null,"confidence":0.0}'
        item = self.bank['|'.join(sorted((a, b)))]
        index, confidence = response_values(dict(predicted_best_index=item['predicted_best_index'],
                                                 confidence=item['confidence']))
        winner = item['order'][index] if index is not None else None
        mapped = (a, b).index(winner) if winner is not None else None
        valid_winner = winner if winner is not None and confidence >= self.threshold else None
        self.ledger.append(dict(a=a, b=b, winner=valid_winner, confidence=confidence,
                                source_group_index=item['source_group_index']))
        return json.dumps(dict(predicted_best_index=mapped, confidence=confidence))


def select(module, job, bank, code, method, threshold):
    broker = ReplayBank(bank, job['budget'], threshold)
    code_identity = {value: key for key, value in code.items()}
    if len(code_identity) != len(code):
        raise ValueError('Candidate pool must have distinct code contents')
    # Offline transport only: same corrected cache/tournament, frozen source
    # judgments instead of live API generation. Original prompt remains on disk.
    module.build_pairwise_prompt = lambda **kw: json.dumps([code_identity[kw['code_a']], code_identity[kw['code_b']]])
    module.query = broker.query
    module.random = random.Random(job['seed'])
    model = module.WorldModel('offline task '+job['task'], 'identity-only transport',
        task_name=job['task'], config=module.WorldModelConfig(confidence_threshold=threshold,
        max_concurrent_requests=1, selection_policy='original' if method == 'corrected_tournament' else method,
        comparison_budget=job['budget'], selection_seed=job['seed']))
    nodes = [types.SimpleNamespace(id=i, code=code[i]) for i in job['ids']]
    ranked, comparisons, meta = model.tournament_rank(nodes)
    top = [n.id for n in ranked if meta[n.id]['rank'] == 0]
    if not top:
        raise ValueError('Empty selection')
    stats = dict(unique_feedback_reads=len(broker.ledger), budget_denials=broker.denied,
                 comparison_records=len(comparisons),
                 cache_reads=max(0, len(comparisons)-len(broker.ledger)-broker.denied))
    return top, broker.ledger, stats


def evaluate(ids, selected, utility):
    best = max(utility[i] for i in ids)
    worst = min(utility[i] for i in ids)
    regret = statistics.fmean((best-utility[i])/(best-worst) if best != worst else 0 for i in selected)
    hit = sum(utility[i] == best for i in selected)/len(selected)
    return dict(regret=regret, best_hit=hit)


def percentile(values, q):
    values = sorted(values)
    index = (len(values)-1)*q
    lo = int(index)
    hi = min(lo+1, len(values)-1)
    return values[lo]*(hi-index) + values[hi]*(index-lo) if lo != hi else values[lo]


def summarize(rows, protocol):
    grouped = defaultdict(list)
    for row in rows:
        grouped[(row['task'], row['method'])].append(row)
    metrics = ('regret', 'best_hit', 'unique_feedback_reads', 'cache_reads', 'budget_denials')
    per_task = {t: {m: {k: statistics.fmean(r['metrics'][k] for r in grouped[(t, m)])
                           for k in metrics} for m in protocol['methods']}
                for t in sorted({r['task'] for r in rows})}
    macro = {m: {k: statistics.fmean(t[m][k] for t in per_task.values()) for k in metrics}
             for m in protocol['methods']}
    contrasts = {}
    for control, method in [tuple(protocol['primary_comparison']), tuple(protocol['mechanism_control'])]:
        name = method+' minus '+control
        contrasts[name] = {}
        for metric in ('regret', 'best_hit'):
            deltas = [t[method][metric]-t[control][metric] for t in per_task.values()]
            rng = random.Random(protocol['bootstrap_seed'])
            samples = [statistics.fmean(rng.choices(deltas, k=len(deltas)))
                       for _ in range(protocol['bootstrap_repeats'])]
            contrasts[name][metric] = dict(delta=statistics.fmean(deltas),
                task_cluster_95=[percentile(samples, .025), percentile(samples, .975)],
                tasks_better=sum(x < -1e-12 if metric == 'regret' else x > 1e-12 for x in deltas),
                tasks_equal=sum(abs(x) < 1e-12 for x in deltas),
                tasks_worse=sum(x > 1e-12 if metric == 'regret' else x < -1e-12 for x in deltas))
    return dict(tasks=len(per_task), jobs=len(rows)//len(protocol['methods']),
                selection_evaluations=len(rows), macro=macro, contrasts=contrasts, per_task=per_task)


def execute(prepared, output):
    protocol = json.loads((EXPERIMENT/'protocol.json').read_text())
    prepared, output = Path(prepared), Path(output)
    if output.exists():
        raise ValueError('Preserve old outputs; choose a new directory')
    lock = json.loads((EXPERIMENT/'implementation-lock.json').read_text())
    for p, h in lock['sha256'].items():
        if digest(ROOT/p) != h:
            raise ValueError('Locked input/source changed: '+p)
    output.mkdir(parents=True)
    start = time.monotonic()
    bank = json.loads((prepared/'feedback.json').read_text())
    paths = json.loads((prepared/'code_files.json').read_text())
    jobs = [json.loads(line) for line in (prepared/'jobs.jsonl').read_text().splitlines()]
    module = load_world()
    pending = []
    for number, job in enumerate(jobs, 1):
        code = {i: (ROOT/paths[job['task']][i]).read_text() for i in job['ids']}
        for method in protocol['methods']:
            selected, trace, stats = select(module, job, bank[job['task']], code, method, protocol['confidence_threshold'])
            pending.append(dict(job_id=job['job_id'], task=job['task'], pool_id=job['pool_id'],
                repeat=job['repeat'], method=method, selected=selected, trace=trace, stats=stats))
        if number % 100 == 0:
            print(f'selected {number}/{len(jobs)} fresh jobs', flush=True)
    # Crucial boundary: all choices are finished before loading evaluation values.
    labels = json.loads((prepared/'evaluation_labels.json').read_text())
    by_id = {j['job_id']: j for j in jobs}
    for row in pending:
        metrics = evaluate(by_id[row['job_id']]['ids'], row['selected'], labels[row['task']])
        row['metrics'] = {**metrics, **row['stats']}
    with gzip.open(output/'decisions.jsonl.gz', 'wt') as stream:
        for row in pending:
            stream.write(json.dumps(row, sort_keys=True)+'\n')
    summary = summarize(pending, protocol)
    summary.update(experiment_id=protocol['id'], elapsed_seconds=time.monotonic()-start,
                   historical_results_used=False, new_model_calls=0, new_full_agent_runs=0,
                   evaluation_scope='Fresh jobs and outputs on previously inspected tasks and one frozen author feedback run.',
                   implementation_lock_sha256=digest(EXPERIMENT/'implementation-lock.json'))
    dump(output/'summary.json', summary)
    with (output/'per_task.csv').open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=['task','method',*next(iter(summary['macro'].values()))])
        writer.writeheader()
        for task, methods in summary['per_task'].items():
            for method, values in methods.items():
                writer.writerow(dict(task=task, method=method, **values))
    return summary


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--prepared', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    result = execute(args.prepared, args.output)
    print(json.dumps({k: result[k] for k in ['tasks','jobs','macro','contrasts']}, indent=2))
