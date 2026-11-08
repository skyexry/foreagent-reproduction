"""Install the audited overlay into a separate, exact author checkout."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil

HERE = Path(__file__).resolve().parent


def install(destination):
    destination = Path(destination).resolve()
    manifest = json.loads((HERE/'manifest.json').read_text())
    aide = destination/'mle-bench/agents/aide/aide'
    grader = destination/'mle-bench/mlebench/competitions/stanford-covid-vaccine/grade.py'
    root=Path(__file__).resolve().parents[2]
    source_map=json.loads((root/'phase1-reproduction/SOURCES.json').read_text())
    protected_roots=[root/'phase1-reproduction',root/'vendor/foreagent_upstream',
                     Path(source_map['source_roots']['author_checkout']).resolve()]
    if any(destination==p or p in destination.parents for p in protected_roots):
        raise ValueError('Install into a separate checkout, preserving frozen author sources')
    if (destination/'C0_MANIFEST.json').exists() or any((aide/n).exists() for n in ('correctness.py','ranking.py')):
        raise ValueError('Destination already has an overlay/helper; preserve it')
    for name, expected in manifest['source_sha256'].items():
        if hashlib.sha256((aide/name).read_bytes()).hexdigest() != expected:
            raise ValueError('Destination must contain the exact original source: '+name)
    if hashlib.sha256(grader.read_bytes()).hexdigest() != manifest['grader_source_sha256']:
        raise ValueError('Original grader mismatch')
    for name, expected in manifest['overlay_sha256'].items():
        if hashlib.sha256((HERE/'overlay'/name).read_bytes()).hexdigest() != expected:
            raise ValueError('Overlay checksum mismatch: '+name)
    for name in ('agent.py', 'world_model.py', 'correctness.py', 'ranking.py'):
        shutil.copyfile(HERE/'overlay'/name, aide/name)
    shutil.copyfile(HERE/'overlay/grade.py', grader)
    shutil.copyfile(HERE/'correctness.py', destination/'mle-bench/mlebench/clean_baseline_score.py')
    (destination/'C0_MANIFEST.json').write_text(json.dumps(manifest, indent=2)+'\n')


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('destination', type=Path)
    install(p.parse_args().destination)
