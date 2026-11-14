"""Recompute v5 descriptive statistics from the archived online-run audit."""
import json
from pathlib import Path
from scipy.stats import fisher_exact
root = Path(__file__).resolve().parents[1]
d = json.loads((root / 'figures/online_analysis.json').read_text())
batches = d['batches']
n0 = [b['top_ties'] for b in batches]
expected = [.2*n + .8**n for n in n0]
res = {
    'rank_zero_counts': n0,
    'rank_zero_total': sum(n0),
    'expected_executions_by_batch': expected,
    'expected_executions_total': sum(expected),
    'actual_executions_by_batch': [b['executed'] for b in batches],
    'fresh_confidence_contingency': [[1,34],[41,169]],
    'fisher_two_sided': dict(zip(['odds_ratio','p_value'], fisher_exact([[1,34],[41,169]]))),
    'fisher_one_sided_less': dict(zip(['odds_ratio','p_value'], fisher_exact([[1,34],[41,169]], alternative='less'))),
    'test_selection_gap': .2663989312 - .25668736747,
    'caveat': 'Fisher is exploratory at call level; calls are clustered by batch/run. The selection gap is descriptive, not a causal metric-mismatch effect.'
}
(root / 'figures/audit_v5.json').write_text(json.dumps(res, indent=2)+'\n')
print(json.dumps(res, indent=2))
