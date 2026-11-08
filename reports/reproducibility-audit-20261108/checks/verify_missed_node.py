"""Regrade already downloaded author node 95a7c811; no network, model calls, or training.
Usage: ACCEPTANCE_PYTHON verify_missed_node.py ROOT PRIVATE_CSV OUTPUT.json
"""
import csv,gzip,hashlib,importlib.util,json,sys
from pathlib import Path
import pandas as pd
sys.dont_write_bytecode=True
r=Path(sys.argv[1]).resolve();d=r/'reports/reproducibility-audit-20261108/evidence/author-missed-node';a=Path(sys.argv[2]);sys.path.insert(0,str(r))
from scripts.verify_online_baseline import score_by_id
run='stanford-covid-vaccine_01abb886-c4d4-4db9-a3a9-176aab3cb038'
j=json.loads(gzip.decompress((r/'data/historical/source_records'/run/'journal.json.gz').read_bytes()));n=next(n for n in j['nodes'] if n['id'].startswith('95a7c811'));m=json.loads((d/'metadata.json').read_text());assert (d/'code.py').read_text()==n['code'];assert m['node_id']==n['id'];assert '0.1583' in m['metric']
src=json.loads((d/'source.json').read_text())
for item in src['downloads']:assert hashlib.sha256((d/item['file']).read_bytes()).hexdigest()==item['sha256']
ind=score_by_id(list(csv.DictReader((d/'submission.csv').open())),list(csv.DictReader(a.open())))
base=r/'phase1-reproduction/code/author/mle-bench';sys.path.insert(0,str(base));sp=importlib.util.spec_from_file_location('audit_stanford_grader',base/'mlebench/competitions/stanford-covid-vaccine/grade.py');mod=importlib.util.module_from_spec(sp);sp.loader.exec_module(mod);native=float(mod.grade(pd.read_csv(d/'submission.csv'),pd.read_csv(a)));assert abs(native-ind['score'])<1e-12
ref=json.loads((r/'phase1-reproduction/experiments/online-stanford-v2/author-final-reference.json').read_text());published=next(x for x in ref['runs'] if x['run']==run)
rec={'run':run,'missed_journal_best':n['id'],'missed_internal_metric':n['metric']['value'],'published_final_node':published['node_id'],'published_final_internal_metric':published['agent_metric']['value'],'published_final_private_score':0.2576795279904613,'missed_node_independent_score':ind,'missed_node_native_score':native,'missed_minus_published_private':native-0.2576795279904613,'code_equals_journal':True,'metadata_id_equals_journal':True,'submission_sha256':hashlib.sha256((d/'submission.csv').read_bytes()).hexdigest(),'causal_scope':'Restores the validation-selected endpoint from an already completed author trajectory; counterfactual later search under a corrected incumbent was not run.','new_model_calls':0,'new_training_runs':0}
Path(sys.argv[3]).write_text(json.dumps(rec,indent=2)+'\n');print(json.dumps(rec,indent=2))
