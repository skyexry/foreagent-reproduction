"""Fetch and structurally validate the 78 feedback tables registered for R8."""
import argparse
from collections import Counter
import concurrent.futures
import datetime
import hashlib
import json
import math
from pathlib import Path
import ssl
import subprocess
import tempfile
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
E = ROOT/'experiments/round-08'


def check_registration():
    reg = json.loads((E/'registration.json').read_text())
    for name, digest in reg['files'].items():
        assert hashlib.sha256((E/name).read_bytes()).hexdigest() == digest, name
    commit = subprocess.check_output(['git', 'log', '-1', '--format=%H', '--',
                       'experiments/round-08/registration.json'], cwd=ROOT, text=True).strip()
    subprocess.run(['git', 'merge-base', '--is-ancestor', commit, 'HEAD'], cwd=ROOT, check=True)
    for name, digest in reg['files'].items():
        content = subprocess.check_output(['git', 'show', commit+':experiments/round-08/'+name], cwd=ROOT)
        assert hashlib.sha256(content).hexdigest() == digest
    addendum_path = E/'data_addendum_registration.json'
    if addendum_path.exists():
        addendum = json.loads(addendum_path.read_text())
        extra_commit = subprocess.check_output(['git', 'log', '-1', '--format=%H', '--',
                         'experiments/round-08/data_addendum_registration.json'], cwd=ROOT, text=True).strip()
        subprocess.run(['git', 'merge-base', '--is-ancestor', extra_commit, 'HEAD'], cwd=ROOT, check=True)
        for name, expected in addendum['files'].items():
            assert hashlib.sha256((E/name).read_bytes()).hexdigest() == expected
            registered = subprocess.check_output(['git', 'show', extra_commit+':experiments/round-08/'+name], cwd=ROOT)
            assert hashlib.sha256(registered).hexdigest() == expected
    return commit


def verify_source(entry, path):
    data = path.read_bytes()
    assert len(data) == entry['bytes'], (entry['task'], 'size')
    if entry.get('lfs'):
        lfs = entry['lfs']; expected = lfs.get('oid') or lfs.get('sha256')
        assert hashlib.sha256(data).hexdigest() == expected, (entry['task'], 'LFS hash')
    else:
        blob = b'blob '+str(len(data)).encode()+b'\0'+data
        assert hashlib.sha1(blob).hexdigest() == entry['git_blob_oid'], (entry['task'], 'Git blob hash')
    return hashlib.sha256(data).hexdigest()


def normalize_prediction(pred, a, b):
    pred = pred if isinstance(pred, dict) else {}
    index = pred.get('best_index')
    valid_index = isinstance(index, (int, float)) and not isinstance(index, bool) and index in (0, 1)
    raw = pred.get('confidence'); fallback = raw is None
    try:
        confidence = float(raw)
    except (TypeError, ValueError):
        confidence = .5; fallback = True
    assert math.isfinite(confidence) and 0 <= confidence <= 1, 'Nonfinite/out-of-range confidence'
    return dict(winner=(a, b)[int(index)] if valid_index else None,
                confidence=confidence if valid_index else 0., confidence_fallback=fallback,
                invalid_winner=not valid_index)


def parse_table(raw, groups, recovered=()):
    names = {Path(path).name for group in groups for path in group['paths']}
    suffixes = {name[-7:]: name for name in names}
    assert len(suffixes) == len(names), 'Ambiguous candidate suffixes'
    edges = {tuple(sorted(Path(path).name for path in group['paths'])) for group in groups}
    def identity(path):
        name = Path(path).name
        if name in names:
            return name
        assert name in suffixes, ('Unknown candidate identity', name)
        return suffixes[name]
    rows = raw.get('results') if isinstance(raw, dict) else raw
    assert isinstance(rows, list), 'Expected alignment results'
    rows = list(rows)
    original_count = len(rows)
    for record in recovered:
        assert 'error' in record['parsed'] and record['normalized']['invalid_winner']
        rows.append(dict(solutions=[dict(path=x) for x in record['paths_order']], prediction={},
                         recovered_record=record))
    table = {}; counts = Counter()
    for index, row in enumerate(rows):
        assert isinstance(row, dict) and len(row['solutions']) == 2
        a, b = [identity(s['path']) for s in row['solutions']]
        assert a != b
        pair = tuple(sorted((a, b)))
        assert pair in edges and pair not in table, 'Duplicate or unknown unordered pair'
        result = normalize_prediction(row.get('prediction'), a, b)
        table[pair] = {**result, 'author_row': index, 'recovered_raw': index >= original_count}
        if index >= original_count:
            record = row['recovered_record']
            assert pair == tuple(record['candidate_pair'])
            assert {k: result[k] for k in record['normalized']} == record['normalized']
            table[pair]['raw_group_index'] = record['group_index']
        counts['raw_recovered_records'] += index >= original_count
        counts['pairs'] += 1
        counts['invalid_winner'] += result['invalid_winner']
        counts['confidence_fallback'] += result['confidence_fallback']
        counts['valid_at_07'] += result['winner'] is not None and result['confidence'] >= .7
    assert set(table) == edges, ('Pair coverage mismatch', len(table), len(edges))
    return table, dict(counts)


def load_table(entry, groups):
    path = ROOT/entry['target']; digest = verify_source(entry, path)
    extra_path = E/'recovered_feedback.json'
    extra = [r for r in json.loads(extra_path.read_text())['records']
             if (r['feedback_run'], r['task']) == (entry['feedback_run'], entry['task'])] if extra_path.exists() else []
    table, counts = parse_table(json.loads(path.read_text()), groups, extra)
    return table, dict(feedback_run=entry['feedback_run'], task=entry['task'], sha256=digest,
                       bytes=path.stat().st_size, source_git_blob_oid=entry['git_blob_oid'], **counts)


def load_groups():
    corpus = json.loads((ROOT/'experiments/corpus26-v2/protocol.json').read_text())
    groups = {}
    for t in corpus['tasks']:
        task = t['task']; p = ROOT/f'data/coverage/solutions_subset_50/{task}/ground_truth/groups_{task}_n2.json'
        assert hashlib.sha256(p.read_bytes()).hexdigest() == t['source']['ground_truth_sha256']
        groups[task] = json.loads(p.read_text())
    return groups


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--fetch', action='store_true')
    p.add_argument('--output', type=Path, default=ROOT/'runs/round08-data-validation')
    args = p.parse_args(); protocol_commit = check_registration()
    entries = json.loads((E/'data_manifest.json').read_text())['files']
    assert len(entries) == 78
    if args.fetch:
        try:
            import certifi
            context = ssl.create_default_context(cafile=certifi.where())
        except ImportError:
            context = ssl.create_default_context()
        def fetch(e):
            dst = ROOT/e['target']
            if dst.exists():
                verify_source(e, dst); return
            dst.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(dir=dst.parent, suffix='.part', delete=False) as f:
                temp = Path(f.name)
            try:
                last_error = None
                for attempt in range(3):
                    try:
                        with urllib.request.urlopen(e['url'], context=context, timeout=180) as response, temp.open('wb') as out:
                            while chunk := response.read(1024*1024): out.write(chunk)
                        verify_source(e, temp); temp.replace(dst); return
                    except Exception as exc:
                        last_error = exc
                raise last_error
            finally:
                temp.unlink(missing_ok=True)
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(fetch, entries))
    groups = load_groups(); records = []; pooled = {}
    for entry in entries:
        _, record = load_table(entry, groups[entry['task']]); records.append(record)
        counts = pooled.setdefault(entry['feedback_run'], Counter())
        counts['files'] += 1
        for key in ['pairs', 'invalid_winner', 'confidence_fallback', 'valid_at_07', 'raw_recovered_records']:
            counts[key] += record[key]
    extra_commit = subprocess.check_output(['git', 'log', '-1', '--format=%H', '--',
                         'experiments/round-08/data_addendum_registration.json'], cwd=ROOT, text=True).strip()
    result = dict(status='passed', protocol_commit=protocol_commit, data_source_addendum_commit=extra_commit,
                  recovered_original_api_failures=sum(r['raw_recovered_records'] for r in records),
                  files_verified=len(records),
                  bytes_verified=sum(e['bytes'] for e in entries),
                  checked_at_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                  by_feedback_run={k: dict(v) for k, v in pooled.items()}, files=records,
                  new_model_calls=0, candidate_training_runs=0,
                  scope='Structure, source hashes and coverage only; no method outcome evaluation.')
    out = args.output.resolve(); assert not out.exists(), 'Preserve previous validation output'
    out.mkdir(parents=True)
    (out/'validation.json').write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps({k: v for k, v in result.items() if k != 'files'}), flush=True)


if __name__ == '__main__':
    main()
