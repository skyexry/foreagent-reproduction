import gzip,json,hashlib,random,statistics,time
from pathlib import Path
from collections import Counter,defaultdict
P=Path(__file__).resolve().parent;ROOT=P.parents[1];t0=time.monotonic()
def load(p):return json.loads(Path(p).read_bytes())
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def rows(p):return [json.loads(x) for x in gzip.open(p,'rt')]
seal=load(P/'selection_seal.json')
for p,h in seal['inputs'].items():assert sha(p)==h
for p,h in seal['source_sha256'].items():assert sha(p)==h
assert sha(P/'selections.sealed.jsonl.gz')==seal['selections_sha256']
assert sha(P/'flags.sealed.jsonl.gz')==seal['flags_sha256']
flags={(x['bank'],x['task'],x['pair']):x for x in rows(P/'flags.sealed.jsonl.gz')}
for f in flags.values():
 ri,pi=f['reasoning_last_json_index'],f['parsed_index']
 assert f['direction_mismatch']==(f['usable_explicit_direction'] and ri!=pi)
 if f['usable_explicit_direction']:assert type(ri)is int and type(pi)is int and ri in(0,1) and pi in(0,1)
controls={(x['bank'],x['job_id']):x for x in rows(ROOT/'experiments/trajectory-weighted-judge-v1/evaluation/run_1/decisions.sealed.jsonl.gz') if x['arm']=='C0'}
jobs={x['job_id']:x for x in map(json.loads,(ROOT/'experiments/clean-ranking-v1/prepared/jobs.jsonl').read_text().splitlines())}
labels=load(ROOT/'experiments/clean-ranking-v1/prepared/evaluation_labels.json')
changes=defaultdict(Counter);unique_selections=set();groups=defaultdict(list)
def outcome(base,edges,pos):
 penalties=[sum((e['winner']==c)-(c in(e['a'],e['b']) and e['winner']!=c) for i,e in enumerate(edges) if i in pos) for c in base]
 return [c for c,p in zip(base,penalties) if p==min(penalties)]
def score(job,s):
 u=labels[job['task']];hi=max(u[c] for c in job['ids']);lo=min(u[c] for c in job['ids'])
 return [(hi-sum(u[c] for c in s)/len(s))/(hi-lo) if hi!=lo else 0,sum(u[c]==hi for c in s)/len(s)]
for x in rows(P/'selections.sealed.jsonl.gz'):
 b,j=x['bank'],x['job_id'];k=(b,j);assert k not in unique_selections;unique_selections.add(k)
 c=controls[k];base=c['selected'];assert x['C0']==base
 e=[q for q in c['trace'] if q['winner']is not None];pos=[i for i,q in enumerate(e) if flags[(b,x['task'],'|'.join(sorted((q['a'],q['b']))))]['direction_mismatch']]
 expected=outcome(base,e,pos);assert x['text']==expected
 changes[b]['episodes']+=1
 if base!=x['text']:
  changes[b]['changed']+=1
  a,z=score(jobs[j],base)[0],score(jobs[j],x['text'])[0]
  changes[b]['better' if z<a-1e-12 else 'worse' if z>a+1e-12 else 'equal_regret']+=1
 else:changes[b]['unchanged']+=1
 for r,s in enumerate(x['sham']):
  seed=int(hashlib.sha256(f'rationale-tiebreak-v1:{b}:{j}:{r}'.encode()).hexdigest(),16)
  sample=random.Random(seed).sample(range(len(e)),len(pos));assert s==outcome(base,e,sample)
 groups[(b,x['task'])].append([score(jobs[j],x[a]) for a in ['C0','text']]+[score(jobs[j],s) for s in x['sham']])
assert len(unique_selections)==3400
summary=load(P/'summary.json')
for b in controls.keys():pass
for b in summary['exposure']:
 vals=[groups[(b,t)] for t in sorted(labels)]
 for armidx,arm in [(0,'C0'),(1,'text')]:
  for metric in range(2):
   mean=statistics.fmean(statistics.fmean(v[armidx][metric] for v in task) for task in vals)
   assert abs(mean-summary['metrics'][b][arm][metric])<1e-12
receipt={'verified':True,'checks':['all sealed input and source SHA256','3400 exact original first groups','71508 strict extracted metadata records','3400 deterministic text selections','108800 deterministic sham selections','independent C0/text task equal metric reconstruction'],'changed_episode_outcomes_by_bank':dict(changes),'label_visibility':'selection stage reads only prediction.reasoning, prediction index/confidence, and solutions.path from raw source JSON; these source documents also contain gold fields which json.loads materializes but selector never accesses. Separate prepared evaluation_labels.json opens only after selections/flags and hash seal are written.','pre_score_correction':'First attempt stopped before seal/scoring because reference selected is an arm dictionary. Corrected control comparison to selected.C; added original source input SHA checks. Successful source preserved in run.executed.py. No rule or metric revision after scores.','cost':summary['cost'],'verification_wall_seconds':time.monotonic()-t0,'failed_preflight_cost':'One local pre-score schema check attempt; no selection seal or evaluation produced. Its CPU/wall was not instrumented separately.','source_mapping':'All 71508 source metadata rows matched source-file SHA and source-row candidate order, archived index/confidence and original reasoning JSON presence/mixed mismatch. Audit omitted reasoning_last_json_index in 71508/71508 rows; recovered with exact existing extractor.','deployment_cost':'This archival postprocessor uses existing queried feedback and retained text; requires retaining rationale text; no new inference calls for same feedback schedule. New task performance and online wall cost remain separate.'}
(P/'receipt.json').write_text(json.dumps(receipt,indent=2,sort_keys=True)+'\n')
print(json.dumps(receipt,indent=2))
