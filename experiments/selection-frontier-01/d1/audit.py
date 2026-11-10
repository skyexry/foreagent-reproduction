"""Read-only artifact audit; independent arithmetic from sealed run outputs."""
import argparse, hashlib, json, math, random, statistics
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('run',type=Path);args=p.parse_args();run=args.run
sha=lambda f:hashlib.sha256(f.read_bytes()).hexdigest()
read=lambda n:json.loads((run/n).read_text())
load=lambda n:[json.loads(x) for x in (run/n).read_text().splitlines()]
manifest=read('output_manifest.json')
assert all(sha(run/n)==v for n,v in manifest.items())
s=read('final_info.json');jobs=load('per_job_evidence.jsonl');tasks=load('per_task.jsonl');sealed=load('sealed_selections.jsonl')
assert s['status']=='success' and len(jobs)==850 and len(tasks)==26 and len(sealed)==2550
assert len({x['job_id'] for x in jobs})==850
assert sum(x['jobs'] for x in tasks)==850 and sum(x['pools'] for x in tasks)==425
v=[]
for task in sorted({x['task'] for x in jobs}):
 g=[x for x in jobs if x['task']==task]
 d=statistics.fmean(x['scores']['T']['regret']-x['scores']['U']['regret'] for x in g)
 v.append(d)
 assert d==next(x for x in tasks if x['task']==task)['metrics']['delta_T_minus_U']
assert statistics.fmean(v)==s['macro']['delta_T_minus_U']
r=random.Random(20261108093)
b=sorted(statistics.fmean(r.choices(v,k=26)) for _ in range(10000))
def q(x):
 k=(len(b)-1)*x;lo=int(k);hi=min(lo+1,len(b)-1)
 return b[lo]*(hi-k)+b[hi]*(k-lo) if lo!=hi else b[lo]
assert [q(.025),q(.975)]==s['intervals']['delta_T_minus_U']['task_cluster_95']
assert len([x for x in jobs if x['n']==3 and x['same_next_edge'] and x['delta_T_minus_U']==0])==4
assert all(math.isclose(x['delta_T_minus_U'],x['D_harm']+x['D_missed'],abs_tol=1e-14) for x in jobs)
seal=read('selection_seal.json')
assert all(sha(run/n)==h for n,h in seal['sha256'].items())
assert seal['sealed_utc']<read('full_length_verification.json')['evaluation_started_utc']
lo=[{'excluded_task':t['task'],'delta_T_minus_U':statistics.fmean(x['metrics']['delta_T_minus_U'] for x in tasks if x is not t)} for t in tasks]
assert lo==read('leave_one_task_out.json')
assert all(s['costs']['logical_reads'][branch]==sum(x['logical_reads'] for x in sealed if x['branch']==branch) for branch in ('S','U','T'))
assert not s['gates']['eligible_for_D2_registration']
print(json.dumps({'status':'passed','run':str(run),'jobs':850,'tasks':26,'pools':425,
 'script_sha256':sha(Path(__file__)),'run_manifest_sha256':sha(run/'output_manifest.json'),
 'checks':['every output hash','all denominators','paired task macro from job evidence',
 'exact seeded primary bootstrap','all n=3 natural controls','harm/missed identity',
 'selection seal and evaluation time order','leave-one arithmetic','logical cost totals','D2 gate']},indent=2))
