"""Measure a training signal on a fixed development slice, without fitting a model."""
import argparse
from collections import Counter, defaultdict
import gzip
import hashlib
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))
from reproduction.clean_ranking_v1.loader import load_world
from reproduction.clean_ranking_v1.run import evaluate, select


def load(path):
    return json.loads(path.read_bytes())


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(out):
    out.mkdir(parents=True, exist_ok=False)
    base = ROOT / 'experiments/clean-ranking-v1'
    prepared = base / 'prepared'
    jobs = [job for job in map(json.loads, (prepared/'jobs.jsonl').read_text().splitlines())
            if job['pool_id'] == 0]
    assert len(jobs) == 52 and len({job['task'] for job in jobs}) == 26
    archive = base/'results/decisions.jsonl.gz'
    assert digest(archive) == load(base/'results/verification.json')['decisions_sha256']
    with gzip.open(archive, 'rt') as stream:
        original = {r['job_id']: r for r in map(json.loads, stream) if r['method']=='corrected_tournament'}
    bank = load(prepared/'feedback.json')
    paths = load(prepared/'code_files.json')
    labels = load(prepared/'evaluation_labels.json')
    world = load_world()
    records = []
    repeated = defaultdict(list)
    for job in jobs:
        task = job['task']
        utility = labels[task]
        code = {i:(ROOT/paths[task][i]).read_text() for i in job['ids']}
        span = max(utility[i] for i in code) - min(utility[i] for i in code)
        saved = original[job['job_id']]
        selected, trace, stats = select(world,job,bank[task],code,'corrected_tournament',.7)
        assert (selected,trace,stats) == (saved['selected'],saved['trace'],saved['stats'])
        for turn, event in enumerate(trace):
            a,b = event['a'],event['b']
            if event['winner'] is None or utility[a] == utility[b]:
                continue
            right,wrong = sorted((a,b),key=utility.get,reverse=True)
            pair = '|'.join(sorted((a,b)))
            entry = bank[task][pair]
            outcomes = {}
            for action,candidate in [('right',right),('wrong',wrong)]:
                changed = dict(entry,predicted_best_index=entry['order'].index(candidate))
                supplied = {**bank[task],pair:changed}
                picked, path, counts = select(world,job,supplied,code,'corrected_tournament',.7)
                assert path[:turn] == trace[:turn]
                assert path[turn] == {**event,'winner':candidate}
                if candidate == event['winner']:
                    assert (picked,path,counts)==(selected,trace,stats)
                outcomes[action] = evaluate(job['ids'],picked,utility)['regret']
            delta = outcomes['wrong']-outcomes['right']
            row = dict(task=task,job=job['job_id'],pair=pair,repeat=job['repeat'],
                       gap=(utility[right]-utility[wrong])/span,delta=delta,**outcomes)
            records.append(row)
            repeated[task,pair].append(row)
    twins = [v for _,v in sorted(repeated.items()) if len(v)==2]
    differing = []
    for x,y in twins:
        assert x['repeat'] != y['repeat'] and x['gap'] == y['gap']
        if abs(x['delta']-y['delta'])>1e-12:
            differing.append([x,y])
    signs = Counter('positive' if d>1e-12 else 'negative' if d< -1e-12 else 'zero'
                    for d in (r['delta'] for r in records))
    summary = dict(tasks=26,jobs=len(jobs),accepted_strict_edge_occurrences=len(records),
                   signs=dict(signs),pairs_seen_in_both_repeats=len(twins),
                   differing_effect_across_repeats=len(differing),example=next(iter(differing),None),
                   source_sha256={str(f.relative_to(ROOT)):digest(f) for f in
                       [HERE/'protocol.json',Path(__file__),archive,prepared/'feedback.json',
                        prepared/'evaluation_labels.json',prepared/'jobs.jsonl']},
                   model_training=0,new_judge_calls=0)
    (out/'rows.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in records))
    (out/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:v for k,v in summary.items() if k!='source_sha256'},ensure_ascii=False))


if __name__=='__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('out',type=Path)
    run(parser.parse_args().out)
