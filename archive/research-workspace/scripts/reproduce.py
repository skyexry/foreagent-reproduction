"""Offline frozen-baseline verification. Outputs go only to fresh ignored runs/."""
import argparse
import gzip
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
VENDOR = ROOT/'vendor/foreagent_upstream/mle-bench/agents/aide/aide'

def call(args, out):
    env = dict(os.environ, PYTHONHASHSEED='0', PYTHONDONTWRITEBYTECODE='1', FOREAGENT_RUN_DIR=str(out))
    subprocess.run([sys.executable, *args], cwd=ROOT, env=env, check=True)

def copy(src, dst):
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src, dst)

def run(name):
    out = ROOT/'runs'/name
    assert not out.exists(), f'Inspect or move existing {out.relative_to(ROOT)} before another run'
    out.mkdir(parents=True)
    if name == 'historical':
        copy(VENDOR/'world_model.py', out/'world_model_original.py')
        copy(VENDOR/'agent.py', out/'agent_original.py')
        copy(ROOT/'experiments/historical-v1/source_manifest.json', out/'source_manifest.json')
        (out/'source_records').symlink_to('../../data/historical/source_records', target_is_directory=True)
        call(['reproduction/historical/replay_author.py'], out)
        call(['reproduction/historical/verify_and_report.py'], out)
        expected = json.loads((ROOT/'provenance/expected_run_hashes.json').read_text())['historical']
        for file, value in expected.items():
            assert hashlib.sha256((out/file).read_bytes()).hexdigest() == value, file
    elif name == 'corpus':
        copy(VENDOR/'world_model.py', out/'world_model_original.py')
        copy(ROOT/'vendor/foreagent_variants/world_model_cache_direction_canonical.py', out/'world_model_cache_fixed.py')
        for file in ['protocol.json', 'v2_spec.json']:
            copy(ROOT/'experiments/corpus26-v2'/file, out/file)
        for variant in ['original', 'cache-fixed']:
            copy(out/'protocol.json', out/variant/'protocol.json')
            call(['reproduction/corpus/replay_full.py', '--variant', variant], out)
        call(['reproduction/corpus/verify_replay.py'], out)
    elif name == 'five-task':
        call(['replay_foreagent_selection.py'], out)
        new = json.loads((out/'results.json').read_text())
        old = json.loads((ROOT/'experiments/tournament_replay_results.json').read_text())
        # Portability changes alter adapter/script hashes, not experimental outputs.
        for key in ['overall_task_macro', 'paired', 'per_task', 'run_trace_sha256', 'source_hashes', 'protocol_sha256']:
            assert new[key] == old[key], key
    elif name == 'mechanisms':
        call(['audit_foreagent_mechanisms.py'], out)
        result = json.loads((out/'audit.json').read_text())
        assert len(result['gates']['cases']) == 18 and len(result['stopping']) == 14
        assert len(result['execution_routing']['cases']) == 6 and len(result['native_replay']['cases']) == 100
        old = json.loads((ROOT/'experiments/mechanisms-v1/audit.json').read_text())
        # Source paths and portability script hashes are recorded separately.
        for key in ['gates', 'stopping', 'execution_routing', 'empirical']:
            assert result[key] == old[key], key
    elif name == 'pairwise':
        call(['scripts/verify_pairwise.py'], out)
    elif name == 'selection':
        call(['verify_foreagent_selection.py'], out)
    print('VERIFIED', name, flush=True)

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('experiment', choices=['all', 'historical', 'corpus', 'five-task', 'mechanisms', 'pairwise', 'selection'])
    args = parser.parse_args()
    names = ['selection', 'pairwise', 'five-task', 'mechanisms', 'historical', 'corpus'] if args.experiment == 'all' else [args.experiment]
    for name in names:
        run(name)

if __name__ == '__main__':
    main()
