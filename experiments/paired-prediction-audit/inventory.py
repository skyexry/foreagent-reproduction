"""Join the frozen switched pairs to archived predictions and observed runtime."""
import argparse
import gzip
import hashlib
import json
import re
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CHRON = ROOT / 'experiments/chronological-memory-v1/run-001/batches.jsonl'
SWITCH = ROOT / 'experiments/c0-memory-switch-v1/memory-run-001/switches.jsonl'
LOCAL = 'stanford-autodl-v2'


def blob(data):
    return hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()


def lines(path):
    return [json.loads(line) for line in path.read_text().splitlines()]


def local_tree(base):
    out = []
    for p in base.rglob('*'):
        if p.is_file() and p.name in {'submission.csv','code.py','solution.py'}:
            out.append(dict(type='file', path=p.relative_to(ROOT).as_posix(), oid=blob(p.read_bytes())))
    for p in (ROOT/'experiments/online-stanford-v2').glob('*.csv.gz'):
        out.append(dict(type='file',path=p.relative_to(ROOT).as_posix(),oid=blob(gzip.decompress(p.read_bytes()))))
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('trees', type=Path)
    ap.add_argument('out', type=Path)
    args = ap.parse_args()
    rows = [r for r in lines(SWITCH) if r['c0_top_known'] and r['c0'].get('switch')]
    batches = lines(CHRON)
    pool = {(r['run'], i) for r in batches for i in r['candidates']}
    task_of = {r['run']:r['task'] for r in batches}
    assert len(rows) == 80 and len(pool) == 1360
    nodes = {}
    by_code = defaultdict(dict)
    costs = defaultdict(list)
    totals = {}
    loose = {}
    for name, task in sorted(task_of.items()):
        if name == LOCAL:
            base = ROOT/'phase1-reproduction/records'/LOCAL
            tree = local_tree(base)
            journal = json.loads((base/'logs/exp/journal.json').read_bytes())
        else:
            tree = json.loads((args.trees/(name+'.json')).read_text())
            journal = json.loads(gzip.decompress((ROOT/'data/historical/source_records'/name/'journal.json.gz').read_bytes()))
        files = {r['path']:r for r in tree if r['type']=='file'}
        ns = {n['id'][:8]:n for n in journal['nodes']}
        assert len(ns) == len(journal['nodes'])
        for n in ns.values():
            nodes[name,n['id']] = n
            if (name,n['id']) in pool and not n.get('is_skipped') and n.get('exec_time') and n['exec_time']>0:
                costs[task].append(dict(run=name,id=n['id'],seconds=n['exec_time'],valid=not n.get('is_buggy') and n.get('exc_type') is None))
        bound = set()
        other = []
        for path,item in files.items():
            if not (path.endswith('/submission.csv') or (name==LOCAL and path.endswith('.csv.gz'))):
                continue
            prefix = path.rsplit('/',1)[0]
            m = re.search(r'/all_nodes/node_([0-9a-f]{8})$', prefix)
            if not m:
                other.append(item['oid'])
                continue
            node = ns.get(m[1])
            if node is None:
                raise ValueError((name,path,'node missing in final journal'))
            code = files[prefix+'/code.py']['oid']
            assert code == blob(node['code'].encode()), (name,path)
            bound.add(item['oid'])
            if node.get('is_skipped') or node.get('is_buggy') or node.get('exec_time') is None:continue
            key = (task,code)
            prefer = (int('/save_' in path),len(path),path)
            pred = dict(path=path,oid=item['oid'],source_id=node['id'],source_run=name,
                        eval_path=prefix+'/eval_output.json' if prefix+'/eval_output.json' in files else None)
            old=by_code[key].get(item['oid'])
            if old is None or prefer<old[0]:
                by_code[key][item['oid']] = (prefer,pred)
        loose[name] = sorted(set(other)-bound)
        totals[name] = dict(unique_prediction_blobs=len(bound)+len(set(other)-bound), unique_node_prediction_blobs=len(bound),
                            unmatched_shared_submission_blobs=len(loose[name]))
        # Shared submissions are known to be overwritten by the last executed code.
        # An unmatched shared blob must be resolved independently before a zero-pair conclusion.
    assert not any(loose.values()), 'Unattributed shared submissions remain'
    out = []
    for r in rows:
        name,task = r['run'],r['task']
        result=dict(run=name,task=task,first_log_line=r['first_log_line'],disjoint=r['c0']['p_switch']=='1')
        for arm,k in [('c0','baseline_choice'),('memory','fusion_choice')]:
            i=r['c0'][k];n=nodes[name,i];code=blob(n['code'].encode())
            preds=[v[1] for v in by_code.get((task,code),{}).values()]
            result[arm]=dict(id=i,code_oid=code,was_skipped=n.get('is_skipped'),exec_seconds=n.get('exec_time'),predictions=preds)
        out.append(result)
    args.out.mkdir(parents=True,exist_ok=True)
    for f,value in [('pairs.json',out),('runtime.json',costs),('files.json',totals),('unmatched_shared.json',loose)]:
        (args.out/f).write_text(json.dumps(value,indent=2)+'\n')
    print('pairs',len(out),'both',sum(all(x[a]['predictions'] for a in ('c0','memory')) for x in out),
          'available',sum(bool(x[a]['predictions']) for x in out for a in ('c0','memory')),
          'unbound_shared',sum(map(len,loose.values())))


if __name__=='__main__':
    main()
