"""Small correctness helpers shared by both ranking arms; no policy or API calls."""
import csv
import hashlib
import json
import math
from pathlib import Path
import shutil
import tempfile


def response_values(parsed):
    winner = parsed.get('predicted_best_index')
    if isinstance(winner, str) and winner in ('0', '1'):
        winner = int(winner)
    if type(winner) is not int or winner not in (0, 1):
        winner = None
    confidence = parsed.get('confidence', 0.5)
    try:
        if isinstance(confidence, bool):
            raise ValueError('boolean confidence')
        confidence = float(confidence)
        if not math.isfinite(confidence) or not 0 <= confidence <= 1:
            raise ValueError('confidence outside [0,1]')
    except (TypeError, ValueError):
        confidence = 0.0
        winner = None
    return winner, confidence


def prepare_submission(workspace):
    path = Path(workspace) / 'submission'
    if path.is_symlink() or path.is_file():
        path.unlink()
    elif path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True)


def submission_problem(workspace):
    path = Path(workspace) / 'submission/submission.csv'
    if path.is_symlink() or not path.is_file():
        return 'missing regular submission.csv'
    try:
        with path.open(newline='') as stream:
            reader = csv.DictReader(stream)
            names = reader.fieldnames or []
            if not names or len(names) != len(set(names)):
                return 'empty or duplicate CSV columns'
            rows = list(reader)
        if not rows or any(None in r or any(v is None for v in r.values()) for r in rows):
            return 'empty or malformed CSV rows'
        # Stanford's five-target schema is task specific; text tasks stay text.
        if 'id_seqpos' in names:
            columns = ('reactivity', 'deg_Mg_pH10', 'deg_Mg_50C', 'deg_pH10', 'deg_50C')
            if not set(columns) <= set(names):
                return 'missing Stanford target columns'
            ids = [r['id_seqpos'] for r in rows]
            if len(set(ids)) != len(ids) or any(not x for x in ids):
                return 'duplicate or empty Stanford IDs'
            if any(not math.isfinite(float(r[c])) for r in rows for c in columns):
                return 'nonfinite Stanford predictions'
        return None
    except (OSError, csv.Error, ValueError, UnicodeError) as error:
        return str(error)


def atomic_write(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as stream:
        temporary = Path(stream.name)
        stream.write(data)
    temporary.replace(path)


def save_checkpoint(workspace, artifacts, node):
    """Read the best node's own archived predictions, never the current scratch CSV."""
    workspace = Path(workspace)
    prediction = Path(artifacts) / ('node_' + node.id[:8]) / 'submission.csv'
    code_file = prediction.parent / 'code.py'
    if not prediction.is_file() or not code_file.is_file():
        raise ValueError('Best-node artifacts are incomplete: ' + node.id)
    code = (node.code or '').encode()
    if code_file.read_bytes() != code:
        raise ValueError('Best-node code does not match archived code')
    data = prediction.read_bytes()
    atomic_write(workspace/'best_solution/solution.py', code)
    atomic_write(workspace/'best_submission/submission.csv', data)
    info = f'node_id: {node.id}\n\nmetric: {node.metric}\n\nsolution:\n{node.plan}'
    atomic_write(workspace/'best_solution/node_info.txt', info.encode())
    manifest = dict(node_id=node.id, code_sha256=hashlib.sha256(code).hexdigest(),
                    prediction_sha256=hashlib.sha256(data).hexdigest(), metric=str(node.metric))
    # Commit marker written last. Consumers must verify the hashes before grading.
    atomic_write(workspace/'best_checkpoint.json', (json.dumps(manifest, indent=2)+'\n').encode())
    return manifest


def verify_checkpoint(workspace):
    workspace = Path(workspace)
    info = json.loads((workspace/'best_checkpoint.json').read_text())
    for field, relative in [('code_sha256', 'best_solution/solution.py'),
                            ('prediction_sha256', 'best_submission/submission.csv')]:
        if hashlib.sha256((workspace/relative).read_bytes()).hexdigest() != info[field]:
            raise ValueError('Checkpoint identity mismatch: ' + relative)
    return info


def stanford_score(predictions, answers):
    """Independent ID-joined MCRMSE, with public-input prediction schema validation."""
    if not predictions or len(predictions) != len(answers):
        raise ValueError('row count mismatch')
    p = {r['id_seqpos']: r for r in predictions}
    y = {r['id_seqpos']: r for r in answers}
    if len(p) != len(predictions) or len(y) != len(answers) or p.keys() != y.keys():
        raise ValueError('duplicate or mismatched IDs')
    columns = ('reactivity', 'deg_Mg_pH10', 'deg_Mg_50C', 'deg_pH10', 'deg_50C')
    if any(not math.isfinite(float(r[c])) for r in predictions for c in columns):
        raise ValueError('nonfinite predictions')
    if any(str(r['keep']).lower() not in ('true', 'false', '1', '0') for r in answers):
        raise ValueError('invalid keep mask')
    kept = sorted(k for k in y if str(y[k]['keep']).lower() in ('true', '1'))
    if not kept:
        raise ValueError('empty mask')
    if any(not math.isfinite(float(y[k][c])) for k in kept for c in columns[:3]):
        raise ValueError('nonfinite evaluation targets')
    return math.fsum(math.sqrt(math.fsum((float(p[k][c])-float(y[k][c]))**2
                                        for k in kept)/len(kept)) for c in columns[:3])/3
