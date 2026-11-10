#!/usr/bin/env python3
"""Evaluator-only partial oracle interventions on true adaptive C0 paths."""
import argparse
from collections import Counter,defaultdict
from datetime import datetime,timezone
import gzip
import hashlib
import json
import math
from pathlib import Path
import platform
import random
import shutil
import signal
import statistics
import subprocess
import sys
import time
import traceback

HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
sys.path.insert(0,str(ROOT));sys.dont_write_bytecode=True
from reproduction.clean_ranking_v1.correctness import response_values
from reproduction.clean_ranking_v1.loader import load_world
from reproduction.clean_ranking_v1.run import select,evaluate,percentile

PROTOCOL_SHA='9f728217c5ad0e8ea13831f4d6084b00d88ba25f0ba465c754d048776e2d4af3'
ARMS=('O','D','A')
CONTRASTS={'O_minus_D':('O','D'),'O_minus_A':('O','A'),'A_minus_D':('A','D')}


def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def load(p):return json.loads(Path(p).read_text())
def dump(p,x):Path(p).write_text(json.dumps(x,indent=2,sort_keys=True,allow_nan=False)+'\n')
def objsha(x):return hashlib.sha256(json.dumps(x,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
def fold_for(task,pair):return int(hashlib.sha256((task+'\x1f'+pair).encode()).hexdigest(),16)%4


def parsed(item):
    index,conf=response_values(item)
    return (item['order'][index] if index is not None and conf>=.7 else None),conf


def oracle_bank(bank,labels,arm,fold):
    result={};metadata={};count=Counter()
    for task,table in bank.items():
        result[task]={};metadata[task]={}
        for pair,item in table.items():
            a,b=item['order'];oldwinner,conf=parsed(item)
            eligible=fold_for(task,pair)==fold
            strict=labels[task][a]!=labels[task][b]
            truth=(a if labels[task][a]>labels[task][b] else b) if strict else None
            target=eligible and strict and ((oldwinner is not None) if arm=='D' else (oldwinner is None))
            actionable=target and (oldwinner!=truth)
            updated=dict(item)
            if actionable:
                updated['predicted_best_index']=item['order'].index(truth)
                if arm=='A':updated['confidence']=.7
            altered=updated!=item
            assert altered==actionable
            assert eligible or updated==item
            assert strict or updated==item
            if arm=='D':
                assert updated['confidence']==item['confidence']
                assert oldwinner is not None or updated==item
            else:assert oldwinner is None or updated==item
            if altered:assert parsed(updated)[0]==truth
            count['all_pair_addresses']+=1;count['eligible_addresses']+=eligible
            count['eligible_target_addresses']+=target;count['altered_addresses']+=altered
            count['eligible_true_tie_addresses']+=eligible and not strict
            result[task][pair]=updated
            metadata[task][pair]={'eligible':eligible,'target':target,'altered':altered,
                                  'original_accepted':oldwinner is not None,'true_tie':not strict}
    return result,metadata,dict(count)


def infer(values,tasks):
    rng=random.Random(20261108093)
    samples=[statistics.fmean(rng.choices(values,k=len(values))) for _ in range(10000)]
    loo={t:statistics.fmean(v for j,v in zip(tasks,values) if j!=t) for t in tasks}
    return {'gain':statistics.fmean(values),'ci95':[percentile(samples,.025),percentile(samples,.975)],
            'per_task_gain':dict(zip(tasks,values)),'leave_one_task_out':loo,
            'leave_one_min':min(loo.values()),'leave_one_max':max(loo.values()),
            'every_leave_one_positive':all(v>0 for v in loo.values()),
            'tasks_improved':sum(v>1e-12 for v in values),'tasks_unchanged':sum(abs(v)<=1e-12 for v in values),
            'tasks_worsened':sum(v < -1e-12 for v in values)}


def summarize(data):
    tasks=sorted(data);metric_keys=next(iter(data.values()))['O'].keys()
    macro={a:{m:statistics.fmean(data[t][a][m] for t in tasks) for m in metric_keys} for a in ARMS}
    contrast={}
    for name,(left,right) in CONTRASTS.items():
        contrast[name]={}
        for m in ('regret','best_hit'):
            values=[(data[t][left][m]-data[t][right][m])*(1 if m=='regret' else -1) for t in tasks]
            contrast[name][m]=infer(values,tasks)
    return {'tasks':len(tasks),'macro':macro,'contrasts':contrast}


def analyze(out):
    began=time.monotonic();assert sha(HERE/'protocol.json')==PROTOCOL_SHA
    frozen=load(HERE.parent/'protocol.json')['frozen_sha256'];binding=dict(frozen)
    for p,h in frozen.items():assert sha(ROOT/p)==h,p
    for p in ('reproduction/clean_ranking_v1/run.py','reproduction/clean_ranking_v1/correctness.py',
              'reproduction/clean_ranking_v1/loader.py','reproduction/clean_ranking_v1/overlay/world_model.py'):
        binding[p]=sha(ROOT/p)
    binding[str((HERE/'protocol.json').relative_to(ROOT))]=PROTOCOL_SHA
    dump(out/'execution_details.preregistered.json',{
        'created_before_oracle_label_load':True,'fold_exact':'int(sha256(UTF8(task + U+001F + canonical_pair)).hexdigest(),16)%4',
        'canonical_pair':'| joined lexicographically sorted candidate IDs; existing bank key',
        'O_repeats':'One original control per job, paired with each of four D/A folds',
        'direction_change':'D changes only incorrect accepted strict direction; confidence raw field unchanged',
        'abstention_change':'A changes only originally abstained strict pair; true direction and confidence=.7',
        'gold_boundary':'Evaluator reads labels to make oracle feedback; frozen policy receives only modified raw feedback, no labels/oracle flags.',
        'label_file_access':'Denied during every select() call, including O. Gold-backed oracle is intentionally evaluator-side.'})
    prepared=ROOT/'experiments/clean-ranking-v1/prepared'
    jobs=[json.loads(s) for s in (prepared/'jobs.jsonl').read_text().splitlines()]
    byid={j['job_id']:j for j in jobs}
    paths=load(prepared/'code_files.json')
    code={t:{i:(ROOT/p).read_text() for i,p in files.items()} for t,files in paths.items()}
    banks={'DS1':load(prepared/'feedback.json')}
    bm=load(HERE.parent/'banks/manifest.json');tm=load(HERE.parent/'deepseek-transfer/banks_1/manifest.json')
    for manifest_path in (HERE.parent/'banks/manifest.json',HERE.parent/'deepseek-transfer/banks_1/manifest.json'):
        binding[str(manifest_path.relative_to(ROOT))]=sha(manifest_path)
    for name,meta in {**bm['banks'],**tm['banks']}.items():
        p=ROOT/meta['path'];assert sha(p)==meta['sha256'];binding[meta['path']]=sha(p)
        banks[name]=json.loads(gzip.decompress(p.read_bytes()))
    original={}
    with gzip.open(ROOT/'experiments/clean-ranking-v1/results/decisions.jsonl.gz','rt') as stream:
        for line in stream:
            r=json.loads(line)
            if r['method']=='corrected_tournament':original[('DS1',r['job_id'])]={k:r[k] for k in ('selected','trace','stats')}
    for source in (HERE.parent/'c0-final-selection/run-002/decisions.sealed.jsonl.gz',
                   HERE.parent/'deepseek-transfer/run_1/decisions.sealed.jsonl.gz'):
        binding[str(source.relative_to(ROOT))]=sha(source)
        with gzip.open(source,'rt') as stream:
            for line in stream:
                r=json.loads(line)
                if r['bank']=='DS':continue
                original[(r['bank'],r['job_id'])]={'selected':r['selected']['C'],'trace':r['trace'],'stats':r['stats']}
    dump(out/'input_sha256.json',binding)
    # Labels stay entirely in this evaluator; the imported C0 only sees oracle feedback.
    label_path=prepared/'evaluation_labels.json';labels=load(label_path)
    model=load_world();bank_checks={};fold_opportunity={};per_task={};per_episode=[]
    decisions_path=out/'decisions.oracle.jsonl.gz';fold_scores_path=out/'per_fold_scores.jsonl.gz'
    decisions=gzip.open(decisions_path,'wt');fold_scores=gzip.open(fold_scores_path,'wt')
    decision_hashes={};selection_count=0;guard_attempts=[]
    original_open=Path.open
    def guard(self,*args,**kwargs):
        if self.resolve()==label_path:
            guard_attempts.append(str(self));raise AssertionError('C0 attempted direct label-file access')
        return original_open(self,*args,**kwargs)
    def run_select(job,bank):
        Path.open=guard
        try:return select(model,job,bank[job['task']],{i:code[job['task']][i] for i in job['ids']},'corrected_tournament',.7)
        finally:Path.open=original_open
    try:
        for bank_name,bank in banks.items():
            bjobs=[j for j in jobs if j['task'] in bank];checks=Counter();raw={};fold_opportunity[bank_name]={}
            # O is one real control path per admitted job.
            for job in bjobs:
                selected,trace,stats=run_select(job,bank);saved=original[(bank_name,job['job_id'])]
                assert selected==saved['selected'] and trace==saved['trace'] and stats==saved['stats']
                raw[(job['job_id'],'O',None)]={'selected':selected,'trace':trace,'stats':stats,'exposure':
                    {'eligible_queried':0,'target_queried':0,'altered_queried':0}}
                checks['frozen_control_selected_trace_ledger_exact']+=1
            for fold in range(4):
                for arm in ('D','A'):
                    altered,metadata,opportunity=oracle_bank(bank,labels,arm,fold)
                    fold_opportunity[bank_name][arm+str(fold)]=opportunity
                    for job in bjobs:
                        selected,trace,stats=run_select(job,altered)
                        assert len(trace)==len({tuple(sorted((e['a'],e['b']))) for e in trace})
                        assert len(trace)==stats['unique_feedback_reads']<=job['budget']
                        exposure=Counter()
                        for edge in trace:
                            pair='|'.join(sorted((edge['a'],edge['b'])))
                            m=metadata[job['task']][pair];actual,conf=parsed(altered[job['task']][pair])
                            assert edge['winner']==actual and edge['confidence']==conf
                            exposure['eligible_queried']+=m['eligible']
                            exposure['target_queried']+=m['target']
                            exposure['altered_queried']+=m['altered']
                            exposure['accepted_queried']+=actual is not None
                        if not exposure['altered_queried']:
                            O=raw[(job['job_id'],'O',None)]
                            assert (selected,trace,stats)==(O['selected'],O['trace'],O['stats'])
                            checks['zero_realized_change_implies_identical_control']+=1
                        raw[(job['job_id'],arm,fold)]={'selected':selected,'trace':trace,'stats':stats,'exposure':dict(exposure)}
                        checks['oracle_queried_edge_gate_direction_confidence_checks']+=len(trace)
                    # Each pair belongs to one eligible fold; eligibility itself is outcome-free.
                    checks['oracle_banks_built_and_all_pairs_checked']+=1
                    print(json.dumps({'stage':'selected_fold','bank':bank_name,'fold':fold,'arm':arm,'jobs':len(bjobs),
                                      'elapsed_seconds':time.monotonic()-began}),flush=True)
            for arm in ('D','A'):
                assert sum(fold_opportunity[bank_name][arm+str(f)]['eligible_addresses'] for f in range(4))==sum(map(len,bank.values()))
            # Seal all 9 actual paths per job for this bank before scoring any of them.
            bank_digest=hashlib.sha256()
            for job in bjobs:
                for arm,fold in [('O',None)]+[(a,f) for f in range(4) for a in ('D','A')]:
                    r={'bank':bank_name,'job_id':job['job_id'],'task':job['task'],'arm':arm,'fold':fold,
                       **raw[(job['job_id'],arm,fold)]}
                    r['decision_sha256']=objsha(r)
                    text=json.dumps(r,sort_keys=True)+'\n';decisions.write(text);bank_digest.update(text.encode());selection_count+=1
            decisions.flush();decision_hashes[bank_name]=bank_digest.hexdigest()
            aggregate=defaultdict(list)
            for job in bjobs:
                job_result={}
                for arm in ARMS:
                    records=[]
                    for fold in ([None] if arm=='O' else range(4)):
                        r=raw[(job['job_id'],arm,fold)];metric=evaluate(job['ids'],r['selected'],labels[job['task']])
                        hi=max(labels[job['task']][i] for i in job['ids']);lo=min(labels[job['task']][i] for i in job['ids'])
                        independent=0 if hi==lo else math.fsum(hi-labels[job['task']][i] for i in r['selected'])/(len(r['selected'])*(hi-lo))
                        assert math.isclose(metric['regret'],independent,abs_tol=1e-12)
                        metric.update(r['stats'])
                        metric.update({m:r['exposure'].get(m,0) for m in ('eligible_queried','target_queried','altered_queried')})
                        metric['selected_size']=len(r['selected']);records.append(metric)
                        fold_scores.write(json.dumps({'bank':bank_name,'job_id':job['job_id'],'task':job['task'],
                                                       'arm':arm,'fold':fold,'metrics':metric},sort_keys=True)+'\n')
                    job_result[arm]={m:statistics.fmean(r[m] for r in records) for m in records[0]}
                    aggregate[(job['task'],arm)].append(job_result[arm])
                per_episode.append({'bank':bank_name,'job_id':job['job_id'],'task':job['task'],'metrics':job_result,
                    'g_D':job_result['O']['regret']-job_result['D']['regret'],
                    'g_A':job_result['O']['regret']-job_result['A']['regret'],
                    'g_D_minus_g_A':job_result['A']['regret']-job_result['D']['regret']})
            per_task[bank_name]={task:{arm:{m:statistics.fmean(r[m] for r in aggregate[(task,arm)])
                for m in aggregate[(task,arm)][0]} for arm in ARMS} for task in sorted(bank)}
            bank_checks[bank_name]=dict(checks)
            bank_summary=summarize(per_task[bank_name])
            dump(out/('stage_'+bank_name+'.json'),bank_summary)
            print(json.dumps({'stage':'bank_complete','bank':bank_name,'summary':bank_summary,'checks':dict(checks),
                              'elapsed_seconds':time.monotonic()-began}),flush=True)
            raw.clear()
    finally:decisions.close();fold_scores.close();Path.open=original_open
    assert not guard_attempts
    tasks26=sorted(banks['DS1']);gpt_names=list(bm['banks']);new_names=list(tm['banks']);common=tm['common_tasks']
    metrics=per_task['DS1'][tasks26[0]]['O'].keys()
    def pool(names,tasks):return {t:{a:{m:statistics.fmean(per_task[n][t][a][m] for n in names) for m in metrics} for a in ARMS} for t in tasks}
    pooled_gpt=pool(gpt_names,tasks26)
    all_summary={n:summarize(d) for n,d in per_task.items()};all_summary['GPT_task_first_pooled']=summarize(pooled_gpt)
    common_data={n:{t:d[t] for t in common} for n,d in per_task.items()}
    common_data['GPT_task_first_pooled']={t:pooled_gpt[t] for t in common}
    common_data['DS0_task_first_pooled']=pool(new_names,common)
    common_summary={n:summarize(d) for n,d in common_data.items()}
    late=next(n for n in new_names if len(banks[n])==26)
    families=['DS1',late,'GPT_task_first_pooled'];criteria={}
    for mechanism in ('D','A'):
        family_results={f:all_summary[f]['contrasts']['O_minus_'+mechanism]['regret'] for f in families}
        criteria[mechanism]={'family_criteria':{f:{'gain_ge_001':r['gain']>=.01,'CI_lower_positive':r['ci95'][0]>0} for f,r in family_results.items()}}
        criteria[mechanism]['qualifies']=all(r['gain']>=.01 and r['ci95'][0]>0 for r in family_results.values())
    order=[all_summary[f]['contrasts']['A_minus_D']['regret'] for f in families]
    stable_D=all(r['ci95'][0]>0 for r in order);stable_A=all(r['ci95'][1]<0 for r in order)
    criteria['D_vs_A_order']={'families':families,'all_intervals_favor_D':stable_D,'all_intervals_favor_A':stable_A,
                              'point_estimate_signs':[1 if r['gain']>0 else -1 if r['gain']<0 else 0 for r in order]}
    qualifiers=[m for m in ('D','A') if criteria[m]['qualifies']]
    if len(qualifiers)==1:decision='prioritize_'+qualifiers[0]+'_judge_module_oracle_research_only'
    elif len(qualifiers)==2 and stable_D:decision='both_qualify_prioritize_direction_oracle_research_only'
    elif len(qualifiers)==2 and stable_A:decision='both_qualify_prioritize_abstention_oracle_research_only'
    else:decision='retain_C0_and_prioritize_minimal_label_blind_verifier_prototype_as_engineering_research'
    criteria['decision']=decision
    dump(out/'per_task.json',{'by_bank':per_task,'GPT_task_first_pooled':pooled_gpt,'common_tasks':common_data})
    (out/'per_episode_fold_averaged.jsonl').write_text(''.join(json.dumps(r,sort_keys=True)+'\n' for r in per_episode))
    dump(out/'fold_opportunity.json',fold_opportunity)
    dump(out/'selection_receipt.json',{'decisions_sha256':sha(decisions_path),'bank_decision_sha256':decision_hashes,
        'selection_records':selection_count,'oracle_labels_used_by_evaluator':True,'frozen_C0_direct_label_access_attempts':guard_attempts,
        'oracle_feedback_only_passed_to_frozen_C0':True,'all_controls_match':sum(c['frozen_control_selected_trace_ledger_exact'] for c in bank_checks.values())})
    result={'status':'passed','id':'partial-judge-intervention-c0','protocol_sha256':PROTOCOL_SHA,'summaries':all_summary,
        'common_10_summaries':common_summary,'common_tasks':common,'criteria':criteria,'checks':bank_checks,
        'selection_records':selection_count,'control_jobs':len(per_episode),'folds':4,'interventions':2,
        'scope':'Evaluator-side partial oracle; gold-backed directions are not deployable predictions. All original development tasks, own actual adaptive C0 path per arm.',
        'elapsed_seconds':time.monotonic()-began,'cost':{'new_model_calls':0,'training':0,'GPU':0,'actual_logical_query_counts':'per_fold_scores and macro summaries; intervention paths may differ'}}
    dump(out/'summary.json',result)
    for p,h in frozen.items():assert sha(ROOT/p)==h,p
    print(json.dumps({'stage':'complete','criteria':criteria,'elapsed_seconds':result['elapsed_seconds']}),flush=True)
    return result


def main():
    p=argparse.ArgumentParser();p.add_argument('--out',required=True);a=p.parse_args()
    out=(HERE/a.out).resolve();assert out.parent==HERE and not out.exists();out.mkdir()
    shutil.copyfile(__file__,out/'experiment.snapshot.py');shutil.copyfile(HERE/'protocol.json',out/'protocol.snapshot.json')
    dump(out/'command.json',{'argv':sys.argv,'python':sys.version,'platform':platform.platform(),
        'started_utc':datetime.now(timezone.utc).isoformat(),'script_sha256':sha(__file__),'protocol_sha256':PROTOCOL_SHA,
        'git_head':subprocess.check_output(['git','-C',str(ROOT),'rev-parse','HEAD'],text=True).strip(),'max_seconds':600})
    def stop(*args):raise TimeoutError('600 second analysis cap')
    signal.signal(signal.SIGALRM,stop);signal.alarm(600)
    start=time.monotonic();status,error='failed',None
    try:analyze(out);status='success'
    except BaseException:error=traceback.format_exc();print(error,flush=True)
    finally:
        signal.alarm(0);(out/'failure.log').write_text(error or '')
        dump(out/'final_info.json',{'status':status,'error':error,'elapsed_seconds':time.monotonic()-start})
        dump(out/'hashes.json',{p.name:sha(p) for p in out.iterdir() if p.is_file() and p.name!='hashes.json'})
    if error:sys.exit(1)


if __name__=='__main__':main()
