"""Label-free independent readback of the sealed comparator artifacts."""
from collections import Counter
import gzip
import json
from pathlib import Path

import numpy as np

from data import ARMS, HERE, ROOT, all_pairs, inventory, load_codes, same_content, sha256, write_json


def verify():
    seal = json.loads((HERE / 'prediction_seal.json').read_text())
    predictions = ROOT / seal['predictions']
    assert sha256(predictions) == seal['predictions_sha256']
    assert sha256(HERE / 'model_spec.json') == seal['model_spec_sha256']
    embeddings_path = ROOT / seal['embeddings']
    assert sha256(embeddings_path) == seal['embeddings_sha256']
    embeddings = np.load(embeddings_path, allow_pickle=False)
    embedded_codes = dict(zip(embeddings['code_keys'].tolist(), embeddings['code']))
    embedded_tasks = dict(zip(embeddings['task_keys'].tolist(), embeddings['context']))
    codes = load_codes()
    assert inventory(codes)['code_fingerprints_sha256'] == seal['inventory']['code_fingerprints_sha256']
    with gzip.open(predictions, 'rt') as stream:
        rows = [json.loads(line) for line in stream]
    lookup = {(r['task'], r['pair']): r for r in rows}
    expected = {(task, a + '|' + b) for task in codes for a, b in all_pairs(codes[task])}
    assert len(lookup) == len(rows) and set(lookup) == expected
    counts = Counter()
    for row in rows:
        task = row['task']
        a, b = row['pair'].split('|')
        assert a < b and set(row['winners']) == set(ARMS) and set(row['ties']) == set(ARMS)
        for arm in ARMS:
            assert row['winners'][arm] in (a, b)
            assert isinstance(row['ties'][arm], bool)
            if row['ties'][arm]:
                assert row['winners'][arm] == a
            if codes[task][a]['byte_sha256'] == codes[task][b]['byte_sha256']:
                assert row['ties'][arm]
            counts[arm + '_ties'] += row['ties'][arm]
    training_pair_total = 0
    for record in seal['folds']:
        heldout = record['task']
        directory = HERE / 'folds' / heldout
        manifest = json.loads((directory / 'manifest.json').read_text())
        assert sha256(directory / 'manifest.json') == record['manifest_sha256']
        assert sha256(directory / 'training_pairs.jsonl.gz') == manifest['training_pairs_sha256']
        assert sha256(directory / 'model.npz') == manifest['model_sha256']
        assert len(manifest['training_tasks']) == 25 and heldout not in manifest['training_tasks']
        assert all(entry['task'] != heldout for entry in manifest['files_opened'])
        fingerprints = {key: {r[key] for r in codes[heldout].values()}
                        for key in ('byte_sha256', 'ast_sha256')}
        with gzip.open(directory / 'training_pairs.jsonl.gz', 'rt') as stream:
            pairs = [json.loads(line) for line in stream]
        assert len(pairs) == record['training_pairs'] == manifest['pairs']
        for pair in pairs:
            assert pair['task'] != heldout
            a, b = pair['pair'].split('|')
            left, right = codes[pair['task']][a], codes[pair['task']][b]
            assert not same_content(left, right)
            assert not any(code[key] in fingerprints[key]
                           for code in (left, right) for key in fingerprints)
        model = np.load(directory / 'model.npz', allow_pickle=False)
        task_vector = np.clip((np.asarray(embedded_tasks[heldout], dtype=np.float64)
                               - model['context_mean']) / model['context_std'], -5, 5)
        ids = sorted(codes[heldout])
        scores = {}
        for candidate in ids:
            z = np.clip((np.asarray(embedded_codes[heldout + '|' + candidate], dtype=np.float64)
                         - model['code_mean']) / model['code_std'], -5, 5)
            feature = np.concatenate((z, z * task_vector))
            scores[candidate] = {arm: float(feature @ model[arm]) for arm in ARMS}
        for a, b in all_pairs(codes[heldout]):
            row = lookup[heldout, a + '|' + b]
            for arm in ARMS:
                margin = scores[a][arm] - scores[b][arm]
                if codes[heldout][a]['byte_sha256'] == codes[heldout][b]['byte_sha256']:
                    assert abs(margin) < 1e-10
                    margin = 0.0
                assert row['winners'][arm] == (a if margin >= 0 else b)
                assert row['ties'][arm] == (margin == 0)
        for arm in ARMS:
            assert model[arm].shape == (1024,) and np.isfinite(model[arm]).all()
            assert manifest['arms'][arm]['steps'] == 80
        training_pair_total += len(pairs)
    receipt = dict(status='passed', prediction_rows=len(rows), folds=len(seal['folds']),
                   fits=seal['fits'], training_pairs_across_folds=training_pair_total,
                   ties=dict(counts), heldout_label_or_credit_files_read=False,
                   exact_ast_filter_rechecked=True,
                   prediction_seal_sha256=sha256(HERE / 'prediction_seal.json'),
                   verifier_sha256=sha256(Path(__file__)))
    write_json(HERE / 'verification.json', receipt)
    print(json.dumps(receipt))


if __name__ == '__main__':
    verify()
