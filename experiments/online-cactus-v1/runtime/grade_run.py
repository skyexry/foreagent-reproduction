"""External Cactus submission checks and official/independent ROC AUC grading."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import runpy
import sys
import time

import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score

HERE = Path(__file__).resolve().parent
UPSTREAM = Path('/root/autodl-tmp/foreagent/preflight/upstream/mle-bench')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--scope', required=True)
    args = parser.parse_args()
    if not args.scope or any(c not in 'abcdefghijklmnopqrstuvwxyz0123456789-' for c in args.scope):
        raise ValueError('invalid scope')
    run_dir = HERE / 'runs' / args.scope
    submission = run_dir / 'workspaces/exp/best_submission/submission.csv'
    answers_path = HERE / 'data-source/prepared/private/test.csv'
    output_dir = HERE / 'external-grading' / args.scope
    output_dir.mkdir(parents=True, exist_ok=True)
    output_dir.chmod(0o700)
    assert hashlib.md5(answers_path.read_bytes()).hexdigest() == 'ebdb02d62dbaf60270a9b3a8617840af', 'answer checksum differs from original split'
    original_digest = hashlib.sha256(submission.read_bytes()).hexdigest()
    predicted = pd.read_csv(submission, dtype={'id': str})
    answers = pd.read_csv(answers_path, dtype={'id': str})
    assert predicted.columns.tolist() == ['id', 'has_cactus'], 'submission columns'
    assert answers.columns.tolist() == ['id', 'has_cactus'], 'answer columns'
    for label, frame in [('submission', predicted), ('answers', answers)]:
        assert len(frame) == 3325, label + ' row count'
        assert frame['id'].notna().all(), label + ' null ID'
        assert frame['id'].nunique() == len(frame), label + ' duplicate ID'
        assert np.isfinite(frame['has_cactus'].to_numpy(dtype=float)).all(), label + ' non-finite value'
    assert set(predicted['id']) == set(answers['id']), 'submission/answer ID sets'
    sys.path.insert(0, str(UPSTREAM))
    grade_file = UPSTREAM / 'mlebench/competitions/aerial-cactus-identification/grade.py'
    official = float(runpy.run_path(str(grade_file))['grade'](predicted.copy(), answers.copy()))
    aligned = answers.set_index('id')['has_cactus'].loc[predicted['id']].to_numpy()
    independent = float(roc_auc_score(aligned, predicted['has_cactus'].to_numpy(dtype=float)))
    assert math.isfinite(official) and math.isfinite(independent), 'non-finite grade'
    assert math.isclose(official, independent, rel_tol=0, abs_tol=1e-12), 'official/independent grade disagreement'
    assert hashlib.sha256(submission.read_bytes()).hexdigest() == original_digest, 'selected submission changed during grading'
    record = {'scope': args.scope, 'time': time.time(), 'rows': len(predicted),
              'columns': predicted.columns.tolist(), 'id_unique': True, 'id_sets_match': True,
              'finite_predictions': True, 'official_roc_auc': official,
              'independent_id_aligned_roc_auc': independent,
              'absolute_grade_difference': abs(official - independent),
              'selected_submission_sha256': original_digest,
              'answer_sha256': hashlib.sha256(answers_path.read_bytes()).hexdigest(),
              'official_grade_source_sha256': hashlib.sha256(grade_file.read_bytes()).hexdigest(),
              'selected_submission': str(submission),
              'evaluation_policy': 'external only; retain agent-selected best; no feedback to agent'}
    destination = output_dir / ('grade-' + str(time.time_ns()) + '.json')
    destination.write_text(json.dumps(record, indent=2) + '\n')
    destination.chmod(0o600)
    print(json.dumps({'scope': args.scope, 'official_roc_auc': official,
                      'independent_roc_auc': independent, 'rows': len(predicted),
                      'record': str(destination)}))


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        scope = sys.argv[sys.argv.index('--scope') + 1] if '--scope' in sys.argv else 'unknown'
        if scope and all(c in 'abcdefghijklmnopqrstuvwxyz0123456789-' for c in scope):
            directory = HERE / 'external-grading' / scope
            directory.mkdir(parents=True, exist_ok=True)
            directory.chmod(0o700)
            failure = directory / ('grade-failed-' + str(time.time_ns()) + '.json')
            failure.write_text(json.dumps({'scope': scope, 'time': time.time(),
                'status': 'grading failed', 'error_type': type(error).__name__,
                'message': str(error)}, indent=2) + '\n')
            failure.chmod(0o600)
        raise
