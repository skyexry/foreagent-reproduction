"""Replay original ForeAgent control logic on released real run transcripts.

python replay_author.py
Inputs: source_records/<run>/config.yaml, journal.json.gz, aide.log.gz.
History responses and logged Bernoulli outcomes are supplied as observations.
An explicit demonstration RNG is used only for unidentified revival opponents;
it is not presented as the original run seed. Expected ranks are scoring targets.
"""
import ast
import collections
import csv
import gzip
import hashlib
import inspect
import json
import os
import logging
from pathlib import Path
import re
import sys
import types
sys.dont_write_bytecode=True
from execution_policy import apply_execution_policy, verify_execution_policy

ROOT=Path(os.environ['FOREAGENT_RUN_DIR'])
REVISION='6b322cb88bdbcb2b2d3897ec7d0ded94a5bb2d06'
EXPECTED='df85087f0a23e5d95cb507fadc36fd5694f6abafe80d9ae2a841cdb838915d79'
PREFIX=r'^\[[^]]+\] (?:INFO|WARNING|ERROR): '
GEN=re.compile(PREFIX+r'Generated improvement candidate (\d+)/(\d+): ([0-9a-f]{8})')
COMPLETE=re.compile(PREFIX+r'World Model prediction completed in ')
NORMAL_WIN=re.compile(PREFIX+r'Round (\d+): Node ([0-9a-f]{8}) beats ([0-9a-f]{8}) \(confidence: ([0-9.]+)\)')
NORMAL_UNKNOWN=re.compile(PREFIX+r'Round (\d+): Node ([0-9a-f]{8}) vs ([0-9a-f]{8}) inconclusive \(confidence: ([0-9.]+)\)')
REVIVAL=re.compile(PREFIX+r'Round (\d+) \(Re-match\): Node ([0-9a-f]{8}) (.*)')
DECISION=re.compile(PREFIX+r'(Executing|Skipping) candidate \(rank=(\d+), ([^)]*)\): ([0-9a-f]{8})')
PARSED=re.compile(PREFIX+r'Agent is parsing execution results for node ([0-9a-f]+)')


def dump(path,data):path.write_text(json.dumps(data,ensure_ascii=False,indent=2))


def original_module():
    source=ROOT/'world_model_original.py'
    assert hashlib.sha256(source.read_bytes()).hexdigest()==EXPECTED
    tree=ast.parse(source.read_text())
    tree.body=[n for n in tree.body if not(isinstance(n,ast.ImportFrom) and n.level)]
    mod=types.ModuleType('author_original_replay')
    sys.modules[mod.__name__]=mod
    def local(**kw):raise AssertionError('Historical replay uses stored responses.')
    mod.__dict__.update(Node=types.SimpleNamespace,query=local)
    exec(compile(tree,str(source),'exec'),mod.__dict__)
    mod.logger.setLevel(logging.CRITICAL)
    return mod


def config(text):
    def value(name):
        matches=re.findall(r'^\s*'+name+r':\s*(.*)$',text,re.M)
        assert len(matches)==1,(name,matches)
        return matches[0].strip()
    return {'model':value('world_model_model'),'temperature':float(value('world_model_temp')),
            'confidence_threshold':float(value('world_model_confidence_threshold')),
            'exec_probability':float(value('world_model_exec_probability')),
            'num_candidates':int(value('improve_num_candidates')),'top_k':int(value('improve_top_k')),
            'explicit_controller_seed_fields':[l for l in text.splitlines() if re.search(r'seed|random_state',l,re.I)]}


def parse_run(folder):
    with gzip.open(folder/'journal.json.gz','rt') as f:journal=json.load(f)
    with gzip.open(folder/'aide.log.gz','rt') as f:lines=f.read().splitlines()
    nodes={n['id']:n for n in journal['nodes']}
    prefixes={n[:8]:n for n in nodes}
    assert len(prefixes)==len(nodes)
    batches=[];current=None
    for lineno,line in enumerate(lines,1):
        m=GEN.match(line)
        if m:
            if current is None or current['completed']:
                current={'batch':len(batches)+1,'generation':[],'normal':[],'revival':[],
                         'decisions':[],'forced_events':[],'parsed_execution':[],'completed':False}
                batches.append(current)
            ordinal,target,short=m.groups()
            current['generation'].append({'ordinal':int(ordinal),'target':int(target),'short':short,'line':lineno})
            continue
        if current is None:continue
        if COMPLETE.match(line):
            current['completed']=True;current['completion_line']=lineno
        elif m:=NORMAL_WIN.match(line):
            r,winner,loser,conf=m.groups();current['normal'].append({'round':int(r),'winner':winner,'loser':loser,'confidence':conf,'line':lineno})
        elif m:=NORMAL_UNKNOWN.match(line):
            r,a,b,conf=m.groups();current['normal'].append({'round':int(r),'a':a,'b':b,'winner':None,'confidence':conf,'line':lineno})
        elif m:=REVIVAL.match(line):
            r,pending,result=m.groups()
            outcome=0 if result.startswith('beats winner') else (1 if result.startswith('lost to winner') else None)
            current['revival'].append({'round':int(r),'pending':pending,'winner_slot':outcome,'line':lineno})
        elif m:=DECISION.match(line):
            action,rank,detail,short=m.groups()
            current['decisions'].append({'short':short,'rank':int(rank),'executed':action=='Executing',
                                         'probability_tested':'beyond Top-' not in detail,'line':lineno})
        elif 'No nodes executed due to probability. Forcing execution of Rank 0 candidate.' in line:
            current['forced_events'].append(lineno)
        elif m:=PARSED.match(line):
            current['parsed_execution'].append(m[1])
    return journal,nodes,prefixes,batches


def main():
    verify_execution_policy()
    mod=original_module()
    all_rows=[];run_rows=[];skipped=[]
    for folder in sorted((ROOT/'source_records').iterdir()):
        if not folder.is_dir():continue
        cfg=config((folder/'config.yaml').read_text())
        assert cfg['top_k']==1
        journal,nodes,prefix,batches=parse_run(folder)
        accepted=[]
        for batch in batches:
            unknown=[g['short'] for g in batch['generation'] if g['short'] not in prefix]
            if not batch['completed'] or unknown:
                skipped.append({'run':folder.name,'batch':batch['batch'],'completed':batch['completed'],
                                'generated_short_ids':[x['short'] for x in batch['generation']],
                                'journal_missing_ids':unknown,'reason':'unfinished_log_batch' if not batch['completed'] else 'generated_nodes_absent_from_final_journal'})
                continue
            ids=[prefix[g['short']] for g in batch['generation']]
            ns=[nodes[x] for x in ids]
            # A journal score is an output target, never a decision input.
            assert ids==[n['id'] for n in sorted(ns,key=lambda n:n['ctime'])]
            parent_ids={journal['node2parent'].get(x) for x in ids}
            assert len(parent_ids)==1
            histories={json.dumps(n['wm_comparison_results'],sort_keys=True) for n in ns}
            assert len(histories)==1 and ns[0]['wm_comparison_results']
            transcript=ns[0]['wm_comparison_results']
            assert len(batch['decisions'])==len(ids),(folder.name,batch['batch'],'decision log count')
            wm=mod.WorldModel(folder.name,'historical records',config=mod.WorldModelConfig(
                model=cfg['model'],temperature=cfg['temperature'],confidence_threshold=cfg['confidence_threshold'],
                exec_probability=cfg['exec_probability']))
            cursors={'history':0,'normal':0,'revival':0};pair_checks=[]
            def replay_batch(pairs,max_workers=None):
                call_line=inspect.currentframe().f_back.f_lineno
                assert call_line in [519,568],call_line
                kind='normal' if call_line==519 else 'revival'
                result=[]
                for a,b,r in pairs:
                    c=transcript[cursors['history']];cursors['history']+=1
                    event=batch[kind][cursors[kind]];cursors[kind]+=1
                    assert c['round']==r==event['round']
                    assert c['valid']==(c['confidence']>=cfg['confidence_threshold'])
                    if kind=='normal':
                        assert f"{c['confidence']:.2f}"==event['confidence']
                        if event['winner'] is None:
                            assert a.id[:8]==event['a'] and b.id[:8]==event['b']
                            assert not c['valid'] and c['winner'] is None
                        else:
                            assert c['valid'] and (a,b)[c['winner']].id[:8]==event['winner']
                            assert (a,b)[1-c['winner']].id[:8]==event['loser']
                    else:
                        assert a.id[:8]==event['pending'] and c['winner']==event['winner_slot']
                    pair_checks.append({'round':r,'kind':kind,'a':a.id,'b':b.id,
                                        'b_identity_provenance':'derived_original_normal_pair_and_log_verified' if kind=='normal' else 'demonstration_rng_not_historical',
                                        'winner_slot':c['winner'],'valid':c['valid'],'log_line':event['line']})
                    result.append(mod.ComparisonResult(winner_idx=c['winner'],
                        loser_idx=None if c['winner'] is None else 1-c['winner'],confidence=c['confidence'],round_num=r,is_valid=c['valid']))
                return result
            wm._batch_predict_pairwise=replay_batch
            mod.random.seed(0)  # Explicit synthetic opponent choices; ranks are verified conditional on recorded responses.
            candidates=[types.SimpleNamespace(id=n['id'],code=n['code']) for n in ns]
            ranked,comparisons,meta=wm.tournament_rank(candidates)
            assert cursors['history']==len(transcript)
            assert cursors['normal']==len(batch['normal']) and cursors['revival']==len(batch['revival'])
            expected_meta={n['id']:{'rank':n['wm_predicted_rank'],'round':n['wm_round']} for n in ns}
            rank_match=meta==expected_meta
            log_sorted=[prefix[e['short']] for e in batch['decisions']]
            order_match=[n.id for n in ranked]==log_sorted
            for e in batch['decisions']:assert meta[prefix[e['short']]]['rank']==e['rank']
            probability=[e for e in batch['decisions'] if e['probability_tested']]
            position=[0]
            def recorded_coin():
                outcome=probability[position[0]]['executed'];position[0]+=1;return outcome
            wm.should_execute=recorded_coin
            policy=apply_execution_policy(ranked,meta,wm)
            assert position[0]==len(probability)
            expected_probability=[prefix[e['short']] for e in probability if e['executed']]
            probability_match=policy['probability_executed']==expected_probability
            fallback_match=int(policy['forced_fallback'])==len(batch['forced_events'])
            expected_execution={n['id'] for n in ns if not n['is_skipped']}
            execution_match=set(policy['final_executed'])==expected_execution
            parsed_in_batch=[x for x in batch['parsed_execution'] if x in ids]
            execution_log_match=policy['final_executed']==parsed_in_batch
            row={'run':folder.name,'batch':batch['batch'],'candidate_count':len(ids),
                 'parent_id':next(iter(parent_ids)),'generation_order':ids,
                 'comparison_count':len(comparisons),'normal_pairs_log_checked':len(batch['normal']),
                 'revival_pending_nodes_log_checked':len(batch['revival']),
                 'rank_and_round_match':rank_match,'sorted_order_matches_log':order_match,
                 'probability_decisions_match_log':probability_match,'forced_fallback_match_log':fallback_match,
                 'final_execution_matches_journal':execution_match,'final_execution_order_matches_log':execution_log_match,
                 'replayed_rank_meta':meta,'author_rank_meta':expected_meta,
                 'replayed_sorted_order':[n.id for n in ranked],'author_sorted_order':log_sorted,
                 'replayed_final_execution':policy['final_executed'],'author_final_execution':sorted(expected_execution),
                 'forced_fallback':policy['forced_fallback'],'comparison_log_checks':pair_checks,
                 'source_url':f'https://huggingface.co/datasets/zjunlp/PredictBeforeExecute/blob/{REVISION}/agent_runs/ForeAgent/{folder.name}/logs/journal.json'}
            all_rows.append(row);accepted.append(row)
        run_rows.append({'run':folder.name,'config':cfg,'logged_batches':len(batches),
                         'verified_batches':len(accepted),'candidate_count':sum(r['candidate_count'] for r in accepted),
                         'rank_matches':sum(r['rank_and_round_match'] for r in accepted),
                         'execution_matches':sum(r['final_execution_matches_journal'] for r in accepted)})
        print(folder.name,'batches',len(accepted),'ranking matches',sum(r['rank_and_round_match'] for r in accepted),
              'execution matches',sum(r['final_execution_matches_journal'] for r in accepted),flush=True)
    assert len(run_rows)==15
    flags=['rank_and_round_match','sorted_order_matches_log','probability_decisions_match_log',
           'forced_fallback_match_log','final_execution_matches_journal','final_execution_order_matches_log']
    summary={'dataset_revision':REVISION,'original_world_model_sha256':EXPECTED,'runs_checked':len(run_rows),
             'batches_replayed':len(all_rows),'candidates_replayed':sum(r['candidate_count'] for r in all_rows),
             'comparison_records_replayed':sum(r['comparison_count'] for r in all_rows),
             'matches':{flag:sum(r[flag] for r in all_rows) for flag in flags},
             'candidate_rank_round_matches':sum(r['candidate_count'] for r in all_rows if r['rank_and_round_match']),
             'forced_fallback_batches':sum(r['forced_fallback'] for r in all_rows),
             'logged_batches_outside_final_journal_or_incomplete':len(skipped),
             'network_calls':0,'candidate_training_runs':0,
             'mode':'Historical-response-sequence control-flow replay with log-observed probability decisions.',
             'randomness_note':'Revival opponent identities are synthetic because original RNG state is unavailable. Normal pair identities and pending-node identities are independently log-checked. Stored responses are supplied by batch/position, not synthetic pair identity.',
             'scope':'Verifies original ranking and execution state updates conditional on released historical responses/actions; independent generation of LLM responses and recovery of original RNG state are separate tasks.',
             'per_run':run_rows}
    dump(ROOT/'replay_results.json',all_rows);dump(ROOT/'summary.json',summary);dump(ROOT/'excluded_log_batches.json',skipped)
    with (ROOT/'per_run.csv').open('w',newline='') as f:
        keys=['run','logged_batches','verified_batches','candidate_count','rank_matches','execution_matches']
        w=csv.DictWriter(f,fieldnames=keys);w.writeheader();w.writerows({k:r[k] for k in keys} for r in run_rows)
    print('SUMMARY',json.dumps({k:v for k,v in summary.items() if k!='per_run'},ensure_ascii=False),flush=True)


if __name__=='__main__':main()
