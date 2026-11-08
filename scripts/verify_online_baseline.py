"""CPU-only audit of a frozen Stanford ForeAgent run; never runs generated code or APIs."""
import argparse
from collections import Counter
import csv
import gzip
import hashlib
import importlib.util
import io
import json
import math
from pathlib import Path
import re
import subprocess
import sys
import types
import warnings

ROOT = Path(__file__).resolve().parents[1]
COMMIT = 'c4d52cf99bd870d830b456ac7c0684aec1aef375'
TARGETS = ('reactivity', 'deg_Mg_pH10', 'deg_Mg_50C')
PREDICTIONS = (*TARGETS, 'deg_pH10', 'deg_50C')


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(path, algorithm='sha256'):
    return hashlib.new(algorithm, path.read_bytes()).hexdigest()


def read_csv(path):
    return list(csv.DictReader(io.StringIO(path.read_text())))


def score_by_id(predictions, answers):
    """Independent MCRMSE: join unique IDs, apply private keep mask, average 3 RMSEs."""
    require(bool(predictions) and len(predictions) == len(answers), 'Row count mismatch')
    ps = {r['id_seqpos']: r for r in predictions}
    truth = {r['id_seqpos']: r for r in answers}
    require(len(ps) == len(predictions) and len(truth) == len(answers), 'Duplicate IDs')
    require(ps.keys() == truth.keys(), 'ID sets differ')
    for row in predictions:
        require(all(math.isfinite(float(row[c])) for c in PREDICTIONS), 'Nonfinite prediction')
    require(all(r['keep'].lower() in ('true', 'false', '1', '0') for r in answers), 'Invalid mask')
    ids = sorted(k for k, r in truth.items() if r['keep'].lower() in ('true', '1'))
    require(bool(ids), 'Empty scoring mask')
    per_target = {c: math.sqrt(math.fsum((float(ps[k][c])-float(truth[k][c]))**2
                                       for k in ids)/len(ids)) for c in TARGETS}
    return {'score': math.fsum(per_target.values())/3, 'per_target_rmse': per_target,
            'scored_rows': len(ids), 'prediction_rows': len(predictions)}


def check_source(source):
    tree = subprocess.check_output(['git', '-C', str(source), 'ls-tree', '-r', COMMIT], text=True)
    checked = 0
    for line in tree.splitlines():
        header, name = line.split('\t')
        mode, kind, oid = header.split()
        if kind != 'blob':
            continue
        path = source/name
        require(path.is_file() and mode != '120000', 'Missing or symlink source: '+name)
        data = path.read_bytes()
        actual = hashlib.sha1(('blob '+str(len(data))+'\0').encode()+data).hexdigest()
        require(actual == oid, 'Upstream source mismatch: '+name)
        checked += 1
    return {'commit': COMMIT, 'git_blobs_verified': checked}


def check_run(run, source, summary):
    import yaml
    class PathLoader(yaml.SafeLoader):
        pass
    PathLoader.add_constructor('tag:yaml.org,2002:python/object/apply:pathlib.PosixPath',
                               lambda loader, node: str(Path(*loader.construct_sequence(node))))
    cfg = yaml.load((run/'logs/exp/config.yaml').read_text(), Loader=PathLoader)
    published = yaml.safe_load((source/'mle-bench/agents/aide/config.yaml').read_text())['ForeAgent/DeepSeek-V3.2']
    for key, expected in published['kwargs'].items():
        value = cfg
        for part in key.split('.'):
            value = value[part]
        require(value == expected, 'Published parameter differs: '+key)
    snapshot = run/'runtime-snapshot'
    hashes = json.loads((snapshot/'SHA256.json').read_text())
    for name, value in hashes.items():
        require(digest(snapshot/name) == value, 'Runtime snapshot differs: '+name)
    anchor = json.loads((ROOT/'experiments/environment-acceptance/online-evidence.json').read_text())
    for name, item in anchor['run_files'].items():
        require(digest(run/name) == item['sha256'], 'Frozen run evidence differs: '+name)
    require(digest(run/'logs/exp/journal.json') == summary['journal_sha256'], 'Journal digest differs')
    raw = json.loads((run/'logs/exp/journal.json').read_text())
    nodes = raw['nodes']
    require(len({n['id'] for n in nodes}) == len(nodes), 'Duplicate journal IDs')
    good = [n for n in nodes if not n['is_buggy'] and not n['is_skipped']]
    require(good and all(n['metric']['maximize'] is False for n in good), 'Metric direction differs')
    independent_best = min(good, key=lambda n: n['metric']['value'])
    # Import source-only journal modules without aide.__init__, which also loads the live agent/API stack.
    package = types.ModuleType('aide')
    package.__path__ = [str(source/'mle-bench/agents/aide/aide')]
    sys.modules['aide'] = package
    from aide.journal import Journal
    from aide.utils.serialize import load_json
    best = load_json(run/'logs/exp/journal.json', Journal).get_best_node()
    require(best.id == independent_best['id'] == summary['selected_node_id'], 'Incumbent differs')
    workspace = run/'workspaces/exp'
    code = (workspace/'best_solution/solution.py').read_text()
    node_dir = workspace/'all_nodes'/('node_'+best.id[:8])
    require(code == best.code == (node_dir/'code.py').read_text(), 'Final code differs')
    prediction = workspace/'best_submission/submission.csv'
    require(prediction.read_bytes() == (node_dir/'submission.csv').read_bytes(), 'Node predictions differ')
    require(digest(prediction) == summary['csv_sha256'], 'Submission digest differs')
    archived = ROOT/'experiments/online-stanford-v2'/summary['prediction_file']
    require(gzip.decompress(archived.read_bytes()) == prediction.read_bytes(), 'Archived predictions differ')
    log = (run/'logs/exp/aide.log').read_text()
    labels = list(re.finditer(r'(?m)^\[[^\]]+\] INFO: Step (\d+)/5000$', log))
    batches = []
    batch_feedback = []
    for i, label in enumerate(labels):
        lo = int(label[1])-1
        if lo >= len(nodes):
            break
        hi = int(labels[i+1][1])-1 if i+1 < len(labels) else len(nodes)
        ns = nodes[lo:hi]
        if not any(n['wm_predicted_rank'] is not None for n in ns):
            continue
        require(len(ns) == 10 and all(n['wm_predicted_rank'] is not None for n in ns), 'Partial batch')
        cs = ns[0]['wm_comparison_results']
        require(all(n['wm_comparison_results'] == cs for n in ns), 'Comparison history differs')
        text = log[label.start():labels[i+1].start() if i+1 < len(labels) else len(log)]
        messages = re.findall(r"(?ms)^\[[^\n]+\] INFO: Querying model 'DeepSeek-V3\.2-Thinking' with message:.*?(?=^\[\d{4}-|\Z)", text)
        pairs = []
        for message in messages:
            sides = message.rsplit('### Solution 0:\n```python\n\n', 1)[1].split('\n```\n\n### Solution 1:\n```python\n\n', 1)
            ids = []
            for side in sides:
                matches = [n['id'] for n in ns if side == n['code'] or side.startswith(n['code']+'\n```')]
                require(len(matches) == 1, 'Ambiguous comparison prompt identity')
                ids.append(matches[0])
            pairs.append(tuple(sorted(ids)))
        batch_feedback.append({'outer_iteration': i+1, 'logged_comparison_requests': len(pairs),
                               'unique_unordered_pairs': len(set(pairs))})
        batches.append(dict(outer_iteration_in_segment=i+1, candidates=len(ns),
                            executed=sum(not n['is_skipped'] for n in ns),
                            cached_reads=text.count('INFO: Cache hit for pair:'),
                            comparison_records=len(cs),
                            forced_execution='Forcing execution of Rank 0 candidate.' in text,
                            max_round_limit='Tournament exceeded maximum rounds, breaking' in text))
    require(batches == summary['complete_batch_details'], 'Batch summary differs')
    receipts = [json.loads(line) for line in (run/'api.jsonl').read_text().splitlines() if line]
    successful = Counter(r['role'] for r in receipts if r['http'] == 200)
    for role, values in summary['received_api_responses_by_role'].items():
        require(successful[role] == values['successes'], 'API receipt count differs: '+role)
    lineage = []
    key = best.id
    while key:
        n = next(n for n in nodes if n['id'] == key)
        lineage.append({k: n.get(k) for k in ('id', 'is_buggy', 'wm_predicted_rank')})
        key = raw['node2parent'].get(key)
    return {'published_parameter_values': published['kwargs'], 'runtime_files_verified': len(hashes),
            'run_files_verified': len(anchor['run_files']), 'nodes': len(nodes),
            'executed': sum(not n['is_skipped'] for n in nodes),
            'skipped': sum(n['is_skipped'] for n in nodes), 'completed_batches': len(batches),
            'forced_execution_batches': sum(b['forced_execution'] for b in batches),
            'completed_batch_comparison_records': sum(b['comparison_records'] for b in batches),
            'completed_batch_cache_reads': sum(b['cached_reads'] for b in batches),
            'completed_batch_feedback': batch_feedback,
            'completed_batch_unique_unordered_pairs_summed': sum(b['unique_unordered_pairs'] for b in batch_feedback),
            'successful_api_receipts': dict(successful),
            'api_accounting': 'Successful receipts include the incomplete last iteration; transport failures and billable requests are distinct.',
            'upstream_and_independent_best_node': best.id, 'best_node_lineage': lineage,
            'final_submission_sha256': digest(prediction)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--run', type=Path, required=True)
    parser.add_argument('--data-root', type=Path, required=True, help='Directory containing prepared/')
    parser.add_argument('--references', type=Path, required=True, help='Downloaded author-reference directory')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    import pandas as pd
    import yaml
    source = args.source.resolve()
    result = {'scope': 'Local acceptance of original ForeAgent only', 'source': check_source(source),
              'new_model_api_calls': 0, 'new_training_runs': 0}
    competition = source/'mle-bench/mlebench/competitions/stanford-covid-vaccine'
    checksums = yaml.safe_load((competition/'checksums.yaml').read_text())
    data_hashes = {}
    for split in ('public', 'private'):
        for name, expected in checksums[split].items():
            file = args.data_root/'prepared'/split/name
            require(digest(file, 'md5') == expected, 'Prepared data differs: '+split+'/'+name)
            data_hashes[split+'/'+name] = digest(file)
    train = pd.read_json(args.data_root/'prepared/public/train.json', lines=True)
    test = pd.read_json(args.data_root/'prepared/public/test.json', lines=True)
    require(set(train['id']).isdisjoint(test['id']), 'Train/test IDs overlap')
    result['data'] = {'sha256': data_hashes, 'train_sequences': len(train),
                      'test_sequences': len(test), 'train_test_id_overlap': 0}
    summary = json.loads((ROOT/'experiments/online-stanford-v2/final-summary.json').read_text())
    result['run'] = check_run(args.run, source, summary)
    sys.path.insert(0, str(source/'mle-bench'))
    spec = importlib.util.spec_from_file_location('pinned_stanford_grader', competition/'grade.py')
    grader = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(grader)
    answer_file = args.data_root/'prepared/private/test.csv'
    answer_rows = read_csv(answer_file)
    answers = pd.read_csv(answer_file)
    reference = json.loads((ROOT/'experiments/online-stanford-v2/author-final-reference.json').read_text())
    files = [('local', args.run/'workspaces/exp/best_submission/submission.csv', summary['official_private_score'], summary['csv_sha256'])]
    files += [(r['run'], args.references/r['run']/'submission.csv', r['official_score'], r['submission_sha256']) for r in reference['runs']]
    scores = {}
    for name, file, expected, expected_hash in files:
        require(digest(file) == expected_hash, 'Reference submission differs: '+name)
        independent = score_by_id(read_csv(file), answer_rows)
        frame = pd.read_csv(file)
        official = float(grader.grade(frame, answers))
        require(math.isclose(official, independent['score'], abs_tol=1e-12, rel_tol=0), 'Official and ID-aligned scores differ: '+name)
        require(round(official, 5) == expected, 'Saved score differs: '+name)
        scores[name] = {**independent, 'official_score': official, 'sha256': expected_hash}
    result['scores'] = scores
    # Metamorphic check: predictions and labels stay fixed; vary only CSV row order.
    prediction = pd.read_csv(files[0][1])
    shuffled = prediction.sample(frac=1, random_state=42).reset_index(drop=True)
    rows = list(csv.DictReader(io.StringIO(shuffled.to_csv(index=False))))
    independent_shuffled = score_by_id(rows, answer_rows)['score']
    require(math.isclose(independent_shuffled, scores['local']['score'], abs_tol=1e-12, rel_tol=0), 'Independent scorer is order-sensitive')
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter('always')
        raw_shuffled = float(grader.grade(shuffled, answers))
    canonical = float(grader.grade(shuffled.sort_values('id_seqpos').reset_index(drop=True),
                                  answers.sort_values('id_seqpos').reset_index(drop=True)))
    require(math.isclose(canonical, independent_shuffled, abs_tol=1e-12, rel_tol=0), 'Canonical scoring differs')
    result['scorer_order_diagnostic'] = {
        'original_submission': scores['local']['official_score'], 'shuffled_upstream': raw_shuffled,
        'shuffled_id_aligned': independent_shuffled, 'canonical_upstream': canonical,
        'upstream_row_order_bug_observed': not math.isclose(raw_shuffled, independent_shuffled, abs_tol=1e-12, rel_tol=0),
        'warning_types': sorted({type(w.message).__name__ for w in caught}),
        'handling': 'Pinned scorer preserved. Frozen files agree with ID-aligned scores. Future evaluation requires ID validation and canonical ordering or explicit score agreement.'}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps({'status': 'passed_with_documented_upstream_scorer_issue',
                      'official_score': scores['local']['official_score'], 'nodes': result['run']['nodes'],
                      'author_submissions_regraded': len(scores)-1, 'output': str(args.output)}))


if __name__ == '__main__':
    main()
