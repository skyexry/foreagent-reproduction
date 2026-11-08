"""Prepare new jobs from original author files, with separately held evaluation labels."""
from collections import defaultdict
import hashlib
import itertools
import json
import math
from pathlib import Path
import random

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT/'data/reward-model/corpus-6b322cb-raw-v1'
FEEDBACK_RUN = 'deepseek-reasoner_1p0_pboost_cot_20251209_164656'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def dump(path, obj):
    Path(path).write_text(json.dumps(obj, ensure_ascii=False, indent=2, allow_nan=False)+'\n')


def prepare(protocol, output):
    output = Path(output)
    if output.exists():
        raise ValueError('New prepared directory required')
    output.mkdir(parents=True)
    source_hashes, exclusions = {}, {}
    banks, labels, code_files, jobs = {}, {}, {}, []
    for gt in sorted((RAW/'solutions_subset_50').glob('*/ground_truth/*n2.json')):
        task = gt.parents[1].name
        source = ROOT/'data/author_reference'/f'{task}.json'
        source_hashes[str(gt.relative_to(ROOT))] = digest(gt)
        source_hashes[str(source.relative_to(ROOT))] = digest(source)
        groups = json.loads(gt.read_text())
        rows = json.loads(source.read_text())['results']
        index = defaultdict(list)
        for r in rows:
            ss = r.get('solutions', [])
            if len(ss) == 2:
                index[tuple([s['path'] for s in ss]+[str(s['score']) for s in ss])].append(r)
        scores, contents = {}, {}
        finite_groups = []
        bad = []
        for i, g in enumerate(groups):
            if not all(math.isfinite(float(s)) for s in g['scores']):
                bad.append(i)
                continue
            finite_groups.append((i, g))
            for p, score in zip(g['paths'], g['scores']):
                name = Path(p).name
                value = -float(score) if g['is_lower_better'] else float(score)
                if name in scores and scores[name] != value:
                    raise ValueError('Inconsistent candidate score')
                scores[name] = value
                code = gt.parents[1]/'code'/name
                contents[name] = digest(code)
                source_hashes[str(code.relative_to(ROOT))] = contents[name]
        # Representative choice uses filename, never the performance values.
        representative = {}
        for name in sorted(scores):
            representative.setdefault(contents[name], name)
        kept = set(representative.values())
        opaque = {n: contents[n][:20] for n in kept}
        if len(set(opaque.values())) != len(kept):
            raise ValueError('Opaque-ID collision')
        bank = {}
        for group_index, g in finite_groups:
            names = [Path(p).name for p in g['paths']]
            if not all(n in kept for n in names):
                continue
            key = tuple([Path(p).stem[-4:]+'.py' for p in g['paths']] + [str(s) for s in g['scores']])
            found = index[key]
            if len(found) != 1:
                raise ValueError('Raw feedback join is not unique')
            row = found[0]
            if row['groundtruth']['best_index'] != g['best_index']:
                raise ValueError('Author label mismatch')
            ids = [opaque[n] for n in names]
            prediction = row.get('prediction', {})
            pair = '|'.join(sorted(ids))
            if pair in bank:
                raise ValueError('Duplicate source pair')
            # No scores, correct flag, reasoning or ground-truth field in policy bank.
            bank[pair] = {'order': ids,
                'predicted_best_index': prediction.get('best_index'),
                'confidence': prediction.get('confidence', 0.5),
                'source_group_index': group_index}
        ids = sorted(opaque.values())
        size_attempts=[]
        for k in range(min(protocol['candidate_count_max'], len(ids)), 1, -1):
            possible = math.comb(len(ids), k)
            wanted = min(protocol['max_distinct_pools_per_task'], possible)
            rng = random.Random(f"{protocol['pool_seed']}:{task}:{k}")
            seen, pools = set(), []
            attempted = 0
            while len(pools) < wanted and attempted < protocol['pool_sampling_attempt_limit']:
                attempted += 1
                pool = tuple(sorted(rng.sample(ids, k)))
                if pool in seen:
                    continue
                seen.add(pool)
                if not all('|'.join(sorted(e)) in bank for e in itertools.combinations(pool, 2)):
                    continue
                pools.append(pool)
            size_attempts.append(dict(candidate_count=k,attempts=attempted,admitted=len(pools)))
            if pools:
                break
        if not pools:
            raise ValueError('No admissible pool for ' + task)
        for p_index, pool in enumerate(pools):
            for repeat in range(protocol['per_pool_repeats']):
                seed_text = f"{protocol['repeat_seed']}:{task}:{p_index}:{repeat}"
                seed = int(hashlib.sha256(seed_text.encode()).hexdigest()[:12], 16)
                order = list(pool)
                random.Random(seed).shuffle(order)
                jobs.append(dict(job_id=f'{task}:{p_index}:{repeat}', task=task,
                    pool_id=p_index, repeat=repeat, seed=seed, ids=order,
                    budget=min(protocol['unique_query_budget_max'], math.comb(k, 2))))
        banks[task] = bank
        labels[task] = {opaque[n]: scores[n] for n in sorted(kept)}
        code_files[task] = {opaque[n]: str((gt.parents[1]/'code'/n).relative_to(ROOT)) for n in sorted(kept)}
        exclusions[task] = dict(raw_pairs=len(groups), nonfinite_group_indices=bad,
            finite_candidate_records=len(scores), distinct_code_candidates=len(kept),
            excluded_duplicate_candidate_files=sorted(set(scores)-kept),
            requested_distinct_pools=wanted, admitted_distinct_pools=len(pools),
            attempted_pool_samples=attempted, candidate_count=k, pool_size_attempts=size_attempts)
    # Source confidences should be JSON numbers; preserve abnormal numeric strings
    # and encode nonfinite values as strings for the strict corrected parser.
    def finite_json(obj):
        if isinstance(obj, float) and not math.isfinite(obj):
            return str(obj)
        if isinstance(obj, list):
            return [finite_json(x) for x in obj]
        if isinstance(obj, dict):
            return {k: finite_json(v) for k, v in obj.items()}
        return obj
    dump(output/'feedback.json', finite_json(banks))
    dump(output/'evaluation_labels.json', labels)
    dump(output/'code_files.json', code_files)
    (output/'jobs.jsonl').write_text(''.join(json.dumps(j, sort_keys=True)+'\n' for j in jobs))
    dump(output/'source_manifest.json', {'dataset_revision': protocol['dataset_revision'],
        'feedback_run': FEEDBACK_RUN, 'sha256': source_hashes,
        'feedback_url_template': 'https://huggingface.co/datasets/zjunlp/PredictBeforeExecute/resolve/'+protocol['dataset_revision']+'/solutions_subset_50/<task>/report/alignment_<task>_n2_data-both_'+FEEDBACK_RUN+'.json',
        'historical_R6_R8_artifacts_used': False, 'exclusions': exclusions})
    return jobs
