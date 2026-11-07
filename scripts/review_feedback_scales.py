"""Post-hoc descriptive scale check on the same eligible, strictly ordered pairs."""
from collections import Counter
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from reproduction.round06.run import load_task
from reproduction.round08.data import check_registration, load_groups, load_table

def summarize(table, truth):
    numbers=Counter()
    for key,winner in truth.items():
        row=table[key]
        numbers['pairs']+=1
        if row['winner'] is not None and row['confidence']>=.7:
            numbers['accepted']+=1
            numbers['accepted_correct']+=row['winner']==winner
    return numbers

if __name__=='__main__':
    check_registration()
    groups=load_groups()
    corpus=json.loads((ROOT/'experiments/corpus26-v2/protocol.json').read_text())
    entries=json.loads((ROOT/'experiments/round-08/data_manifest.json').read_text())['files']
    counts={}
    for spec in corpus['tasks']:
        t=spec['task']
        utility,deepseek=load_task(t,spec['source'])
        truth={pair:max(pair,key=utility.__getitem__) for pair in deepseek
               if all(x in utility for x in pair) and utility[pair[0]]!=utility[pair[1]]}
        counts.setdefault('DeepSeek saved run',Counter()).update(summarize(deepseek,truth))
        for entry in (e for e in entries if e['task']==t):
            table,_=load_table(entry,groups[t])
            assert table.keys()==deepseek.keys()
            counts.setdefault(entry['feedback_run'],Counter()).update(summarize(table,truth))
    for c in counts.values():
        c['coverage']=c['accepted']/c['pairs']
        c['accuracy_among_accepted']=c['accepted_correct']/c['accepted']
    print(json.dumps(counts,indent=2))
