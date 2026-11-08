"""Trusted data gateway, policy runner and independent replay evaluator."""
from collections import Counter
import datetime
import gzip
import hashlib
import itertools
import json
from pathlib import Path
import platform
import time

from reproduction.clean_ranking_v1.correctness import response_values
from reproduction.clean_ranking_v1.ranking import top_set
from reproduction.clean_ranking_v1.run import evaluate, select, summarize
from reproduction.clean_ranking_v1.loader import load_world
from .isolation import PolicyError, Worker, probe

ROOT = Path(__file__).resolve().parents[2]
REGISTRY = ROOT/'research/registry.json'


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read_json(path):
    return json.loads(Path(path).read_text())


def dump(path, value):
    path = Path(path)
    path.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True,
                              indent=2, allow_nan=False)+'\n')


def verify_files(entries, root=ROOT):
    for name, expected in entries.items():
        if digest(Path(root)/name) != expected:
            raise ValueError('Protected source/input changed: '+name)


def load_context():
    registry = read_json(REGISTRY)
    protected = read_json(ROOT/registry['paths']['protected_manifest'])
    verify_files(protected['sha256'])
    config = registry['benchmark']
    locked = read_json(ROOT/config['implementation_lock'])
    verify_files(locked['sha256'])
    prepared = ROOT/config['prepared']
    source = read_json(prepared/'source_manifest.json')
    verify_files(source['sha256'])
    jobs = [json.loads(line) for line in (prepared/'jobs.jsonl').read_text().splitlines()]
    bank = read_json(prepared/'feedback.json')
    if len(jobs) != config['jobs'] or len({j['job_id'] for j in jobs}) != len(jobs):
        raise ValueError('Frozen job population changed')
    for job in jobs:
        if not 0 <= job['budget'] <= config['unique_query_budget_max']:
            raise ValueError('Job budget outside environment contract')
        for a, b in itertools.combinations(job['ids'], 2):
            if '|'.join(sorted((a,b))) not in bank[job['task']]:
                raise ValueError('Admitted pool has an unavailable comparison')
    return registry, jobs, bank, read_json(prepared/'code_files.json')


def public_feedback(bank, a, b, threshold):
    item = bank['|'.join(sorted((a,b)))]
    index, confidence = response_values({'predicted_best_index':item['predicted_best_index'],
                                         'confidence':item['confidence']})
    winner = item['order'][index] if index is not None and confidence >= threshold else None
    return dict(a=a, b=b, winner=winner, confidence=confidence, valid=winner is not None)


class Episode:
    """Only the trusted host owns this object and the complete feedback bank."""
    def __init__(self, job, bank, threshold=.7, max_attempts=1024):
        self.job, self.bank, self.threshold = job, bank, threshold
        self.max_attempts = max_attempts
        self.observed, self.trace, self.actions = {}, [], []

    def observation(self):
        return dict(episode=hashlib.sha256(self.job['job_id'].encode()).hexdigest()[:20],
                    candidates=list(self.job['ids']), seed=self.job['seed'],
                    feedback=[dict(row) for row in self.observed.values()],
                    remaining_budget=self.job['budget']-len(self.observed), attempts=len(self.actions))

    def act(self, action):
        if len(self.actions) >= self.max_attempts:
            raise PolicyError('Episode action-attempt limit exceeded')
        self.actions.append(action)
        if action == {'action':'stop'}:
            return False
        if not isinstance(action,dict) or set(action) != {'action','pair'} or action['action'] != 'compare':
            raise PolicyError('Action must be compare(pair) or stop')
        pair = action['pair']
        if (not isinstance(pair, list) or len(pair) != 2 or pair[0] == pair[1]
                or any(not isinstance(x,str) or x not in self.job['ids'] for x in pair)):
            raise PolicyError('Query requires two distinct candidate IDs from this episode')
        a, b = pair
        key = tuple(sorted(pair))
        cached = key in self.observed
        if not cached and len(self.observed) >= self.job['budget']:
            raise PolicyError('Unique-query budget exceeded')
        row = public_feedback(self.bank, a, b, self.threshold)
        self.observed.setdefault(key, row)
        self.trace.append({**row, 'cached':cached})
        return True

    def selected(self):
        return top_set(self.job['ids'], [(r['a'],r['b'],r['winner']) for r in self.observed.values()])

    def stats(self):
        return dict(unique_feedback_reads=len(self.observed),
                    cache_reads=sum(r['cached'] for r in self.trace), budget_denials=0,
                    comparison_records=len(self.trace), attempts=len(self.actions))


def policy_episode(job, bank, source, registry):
    limits = registry['limits']
    env = Episode(job, bank, registry['benchmark']['confidence_threshold'],
                  limits['max_attempts_per_episode'])
    error, status, reason = None, 'ok', 'budget_exhausted'
    try:
        with Worker(source, limits['response_timeout_seconds'], limits['episode_timeout_seconds']) as worker:
            while len(env.observed) < job['budget']:
                if not env.act(worker.request(env.observation())):
                    reason = 'policy_stop'
                    break
    except Exception as exc:
        status, reason, error = 'failed', 'policy_failure', (type(exc).__name__+': '+str(exc))[:4096]
    return dict(selected=env.selected() if status == 'ok' else [], status=status,
                stop_reason=reason, error=error, trace=env.trace, actions=env.actions, stats=env.stats())


def policy_bytes(path, registry):
    path = Path(path).resolve()
    allowed = (ROOT/registry['policy']['root']).resolve()
    if not path.is_relative_to(allowed) or path.suffix != '.py':
        raise ValueError('Policy must be a .py file inside '+str(allowed))
    raw = path.read_bytes()
    if len(raw) > registry['limits']['policy_bytes_max']:
        raise ValueError('Policy source exceeds contract size')
    raw.decode('utf-8')
    return raw


def run_selection(output, policy=None, limit_jobs=None):
    registry, jobs, bank, code_paths = load_context()
    output = Path(output).resolve()
    allowed = (ROOT/registry['paths']['output_root']).resolve()
    if not output.is_relative_to(allowed) or output == allowed or output.exists():
        raise ValueError('Choose a new output directory beneath '+str(allowed))
    if limit_jobs is not None:
        if not isinstance(limit_jobs,int) or limit_jobs <= 0:
            raise ValueError('limit_jobs must be positive')
        jobs = jobs[:limit_jobs]
    raw = policy_bytes(policy, registry) if policy else None
    isolation = probe() if policy else {'mode':'trusted_frozen_baseline'}
    output.mkdir(parents=True)
    if raw is not None:
        (output/'policy.py').write_bytes(raw)
    dump(output/'episode_plan.json', jobs)
    info = dict(environment_id=registry['environment_id'], registry_sha256=digest(REGISTRY),
        protected_manifest_sha256=digest(ROOT/registry['paths']['protected_manifest']),
        mode='submitted_policy' if policy else 'corrected_tournament', jobs=len(jobs),
        full_population=len(jobs)==registry['benchmark']['jobs'], scope=registry['scope'],
        policy_sha256=hashlib.sha256(raw).hexdigest() if raw is not None else None,
        policy_source=str(Path(policy).resolve().relative_to(ROOT)) if policy else None,
        python=platform.python_version(), isolation=isolation,
        started_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        new_model_calls=0, new_candidate_training_runs=0, new_gpu_rentals=0)
    dump(output/'run_info.json', info)
    module = load_world() if policy is None else None
    start = time.monotonic()
    timing = []
    with (output/'decisions.jsonl.gz').open('wb') as raw_out, gzip.GzipFile(
            filename='', fileobj=raw_out, mode='wb', mtime=0) as stream:
        for number, job in enumerate(jobs, 1):
            before = time.monotonic()
            if time.monotonic()-start > registry['limits']['run_wall_seconds']:
                episode = dict(selected=[], status='failed', error='Global run wall limit',
                    stop_reason='run_limit', trace=[], actions=[], stats=dict(
                    unique_feedback_reads=0,cache_reads=0,budget_denials=0,comparison_records=0,attempts=0))
            elif policy:
                episode = policy_episode(job, bank[job['task']], raw, registry)
            else:
                code = {i:(ROOT/code_paths[job['task']][i]).read_text() for i in job['ids']}
                selected, trace, stats = select(module,job,bank[job['task']],code,
                    'corrected_tournament',registry['benchmark']['confidence_threshold'])
                episode = dict(selected=selected,trace=trace,stats=stats,status='ok',error=None,
                               stop_reason='original_tournament',actions=[])
            row = dict(job_id=job['job_id'], **episode)
            stream.write((json.dumps(row,sort_keys=True,allow_nan=False)+'\n').encode())
            timing.append(dict(job_id=job['job_id'],wall_seconds=time.monotonic()-before))
            if number%100 == 0:
                print(f'completed {number}/{len(jobs)} episodes', flush=True)
    info['selection_wall_seconds'] = time.monotonic()-start
    dump(output/'run_info.json', info)
    dump(output/'timings.json', timing)
    names=['run_info.json','episode_plan.json','decisions.jsonl.gz','timings.json']
    if raw is not None:
        names.append('policy.py')
    dump(output/'run_manifest.json', {name:digest(output/name) for name in names})
    return output


def load_rows(path):
    with gzip.open(path,'rt') as stream:
        return [json.loads(line) for line in stream]


def verify_episode(row, job, bank, registry):
    env = Episode(job,bank,registry['benchmark']['confidence_threshold'],
                  registry['limits']['max_attempts_per_episode'])
    # Every recorded query must be a successful prefix of the action sequence.
    for action, recorded in zip(row['actions'][:len(row['trace'])],row['trace'],strict=True):
        env.act(action)
        if not env.trace or env.trace[-1] != recorded:
            raise ValueError('Feedback transcript inconsistent with frozen source')
    if len(row['trace']) != len(env.trace):
        raise ValueError('Incomplete query transcript')
    for key in ('unique_feedback_reads','cache_reads','budget_denials','comparison_records'):
        if row['stats'][key] != env.stats()[key]:
            raise ValueError('Incorrect ledger: '+key)
    if row['stats']['attempts'] != len(row['actions']):
        raise ValueError('Incorrect action-attempt count')
    if len(row['actions']) > env.max_attempts or len(env.observed) > job['budget']:
        raise ValueError('Policy exceeded host contract')
    if row['status'] == 'ok':
        if row['selected'] != env.selected():
            raise ValueError('Selection differs from frozen aggregation')
        tail = row['actions'][len(row['trace']):]
        if row['stop_reason'] == 'policy_stop':
            if tail != [{'action':'stop'}] or len(env.observed) >= job['budget']:
                raise ValueError('Invalid early-stop transcript')
        elif row['stop_reason'] != 'budget_exhausted' or tail or len(env.observed) != job['budget']:
            raise ValueError('Successful episode has no valid stopping condition')
    elif row['status'] != 'failed' or row['selected']:
        raise ValueError('Failure/selection contract violated')


def evaluate_run(output):
    registry,jobs,bank,_ = load_context()
    output = Path(output).resolve()
    verify_files(read_json(output/'run_manifest.json'), output)
    info = read_json(output/'run_info.json')
    if info['environment_id'] != registry['environment_id'] or info['mode'] not in ('corrected_tournament','submitted_policy'):
        raise ValueError('Unknown environment/mode')
    if info['registry_sha256'] != digest(REGISTRY) or info['protected_manifest_sha256'] != digest(
            ROOT/registry['paths']['protected_manifest']):
        raise ValueError('Environment changed since selection')
    plan = read_json(output/'episode_plan.json')
    if plan != jobs[:len(plan)] or len(plan) != info['jobs'] or not plan:
        raise ValueError('Run plan differs from frozen benchmark/subset contract')
    if info['full_population'] != (len(plan)==len(jobs)):
        raise ValueError('Incorrect population coverage flag')
    if info['mode']=='submitted_policy' and digest(output/'policy.py') != info['policy_sha256']:
        raise ValueError('Policy snapshot hash mismatch')
    rows = load_rows(output/'decisions.jsonl.gz')
    if [r['job_id'] for r in rows] != [j['job_id'] for j in plan]:
        raise ValueError('Missing, duplicate or reordered episodes')
    reference = {r['job_id']:r for r in load_rows(ROOT/registry['benchmark']['reference_decisions'])
                 if r['method']=='corrected_tournament'}
    for row,job in zip(rows,plan,strict=True):
        if info['mode']=='corrected_tournament':
            for key in ('selected','trace','stats'):
                if row[key] != reference[job['job_id']][key]:
                    raise ValueError('Baseline replay differs from frozen result: '+key)
            if row['status'] != 'ok':
                raise ValueError('Baseline failed')
        else:
            verify_episode(row,job,bank[job['task']],registry)
    # Execution utilities are parsed only by this independent evaluation stage.
    labels = read_json(ROOT/registry['benchmark']['prepared']/'evaluation_labels.json')
    scored=[]
    for row,job in zip(rows,plan,strict=True):
        for method,selected,stats in [
            ('corrected_tournament',reference[job['job_id']]['selected'],reference[job['job_id']]['stats']),
            ('submitted_policy',row['selected'],row['stats'])]:
            metrics = evaluate(job['ids'],selected,labels[job['task']]) if selected else dict(regret=1.0,best_hit=0.0)
            scored.append(dict(task=job['task'],method=method,metrics={**metrics,**stats}))
    protocol=read_json(ROOT/registry['benchmark']['protocol'])
    protocol={**protocol,'methods':['corrected_tournament','submitted_policy'],
              'primary_comparison':['corrected_tournament','submitted_policy'],
              'mechanism_control':['corrected_tournament','submitted_policy']}
    summary=summarize(scored,protocol)
    counts=Counter(r['status'] for r in rows)
    summary.update(environment_id=registry['environment_id'],mode=info['mode'],scope=registry['scope'],
        full_population=info['full_population'],episode_status_counts=dict(counts),
        failure_penalty=dict(regret=1.0,best_hit=0.0),planned_denominator=len(plan),
        valid_only_episode_mean_regret=(sum(r['metrics']['regret'] for r,row in zip(
            scored[1::2],rows,strict=True) if row['status']=='ok')/counts['ok'] if counts['ok'] else None),
        input_implementation_and_trace_checks='passed',new_model_calls=0,new_candidate_training_runs=0)
    evaluation=output/'evaluation'
    if evaluation.exists():
        if read_json(evaluation/'summary.json') != summary:
            raise ValueError('Existing evaluation differs from independent recomputation')
    else:
        evaluation.mkdir()
        dump(evaluation/'summary.json',summary)
        dump(evaluation/'verification.json',dict(status='passed',episodes=len(rows),
            source_manifest_sha256=digest(ROOT/registry['paths']['protected_manifest']),
            decisions_sha256=digest(output/'decisions.jsonl.gz'),
            labels_enter_only_after_selection=True,baseline_reference_checked=True))
    return summary
