"""Offline position baselines and paired disagreement audit; no API or code execution."""
from collections import Counter
import hashlib
import json
from pathlib import Path

from prepare_coverage import ROOT, DATA


def main():
    exp = ROOT/'experiments'
    results = json.loads((exp/'coverage_retry_results.json').read_text())['adopted_results']
    manifest = json.loads((exp/'coverage_manifest.json').read_text())
    author = json.loads((exp/'coverage_author_reference.json').read_text())
    refs = {(m['task'],m['source_group_index']):m for t in author['tasks'] for m in t['matches']}
    rows = []
    for r in results:
        g = manifest['groups'][r['index']]; a = refs[r['task'],r['source_group_index']]
        y = g['best_index']; ours = r['parsed']['predicted_best_index']; theirs = a['author_prediction']
        assert r['error'] is None and r['best_index'] == a['best_index'] == y
        assert r['correct'] == int(ours == y)
        category = ('both_correct' if ours == y and theirs == y else 'ours_only' if ours == y else 'author_only' if theirs == y else 'both_wrong')
        sizes = []
        for path in g['paths']:
            content = (DATA/path).read_bytes()
            assert hashlib.sha256(content).hexdigest() == manifest['sha256'][path]
            sizes.append(len(content.decode().splitlines()))
        rows.append({'index':r['index'],'task':r['task'],'source_group_index':r['source_group_index'],
                     'true_index':y,'ours':ours,'author':theirs,'category':category,
                     'scores':g['scores'],'is_lower_better':g['is_lower_better'],
                     'absolute_score_gap_within_metric':abs(g['scores'][0]-g['scores'][1]),
                     'candidate_lines':sizes,'adopted_attempt':r['adopted_attempt']})
    assert len(rows) == 246 and len({r['index'] for r in rows}) == 246
    tasks = []
    for t in manifest['tasks']:
        rr = [r for r in rows if r['task'] == t['task']]
        tasks.append({'task':t['task'],'n':len(rr),'always_0_correct':sum(r['true_index']==0 for r in rr),
                      'always_1_correct':sum(r['true_index']==1 for r in rr),
                      'ours_correct':sum(r['ours']==r['true_index'] for r in rr),
                      'author_correct':sum(r['author']==r['true_index'] for r in rr),
                      'ours_choose_0':sum(r['ours']==0 for r in rr),
                      'categories':dict(Counter(r['category'] for r in rr))})
    categories = dict(Counter(r['category'] for r in rows))
    n = len(rows); baseline0 = sum(r['true_index']==0 for r in rows)
    correct = sum(r['ours']==r['true_index'] for r in rows)
    long = [r for r in rows if r['candidate_lines'][0]!=r['candidate_lines'][1]]
    selection = []
    for category in ['ours_only','author_only','both_wrong']:
        seen = set()
        for r in rows:
            if r['category'] == category and r['task'] not in seen:
                selection.append(r['index']); seen.add(r['task'])
                if len(seen)==3: break
    top = sorted(tasks,key=lambda t:(-t['categories'].get('both_wrong',0),t['task']))[:2]
    for t in top:
        i = next(r['index'] for r in rows if r['task']==t['task'] and r['category']=='both_wrong')
        if i not in selection: selection.append(i)
    export = {'n':n,'label_counts':dict(Counter(r['true_index'] for r in rows)),
        'prediction_counts':{'ours':dict(Counter(r['ours'] for r in rows)),'author':dict(Counter(r['author'] for r in rows))},
        'baselines':{'always_0':{'correct':baseline0,'accuracy':baseline0/n},
                     'always_1':{'correct':n-baseline0,'accuracy':(n-baseline0)/n},
                     'fair_random':{'expected_accuracy':0.5,'observed_run':False}},
        'ours_correct':correct,'author_correct':sum(r['author']==r['true_index'] for r in rows),
        'ours_gain_over_always_0':correct-baseline0,
        'paired_vs_always_0':{'ours_only_correct':sum(r['ours']==r['true_index'] and r['true_index']==1 for r in rows),
                             'baseline_only_correct':sum(r['ours']!=r['true_index'] and r['true_index']==0 for r in rows)},
        'conditional_accuracy':{str(y):{'n':sum(r['true_index']==y for r in rows),
                  'correct':sum(r['ours']==y and r['true_index']==y for r in rows)} for y in (0,1)},
        'categories':categories,'agreement':sum(r['ours']==r['author'] for r in rows)/n,
        'code_length_proxy':{'unequal_length_pairs':len(long),
              'ours_choose_longer':sum(r['ours']==int(r['candidate_lines'][1]>r['candidate_lines'][0]) for r in long),
              'longer_is_true_winner':sum(r['true_index']==int(r['candidate_lines'][1]>r['candidate_lines'][0]) for r in long),
              'limitation':'Post-hoc descriptive proxy only; source lines are not architecture complexity or compute.'},
        'review_selection':{'indices':selection,'rule':'First three distinct tasks by manifest index in each of ours_only, author_only, both_wrong; plus first pair in each of top two tasks by both_wrong count (ties alphabetical). Exploratory, not a random sample.'},
        'per_task':tasks,'pairs':rows}
    (exp/'coverage_analysis.json').write_text(json.dumps(export,ensure_ascii=False,indent=2))
    # Retain both full rationales locally for the fixed qualitative sample.
    evidence=[]
    for i in selection:
        r=next(r for r in rows if r['index']==i);g=manifest['groups'][i]
        p=ROOT/'outputs/coverage-20261021'
        if r['adopted_attempt']==2: p=p/'retry-attempt-002'
        record=p/f'pair-{i:03d}.json';saved=json.loads(record.read_text())
        source=ROOT/'data/author_reference'/f'{r["task"]}.json'
        names=[Path(path).stem[-4:]+'.py' for path in g['paths']]
        matched=[a for a in json.loads(source.read_text())['results'] if [s['path'] for s in a['solutions']]==names and [s['score'] for s in a['solutions']]==g['scores']]
        assert len(matched)==1 and matched[0]['prediction']['best_index']==r['author']
        evidence.append({**r,'ours_record':str(record),'ours_record_sha256':hashlib.sha256(record.read_bytes()).hexdigest(),
              'author_record':str(source),'author_record_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
              'ours_answer':saved['response']['choices'][0]['message']['content'],
              'author_reasoning':matched[0]['prediction'].get('reasoning'), 'candidate_paths':g['paths']})
    (ROOT/'outputs/coverage-20261021/qualitative_review_evidence.json').write_text(json.dumps(evidence,ensure_ascii=False,indent=2))
    print(json.dumps({k:export[k] for k in ['baselines','ours_gain_over_always_0','paired_vs_always_0','categories','agreement','code_length_proxy','review_selection']},ensure_ascii=False))


if __name__=='__main__':
    main()
