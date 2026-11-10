"""Frozen four-arm, leave-one-task-out comparator; no outcome-based tuning."""
import os
for _key in ('OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS', 'OMP_NUM_THREADS', 'VECLIB_MAXIMUM_THREADS', 'NUMEXPR_NUM_THREADS'):
    os.environ[_key] = '1'

import argparse
from collections import Counter
import json
from pathlib import Path
import platform
import time

import numpy as np
import scipy
from scipy.special import expit

from data import (ARMS, EXPERIMENT, HERE, ROOT, all_pairs, inventory, load_codes,
                  load_fold, object_sha256, same_content, sha256, write_json, write_jsonl_gz)


SPEC = dict(
    id='trajectory-weighted-judge-v1-encoder-linear-v1',
    representation='Salesforce/CodeT5-small frozen encoder',
    encoder_revision='b1ee9570c289f21b5922b9c768a1ce12957bf968',
    embedding_dimension=512, parameter_count=1024,
    feature='concat(standardized_code, standardized_code * standardized_task_context)',
    scaler='code per-dimension mean/std on unique retained training candidates; context on unique training tasks; population std floor 1e-6; each standardized vector clipped [-5,5] before interaction',
    score='dot(theta,feature); no intercept; p(a wins)=sigmoid(score(a)-score(b))',
    initialization='all zeros, separately identical for every arm and fold',
    loss='mean across training tasks of within-task arm-weighted binary cross entropy + 0.001*||theta||^2/2',
    samples='finite strict pairs from credit; same byte/AST pairs removed; any training pair sharing either code byte/AST with any heldout candidate removed',
    steps=80, optimizer='full-batch Adam', learning_rate=0.02,
    beta1=0.9, beta2=0.999, epsilon=1e-8, l2=0.001,
    arms=list(ARMS), threads=1, dtype='float64',
    tie_rule='exact zero score difference chooses lexicographically first candidate; ties are explicitly recorded',
    feature_access='code and task-context embeddings only; IDs serve indexing and tie-breaking; no source names, outcomes, weights, confidence, origins or costs in features',
    validation='26 outer leave-one-task-out folds; no validation-set early stopping or hyperparameter selection; identical samples/scalers/steps/init across arms',
    claim_scope='compact frozen-encoder linear pilot; not a ForeCritic-9B reproduction')


def save_spec():
    target = HERE / 'model_spec.json'
    if target.exists():
        assert json.loads(target.read_text()) == SPEC, 'Frozen specification changed'
    else:
        write_json(target, SPEC)
    return sha256(target)


def scaler(values):
    return values.mean(axis=0), np.maximum(values.std(axis=0), 1e-6)


def standardized(values, mean, std):
    return np.clip((values - mean) / std, -5, 5)


def features(code, context, code_scaler, context_scaler):
    z = standardized(code, *code_scaler)
    t = standardized(context, *context_scaler)
    return np.concatenate((z, z * t), axis=1)


def train_arm(x, left, right, labels, weights):
    theta = np.zeros(x.shape[1], dtype=np.float64)
    m = theta.copy()
    v = theta.copy()
    assert abs(weights.sum() - 1) < 1e-10
    for step in range(1, SPEC['steps'] + 1):
        scores = x @ theta
        logits = scores[left] - scores[right]
        g = (expit(logits) - labels) * weights
        candidate_gradient = (np.bincount(left, weights=g, minlength=len(x))
                              - np.bincount(right, weights=g, minlength=len(x)))
        gradient = x.T @ candidate_gradient + SPEC['l2'] * theta
        m = SPEC['beta1'] * m + (1 - SPEC['beta1']) * gradient
        v = SPEC['beta2'] * v + (1 - SPEC['beta2']) * gradient ** 2
        theta -= SPEC['learning_rate'] * (m / (1 - SPEC['beta1'] ** step)) / (
            np.sqrt(v / (1 - SPEC['beta2'] ** step)) + SPEC['epsilon'])
        assert np.isfinite(theta).all()
    scores = x @ theta
    logits = scores[left] - scores[right]
    loss = np.sum(weights * (np.logaddexp(0, logits) - labels * logits))
    return theta, dict(steps=SPEC['steps'], weighted_bce=float(loss),
                       penalized_loss=float(loss + SPEC['l2'] * np.dot(theta, theta) / 2),
                       parameter_norm=float(np.linalg.norm(theta)))


def run(args):
    started = time.time()
    spec_sha = save_spec()
    assert args.credit.joinpath('receipt.json').exists(), 'Credit run must be complete before fit'
    credit_receipt = json.loads((args.credit / 'receipt.json').read_text())
    assert credit_receipt['status'] == 'passed'
    assert args.embeddings.exists(), 'Frozen representation must exist before fit'
    assert not (HERE / 'prediction_seal.json').exists(), 'Existing sealed run must be preserved'
    folds_dir = HERE / 'folds'
    folds_dir.mkdir(exist_ok=False)
    codes = load_codes()
    archive = np.load(args.embeddings, allow_pickle=False)
    code_keys = archive['code_keys'].tolist()
    task_keys = archive['task_keys'].tolist()
    z_code = np.asarray(archive['code'], dtype=np.float64)
    z_context = np.asarray(archive['context'], dtype=np.float64)
    assert len(code_keys) == len(set(code_keys)) == sum(map(len, codes.values()))
    assert set(code_keys) == {task + '|' + candidate for task in codes for candidate in codes[task]}
    assert set(task_keys) == set(codes)
    assert z_code.shape == (len(code_keys), 512) and z_context.shape == (len(task_keys), 512)
    assert np.isfinite(z_code).all() and np.isfinite(z_context).all()
    assert np.allclose(np.linalg.norm(z_code, axis=1), 1, atol=1e-5)
    assert np.allclose(np.linalg.norm(z_context, axis=1), 1, atol=1e-5)
    code_lookup = {key: i for i, key in enumerate(code_keys)}
    task_lookup = {task: i for i, task in enumerate(task_keys)}
    outputs = []
    fold_receipts = []
    for heldout in sorted(codes):
        fold_started = time.time()
        pairs, manifest = load_fold(heldout, codes, args.credit / 'tasks', credit_receipt['task_weight_sha256'])
        directory = folds_dir / heldout
        directory.mkdir()
        write_jsonl_gz(directory / 'training_pairs.jsonl.gz',
                       [dict(task=r['task'], pair=r['pair']) for r in pairs])
        training_keys = sorted({r['task'] + '|' + r[side] for r in pairs for side in ('a', 'b')})
        training_tasks = sorted({r['task'] for r in pairs})
        code_scaler = scaler(z_code[[code_lookup[k] for k in training_keys]])
        context_scaler = scaler(z_context[[task_lookup[k] for k in training_tasks]])
        training_index = {key: i for i, key in enumerate(training_keys)}
        x = features(z_code[[code_lookup[k] for k in training_keys]],
                     z_context[[task_lookup[k.split('|')[0]] for k in training_keys]],
                     code_scaler, context_scaler)
        left = np.asarray([training_index[r['task'] + '|' + r['a']] for r in pairs])
        right = np.asarray([training_index[r['task'] + '|' + r['b']] for r in pairs])
        labels = np.asarray([r['label'] for r in pairs], dtype=np.float64)
        test_ids = sorted(codes[heldout])
        test_x = features(z_code[[code_lookup[heldout + '|' + k] for k in test_ids]],
                          z_context[[task_lookup[heldout]] * len(test_ids)],
                          code_scaler, context_scaler)
        test_index = {key: i for i, key in enumerate(test_ids)}
        parameters = {}
        arm_scores = {}
        training_stats = {}
        for arm in ARMS:
            weights = np.asarray([r['weights'][arm] / len(training_tasks) for r in pairs])
            theta, training_stats[arm] = train_arm(x, left, right, labels, weights)
            parameters[arm] = theta
            arm_scores[arm] = test_x @ theta
        tie_counts = Counter()
        max_swap_error = 0.0
        for a, b in all_pairs(codes[heldout]):
            winners, ties = {}, {}
            for arm in ARMS:
                logit = float(arm_scores[arm][test_index[a]] - arm_scores[arm][test_index[b]])
                max_swap_error = max(max_swap_error, abs(float(expit(logit) + expit(-logit)) - 1))
                if same_content(codes[heldout][a], codes[heldout][b]):
                    # AST equality can differ in comments; encoder features can differ.
                    # Only byte-identical code must produce identical embeddings/scores.
                    if codes[heldout][a]['byte_sha256'] == codes[heldout][b]['byte_sha256']:
                        assert abs(logit) < 1e-10, 'Identical code should have identical score'
                        logit = 0.0
                ties[arm] = (logit == 0)
                winners[arm] = a if logit >= 0 else b
                tie_counts[arm] += ties[arm]
            outputs.append(dict(task=heldout, pair=a + '|' + b, winners=winners, ties=ties))
        assert max_swap_error < 1e-12
        np.savez_compressed(directory / 'model.npz', **parameters,
                            code_mean=code_scaler[0], code_std=code_scaler[1],
                            context_mean=context_scaler[0], context_std=context_scaler[1])
        manifest.update(training_unique_candidates=len(training_keys),
                        scaler_training_tasks=training_tasks,
                        model_spec_sha256=spec_sha, arms=training_stats,
                        inference_pairs=len(all_pairs(codes[heldout])), ties=dict(tie_counts),
                        swap_probability_max_abs_error=max_swap_error,
                        wall_seconds=time.time() - fold_started,
                        training_pairs_sha256=sha256(directory / 'training_pairs.jsonl.gz'),
                        model_sha256=sha256(directory / 'model.npz'))
        write_json(directory / 'manifest.json', manifest)
        fold_receipts.append(dict(task=heldout, manifest_sha256=sha256(directory / 'manifest.json'),
                                  training_pairs=manifest['pairs'], inference_pairs=manifest['inference_pairs']))
        print(json.dumps(dict(fold=heldout, training_pairs=manifest['pairs'],
                              wall_seconds=manifest['wall_seconds'])), flush=True)
    output = HERE / 'oof_predictions.jsonl.gz'
    write_jsonl_gz(output, outputs)
    assert len(outputs) == inventory(codes)['all_inference_pairs']
    receipt = dict(id=SPEC['id'], predictions_sha256=sha256(output), predictions=str(output.relative_to(ROOT)),
                   model_spec_sha256=spec_sha, source_sha256={p.name: sha256(p) for p in (HERE / 'fit.py', HERE / 'data.py')},
                   embeddings=str(args.embeddings.relative_to(ROOT)), embeddings_sha256=sha256(args.embeddings),
                   credit_receipt_sha256=sha256(args.credit / 'receipt.json'),
                   folds=fold_receipts, fits=len(fold_receipts) * len(ARMS), optimizer_steps=80 * len(fold_receipts) * len(ARMS),
                   parameters_per_fit=1024, input_features=1024, prediction_rows=len(outputs),
                   wall_seconds=time.time() - started,
                   python=platform.python_version(), numpy=np.__version__, scipy=scipy.__version__,
                   machine=platform.machine(), processor=platform.processor(), threads=1,
                   training_results_used_for_selection=False, evaluation_labels_loaded_by_trainer=False,
                   costs=dict(paid_api_calls=0, candidate_executions=0, gpu_rentals=0),
                   inventory=inventory(codes), limitations=[
                       '26 development tasks reused; folds share training data.',
                       'Linear head on frozen compact public encoder; feature truncation belongs to representation receipt.',
                       'Exact and canonical AST filters leave renamed/edited near-duplicate risk.',
                       'Training labels and costs are archived execution outcomes; provenance confounding may persist.'])
    write_json(HERE / 'prediction_seal.json', receipt)
    print(json.dumps(dict(predictions_sha256=receipt['predictions_sha256'], fits=receipt['fits'],
                         prediction_rows=len(outputs), wall_seconds=receipt['wall_seconds'])))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--embeddings', type=Path, default=EXPERIMENT / 'representation/run_1/embeddings.npz')
    parser.add_argument('--credit', type=Path, default=EXPERIMENT / 'credit/run_1')
    parser.add_argument('--freeze-spec-only', action='store_true')
    args = parser.parse_args()
    if args.freeze_spec_only:
        print(save_spec())
    else:
        run(args)
