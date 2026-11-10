"""Task-isolated training input and label-free code fingerprints.

The held-out task's credit file is never opened by ``load_fold``.  Code
fingerprints may be inspected across tasks solely for duplicate filtering.
"""
import ast
from collections import Counter
import gzip
import hashlib
import itertools
import json
from pathlib import Path
import warnings

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
EXPERIMENT = HERE.parent
ARMS = ('uniform', 'gap', 'terminal', 'shuffled')


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def object_sha256(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def write_json(path, value):
    Path(path).write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')


def write_jsonl_gz(path, rows):
    # Stable gzip headers, including the original filename, matter to sealing.
    with Path(path).open('wb') as raw:
        with gzip.GzipFile(filename='', fileobj=raw, mode='wb', mtime=0) as out:
            for row in rows:
                out.write((json.dumps(row, sort_keys=True, separators=(',', ':')) + '\n').encode())


def load_codes():
    source = ROOT / 'experiments/clean-ranking-v1/prepared/code_files.json'
    paths = json.loads(source.read_text())
    result = {}
    for task, entries in sorted(paths.items()):
        result[task] = {}
        for candidate, relative in sorted(entries.items()):
            path = ROOT / relative
            raw = path.read_bytes()
            text = raw.decode('utf-8')
            with warnings.catch_warnings():
                warnings.simplefilter('ignore', SyntaxWarning)
                canonical = ast.dump(ast.parse(text), include_attributes=False)
            result[task][candidate] = dict(
                text=text, byte_sha256=hashlib.sha256(raw).hexdigest(),
                ast_sha256=hashlib.sha256(canonical.encode()).hexdigest(),
                bytes=len(raw))
    return result


def same_content(left, right):
    return any(left[k] == right[k] for k in ('byte_sha256', 'ast_sha256'))


def all_pairs(codes):
    return list(itertools.combinations(sorted(codes), 2))


def load_fold(heldout, codes, credit_directory, expected_sha256=None):
    """Load strict supervised pairs from other tasks with explicit dedup audit."""
    assert heldout in codes
    blocked = {k: {v[k] for v in codes[heldout].values()}
               for k in ('byte_sha256', 'ast_sha256')}
    rows = []
    opened = []
    counts = {}
    for task in sorted(codes):
        if task == heldout:
            continue
        source = Path(credit_directory) / (task + '.json')
        if expected_sha256 is not None:
            assert sha256(source) == expected_sha256[task], (task, 'credit hash mismatch')
        pairs = json.loads(source.read_text())
        opened.append(dict(task=task, path=str(source.relative_to(ROOT)), sha256=sha256(source)))
        count = Counter(credit_rows=len(pairs))
        for pair, record in sorted(pairs.items()):
            a, b = pair.split('|')
            assert a < b and a in codes[task] and b in codes[task]
            if same_content(codes[task][a], codes[task][b]):
                count['same_content_removed'] += 1
                continue
            if any(codes[task][candidate][key] in blocked[key]
                   for candidate in (a, b) for key in blocked):
                count['heldout_content_removed'] += 1
                continue
            winner = record['winner']
            assert winner in (a, b)
            weights = {'uniform': 1.0, **{arm: float(record[arm]) for arm in ARMS[1:]}}
            assert all(1 <= v <= 2 + 1e-12 for v in weights.values())
            rows.append(dict(task=task, pair=pair, a=a, b=b, label=int(winner == a),
                             weights=weights))
            count['retained'] += 1
        assert count['retained'] > 0, task
        counts[task] = dict(count)
    assert heldout not in {r['task'] for r in rows}
    assert heldout not in {r['task'] for r in opened}
    # Every task has total sample weight one before the mean across tasks.
    task_counts = Counter(row['task'] for row in rows)
    for arm in ARMS:
        totals = Counter()
        for row in rows:
            totals[row['task']] += row['weights'][arm]
        for row in rows:
            row['weights'][arm] /= totals[row['task']]
        for task in task_counts:
            assert abs(sum(r['weights'][arm] for r in rows if r['task'] == task) - 1) < 1e-10
    ids = [dict(task=r['task'], pair=r['pair']) for r in rows]
    return rows, dict(heldout=heldout, training_tasks=sorted(task_counts),
                      files_opened=opened, counts_by_task=counts, pairs=len(rows),
                      pair_ids_sha256=object_sha256(ids),
                      heldout_credit_opened=False, task_weight_total_per_arm=1.0)


def inventory(codes):
    flat = [v for task in codes.values() for v in task.values()]
    cross = {}
    for key in ('byte_sha256', 'ast_sha256'):
        groups = {}
        for task, entries in codes.items():
            for candidate, row in entries.items():
                groups.setdefault(row[key], []).append((task, candidate))
        cross[key] = [v for v in groups.values() if len({x[0] for x in v}) > 1]
    fingerprints = {task: {candidate: {k: row[k] for k in ('byte_sha256', 'ast_sha256')}
                           for candidate, row in entries.items()} for task, entries in codes.items()}
    return dict(tasks=len(codes), codes=len(flat), code_bytes=sum(v['bytes'] for v in flat),
                code_fingerprints_sha256=object_sha256(fingerprints),
                all_inference_pairs=sum(len(all_pairs(v)) for v in codes.values()),
                exact_or_ast_cross_task_groups=cross,
                task_candidate_counts={k: len(v) for k, v in codes.items()},
                policy='Remove same-content supervised pairs and training pairs with either code byte/AST-identical to any heldout code; predict all heldout pairs.',
                residual_risk='AST identity retains identifiers and literal values; renamed or structurally edited near-duplicates can remain.')


if __name__ == '__main__':
    value = inventory(load_codes())
    write_json(HERE / 'code_inventory.json', value)
    print(json.dumps({k: v for k, v in value.items() if k != 'task_candidate_counts'}))
