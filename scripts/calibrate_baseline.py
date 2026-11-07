"""Run the registered confidence grid on the unchanged original controller."""
import concurrent.futures
import hashlib
import json
import os
from pathlib import Path
import shutil
import statistics
import subprocess
import sys

from audit_baseline_scores import ROOT, audit

FROZEN = ROOT/'runs/corpus'
OUTPUT = ROOT/'runs/environment-calibration'
SCRIPT = ROOT/'reproduction/corpus/replay_full.py'
GATES = (0.5, 0.6, 0.7, 0.8, 0.9, 1.0)
METRICS = ('normalized_regret', 'uniform_tie_best_hit', 'unique_feedback_queries', 'expected_execution_count')


def record_settings(folder, gate):
    settings = dict(confidence_threshold=gate, exec_probability=0.2, top_k=1,
                    variant="original", protocol="experiments/environment-audit/protocol.md",
                    frozen_parent="experiments/corpus26-v2/protocol.json")
    (folder / "effective_settings.json").write_text(json.dumps(settings, indent=2) + "\n")


def experiment(gate):
    dest = OUTPUT/str(gate)
    dest.mkdir(parents=True, exist_ok=False)
    for name in ('v2_spec.json', 'world_model_original.py', 'agent_original.py'):
        source = FROZEN/name
        if source.exists():
            shutil.copy(source, dest/name)
    variant = dest/'original'
    variant.mkdir()
    record_settings(variant, gate)
    shutil.copy(FROZEN/'protocol.json', variant/'protocol.json')
    # Keep the frozen harness and scorer. Override only the threshold supplied to
    # the actual tournament. Its internal published-config sanity test stays fixed.
    source = SCRIPT.read_text()
    config = 'confidence_threshold=.7, exec_probability=.2, temperature=1.'
    assert source.count(config) == 1
    sys.path.insert(0, str(SCRIPT.parent))
    os.environ['FOREAGENT_RUN_DIR'] = str(dest)
    namespace = {'__name__': 'calibration_replay', '__file__': str(SCRIPT)}
    exec(compile(source.replace(config, config.replace('=.7', '=' + str(gate))), str(SCRIPT), 'exec'), namespace)
    namespace.update(VARIANT='original', HERE=variant)
    namespace['run']()
    print(audit(variant))


def run_worker(gate):
    env = dict(os.environ, PYTHONHASHSEED='0')
    with (OUTPUT/f'{gate}.log').open('w') as log:
        subprocess.run([sys.executable, __file__, str(gate)], env=env, stdout=log, stderr=subprocess.STDOUT, check=True)


def main():
    OUTPUT.mkdir(exist_ok=False)
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        list(pool.map(run_worker, GATES))
    results = {g: json.loads((OUTPUT/str(g)/'original/results.json').read_text()) for g in GATES}
    reference = json.loads((FROZEN/'original/results.json').read_text())
    assert results[.7]['per_task'] == reference['per_task']
    tasks = sorted([r['task'] for r in reference['per_task']], key=lambda t: hashlib.sha256(t.encode()).digest())
    def means(g, members):
        rows = [r['mean'] for r in results[g]['per_task'] if r['task'] in members]
        return {m: statistics.mean(row[m] for row in rows) for m in METRICS}
    def admissible(a, b):
        return (a['uniform_tie_best_hit'] >= b['uniform_tie_best_hit']
                and all(a[k] <= b[k] for k in ('unique_feedback_queries','expected_execution_count')))
    dev = {g: means(g, tasks[:18]) for g in GATES}
    chosen = min((g for g in GATES if admissible(dev[g], dev[.7])),
                 key=lambda g: (dev[g]['normalized_regret'], abs(.7-g), g))
    control = means(.7, tasks[18:])
    valid = means(chosen, tasks[18:])
    receipt = dict(development_tasks=tasks[:18], validation_tasks=tasks[18:], development=dev,
                   eligible=[g for g in GATES if admissible(dev[g],dev[.7])], selected_gate=chosen,
                   validation=valid, validation_control=control, validation_constraints=admissible(valid,control),
                   control_matches_frozen_per_task=True)
    (OUTPUT/'summary.json').write_text(json.dumps(receipt,indent=2)+'\n')


if __name__ == '__main__':
    if len(sys.argv) == 2:
        experiment(float(sys.argv[1]))
    else:
        main()
