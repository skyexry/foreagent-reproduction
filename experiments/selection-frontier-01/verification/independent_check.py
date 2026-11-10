"""Independent, standard-library-only reanalysis of registered D1/J1."""
import argparse
from collections import Counter, defaultdict
from fractions import Fraction
import gzip
from hashlib import sha256
from itertools import combinations
import json
from math import isclose, isfinite
from pathlib import Path
import random
from statistics import fmean

parser = argparse.ArgumentParser()
parser.add_argument('root', type=Path)
parser.add_argument('out', type=Path)
args = parser.parse_args()
root, out = args.root, args.out
out.mkdir(parents=True, exist_ok=False)
def sha(path):
    return sha256(path.read_bytes()).hexdigest()
def read(path):
    return json.loads(path.read_bytes())
def save(path, value):
    path.write_text(json.dumps(value, sort_keys=True, indent=2, ensure_ascii=False) + '\n')

protocol_path = root/'experiments/selection-frontier-01/protocol.json'
protocol = read(protocol_path)
p = root/'experiments/clean-ranking-v1'
assert all(sha(root/k) == v for k,v in protocol['frozen_sha256'].items())
bank_path = p/'prepared/feedback.json'
bank_hash = sha(bank_path)
assert bank_hash == read(p/'implementation-lock.json')['sha256']['experiments/clean-ranking-v1/prepared/feedback.json']
bank = read(bank_path)
jobs = [json.loads(line) for line in (p/'prepared/jobs.jsonl').open()]
assert len(jobs) == len(set(j['job_id'] for j in jobs)) == 850
assert len(set((j['task'],j['pool_id']) for j in jobs)) == 425
assert len(set(j['task'] for j in jobs)) == 26

methods = ('coverage_random','coverage_decision_sensitive')
fields = ('a','b','winner','confidence','source_group_index')
traces = {m:{} for m in methods}
source = p/'results/decisions.jsonl.gz'
with gzip.open(source,'rt') as stream:
    for line in stream:
        item = json.loads(line)
        m = item['method']
        if m in traces:
            assert item['job_id'] not in traces[m]
            traces[m][item['job_id']] = [tuple(e[k] for k in fields) for e in item['trace']]
for group in traces.values():
    assert group.keys() == {j['job_id'] for j in jobs}

def top(ids, edges):
    score = []
    for code in ids:
        matches = [w for a,b,w,*_ in edges if w is not None and code in (a,b)]
        rate = Fraction(matches.count(code), len(matches)) if matches else Fraction(1,2)
        score.append((rate, len(matches)))
    return [code for code,key in zip(ids,score) if key == max(score)]

def verify_bank(task, edge):
    a,b,w,c,idx = edge
    raw = bank[task]['|'.join(sorted((a,b)))]
    raw_index = raw['predicted_best_index']
    if isinstance(raw_index,str) and raw_index in ('0','1'):
        raw_index = int(raw_index)
    try:
        parsed = float(raw.get('confidence',.5))
        assert not isinstance(raw.get('confidence'), bool) and isfinite(parsed) and 0 <= parsed <= 1
    except (ValueError,TypeError,AssertionError):
        parsed = 0.
        raw_index = None
    valid = type(raw_index) == int and raw_index in (0,1) and parsed >= .7
    assert c == parsed and idx == raw['source_group_index']
    assert w == (raw['order'][raw_index] if valid else None)

sealed = {}
full_sets = {}
for job in jobs:
    jid, ids = job['job_id'],job['ids']
    rng = random.Random(job['seed'])
    chain = ids.copy()
    rng.shuffle(chain)
    pairs = [tuple(sorted(pair)) for pair in zip(chain,chain[1:])]
    seen_prefix = set(pairs)
    n = len(pairs)
    rr,tt = [traces[m][jid] for m in methods]
    assert len(rr) == len(tt) == min(job['budget'], len(ids)*(len(ids)-1)//2)
    assert rr[:n] == tt[:n] and [e[:2] for e in rr[:n]] == pairs
    available = {tuple(sorted(e)) for e in combinations(ids,2)}-seen_prefix
    for e in rr[n:]:
        sampled = rng.choice(sorted(available))
        assert sampled == e[:2]
        available.remove(sampled)
    for edges in (rr,tt):
        assert len({tuple(sorted(e[:2])) for e in edges}) == len(edges)
        assert edges[n][:2] not in seen_prefix
        for e in edges:
            verify_bank(job['task'],e)
    sealed[jid] = {key:top(ids,edges) for key,edges in [('S',rr[:n]),('U',rr[:n+1]),('T',tt[:n+1])]}
    full_sets[jid] = {m:top(ids,traces[m][jid]) for m in methods}
save(out/'prefix-selections.json',sealed)
selected_hash = sha(out/'prefix-selections.json')

labels = read(p/'prepared/evaluation_labels.json')
def values(job, selected):
    u = labels[job['task']]
    hi,lo = max(u[i] for i in job['ids']), min(u[i] for i in job['ids'])
    losses = [(hi-u[i])/(hi-lo) if hi>lo else 0 for i in selected]
    return fmean(losses), fmean(u[i]==hi for i in selected)
# Full historical arms independently reproduce saved selections and metrics.
job_map = {j['job_id']:j for j in jobs}
history = defaultdict(list)
full_history_count = 0
with gzip.open(source,'rt') as stream:
    for line in stream:
        r = json.loads(line)
        jid,method = r['job_id'],r['method']
        if method in methods:
            selection = full_sets[jid][method]
            assert selection == r['selected']
            loss,hit = values(job_map[jid],selection)
            assert isclose(loss,r['metrics']['regret'],abs_tol=1e-14)
            assert hit == r['metrics']['best_hit']
            history[(r['task'],method)].append((loss,hit))
            full_history_count += 1
summary_old = read(p/'results/summary.json')
for (task,method),rows in history.items():
    expected = summary_old['per_task'][task][method]
    assert isclose(fmean(x[0] for x in rows),expected['regret'],abs_tol=1e-14)
    assert isclose(fmean(x[1] for x in rows),expected['best_hit'],abs_tol=1e-14)

def sign(x):
    return 'positive' if x>1e-12 else 'negative' if x< -1e-12 else 'equal'

episodes = defaultdict(list)
counts = Counter()
examples = {}
for j in jobs:
    jid,t = j['job_id'],j['task']
    rr,tt = [traces[m][jid] for m in methods]
    d = {}
    for branch,sel in sealed[jid].items():
        d[branch],d['hit_'+branch] = values(j,sel)
        d['reads_'+branch] = len(j['ids'])-(branch=='S')
    n = len(j['ids'])-1
    counts['same_next_edge'] += rr[n][:2] == tt[n][:2]
    for k,edges in [('U',rr),('T',tt)]:
        gain = d['S']-d[k]
        d['G_'+k]=gain
        d['harm_'+k]=max(0,-gain)
        d['benefit_'+k]=max(0,gain)
        counts['flip_'+k] += sealed[jid]['S'] != sealed[jid][k]
        counts['invalid_'+k] += edges[n][2] is None
    d['T_minus_U']=d['T']-d['U']
    d['D_harm']=d['harm_T']-d['harm_U']
    d['D_missed']=d['benefit_U']-d['benefit_T']
    assert abs(d['T_minus_U'] - d['D_harm'] - d['D_missed'])<1e-12
    u = labels[t]
    repaired=[]
    errors=0
    for a,b,w,c,idx in rr:
        counts['episodes_edges'] += 1
        if w is None:
            counts['invalid_edges'] += 1
        elif u[a] == u[b]:
            counts['tied_valid_edges'] += 1
        else:
            counts['strict_valid_edges'] += 1
            correct = a if u[a]>u[b] else b
            errors += w != correct
            w = correct
        repaired.append((a,b,w,c,idx))
    counts['strict_errors'] += errors
    counts['jobs_with_error'] += errors>0
    original = full_sets[jid][methods[0]]
    fixed = top(j['ids'],repaired)
    counts['J_set_changes'] += original != fixed
    d['J_original'],d['hit_J_original'] = values(j,original)
    d['J_corrected'],d['hit_J_corrected'] = values(j,fixed)
    d['J_gain']=d['J_original']-d['J_corrected']
    d['J_hit_gain']=d['hit_J_corrected']-d['hit_J_original']
    direction = sign(d['J_gain'])
    counts['J_'+direction] += 1
    if direction not in examples:
        examples[direction] = dict(job_id=jid, before=original, after=fixed, direction_errors=errors, original=d['J_original'], corrected=d['J_corrected'])
    episodes[t].append(d)

per_task = {task:{k:fmean(r[k] for r in rows) for k in rows[0]} for task,rows in sorted(episodes.items())}
def estimate(key):
    x = [v[key] for v in per_task.values()]
    rng = random.Random(protocol['fixed']['bootstrap_seed'])
    means = sorted(fmean(rng.choices(x,k=len(x))) for i in range(protocol['fixed']['paired_task_bootstrap_repeats']))
    def quantile(q):
        at = (len(means)-1)*q
        i = int(at)
        return means[i] + (at-i)*(means[i+1]-means[i])
    return [fmean(x),quantile(.025),quantile(.975)]
effects = {k:estimate(k) for k in next(iter(per_task.values()))}
leave = {omit:fmean(v['T_minus_U'] for t,v in per_task.items() if t!=omit) for omit in per_task}
gate_stop = all(effects['G_'+a][0] < 0 and effects['G_'+a][2]<.01 for a in ['T','U'])
gate_d2 = not gate_stop and effects['T_minus_U'][0]>0 and min(leave.values())>0 and effects['D_harm'][0]>0 and effects['D_harm'][0]>=effects['D_missed'][0]
j_tasks = Counter(sign(v['J_gain']) for v in per_task.values())
d_tasks = Counter(sign(v['T_minus_U']) for v in per_task.values())
save(out/'per-task.json',per_task)
save(out/'summary.json',dict(bootstrap='paired task percentile; each value is [mean,lower95,upper95]', effects=effects, counts=counts, examples=examples, j_tasks=j_tasks,d_tasks=d_tasks, leave_one=leave,gate_stop=gate_stop,gate_D2=gate_d2,source_traces_sha256=sha(source),protocol_sha256=sha(protocol_path),sha256_feedback_bank=bank_hash,sha256_prefix_selections=selected_hash,per_task_sha256=sha(out/'per-task.json'),registered_inputs_verified=len(protocol['frozen_sha256']),full_history_count=full_history_count,jobs=len(jobs),pools=425,tasks=len(per_task)))
print('audit summary',sha(out/'summary.json'))
