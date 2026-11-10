#!/usr/bin/env python3
"""Project pinned report path/index/confidence only; retain missing feedback explicitly."""
from collections import Counter
import gzip
import hashlib
import json
from pathlib import Path
import shutil
import sys
import time

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
sys.path.insert(0,str(ROOT))
from reproduction.round08.data import verify_source
from reproduction.clean_ranking_v1.correctness import response_values


def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def dump(p,x):Path(p).write_text(json.dumps(x,indent=2,sort_keys=True,allow_nan=False)+'\n')


def main():
    source=HERE/sys.argv[1];out=HERE/sys.argv[2]
    assert not out.exists();out.mkdir()
    shutil.copyfile(__file__,out/'builder.snapshot.py')
    shutil.copyfile(HERE/'protocol.json',out/'protocol.snapshot.json')
    manifest=json.loads((source/'download_manifest.json').read_text())
    ds=json.loads((ROOT/'experiments/clean-ranking-v1/prepared/feedback.json').read_text())
    paths=json.loads((ROOT/'experiments/clean-ranking-v1/prepared/code_files.json').read_text())
    frozen=json.loads((ROOT/'experiments/clean-ranking-v1/prepared/source_manifest.json').read_text())['sha256']
    identity={}
    for task,files in paths.items():
        identity[task]={}
        for cid,filename in files.items():
            assert sha(ROOT/filename)==frozen[filename] and cid==sha(ROOT/filename)[:20]
            identity[task][Path(filename).name]=cid
    banks={};audits=[]
    for source_row in manifest['files']:
        if source_row['status']!='verified':continue
        run,task=source_row['feedback_run'],source_row['task']
        p=Path(source_row['target']);assert verify_source(source_row,p)==source_row['sha256']
        gt=ROOT/'data/reward-model/corpus-6b322cb-raw-v1/solutions_subset_50'/task/'ground_truth'/f'groups_{task}_n2.json'
        assert sha(gt)==frozen[str(gt.relative_to(ROOT))]
        groups=json.loads(gt.read_text())
        names={Path(p).name for g in groups for p in g['paths']}
        suffixes={n[-7:]:n for n in names};assert len(suffixes)==len(names)
        group_index={tuple(sorted(Path(p).name for p in g['paths'])):i for i,g in enumerate(groups)}
        def identify(path):
            name=Path(path).name
            return name if name in names else suffixes[name]
        # Groundtruth, correct, solution scores and reasoning fields are projected away.
        raw=json.loads(p.read_text())
        raw_rows=raw['results'];table={};counts=Counter();anomalies=[]
        for number,row in enumerate(raw_rows):
            order_names=[identify(x['path']) for x in row['solutions']]
            assert len(order_names)==2 and order_names[0]!=order_names[1]
            pair_names=tuple(sorted(order_names));assert pair_names in group_index
            if any(n not in identity[task] for n in order_names):
                counts['excluded_not_representative_or_nonfinite']+=1;continue
            order=[identity[task][n] for n in order_names]
            key='|'.join(sorted(order))
            if key not in ds[task]:counts['excluded_not_admitted_pair']+=1;continue
            assert key not in table,'duplicate pair'
            pred=row.get('prediction');pred=pred if isinstance(pred,dict) else {}
            item={'order':order,'predicted_best_index':pred.get('best_index'),
                  'confidence':pred.get('confidence',.5),'source_group_index':group_index[pair_names],
                  'source_row':number,'missing_source_pair':False}
            assert item['source_group_index']==ds[task][key]['source_group_index']
            index,conf=response_values(item)
            counts['source_pairs']+=1;counts['invalid_parsed_index']+=index is None
            counts['missing_confidence_default_05']+='confidence' not in pred
            counts['accepted_07']+=index is not None and conf>=.7
            counts['accepted_05']+=index is not None and conf>=.5
            if index is None:anomalies.append({'pair':key,'source_row':number,'raw_index':item['predicted_best_index'],
                                             'raw_confidence':item['confidence'],'prediction_keys':sorted(pred)})
            table[key]=item
        missing=sorted(set(ds[task])-set(table))
        # Explicit unknown records: no winner direction is imputed from any bank or score.
        for key in missing:
            table[key]={'order':ds[task][key]['order'],'predicted_best_index':None,'confidence':0,
                        'source_group_index':ds[task][key]['source_group_index'],
                        'source_row':None,'missing_source_pair':True}
        assert set(table)==set(ds[task])
        banks.setdefault(run,{})[task]=table
        audits.append({'feedback_run':run,'task':task,'source_path':str(p),'source_sha256':sha(p),
                       'source_git_blob_oid':source_row['git_blob_oid'],'source_lfs':source_row['lfs'],
                       'raw_rows':len(raw_rows),'admitted_pairs':len(table),'missing_pair_count':len(missing),
                       'missing_pairs':missing,'counts':dict(counts),'invalid_records':anomalies})
    bank_files={}
    for run,bank in banks.items():
        dest=out/(run+'.json.gz')
        content=(json.dumps(bank,sort_keys=True,separators=(',',':'),allow_nan=False)+'\n').encode()
        dest.write_bytes(gzip.compress(content,mtime=0))
        assert json.loads(gzip.decompress(dest.read_bytes()))==bank
        bank_files[run]={'path':str(dest.relative_to(ROOT)),'sha256':sha(dest),'tasks':sorted(bank),
                         'task_count':len(bank),'admitted_pairs':sum(map(len,bank.values()))}
    common=sorted(set.intersection(*(set(b) for b in banks.values())))
    dump(out/'mapping_audit.json',{'files':audits,'code_identity_sha256':sha(ROOT/'experiments/selection-frontier-02/banks/mapping_audit.json'),
        'source_projection':'solutions[].path and prediction best_index/confidence only; original score/correct/groundtruth/reasoning discarded',
        'missing_semantics':'explicit unknown index=None confidence=0; query counts, abstention and missing flag retained',
        'missing_pair_total':sum(a['missing_pair_count'] for a in audits)})
    dump(out/'manifest.json',{'status':'passed','banks':bank_files,'common_tasks':common,
        'common_tasks_count':len(common),'source_files_verified':len(audits),
        'download_manifest_sha256':sha(source/'download_manifest.json'),'mapping_audit_sha256':sha(out/'mapping_audit.json'),
        'labels_in_bank':False,'new_model_calls':0,'protocol_sha256':sha(HERE/'protocol.json'),
        'missing_pair_total':sum(a['missing_pair_count'] for a in audits),
        'unavailable_tasks_are_omitted':True})
    dump(out/'hashes.json',{p.name:sha(p) for p in out.iterdir() if p.is_file() and p.name!='hashes.json'})
    print(json.dumps({'banks':bank_files,'common_tasks':common,'missing_pairs':sum(a['missing_pair_count'] for a in audits)},indent=2))


if __name__=='__main__':main()
