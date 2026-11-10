"""Summarize already built task-local credit; audit-only, outside fitting."""
from collections import Counter
import json
from pathlib import Path
import statistics
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build import distribution, dump


def run(output):
    summary = json.loads((output/'summary.json').read_text())
    weights = [v for p in sorted((output/'tasks').glob('*.json')) for v in json.loads(p.read_text()).values()]
    arms = ('terminal','gap','shuffled')
    per_task = summary['per_task']
    matched = sum(t['exploratory_repeat_seed']['matched_pool_pairs'] for t in per_task)
    differing = sum(t['exploratory_repeat_seed']['differing'] for t in per_task)
    result = dict(pairs=len(weights), exposed=sum(v['n']>0 for v in weights),
        unexposed=sum(v['n']==0 for v in weights),
        positive_mean_delta=sum(v['mean_delta']>0 for v in weights),
        negative_mean_delta=sum(v['mean_delta']<0 for v in weights),
        zero_mean_delta=sum(v['mean_delta']==0 for v in weights),
        occurrence_signs=dict(sum((Counter(t['occurrence_signs']) for t in per_task),Counter())),
        raw_weights={a:distribution([v[a] for v in weights]) for a in arms},
        terminal_increment_given_positive=distribution([v['terminal']-1 for v in weights if v['terminal']>1]),
        per_task_ess_fraction={a:dict(min=min(t['raw_weights'][a]['effective_sample_size']/t['eligible_pairs'] for t in per_task),
            median=statistics.median(t['raw_weights'][a]['effective_sample_size']/t['eligible_pairs'] for t in per_task),
            max=max(t['raw_weights'][a]['effective_sample_size']/t['eligible_pairs'] for t in per_task)) for a in arms},
        exploratory_repeat_seed=dict(scope='Both seeds queried the same edge in the same pool; context and paths may differ. Development diagnostic only.',
            matched_pool_pairs=matched, differing=differing, differing_fraction=differing/matched,
            mean_absolute_delta_difference=sum(t['exploratory_repeat_seed']['mean_absolute_difference']*t['exploratory_repeat_seed']['matched_pool_pairs'] for t in per_task if t['exploratory_repeat_seed']['mean_absolute_difference'] is not None)/matched),
        scope='Full prepared pair corpus before trainer code-identity and fold-overlap exclusions; final fitting ESS is fold-specific.')
    dump(output/'diagnostics.json',result)
    print(json.dumps(result,indent=2))


if __name__=='__main__':
    run(Path(sys.argv[1]))
