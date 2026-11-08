"""Re-check saved full runs, contract tests and preservation; zero model calls.

Run from the project root:
python -B experiments/research-env-v1/check_acceptance.py
"""
import io
import json
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from reproduction.research_env_v1.core import (
    digest,dump,evaluate_run,load_context,load_rows,read_json,verify_files)


def main():
    registry,jobs,_,_=load_context()
    directory=ROOT/'experiments/research-env-v1'
    reference=load_rows(ROOT/registry['benchmark']['reference_decisions'])
    old_summary=read_json(ROOT/registry['benchmark']['reference_summary'])
    records={}
    for name,method in [('baseline-v1','corrected_tournament'),('random-v1','random_pairs')]:
        run=directory/'runs'/name
        summary=evaluate_run(run)
        assert summary['episode_status_counts']=={'ok':850}
        expected={r['job_id']:r for r in reference if r['method']==method}
        rows=load_rows(run/'decisions.jsonl.gz')
        assert len(rows)==len(expected)==len(jobs)==850
        for row in rows:
            old=expected[row['job_id']]
            assert row['selected']==old['selected'],row['job_id']
            assert len(row['trace'])==len(old['trace']),row['job_id']
            for new_query,old_query in zip(row['trace'],old['trace'],strict=True):
                assert all(new_query[k]==old_query[k] for k in ('a','b','winner','confidence'))
            assert all(row['stats'][k]==v for k,v in old['stats'].items())
        assert summary['macro']['submitted_policy']==old_summary['macro'][method]
        assert all(value['submitted_policy']==old_summary['per_task'][task][method]
                   for task,value in summary['per_task'].items())
        records[name]=dict(episodes=850,matching_decisions=850,matching_query_traces=850,
            matching_ledgers=850,matching_task_summaries=26,macro=summary['macro']['submitted_policy'],
            selection_wall_seconds=read_json(run/'run_info.json')['selection_wall_seconds'],
            run_manifest_sha256=digest(run/'run_manifest.json'),
            summary_sha256=digest(run/'evaluation/summary.json'),
            verification_sha256=digest(run/'evaluation/verification.json'))
    suite=unittest.defaultTestLoader.discover(str(ROOT/'tests'),pattern='test_research_env_v1.py')
    output=io.StringIO()
    result=unittest.TextTestRunner(stream=output,verbosity=2).run(suite)
    (directory/'tests.log').write_text(output.getvalue())
    if not result.wasSuccessful():
        raise RuntimeError(output.getvalue())
    artifacts=read_json(ROOT/'experiments/clean-ranking-v1/artifact_manifest.json')
    verify_files({p:v['sha256'] for p,v in artifacts.items()})
    before=read_json(directory/'preservation-before.json')
    assert before['clean_manifest_sha256']==digest(ROOT/'experiments/clean-ranking-v1/artifact_manifest.json')
    historical=read_json(ROOT/'experiments/clean-ranking-v1/historical-protection.json')
    verify_files(historical)
    protected=read_json(ROOT/registry['paths']['protected_manifest'])
    verify_files(protected['sha256'])
    receipt=dict(id='research-env-v1',status='passed',scope=registry['scope'],runs=records,
        tests=dict(run=result.testsRun,failures=len(result.failures),errors=len(result.errors),
                   log_sha256=digest(directory/'tests.log')),
        preservation=dict(clean_artifacts_verified=len(artifacts),historical_files_verified=len(historical),
            source_files_verified=len(read_json(ROOT/registry['benchmark']['prepared']/'source_manifest.json')['sha256']),
            protected_files_verified=len(protected['sha256'])),
        protected_manifest_sha256=digest(ROOT/registry['paths']['protected_manifest']),
        acceptance_script_sha256=digest(Path(__file__)),
        resources=dict(new_paid_model_calls=0,new_candidate_training_runs=0,new_gpu_rentals=0),
        pending=['Primary-literature study and complete proposal cards',
                 'AI Scientist pinned-version native adapter, isolated coder workspace and aggregate experiment budget',
                 'New-task confirmation and live end-to-end environment acceptance'])
    dump(directory/'acceptance.json',receipt)
    state=dict(environment_id=registry['environment_id'],status='离线 Environment 与 Evals 已验收',
        development_tasks=26,pools=425,jobs=850,baseline='C0 corrected_tournament',
        acceptance='experiments/research-env-v1/acceptance.json',
        acceptance_sha256=digest(directory/'acceptance.json'),
        acceptance_script_sha256=digest(Path(__file__)),
        completed=['Policy boundary and host-controlled query budget','Frozen scorer and independent evaluation',
                   '850 baseline + 850 random-control episodes reproduce saved results','17 contract/isolation tests'],
        next='Study the comparison-allocation module and primary literature; prepare a reviewable proposal card.',
        pending=receipt['pending'])
    dump(ROOT/registry['paths']['state'],state)
    print(json.dumps(dict(status='passed',tests=result.testsRun,baseline_episodes=850,random_episodes=850,
                         preservation=receipt['preservation']),indent=2))


if __name__=='__main__':
    main()
