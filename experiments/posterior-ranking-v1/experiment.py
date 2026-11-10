"""One preregistered fixed-odds complete-order posterior; select before score.

For a prefix S, append j with factor 2**(# accepted edges i->j, i in S).
Every accepted consistent edge is counted exactly once, when its loser is appended.
F[S] sums prefix weights. G[S] sums continuation weights given candidate set S.
Transition mass F[S]*factor*G[S+j] gives exact rank marginals after division by Z.
No candidate code, raw judge text, unqueried pair, or score enters the selector.
"""
import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
from fractions import Fraction
import gzip
import hashlib
from itertools import combinations, permutations, product
import json
import math
from pathlib import Path
import platform
import random
from statistics import fmean
import sys
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))
from reproduction.clean_ranking_v1.ranking import top_set
from reproduction.clean_ranking_v1.run import evaluate, percentile
PROTOCOL_SHA = 'c0329efda4c2f015d48f650913028e1bda57b003298cb0986685782658e384f0'
PREP = ROOT/'experiments/clean-ranking-v1/prepared'
OLD = ROOT/'experiments/selection-frontier-02/c0-final-selection/run-002'
TRACES = ROOT/'experiments/trajectory-weighted-judge-v1/evaluation/run_1/decisions.sealed.jsonl.gz'
ARMS = ('C', 'R', 'H', 'E', 'B')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path, obj):
    path.write_text(json.dumps(obj, sort_keys=True, indent=2, allow_nan=False)+'\n')


def read(path):
    return json.loads(path.read_bytes())


def records(path):
    with gzip.open(path, 'rt') as stream:
        for line in stream:
            yield json.loads(line)


def frozen():
    assert sha(HERE/'protocol.json') == PROTOCOL_SHA
    protocol = read(HERE/'protocol.json')
    for path, digest in protocol['inputs'].items():
        assert sha(ROOT/path) == digest, path
    return protocol


def posterior(n, edges):
    """Return Z, expected-rank numerators, P(best) numerators; all integers."""
    assert 1 <= n <= 10
    incoming = [0]*n
    for winner, loser in edges:
        assert winner != loser and 0 <= winner < n and 0 <= loser < n
        incoming[loser] |= 1 << winner
    size = 1 << n
    forward = [0]*size
    forward[0] = 1
    for mask in range(size):
        remaining = (size-1)^mask
        while remaining:
            bit = remaining & -remaining
            j = bit.bit_length()-1
            forward[mask|bit] += forward[mask] << (mask & incoming[j]).bit_count()
            remaining ^= bit
    backward = [0]*size
    backward[-1] = 1
    for mask in range(size-2, -1, -1):
        remaining = (size-1)^mask
        while remaining:
            bit = remaining & -remaining
            j = bit.bit_length()-1
            backward[mask] += backward[mask|bit] << (mask & incoming[j]).bit_count()
            remaining ^= bit
    z = forward[-1]
    assert backward[0] == z
    ranks, best, totals = [0]*n, [0]*n, [0]*n
    for mask in range(size-1):
        rank = mask.bit_count()+1
        remaining = (size-1)^mask
        while remaining:
            bit = remaining & -remaining
            j = bit.bit_length()-1
            mass = (forward[mask]*backward[mask|bit]) << (mask & incoming[j]).bit_count()
            totals[j] += mass
            ranks[j] += rank*mass
            if rank == 1:
                best[j] = mass
            remaining ^= bit
    assert totals == [z]*n and sum(best) == z
    assert sum(ranks) == z*n*(n+1)//2
    return z, ranks, best


def brute(n, edges):
    z, ranks, best = 0, [0]*n, [0]*n
    for order in permutations(range(n)):
        pos = {j: k+1 for k,j in enumerate(order)}
        weight = 1 << sum(pos[w] < pos[l] for w,l in edges)
        z += weight
        best[order[0]] += weight
        for j in range(n):
            ranks[j] += pos[j]*weight
    return z, ranks, best


def validate():
    start = time.perf_counter()
    count = 0
    rng = random.Random(20261108094)
    for n in range(1, 7):
        pairs = list(combinations(range(n), 2))
        states = product(range(3), repeat=len(pairs)) if n <= 4 else (
            [rng.randrange(3) for _ in pairs] for _ in range(60 if n == 5 else 20))
        for state in states:
            edges = [(a,b) if s == 1 else (b,a) for (a,b),s in zip(pairs,state) if s]
            actual = posterior(n, edges)
            assert actual == brute(n, edges), (n, edges)
            rev = posterior(n, [(b,a) for a,b in edges])
            assert rev[0] == actual[0]
            assert rev[1] == [(n+1)*actual[0]-x for x in actual[1]]
            count += 1
        z, ranks, best = posterior(n, [])
        assert len(set(ranks)) == len(set(best)) == 1
        assert z == math.factorial(n)
    z, ranks, best = posterior(3, [(0,1),(1,2),(2,0)])
    assert len(set(ranks)) == len(set(best)) == 1
    assert posterior(2, [(0,1)]) == (3, [4,5], [2,1])
    write(HERE/'validation.json', dict(status='passed', exact_permutation_graphs=count,
        max_permutation_n=6, exhaustive_all_directed_or_absent_graphs_n_le_4=True,
        reverse_graph_rank_identity=True, empty_graph_uniform_ties=True, symmetric_cycle_ties=True,
        exact_integer=True, wall_seconds=time.perf_counter()-start, script_sha256=sha(Path(__file__))))


def accepted(ids, trace):
    seen, feedback, edges = set(), [], []
    index = {cid:i for i,cid in enumerate(ids)}
    for item in trace:
        a,b,winner = item['a'],item['b'],item['winner']
        key = tuple(sorted((a,b)))
        assert a != b and {a,b} <= index.keys() and key not in seen
        seen.add(key)
        confidence = item['confidence']
        if winner is not None:
            assert winner in (a,b) and type(confidence) in (float,int)
            assert math.isfinite(confidence) and .7 <= confidence <= 1
            loser = b if winner == a else a
            feedback.append((a,b,winner))
            edges.append((index[winner],index[loser]))
    return feedback, edges


def select():
    frozen()
    validate()
    assert not (HERE/'selection_seal.json').exists()
    jobs = {j['job_id']:j for j in map(json.loads,(PREP/'jobs.jsonl').read_text().splitlines())}
    assert len(jobs) == 850
    prior = {(r['bank'],r['job_id']):r for r in records(OLD/'decisions.sealed.jsonl.gz')}
    rows, times, checks = [], defaultdict(list), Counter()
    start = time.perf_counter()
    for original in records(TRACES):
        if original['arm'] != 'C0':
            continue
        bank, job_id = original['bank'], original['job_id']
        job = jobs[job_id]
        ids = job['ids']
        old = prior[bank,job_id]
        assert original['task'] == job['task'] == old['task']
        assert original['trace'] == old['trace'] and original['stats'] == old['stats']
        assert original['selected'] == old['selected']['C']
        feedback, edges = accepted(ids, original['trace'])
        t = time.process_time_ns()
        z,ranks,best = posterior(len(ids), edges)
        cpu = (time.process_time_ns()-t)/1e9
        times[bank].append(cpu)
        wins,degree = Counter(w for a,b,w in feedback), Counter(x for a,b,w in feedback for x in (a,b))
        ratios = {i:Fraction(wins[i],degree[i]) if degree[i] else Fraction(1,2) for i in ids}
        selected = dict(C=original['selected'], R=[i for i in ids if ratios[i] == max(ratios.values())],
            H=top_set(ids,feedback), E=[i for k,i in enumerate(ids) if ranks[k] == min(ranks)],
            B=[i for k,i in enumerate(ids) if best[k] == max(best)])
        assert selected['H'] == old['selected']['H']
        assert len(original['trace']) == original['stats']['unique_feedback_reads'] <= job['budget'] <= 13
        checks[bank] += 1
        rows.append(dict(bank=bank,job_id=job_id,task=job['task'],ids=ids,selected=selected,
            accepted_edges=edges,unique_reads=len(original['trace']),accepted_reads=len(edges),stats=original['stats'],
            posterior=dict(normalizer=z,rank_numerators=ranks,best_numerators=best),cpu_seconds=cpu))
    assert len(rows) == len({(r['bank'],r['job_id']) for r in rows}) == 3400
    assert len(checks) == 4 and set(checks.values()) == {850}
    decision = HERE/'decisions.sealed.jsonl.gz'
    decision.write_bytes(gzip.compress(''.join(json.dumps(r,sort_keys=True)+'\n' for r in rows).encode(),mtime=0))
    write(HERE/'selection_seal.json',dict(sealed_utc=datetime.now(timezone.utc).isoformat(),
        decisions_sha256=sha(decision),protocol_sha256=PROTOCOL_SHA,script_sha256=sha(Path(__file__)),
        validation_sha256=sha(HERE/'validation.json'),rows=len(rows),selection_arms=ARMS,
        prior_C_H_and_C0_trace_ledger_exact=dict(checks),score_labels_loaded=False,
        ranking_cpu=dict(total_seconds=sum(map(sum,times.values())),by_bank={b:dict(total_seconds=sum(t),
            mean_seconds=fmean(t),median_seconds=percentile(t,.5),p95_seconds=percentile(t,.95),
            max_seconds=max(t)) for b,t in times.items()}),selection_wall_seconds=time.perf_counter()-start,
        python=sys.version,platform=platform.platform()))
    print(json.dumps(dict(stage='sealed',rows=3400,posterior_cpu_seconds=sum(map(sum,times.values())))),flush=True)


def contrast(data, control, arm, metric, draws):
    tasks = sorted(data)
    sign = 1 if metric == 'regret' else -1
    delta = {t:sign*(data[t][control][metric]-data[t][arm][metric]) for t in tasks}
    values = list(delta.values())
    bootstrap = [fmean(values[i] for i in sample) for sample in draws]
    loo = {t:fmean(delta[x] for x in tasks if x != t) for t in tasks}
    return dict(gain=fmean(values),ci95=[percentile(bootstrap,.025),percentile(bootstrap,.975)],
        per_task_gain=delta,tasks_improved=sum(v>1e-12 for v in values),tasks_tied=sum(abs(v)<=1e-12 for v in values),
        tasks_worsened=sum(v < -1e-12 for v in values),leave_one_task_out=loo,
        leave_one_min=min(loo.values()),leave_one_max=max(loo.values()))


def score():
    frozen()
    seal = read(HERE/'selection_seal.json')
    assert seal['protocol_sha256'] == PROTOCOL_SHA and seal['script_sha256'] == sha(Path(__file__))
    assert sha(HERE/'decisions.sealed.jsonl.gz') == seal['decisions_sha256']
    # This first score-label access occurs after the persisted selection seal.
    labels = read(PREP/'evaluation_labels.json')
    tasks = sorted(labels)
    assert len(tasks) == 26
    prior = {(r['bank'],r['job_id']):r for r in map(json.loads,(OLD/'per_episode.jsonl').read_text().splitlines())}
    prior_summary = read(OLD/'summary.json')
    grouped,changes,episodes = defaultdict(list), defaultdict(Counter), []
    checks = Counter()
    for row in records(HERE/'decisions.sealed.jsonl.gz'):
        bank,task,job_id = row['bank'],row['task'],row['job_id']
        utility = labels[task]
        metrics = {}
        for arm in ARMS:
            selected = row['selected'][arm]
            m = evaluate(row['ids'],selected,utility)
            best,worst = max(utility[i] for i in row['ids']),min(utility[i] for i in row['ids'])
            direct = (best-fmean(utility[i] for i in selected))/(best-worst) if best > worst else 0.
            assert abs(m['regret']-direct) < 1e-10
            m.update(unique_reads=row['unique_reads'],accepted_reads=row['accepted_reads'],
                     cache_reads=row['stats']['cache_reads'],budget_denials=row['stats']['budget_denials'],selected_size=len(selected))
            if arm in ('C','H'):
                assert all(abs(m[k]-prior[bank,job_id]['metrics'][arm][k])<1e-12 for k in ('regret','best_hit'))
                checks[bank+'_'+arm] += 1
            grouped[bank,task,arm].append(m)
            metrics[arm] = m
        for arm in ('E','B','R','H'):
            for control in ('C','R','H'):
                key = bank,arm,control
                count = changes[key]
                gain = metrics[control]['regret']-metrics[arm]['regret']
                count['episodes'] += 1
                count['selection_changed'] += set(row['selected'][arm]) != set(row['selected'][control])
                count['regret_improved'] += gain > 1e-12
                count['regret_tied'] += abs(gain) <= 1e-12
                count['regret_worsened'] += gain < -1e-12
        episodes.append(dict(bank=bank,task=task,job_id=job_id,metrics=metrics))
    banks = sorted({b for b,t,a in grouped})
    names = ('regret','best_hit','unique_reads','accepted_reads','cache_reads','budget_denials','selected_size')
    data = {b:{t:{a:{k:fmean(r[k] for r in grouped[b,t,a]) for k in names} for a in ARMS}
               for t in tasks} for b in banks}
    gpt = [b for b in banks if b != 'DS']
    assert len(gpt) == 3
    data['GPT_task_first_pooled'] = {t:{a:{k:fmean(data[b][t][a][k] for b in gpt) for k in names}
                                          for a in ARMS} for t in tasks}
    rng = random.Random(20261108093)
    draws = [rng.choices(range(26),k=26) for _ in range(10000)]
    summaries = {}
    for bank,items in data.items():
        macro = {a:{k:fmean(items[t][a][k] for t in tasks) for k in names} for a in ARMS}
        for a in ('C','H'):
            for k in ('regret','best_hit','unique_reads','cache_reads','budget_denials','selected_size'):
                assert abs(macro[a][k]-prior_summary['summaries'][bank]['macro'][a][k]) < 1e-12
        contrasts = {c+'_minus_'+a:{k:contrast(items,c,a,k,draws) for k in ('regret','best_hit')}
                     for c,a in [('C','E'),('C','B'),('C','R'),('C','H'),('R','E'),('H','E'),('R','B'),('H','B')]}
        summaries[bank] = dict(macro=macro,contrasts=contrasts)
    ds, gp = [summaries[b]['contrasts'] for b in ('DS','GPT_task_first_pooled')]
    gate = dict(DS_gain_ge_01=ds['C_minus_E']['regret']['gain']>=.01,
        GPT_pooled_positive=gp['C_minus_E']['regret']['gain']>0,
        same_direction_vs_simple_and_legacy_both=all(x[k]['regret']['gain']>0 for x in (ds,gp) for k in ('R_minus_E','H_minus_E')),
        CI_lower_positive_both=all(x['C_minus_E']['regret']['ci95'][0]>0 for x in (ds,gp)),
        all_leave_one_positive_both=all(x['C_minus_E']['regret']['leave_one_min']>0 for x in (ds,gp)))
    write(HERE/'per_task.json',data)
    (HERE/'per_episode.jsonl.gz').write_bytes(gzip.compress(''.join(json.dumps(r,sort_keys=True)+'\n' for r in episodes).encode(),mtime=0))
    write(HERE/'summary.json',dict(status='complete',id='posterior-ranking-v1',summaries=summaries,criteria=gate,
        decision='promote_primary_for_fresh_confirmation' if all(gate.values()) else 'retain_C0',
        positive_gain='lower regret or higher best-hit probability for posterior arm',
        selection_changes={b:{a+'_vs_'+c:dict(v) for (bb,a,c),v in changes.items() if bb==b} for b in banks},
        prior_control_episode_matches=dict(checks),prior_macro_matches=10,selection_rows=3400,tasks=26,
        selection_seal_sha256=sha(HERE/'selection_seal.json'),protocol_sha256=PROTOCOL_SHA,
        bootstrap_draws=10000,bootstrap_seed=20261108093,ranking_cpu=seal['ranking_cpu'],
        new_API_calls=0,new_training_runs=0,new_data=0,new_GPU=0,limitations=read(HERE/'protocol.json')['limitations']))
    print(json.dumps(dict(decision='retain_C0' if not all(gate.values()) else 'promote_primary_for_fresh_confirmation',
        criteria=gate,DS=ds['C_minus_E']['regret'],GPT=gp['C_minus_E']['regret']),indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('stage',choices=('select','score'))
    args = parser.parse_args()
    select() if args.stage == 'select' else score()
