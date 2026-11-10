"""Rebuild label-free GPT feedback banks on the frozen clean-ranking pair set."""
import argparse
from collections import Counter
import gzip
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from reproduction.round08.data import normalize_prediction, parse_table, verify_source
from reproduction.clean_ranking_v1.correctness import response_values


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path, obj):
    path.write_text(json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False)+'\n')


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--source-root', type=Path, required=True)
    ap.add_argument('--output', type=Path, default=Path(__file__).resolve().parent)
    args = ap.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=True)
    protocol = json.loads((ROOT/'experiments/selection-frontier-02/protocol.json').read_text())
    for name, expected in protocol['frozen_sha256'].items():
        assert sha(ROOT/name) == expected, name
    E = ROOT/'experiments/round-08'
    entries = json.loads((E/'data_manifest.json').read_text())['files']
    registered = json.loads((E/'data_validation.json').read_text())
    registered_sha = {(r['feedback_run'], r['task']): r['sha256'] for r in registered['files']}
    recovered = json.loads((E/'recovered_feedback.json').read_text())['records']
    addendum = json.loads((E/'data_addendum_registration.json').read_text())
    for name, expected in addendum['files'].items():
        assert sha(E/name) == expected, name
    ds = json.loads((ROOT/'experiments/clean-ranking-v1/prepared/feedback.json').read_text())
    code = json.loads((ROOT/'experiments/clean-ranking-v1/prepared/code_files.json').read_text())
    sources = json.loads((ROOT/'experiments/clean-ranking-v1/prepared/source_manifest.json').read_text())
    assert sum(map(len, code.values())) == 877
    assert sum(map(len, ds.values())) == 17877
    mapping = {}
    groups = {}
    by_name = {}
    for task, files in code.items():
        by_name[task] = {}
        records = []
        for cid, filename in files.items():
            digest = sha(ROOT/filename)
            assert digest == sources['sha256'][filename] and cid == digest[:20]
            name = Path(filename).name
            by_name[task][name] = cid
            records.append(dict(id=cid, filename=name, sha256=digest))
        mapping[task] = records
        gt = ROOT/'data/reward-model/corpus-6b322cb-raw-v1/solutions_subset_50'/task/'ground_truth'/f'groups_{task}_n2.json'
        assert sha(gt) == sources['sha256'][str(gt.relative_to(ROOT))]
        groups[task] = json.loads(gt.read_text())
    banks = {}
    audit = []
    anomalies = []
    legacy_tables = {}
    for entry in entries:
        run, task = entry['feedback_run'], entry['task']
        path = args.source_root/entry['target']
        digest = verify_source(entry, path)
        assert digest == registered_sha[(run, task)]
        raw = json.loads(path.read_text())
        extra = [r for r in recovered if (r['feedback_run'],r['task']) == (run,task)]
        legacy, counts = parse_table(raw, groups[task], extra)
        legacy_tables[(run,task)] = legacy
        names = {Path(p).name for g in groups[task] for p in g['paths']}
        suffix = {n[-7:]: n for n in names}
        assert len(suffix) == len(names)
        def identify(p):
            n = Path(p).name
            return n if n in names else suffix[n]
        group_index = {tuple(sorted(Path(p).name for p in g['paths'])): i for i,g in enumerate(groups[task])}
        rows = [(r, None) for r in raw['results']]
        rows += [(dict(solutions=[dict(path=n) for n in r['paths_order']], prediction={}),r) for r in extra]
        table = {}
        stats = Counter()
        for row_index, (row, recovery) in enumerate(rows):
            order_names = [identify(s['path']) for s in row['solutions']]
            if any(n not in by_name[task] for n in order_names):
                stats['excluded_nonrepresentative_or_nonfinite_pairs'] += 1
                continue
            order = [by_name[task][n] for n in order_names]
            pair = '|'.join(sorted(order))
            if pair not in ds[task]:
                stats['excluded_pair_outside_DS_admitted_set'] += 1
                continue
            assert pair not in table
            pred = row.get('prediction')
            pred = pred if isinstance(pred,dict) else {}
            raw_index = pred.get('best_index')
            # Match DS/C0's representation: absent confidence defaults to .5;
            # explicit null and malformed values stay raw for strict parsing.
            raw_confidence = pred.get('confidence', .5)
            record = dict(order=order, predicted_best_index=raw_index,
                          confidence=raw_confidence,
                          source_group_index=group_index[tuple(sorted(order_names))])
            assert record['source_group_index'] == ds[task][pair]['source_group_index']
            table[pair] = record
            idx, conf = response_values(record)
            stats['pairs'] += 1
            stats['valid_index'] += idx is not None
            stats['valid_at_07'] += idx is not None and conf >= .7
            stats['valid_at_05'] += idx is not None and conf >= .5
            stats['preserved_direction_below_07'] += idx is not None and conf < .7
            stats['recovered_original_failure'] += recovery is not None
            old = legacy[tuple(sorted(order_names))]
            old_winner = by_name[task].get(old['winner'])
            actual_winner = order[idx] if idx is not None else None
            if old_winner != actual_winner or old['confidence'] != conf:
                anomalies.append(dict(run=run,task=task,pair=pair,source_row=row_index,
                    raw_index=raw_index,raw_confidence=raw_confidence,
                    strict_C0_index=idx,strict_C0_confidence=conf,
                    legacy_winner=old_winner,legacy_confidence=old['confidence'],
                    recovered_original_failure=recovery is not None))
        assert set(table) == set(ds[task]), (run,task,len(table),len(ds[task]))
        banks.setdefault(run,{})[task] = table
        audit.append(dict(feedback_run=run,task=task,source_target=entry['target'],
                          source_sha256=digest,source_git_blob_oid=entry['git_blob_oid'],
                          source_rows=len(raw['results']), legacy_counts=counts, **dict(stats)))
    recovery_proofs = []
    recovery_checked = shared_checked = 0
    for source in json.loads((E/'recovery_sources.json').read_text())['files']:
        path = args.source_root/source['target']
        digest = verify_source(source,path)
        assert digest == source['sha256']
        task,run = source['task'],source['feedback_run']
        raw_rows = json.loads(path.read_text())[task][f'groups_{task}_n2.json']
        complete = legacy_tables[(run,task)]
        seen = set()
        for item in raw_rows:
            a,b = [Path(x).name for x in item['paths']]
            pair = tuple(sorted((a,b)))
            assert pair not in seen
            seen.add(pair)
            parsed = item.get('parsed') or {}
            actual = normalize_prediction(dict(best_index=parsed.get('predicted_best_index'),
                                               confidence=parsed.get('confidence')),a,b)
            expected = complete[pair]
            assert (actual['winner'],actual['confidence']) == (expected['winner'],expected['confidence'])
            if expected['recovered_raw']:
                rec = next(r for r in recovered if r['task']==task and tuple(r['candidate_pair'])==pair)
                assert item.get('parsed') == rec['parsed'] and item['group_index'] == rec['group_index']
                assert [Path(x).name for x in item['paths']] == rec['paths_order']
                assert hashlib.sha256(json.dumps(item,sort_keys=True,separators=(',',':')).encode()).hexdigest() == rec['raw_record_sha256']
                assert 'error' in parsed and 'predicted_best_index' not in parsed
                recovery_checked += 1
            else:
                shared_checked += 1
        assert seen == set(complete)
        recovery_proofs.append(dict(task=task,source_target=source['target'],sha256=digest,rows=len(raw_rows)))
    assert recovery_checked == 8 and shared_checked == 5099
    outputs = {}
    for run,bank in banks.items():
        assert sum(map(len,bank.values())) == 17877
        content = (json.dumps(bank,sort_keys=True,separators=(',',':'),allow_nan=False)+'\n').encode()
        dest = out/(run+'.json.gz')
        dest.write_bytes(gzip.compress(content,mtime=0))
        assert json.loads(gzip.decompress(dest.read_bytes())) == bank
        stats = Counter()
        for rec in audit:
            if rec['feedback_run'] == run:
                stats.update({k:rec.get(k,0) for k in ['pairs','valid_index','valid_at_07','valid_at_05','preserved_direction_below_07','recovered_original_failure']})
        outputs[run] = dict(path=str(dest.relative_to(ROOT)),sha256=sha(dest),
            uncompressed_sha256=hashlib.sha256(content).hexdigest(),tasks=len(bank),**dict(stats))
    write(out/'mapping_audit.json',dict(candidate_count=877,pair_count_per_bank=17877,
        candidates=mapping,files=audit,recovery_proofs=recovery_proofs,
        recovered_failures_verified=recovery_checked,shared_backup_records_verified=shared_checked,
        legacy_parser_differences=anomalies,
        legacy_parser_findings=dict(direction_below_threshold_preserved=True,
            fabricated_default_winner=False,
            normalization='Legacy accepts numeric 0/1 incl float, uses .5 on absent/null/unparseable confidence, and suppresses confidence to 0 for invalid index. Bank retains raw fields under C0 strict parsing.')))
    write(out/'manifest.json',dict(status='passed',banks=outputs,source_root=str(args.source_root),
        builder_sha256=sha(Path(__file__)),mapping_audit_sha256=sha(out/'mapping_audit.json'),
        schema='[task][sorted_id_a|sorted_id_b] -> {order, predicted_best_index, confidence, source_group_index}',
        labels_in_bank=False,source_files_verified=78,recovery_files_verified=6,
        frozen_inputs={k:sha(ROOT/k) for k in protocol['frozen_sha256']},new_model_calls=0))
    print(json.dumps(dict(banks=outputs,parser_differences=len(anomalies),recovery_checked=recovery_checked)))


if __name__ == '__main__':
    main()
