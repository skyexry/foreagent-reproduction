"""Inventory existing RM inputs without modifying data or fitting a model."""
import ast
from collections import Counter, defaultdict
import gzip
import hashlib
import json
import math
from pathlib import Path
import statistics
import sys
import warnings

root = Path(sys.argv[1]).resolve()
out = Path(sys.argv[2])
base = root / 'data/coverage/solutions_subset_50'
inputs = {}
codes = {}
raw_hashes = defaultdict(list)
ast_hashes = defaultdict(list)
ast_errors = []
tasks = []
candidate_scores = defaultdict(set)
labels_wrong = []
content_pairs = defaultdict(list)
finite_candidate_ids = set()


def read(path):
    data = path.read_bytes()
    inputs[str(path.relative_to(root))] = hashlib.sha256(data).hexdigest()
    return data


def code_key(task, source):
    return (task, Path(source).name)


for file in sorted(base.glob('*/ground_truth/*n2.json')):
    task = file.parents[1].name
    groups = json.loads(read(file))
    ids = {code_key(task, p) for g in groups for p in g['paths']}
    for key in sorted(ids):
        path = base / task / 'code' / key[1]
        if not path.is_file():
            continue
        data = read(path)
        text = data.decode('utf-8')
        codes[key] = text
        raw_hashes[hashlib.sha256(data).hexdigest()].append(key)
        try:
            with warnings.catch_warnings():
                warnings.simplefilter('ignore', SyntaxWarning)
                canonical = ast.dump(ast.parse(text), include_attributes=False)
            ast_hashes[hashlib.sha256(canonical.encode()).hexdigest()].append(key)
        except (SyntaxError, ValueError):
            ast_errors.append(key)
    stats = Counter()
    seen_pairs = Counter()
    for i, g in enumerate(groups):
        keys = [code_key(task, p) for p in g['paths']]
        scores = [float(s) for s in g['scores']]
        finite = all(math.isfinite(s) for s in scores)
        complete = all(k in codes for k in keys)
        stats['pairs'] += 1
        stats['finite_pairs'] += finite
        stats['both_codes_available'] += complete
        stats['finite_both_codes_available'] += finite and complete
        stats['first_position_wins'] += g['best_index'] == 0
        seen_pairs[tuple(sorted(keys))] += 1
        for key, score in zip(keys, scores):
            candidate_scores[key].add(str(score))
        if finite:
            finite_candidate_ids.update(keys)
            expected = min(range(2), key=scores.__getitem__) if g['is_lower_better'] else max(range(2), key=scores.__getitem__)
            stats['exact_score_ties'] += scores[0] == scores[1]
            if scores[0] != scores[1] and expected != g['best_index']:
                labels_wrong.append({'task': task, 'group_index': i})
            if complete:
                hashes = [hashlib.sha256(codes[k].encode()).hexdigest() for k in keys]
                content_pairs[(task, *sorted(hashes))].append({'group_index': i, 'winner_hash': hashes[g['best_index']], 'winner_index': g['best_index']})
    description = root / 'data/coverage/tasks/description' / ('description_' + task.replace('-', '_') + '.md')
    report = root / 'data/coverage/tasks/data_analysis/result' / ('da_result_' + task + '.txt')
    for path in (description, report):
        if path.is_file():
            read(path)
    stats['candidate_ids'] = len(ids)
    stats['available_code_files'] = sum(k in codes for k in ids)
    stats['duplicate_unordered_pair_rows'] = sum(n - 1 for n in seen_pairs.values())
    tasks.append({'task': task, **dict(stats), 'description_available': description.is_file(), 'report_available': report.is_file()})

raw_set = set(raw_hashes)
journals = []
paths = sorted((root / 'data/historical/source_records').glob('*/journal.json.gz'))
paths += [root / 'phase1-reproduction/records/stanford-autodl-v2/logs/exp/journal.json']
for path in paths:
    if not path.is_file():
        continue
    data = read(path)
    document = json.loads(gzip.decompress(data) if path.suffix == '.gz' else data)
    nodes = document['nodes']
    usable = []
    for node in nodes:
        value = (node.get('metric') or {}).get('value')
        if not node.get('is_skipped') and not node.get('is_buggy') and isinstance(value, (int, float)) and math.isfinite(value):
            usable.append(node)
    journals.append({'path': str(path.relative_to(root)), 'nodes': len(nodes), 'executed_finite_nonbuggy_nodes': len(usable), 'exact_code_overlap_with_available_corpus': sum(hashlib.sha256(n['code'].encode()).hexdigest() in raw_set for n in usable), 'metric_semantics': 'recorded internal metric; private test labels require a separate verified join'})

manifest = json.loads(read(root / 'data/coverage/manifest.json'))
lengths = sorted(map(len, codes.values()))
totals = {key: sum(t.get(key, 0) for t in tasks) for key in ['pairs', 'finite_pairs', 'candidate_ids', 'available_code_files', 'both_codes_available', 'finite_both_codes_available', 'first_position_wins', 'duplicate_unordered_pair_rows', 'exact_score_ties']}
result = {
    'audit_id': 'forecritic-rm-readiness-20261108-v1',
    'scope': 'Read-only inventory; code availability reflects the earlier sampled download. Pair counts share candidates and tasks. No split, fitting, GPU job, or model request executed.',
    'upstream_commit': manifest['upstream_commit'],
    'dataset_revision': manifest['dataset_revision'],
    'new_model_calls': 0, 'new_training_runs': 0,
    'totals': {'tasks': len(tasks), **totals, 'finite_candidate_ids': len(finite_candidate_ids), 'nonfinite_pairs': totals['pairs'] - totals['finite_pairs'], 'missing_candidate_code_files': totals['candidate_ids'] - totals['available_code_files'], 'descriptions': sum(t['description_available'] for t in tasks), 'reports': sum(t['report_available'] for t in tasks)},
    'code_lengths_characters': {'minimum': lengths[0], 'median': statistics.median(lengths), 'maximum': lengths[-1], 'note': 'Characters, not tokenizer tokens; available subset only.'},
    'exact_distinct_code_contents': len(raw_hashes),
    'exact_duplicate_code_groups': [v for v in raw_hashes.values() if len(v) > 1],
    'exact_duplicate_code_score_records': [[{'task': k[0], 'filename': k[1], 'scores': sorted(candidate_scores[k])} for k in v] for v in raw_hashes.values() if len(v) > 1],
    'duplicate_content_pair_groups': [{'task': k[0], 'rows': v, 'same_code_both_sides': k[1] == k[2], 'conflicting_winner_code': len({r['winner_hash'] for r in v}) > 1} for k, v in content_pairs.items() if len(v) > 1 or k[1] == k[2]],
    'ast_distinct_parseable_codes': len(ast_hashes),
    'ast_duplicate_code_groups': [v for v in ast_hashes.values() if len(v) > 1],
    'ast_parse_errors': ast_errors,
    'candidate_ids_with_inconsistent_recorded_scores': [k for k, values in candidate_scores.items() if len(values) > 1],
    'finite_nontied_label_direction_mismatches': labels_wrong,
    'per_task': tasks,
    'journals': journals,
    'source_sha256': dict(sorted(inputs.items())),
}
out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
print(json.dumps({k: result[k] for k in ['audit_id', 'totals', 'code_lengths_characters', 'exact_distinct_code_contents', 'ast_distinct_parseable_codes']}, ensure_ascii=False, indent=2))
print('journals', len(journals), 'finite_internal_nodes', sum(j['executed_finite_nonbuggy_nodes'] for j in journals))
print('integrity', {'direction_mismatches': len(labels_wrong), 'inconsistent_candidate_scores': len(result['candidate_ids_with_inconsistent_recorded_scores']), 'ast_errors': len(ast_errors)})
