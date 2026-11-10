"""Independent post-seal reconstruction of dataset membership, scalers and held-out winners."""
import argparse
import ast
from collections import Counter
import hashlib
from itertools import combinations
from pathlib import Path
import warnings
import numpy as np

from replay import ARMS, EXP, PREP, PRED, PRED_SEAL, ROOT, TRAIN, checked, frozen, read, records, require, sha, write


def main(out):
    protocol = frozen()
    selection = read(out/'selection_seal.json')
    checked(out/'decisions.sealed.jsonl.gz', selection['decisions_sha256'])
    checked(PRED_SEAL, selection['prediction_seal_sha256'])
    seal = read(PRED_SEAL)
    require(seal['fits'] == 104, 'Incomplete training seal')
    checked(PRED, seal['predictions_sha256'])
    model_spec = read(checked(TRAIN/'model_spec.json', seal['model_spec_sha256']))
    credit_dir = EXP/'credit/run_1'
    credit_seal = read(checked(credit_dir/'receipt.json', seal['credit_receipt_sha256']))
    hashes = credit_seal['task_weight_sha256']
    for name, value in seal['source_sha256'].items():
        checked(TRAIN/name, value)
    feats = np.load(checked(EXP/'representation/run_1/embeddings.npz', seal['embeddings_sha256']), allow_pickle=False)
    code = {k:v.astype('float64') for k,v in zip(feats['code_keys'].tolist(),feats['code'],strict=True)}
    context = {k:v.astype('float64') for k,v in zip(feats['task_keys'].tolist(),feats['context'],strict=True)}
    grid = {task:{} for task in hashes}
    for r in records(PRED):
        grid[r['task']][r['pair']] = r
    # This verifier may open every label after the replay has been sealed.
    label_path = PREP/'evaluation_labels.json'
    labels = read(checked(label_path, protocol['inputs'][str(label_path.relative_to(ROOT))]))
    bank = read(PREP/'feedback.json')
    files = read(PREP/'code_files.json')
    rep = EXP/'representation/run_1'
    rep_seal = read(rep/'receipt.json')
    require(rep_seal['feature_sha256'] == seal['embeddings_sha256'] and rep_seal['model_training'] is False
            and rep_seal['revision'] == model_spec['encoder_revision'], 'Frozen encoder lineage')
    checked(rep/'encode.snapshot.py', sha(EXP/'representation/encode.py'))
    raw_context = ROOT/'data/reward-model/corpus-6b322cb-raw-v1/tasks'
    expected = {('code',task+'|'+cid): {path} for task, entries in files.items() for cid,path in entries.items()}
    for task in files:
        paths = set()
        for directory,prefix,suffix in [('description','description_','.md'),('data_analysis/result','da_result_','.txt')]:
            source = next(raw_context/directory/(prefix+key+suffix) for key in (task.replace('-','_'),task)
                          if (raw_context/directory/(prefix+key+suffix)).is_file())
            paths.add(str(source.relative_to(ROOT)))
        expected['context',task] = paths
    provenance = read(rep/'inputs.json')
    require(len(provenance) == len(expected), 'Wrong document count')
    for d in provenance:
        require(set(d['source']) == expected.pop((d['kind'],d['key'])), 'Unexpected embedding source')
        for name,digest in d['source'].items():
            checked(ROOT/name, digest)
    require(not expected, 'Missing embedding source')
    prints = {}
    strict = {}
    missing = {}
    for task, paths in files.items():
        prints[task] = {}
        for cid, path in paths.items():
            source = (ROOT/path).read_bytes()
            require(hashlib.sha256(source).hexdigest()[:20] == cid, 'Code digest')
            with warnings.catch_warnings():
                warnings.simplefilter('ignore', SyntaxWarning)
                syntax = ast.dump(ast.parse(source.decode()), include_attributes=False)
            prints[task][cid] = (cid, hashlib.sha256(syntax.encode()).hexdigest())
        credit = read(checked(credit_dir/'tasks'/f'{task}.json', hashes[task]))
        require(credit.keys()==bank[task].keys(), 'Credit/frozen eligible pair mismatch')
        for key, record in credit.items():
            a,b = key.split('|')
            require(labels[task][a] != labels[task][b] and record['winner']==max((a,b), key=labels[task].get),
                    'Frozen execution direction mismatch')
        strict[task] = {p for p in credit if prints[task][p.split('|')[0]][1] != prints[task][p.split('|')[1]][1]}
        missing[task] = Counter()
        for a,b in combinations(sorted(paths), 2):
            if a+'|'+b not in credit:
                missing[task]['no_archived_pair'] += 1
                if labels[task][a] != labels[task][b]:
                    missing[task]['strict_unarchived'] += 1
    folds = []
    for ref in seal['folds']:
        task = ref['task']
        fold = TRAIN/'folds'/task
        receipt = read(checked(fold/'manifest.json',ref['manifest_sha256']))
        other = set(files) - {task}
        require(set(receipt['training_tasks']) == set(receipt['scaler_training_tasks']) == other, 'Held-out task leak')
        opened = {r['task']: (r['path'], r['sha256']) for r in receipt['files_opened']}
        require(opened == {t:(str((credit_dir/'tasks'/f'{t}.json').relative_to(ROOT)),hashes[t]) for t in other},
                'Opened label/credit files mismatch')
        held = {sig for pair in prints[task].values() for sig in pair}
        admissible = {(t,p) for t in other for p in strict[t] if not any(
            fp in held for cid in p.split('|') for fp in prints[t][cid])}
        entries = list(records(checked(fold/'training_pairs.jsonl.gz', receipt['training_pairs_sha256'])))
        samples = {(r['task'],r['pair']) for r in entries}
        require(samples == admissible and len(entries) == len(samples) == receipt['pairs'], 'Fold membership mismatch')
        train_keys = sorted({t+'|'+cid for t,p in samples for cid in p.split('|')})
        model = np.load(checked(fold/'model.npz',receipt['model_sha256']), allow_pickle=False)
        for key, array in (('code',np.array([code[k] for k in train_keys])),
                           ('context',np.array([context[t] for t in sorted(other)]))):
            require(np.array_equal(array.mean(axis=0),model[key+'_mean']) and
                    np.array_equal(np.maximum(array.std(axis=0),1e-6),model[key+'_std']), 'Training-only scaler')
        ids = sorted(files[task])
        z = np.clip((np.array([code[task+'|'+cid] for cid in ids])-model['code_mean'])/model['code_std'], -5, 5)
        ctx = np.clip((context[task]-model['context_mean'])/model['context_std'], -5, 5)
        x = np.concatenate([z,z*ctx],axis=1)
        count = 0
        for arm in ARMS:
            scores = x @ model[arm]
            require(np.isfinite(scores).all() and receipt['arms'][arm]['steps'] == model_spec['steps'], 'Invalid head')
            for i,j in combinations(range(len(ids)),2):
                a,b = ids[i],ids[j]
                r = grid[task][a+'|'+b]
                tie = scores[i] == scores[j]
                winner = a if scores[i] >= scores[j] else b
                require(r['ties'][arm] == tie and r['winners'][arm] == winner, f'Sealed score mismatch: {task}/{a}/{b}/{arm}')
                count += 1
        folds.append(dict(task=task, train_rows=len(samples), same_ast_training_rows_excluded=sum(len(bank[t])-len(strict[t]) for t in other),
                          heldout_overlap_removed=sum(len(strict[t]) for t in other)-len(samples), verified_winners=count))
    require(len(folds)==26 and sum(f['verified_winners'] for f in folds)==4*18224, 'Incomplete audit')
    write(out/'fold_audit.json', dict(status='passed', checked_all_folds=folds, prediction_seal_sha256=sha(PRED_SEAL),
        verified_winner_tie_decisions=sum(f['verified_winners'] for f in folds), original_credit_directions=sum(map(len,bank.values())),
        absent_from_archived_feedback_by_task=missing, model_spec_sha256=seal['model_spec_sha256'],
        verified_embedding_source_documents=len(provenance), verified_archived_directions=True, reconstructed_train_membership=True, recomputed_scalers=True,
        exact_per_fold_weight_file_hashes=True, residual='Canonical AST equality retains literal values and identifiers; edited code can cross tasks.'))
    print('26 folds, training-only scalers, and 72,896 held-out winner/tie decisions independently verified')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    main(parser.parse_args().output)
