#!/bin/zsh
# From project root. For a fresh official run, use a fresh tag.
# A reviewed host shell permits macOS nested sandbox-exec; the policy stays isolated.
set -euo pipefail
TAG=${1:?Provide a fresh output tag}
OUT="experiments/selection-frontier-02/coverage/replay-${TAG}"
SMOKE="experiments/research-env-v1/runs/frontier02-valid-coverage-smoke-${TAG}"
FULL="experiments/research-env-v1/runs/frontier02-valid-coverage-full-${TAG}"
test ! -e "$OUT"
mkdir "$OUT"
python3 -B -m reproduction.research_env_v1 status --json > "$OUT/status.json"
python3 -B -m reproduction.research_env_v1 run --policy research/policies/valid_coverage_v1.py --limit-jobs 3 --output "$SMOKE" > "$OUT/smoke.log" 2>&1
python3 -B -m reproduction.research_env_v1 evaluate --run "$SMOKE" > "$OUT/smoke-evaluate.log" 2>&1
python3 -B - "$SMOKE" <<'PY'
import gzip, json, sys
from pathlib import Path
p=Path(sys.argv[1])
with gzip.open(p/'decisions.jsonl.gz','rt') as f:
    rows=[json.loads(s) for s in f]
assert len(rows)==3 and all(r['status']=='ok' for r in rows), rows
PY
python3 -B -m reproduction.research_env_v1 run --policy research/policies/valid_coverage_v1.py --output "$FULL" > "$OUT/full.log" 2>&1
python3 -B -m reproduction.research_env_v1 evaluate --run "$FULL" > "$OUT/full-evaluate.log" 2>&1
python3 -B experiments/selection-frontier-02/coverage/analyze.py --run "$FULL" --output "$OUT" > "$OUT/analysis.log" 2>&1
