#!/usr/bin/env python3
"""Pinned same-model transfer on bank-specific actual C0 paths; frozen C/H/L/T."""
import argparse
from collections import Counter,defaultdict
import gzip
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import platform
import random
import shutil
import signal
import statistics
import sys
import time
import traceback

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
sys.path.insert(0,str(ROOT));sys.dont_write_bytecode=True
BASE=HERE.parent/'c0-final-selection/experiment.py'
spec=importlib.util.spec_from_file_location('frozen_c0_final_selection',BASE)
base=importlib.util.module_from_spec(spec);spec.loader.exec_module(base)


def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def load(p):return json.loads(Path(p).read_text())
def dump(p,x):Path(p).write_text(json.dumps(x,indent=2,sort_keys=True,allow_nan=False)+'\n')
def gain(values,tasks):
    rng=random.Random(20261108093)
    samples=[statistics.fmean(rng.choices(values,k=len(values))) for _ in range(10000)]
    loo={t:statistics.fmean(v for t2,v in zip(tasks,values) if t2!=t) for t in tasks}
    return {'gain':statistics.fmean(values),'ci95':[base.percentile(samples,.025),base.percentile(samples,.975)],
            'per_task_gain':dict(zip(tasks,values)),'leave_one_task_out':loo,'leave_one_min':min(loo.values()),
            'leave_one_max':max(loo.values()),'every_leave_one_positive':all(v>0 for v in loo.values()),
            'tasks_improved':sum(v>1e-12 for v in values),'tasks_equal':sum(abs(v)<=1e-12 for v in values),
            'tasks_worsened':sum(v < -1e-12 for v in values)}


def analyze(out,bankdir):
    started=time.monotonic()
    protocol=load(HERE/'protocol.json')
    frozen=load(HERE.parent/'protocol.json')['frozen_sha256']
    for p,h in frozen.items():assert sha(ROOT/p)==h,p
    assert sha(HERE.parent/'c0-final-selection/protocol.json')==protocol['prior_protocol_sha256']
    manifest=load(bankdir/'manifest.json')
    assert manifest['protocol_sha256']==sha(HERE/'protocol.json')
    assert sha(bankdir/'mapping_audit.json')==manifest['mapping_audit_sha256']
    jobs=[json.loads(s) for s in (ROOT/'experiments/clean-ranking-v1/prepared/jobs.jsonl').read_text().splitlines()]
    by_job={j['job_id']:j for j in jobs}
    paths=load(ROOT/'experiments/clean-ranking-v1/prepared/code_files.json')
    code={t:{i:(ROOT/p).read_text() for i,p in files.items()} for t,files in paths.items()}
    banks={}
    for name,meta in manifest['banks'].items():
        path=ROOT/meta['path'];assert sha(path)==meta['sha256']
        banks[name]=json.loads(gzip.decompress(path.read_bytes()))
    inputs=dict(frozen)
    inputs.update({str(BASE.relative_to(ROOT)):sha(BASE),str((bankdir/'manifest.json').relative_to(ROOT)):sha(bankdir/'manifest.json'),
                   str((bankdir/'mapping_audit.json').relative_to(ROOT)):sha(bankdir/'mapping_audit.json'),
                   str((HERE/'protocol.json').relative_to(ROOT)):sha(HERE/'protocol.json')})
    inputs.update({meta['path']:meta['sha256'] for meta in manifest['banks'].values()})
    dump(out/'input_sha256.json',inputs)
    rows=[];checks={};module=base.load_world()
    # Guard the label file for the entire selection phase, even within imported code.
    label_path=ROOT/'experiments/clean-ranking-v1/prepared/evaluation_labels.json'
    original_open=Path.open;access=[]
    def guarded_open(self,*a,**kw):
        if self.resolve()==label_path:
            access.append(str(self));raise AssertionError('Execution labels requested during selection')
        return original_open(self,*a,**kw)
    Path.open=guarded_open
    try:
        for name,bank in banks.items():
            check=Counter()
            for job in jobs:
                if job['task'] not in bank:continue
                task=job['task'];contents={i:code[task][i] for i in job['ids']}
                C,trace,stats=base.select(module,job,bank[task],contents,'corrected_tournament',.7)
                assert len(trace)==stats['unique_feedback_reads']<=job['budget']
                assert len(trace)==len({tuple(sorted((e['a'],e['b']))) for e in trace})
                restricted={'|'.join(sorted((e['a'],e['b']))):bank[task]['|'.join(sorted((e['a'],e['b'])))] for e in trace}
                assert (C,trace,stats)==base.select(module,job,restricted,contents,'corrected_tournament',.7)
                high=base.feedback_edges(trace,bank[task],.7);low=base.feedback_edges(trace,bank[task],.5)
                assert [e[2] for e in high]==[e['winner'] for e in trace]
                ranks=base.ranks(job['ids'],low);best=max(ranks[i] for i in C)
                selected={'C':C,'H':base.top_set(job['ids'],high),'L':base.top_set(job['ids'],low),
                          'T':[i for i in C if ranks[i]==best]}
                assert selected['H']==base.independent_top(job['ids'],high)
                assert selected['L']==base.independent_top(job['ids'],low)
                assert selected['T']==base.independent_top(job['ids'],low,C)
                check['actual_C0_restricted_terminal_replays']+=1
                check['H_L_T_independent_selection_checks']+=3
                queried_missing=sum(bank[task]['|'.join(sorted((e['a'],e['b'])))]['missing_source_pair'] for e in trace)
                row={'bank':name,'job_id':job['job_id'],'task':task,'selected':selected,'trace':trace,'stats':stats,
                     'low_evidence':low,'queried_missing_source_pairs':queried_missing}
                row['selection_trace_sha256']=base.objsha(row);rows.append(row)
            checks[name]=dict(check)
            print(json.dumps({'stage':'selected','bank':name,'checks':dict(check)}),flush=True)
    finally:Path.open=original_open
    assert not access
    seal=out/'decisions.sealed.jsonl.gz'
    seal.write_bytes(gzip.compress(''.join(json.dumps(r,sort_keys=True)+'\n' for r in rows).encode(),mtime=0))
    dump(out/'selection_seal.json',{'decisions_sha256':sha(seal),'labels_loaded':False,'blocked_label_access_attempts':access,
        'jobs':len(rows),'evaluations':len(rows)*4,'checks':checks,'bank_manifest_sha256':sha(bankdir/'manifest.json')})
    # Evaluate only after all new-bank choices are sealed. Prior comparisons enter here.
    labels=load(label_path)
    prior_dir=HERE.parent/'c0-final-selection/run-002'
    for p,h in load(prior_dir/'hashes.json').items():assert sha(prior_dir/p)==h,p
    prior=load(prior_dir/'per_task.json')['by_bank']
    prior_episodes={}
    for line in (prior_dir/'per_episode.jsonl').read_text().splitlines():
        r=json.loads(line);prior_episodes[(r['bank'],r['job_id'])]=r
    grouping=defaultdict(list);episodes=[];mechanism=defaultdict(Counter)
    for row in rows:
        job=by_job[row['job_id']];utility=labels[row['task']];metrics={};counts=Counter()
        for arm,selected in row['selected'].items():
            result=base.evaluate(job['ids'],selected,utility)
            hi=max(utility[i] for i in job['ids']);lo=min(utility[i] for i in job['ids'])
            independent=0 if hi==lo else math.fsum(hi-utility[i] for i in selected)/(len(selected)*(hi-lo))
            assert math.isclose(result['regret'],independent,abs_tol=1e-12)
            result.update(unique_reads=len(row['trace']),cache_reads=row['stats']['cache_reads'],
                          budget_denials=row['stats']['budget_denials'],selected_size=len(selected))
            metrics[arm]=result;grouping[(row['bank'],row['task'],arm)].append(result)
        vd70,vd50=Counter(),Counter()
        for threshold,vd in ((.7,vd70),(.5,vd50)):
            for a,b,w in base.feedback_edges(row['trace'],banks[row['bank']][row['task']],threshold):
                if w is None:continue
                vd[a]+=1;vd[b]+=1
                if threshold==.5:
                    item=banks[row['bank']][row['task']]['|'.join(sorted((a,b)))];_,c=base.response_values(item)
                    if c>=.7:continue
                prefix='high' if threshold==.7 else 'added'
                counts[prefix+'_valid']+=1
                if utility[a]==utility[b]:counts[prefix+'_true_tie']+=1
                else:
                    counts[prefix+'_strict_total']+=1
                    counts[prefix+'_strict_correct']+=utility[w]==max(utility[a],utility[b])
        best_ids=[i for i in job['ids'] if utility[i]==max(utility[j] for j in job['ids'])]
        counts['queried_missing_source_pairs']=row['queried_missing_source_pairs']
        mechanism[row['bank']].update(counts)
        e={'bank':row['bank'],'job_id':row['job_id'],'task':row['task'],'metrics':metrics,
           'primary_gain':metrics['C']['regret']-metrics['L']['regret'],
           'actual_C0_gain_vs_original_DS1':prior_episodes[('DS',row['job_id'])]['metrics']['C']['regret']-metrics['C']['regret'],
           'counts':dict(counts),'coverage':{'best_zero_valid_high':sum(vd70[i]==0 for i in best_ids)/len(best_ids),
                                           'best_zero_valid_low':sum(vd50[i]==0 for i in best_ids)/len(best_ids)}}
        episodes.append(e)
    names=sorted(banks);available={}
    metrics_keys=('regret','best_hit','unique_reads','cache_reads','budget_denials','selected_size')
    for name in names:
        available[name]={t:{arm:{m:statistics.fmean(r[m] for r in grouping[(name,t,arm)]) for m in metrics_keys}
                              for arm in base.ARMS} for t in sorted(banks[name])}
    common=manifest['common_tasks'];assert len(common)>=2
    common_data={name:{t:data[t] for t in common} for name,data in {**prior,**available}.items()}
    def pool(data,names,tasks):
        return {t:{a:{m:statistics.fmean(data[n][t][a][m] for n in names) for m in metrics_keys}
                        for a in base.ARMS} for t in tasks}
    pooled_common=pool(common_data,names,common)
    common_data['DS0_task_first_pooled']=pooled_common
    gpt_names=[n for n in prior if n!='DS']
    common_data['GPT_task_first_pooled']=pool(common_data,gpt_names,common)
    summaries_available={n:base.summary(data) for n,data in available.items()}
    summaries_common={n:base.summary(data) for n,data in common_data.items()}
    setting={}
    for name,data in available.items():
        tasks=sorted(data)
        values=[prior['DS'][t]['C']['regret']-data[t]['C']['regret'] for t in tasks]
        setting[name+'_available_tasks']=gain(values,tasks)
    for name in names+['DS0_task_first_pooled']:
        values=[prior['DS'][t]['C']['regret']-common_data[name][t]['C']['regret'] for t in common]
        setting[name+'_common_tasks']=gain(values,common)
    primary=summaries_common['DS0_task_first_pooled']['contrasts']['C_minus_L']['regret']
    individual=[summaries_common[n]['contrasts']['C_minus_L']['regret']['gain'] for n in names]
    primary_checks={'two_individual_gains_positive':all(v>0 for v in individual),'pooled_gain_ge_001':primary['gain']>=.01,
                    'pooled_all_leave_one_positive':primary['every_leave_one_positive']}
    primary_checks['research_lead']=all(primary_checks.values())
    sec=setting['DS0_task_first_pooled_common_tasks']
    sec_individual=[setting[n+'_common_tasks']['gain'] for n in names]
    secondary_checks={'two_individual_gains_positive':all(v>0 for v in sec_individual),'pooled_gain_ge_001':sec['gain']>=.01,
                      'pooled_all_leave_one_positive':sec['every_leave_one_positive']}
    secondary_checks['research_lead']=all(secondary_checks.values())
    per_task={'available_new_banks':available,'matched_common_all_banks':common_data}
    dump(out/'per_task.json',per_task)
    (out/'per_episode.jsonl').write_text(''.join(json.dumps(e,sort_keys=True)+'\n' for e in episodes))
    dump(out/'mechanisms.json',{n:dict(c) for n,c in mechanism.items()})
    result={'status':'passed','id':protocol['id'],'protocol_sha256':sha(HERE/'protocol.json'),
            'available_task_counts':{n:len(banks[n]) for n in names},'common_tasks':common,'common_task_count':len(common),
            'available_summaries':summaries_available,'matched_common_summaries':summaries_common,
            'judge_setting_actual_C0_gains':setting,'primary_modular_criteria':primary_checks,
            'secondary_judge_setting_criteria':secondary_checks,'checks':checks,'jobs':len(rows),'selection_evaluations':len(rows)*4,
            'prior_reference_summary_sha256':sha(prior_dir/'summary.json'),'source_missing_pair_count':manifest['missing_pair_total'],
            'scope':'Same previously inspected development tasks; archived repeats, temperature/run-time/run-order setting confounded. Common 10-task transfer is separate from 26-task single-bank result.',
            'cost':{'new_model_calls':0,'candidate_training':0,'GPU':0},'elapsed_seconds':time.monotonic()-started}
    dump(out/'summary.json',result)
    print(json.dumps({'primary':primary,'primary_criteria':primary_checks,'secondary':sec,'secondary_criteria':secondary_checks}),flush=True)
    return result


def main():
    p=argparse.ArgumentParser();p.add_argument('--out',required=True);p.add_argument('--banks',default='banks_1');a=p.parse_args()
    out=HERE/a.out;assert not out.exists();out.mkdir()
    shutil.copyfile(__file__,out/'experiment.snapshot.py');shutil.copyfile(BASE,out/'base_c0.snapshot.py')
    shutil.copyfile(HERE/'protocol.json',out/'protocol.snapshot.json')
    dump(out/'command.json',{'argv':sys.argv,'python':sys.version,'platform':platform.platform(),'max_seconds':600,
                            'script_sha256':sha(__file__),'base_code_sha256':sha(BASE)})
    def stop(*a):raise TimeoutError('600 second analysis cap')
    signal.signal(signal.SIGALRM,stop);signal.alarm(600)
    status,error='failed',None;start=time.monotonic()
    try:analyze(out,HERE/a.banks);status='success'
    except BaseException:error=traceback.format_exc();print(error,flush=True)
    finally:
        signal.alarm(0);(out/'failure.log').write_text(error or '')
        dump(out/'final_info.json',{'status':status,'error':error,'elapsed_seconds':time.monotonic()-start})
        dump(out/'hashes.json',{p.name:sha(p) for p in out.iterdir() if p.is_file() and p.name!='hashes.json'})
    if error:sys.exit(1)


if __name__=='__main__':main()
