"""Read back branch receipts and independently recompute task-local weights."""
from collections import Counter, defaultdict
import gzip
import hashlib
import json
from pathlib import Path
import random
import statistics
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT))
from reproduction.clean_ranking_v1.run import evaluate


def load(path):
    return json.loads(path.read_bytes())


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def classify(n):
    return '0' if n == 0 else '1' if n == 1 else '2-3' if n <= 3 else '4+'


def run(output):
    prepared = ROOT/'experiments/clean-ranking-v1/prepared'
    labels = load(prepared/'evaluation_labels.json')
    banks = load(prepared/'feedback.json')
    jobs = {r['job_id']:r for r in map(json.loads, (prepared/'jobs.jsonl').read_text().splitlines())}
    with gzip.open(ROOT/'experiments/clean-ranking-v1/results/decisions.jsonl.gz', 'rt') as stream:
        baseline = {r['job_id']:r for r in map(json.loads, stream) if r['method']=='corrected_tournament'}
    receipt = load(output/'receipt.json')
    for path, expected in receipt['source_sha256'].items():
        assert digest(ROOT/path) == expected, path
    assert digest(output/'summary.json') == receipt['summary_sha256']
    for task, paths in load(prepared/'code_files.json').items():
        assert all(digest(ROOT/path).startswith(candidate) for candidate, path in paths.items()), task
    hashes = {}
    checks = Counter()
    increments = Counter()
    for task in sorted(labels):
        weight_path = output/'tasks'/f'{task}.json'
        assert digest(weight_path) == receipt['task_weight_sha256'][task]
        pairs = load(weight_path)
        rows_path = output/'rows'/f'{task}.jsonl'
        branch_path = output/'branches'/f'{task}.jsonl.gz'
        rows = list(map(json.loads, rows_path.read_text().splitlines()))
        with gzip.open(branch_path, 'rt') as stream:
            branches = list(map(json.loads, stream))
        assert len(branches) == len(rows)
        grouped = defaultdict(list)
        for row, branch in zip(rows, branches):
            saved = baseline[row['job']]
            job = jobs[row['job']]
            turn = branch['turn']
            original_event = saved['trace'][turn]
            assert row['pair'] == branch['pair'] == '|'.join(sorted((original_event['a'],original_event['b'])))
            assert row['job'] == branch['job']
            assert branch['trace'][:turn] == saved['trace'][:turn]
            assert branch['trace'][turn] == {**original_event,'winner':branch['forced']}
            assert branch['forced'] != original_event['winner']
            actual_base = evaluate(job['ids'], saved['selected'], labels[task])['regret']
            actual_branch = evaluate(job['ids'], branch['selected'], labels[task])['regret']
            winner = max(row['pair'].split('|'), key=labels[task].get)
            right, wrong = ((actual_base,actual_branch) if original_event['winner']==winner
                            else (actual_branch,actual_base))
            assert (right,wrong,wrong-right)==(row['right'],row['wrong'],row['delta'])
            span = max(labels[task][i] for i in job['ids'])-min(labels[task][i] for i in job['ids'])
            assert row['gap'] == abs(labels[task][original_event['a']]-labels[task][original_event['b']])/span
            assert branch['stats']['unique_feedback_reads'] <= job['budget']
            grouped[row['pair']].append(row)
            checks['branch_rows_and_prefixes'] += 1
        assert set(pairs)==set(banks[task])
        for pair, value in pairs.items():
            occurrences = grouped[pair]
            mean_delta = statistics.fmean(r['delta'] for r in occurrences) if occurrences else 0.
            mean_gap = statistics.fmean(r['gap'] for r in occurrences) if occurrences else 0.
            assert value['winner']==max(pair.split('|'),key=labels[task].get)
            assert value['n']==len(occurrences)
            assert value['mean_delta']==mean_delta and value['mean_gap']==mean_gap
            assert value['terminal']==1+max(0,mean_delta) and value['gap']==1+mean_gap
            assert all(1<=value[a]<=2 for a in ('terminal','gap','shuffled'))
            increments['terminal'] += value['terminal']>1
            checks['pair_aggregates'] += 1
        for group in ('0','1','2-3','4+'):
            keys = [pair for pair in sorted(pairs) if classify(pairs[pair]['n'])==group]
            values = [pairs[pair]['terminal']-1 for pair in keys]
            random.Random(f'20261108:{task}:{group}').shuffle(values)
            assert all(pairs[pair]['shuffled']==1+value for pair,value in zip(keys,values))
            checks['shuffle_strata'] += 1
        for path in (weight_path, rows_path, branch_path):
            hashes[str(path.relative_to(output))] = digest(path)
    assert checks['branch_rows_and_prefixes']==load(output/'summary.json')['branch_reruns']
    assert checks['pair_aggregates']==17877
    result = dict(status='passed', checks=dict(checks), terminal_increment_pairs=increments['terminal'],
                  output_sha256=hashes, verifier_sha256=digest(Path(__file__)),
                  receipt_sha256=digest(output/'receipt.json'))
    (output/'readback.json').write_text(json.dumps(result, sort_keys=True, indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k!='output_sha256'}))


if __name__=='__main__':
    run(Path(sys.argv[1]))
