"""Post-selection availability of validation scores on the 80 named switched pairs."""
import argparse
from collections import Counter, defaultdict
import hashlib
import json
import math
from pathlib import Path
from memory_switch import json_lines, journal_nodes


def has_validation(node, maximize):
    metric = node.get('metric') or {}
    v = metric.get('value')
    return (node.get('is_buggy') is False and node.get('is_skipped') is False
            and node.get('exec_time') is not None and metric.get('maximize') is maximize
            and type(v) in (int, float) and math.isfinite(v))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('switches', type=Path)
    parser.add_argument('output', type=Path, help='new JSON file')
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    rows = json_lines(args.switches)
    sig = hashlib.sha256(args.switches.read_bytes()).hexdigest()
    named = [r for r in rows if r['c0_top_known'] and r['c0'].get('switch')]
    by_run = defaultdict(list)
    for r in named:
        by_run[r['run']].append(r)
    counts = Counter(dict(neither=0, only_baseline=0, only_fusion=0, both=0))
    for run, nodes in journal_nodes(by_run):
        ns = {n['id']:n for n in nodes}
        for r in by_run[run]:
            maximize = r['task'] in {'aerial-cactus-identification','histopathologic-cancer-detection'}
            choices = [r['c0'][k] for k in ('baseline_choice','fusion_choice')]
            assert choices[0] != choices[1]
            a, b = [has_validation(ns[i], maximize) for i in choices]
            counts[['neither','only_baseline','only_fusion','both'][int(a) + 2*int(b)]] += 1
    assert sum(counts.values()) == len(named)
    result = dict(input_switches_sha256=sig, named_switched_pairs=len(named),
                  validation_score_available=counts, exactly_one=counts['only_baseline']+counts['only_fusion'])
    args.output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
