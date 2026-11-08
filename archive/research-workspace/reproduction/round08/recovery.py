"""Re-audit the six raw backups supporting the eight recovered original failures."""
import argparse
import hashlib
import json
from pathlib import Path
import ssl
import sys
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from reproduction.round08.data import check_registration, load_groups, load_table, normalize_prediction, verify_source
E = ROOT/'experiments/round-08'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fetch', action='store_true')
    parser.add_argument('--output', type=Path, default=ROOT/'runs/round08-raw-recovery')
    args = parser.parse_args(); check_registration()
    try:
        import certifi
        context = ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        context = ssl.create_default_context()
    sources = json.loads((E/'recovery_sources.json').read_text())['files']
    recovered = json.loads((E/'recovered_feedback.json').read_text())['records']
    primary = json.loads((E/'data_manifest.json').read_text())['files']
    groups = load_groups(); proofs = []; recovered_checked = 0
    for source in sources:
        path = ROOT/source['target']
        if not path.exists():
            assert args.fetch, 'Use --fetch to obtain the registered raw source'
            path.parent.mkdir(parents=True, exist_ok=True); temp = path.with_suffix('.part')
            with urllib.request.urlopen(source['url'], context=context, timeout=180) as response, temp.open('wb') as f:
                while chunk := response.read(1024*1024): f.write(chunk)
            verify_source(source, temp); temp.replace(path)
        digest = verify_source(source, path); assert digest == source['sha256']
        task = source['task']; run = source['feedback_run']
        entry = next(e for e in primary if (e['feedback_run'], e['task']) == (run, task))
        complete, _ = load_table(entry, groups[task])
        raw_rows = json.loads(path.read_text())[task][f'groups_{task}_n2.json']
        by_pair = {}; shared = 0
        for item in raw_rows:
            a, b = [Path(x).name for x in item['paths']]; pair = tuple(sorted((a, b)))
            assert pair not in by_pair; by_pair[pair] = item
            parsed = item.get('parsed') or {}
            normalized = normalize_prediction({'best_index': parsed.get('predicted_best_index'),
                                                'confidence': parsed.get('confidence')}, a, b)
            expected = complete[pair]
            assert (normalized['winner'], normalized['confidence']) == (expected['winner'], expected['confidence'])
            if expected['recovered_raw']:
                record = next(r for r in recovered if r['task'] == task and tuple(r['candidate_pair']) == pair)
                assert item.get('parsed') == record['parsed'] and '20251210' in record['parsed']['error']
                assert item['group_index'] == record['group_index']
                assert hashlib.sha256(json.dumps(item, sort_keys=True, separators=(',', ':')).encode()).hexdigest() == record['raw_record_sha256']
                recovered_checked += 1
            else:
                shared += 1
        assert set(by_pair) == set(complete)
        proofs.append(dict(task=task, sha256=digest, raw_records=len(raw_rows), matching_shared_records=shared))
    assert recovered_checked == 8 and sum(p['matching_shared_records'] for p in proofs) == 5099
    result = dict(status='passed', raw_source_files=6, recovered_original_failures_checked=recovered_checked,
                  matching_shared_alignment_records=5099, proofs=proofs, new_model_calls=0)
    out = args.output.resolve(); assert not out.exists(), 'Preserve prior audit output'
    out.mkdir(parents=True); (out/'verification.json').write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
