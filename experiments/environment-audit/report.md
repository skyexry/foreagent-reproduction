# Environment and baselines first

The published baseline (fd55d93) passes a fresh offline reproduction. The original tournament is the reference; uniform random single selection provides a task-specific chance baseline, and the separately frozen canonical cache fix measures an implementation change. All methods are scored using the same pools and utility direction.

| Reference, 26 equally weighted tasks | Best-hit if selecting one | Normalized regret |
| --- | ---: | ---: |
| Uniform random in this pool, exact expectation | 12.5321% | 0.367366 |
| Original tournament | 20.4265% | 0.281000 |
| Canonical cache correction | 21.2000% | 0.277534 |

Clean CPython 3.12.5 venv, certifi 2025.1.31. All 85 frozen files and 97 core data files matched. The release pairwise attachment matched SHA-256. All 20 baseline tests and six reproduce commands passed. Pairwise responses gave 136/246. For the 15 historical runs, the six recorded control outputs matched for all 129 complete batches. Eleven incomplete or unmatched batches and the original rematch RNG remain unresolved. Each corpus variant reproduced 7,800 run records and the expected content fingerprints with zero new model calls or training.

## Scoring check

The historical independent verifier assumes strictly ordered utilities when checking percentile and a nonzero score range when checking regret. The actual scorer supports ties and flat ranges. This audit adds an independent check that assigns half credit for tied opponents and zero regret when every utility is equal. All 15,600 frozen evaluations match; none of their candidate pools had a tied utility. The production scorer and the new verifier agreed on 29 small subsets with tied and flat utilities. The checks also reject duplicate/missing scenario IDs and mismatched candidate order or seed. The published verifier still serves its frozen inputs. Use the added checker on future ties.

## Development calibration

The original implementation, including its cache semantics, was used throughout. Six confidence thresholds were replayed at 7,800 scenarios each. The 0.70 positive control reproduced every original per-task metric. Gate 0.50 was best on the 18 development tasks among feasible grid points (0.50, 0.60, 0.70). The choice was scored against 0.70 on the remaining eight tasks.

| Eight validation tasks, equally weighted | Default 0.70 | Selected 0.50 |
| --- | ---: | ---: |
| Best-hit under uniform single selection | 21.7186% | 28.7500% |
| Normalized regret | 0.372964 | 0.323027 |
| Unique stored feedback lookups per scene | 11.5408 | 7.2825 |
| Expected executions including fallback | 1.0283 | 1.0084 |

Four validation tasks improved on regret and four worsened. PetFinder alone improved by 0.4561. Removing that task as a post-hoc sensitivity check reverses the sign of the mean change in the other seven (about +0.0081). The eight tasks were held out from this parameter decision but had appeared in earlier project experiments. At 0.50 the parser accepts missing-confidence judgments that fall back to 0.50; this setting changes the use of incomplete feedback. The selected gate is the lowest value searched. It is provisional and the published baseline remains 0.70. The grid varies one operational parameter. The saved responses fix generation settings, and execution probability, top-k, and candidate count define budgets or the choice being scored.

## Environments and rerun

Use the baseline README for data and the 246-pair attachment, then from this audit branch in a fresh clone:

```sh
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python scripts/verify_freeze.py
.venv/bin/python scripts/reproduce.py all
.venv/bin/python scripts/audit_baseline_scores.py runs/corpus/original
.venv/bin/python scripts/audit_baseline_scores.py runs/corpus/cache-fixed
.venv/bin/python scripts/calibrate_baseline.py
```

The separate author checkout is c4d52cf. The project README for MLE-bench suggests Python 3.10 while its package metadata requires 3.11 or newer. A Python 3.11 virtual environment with the author's six pinned predictor dependencies and editable MLE-bench passed pip check, both CLIs' help, and an actual competition grader on a synthetic reordered example (ventilator MAE 2.0 including the expiratory mask). The 30 leaderboard files in Git were LFS pointers. Their materialized bytes match the sizes and SHA-256 in the fixed commit. To recreate the host tools using a checkout named skip_bench in the current directory:

```sh
python3.11 -m venv skip_bench/.venv
skip_bench/.venv/bin/python -m pip install -c experiments/environment-audit/author-runtime-macos-arm64.txt -r skip_bench/requirement.txt -e skip_bench/mle-bench
.venv/bin/python scripts/fetch_author_leaderboards.py skip_bench
skip_bench/.venv/bin/python -m skip_bench.grade.run_bench --help
skip_bench/.venv/bin/mlebench --help
```

Online readiness is open. This Mac is arm64 with no Docker or NVIDIA runtime on PATH. The timed AIDE and ForeAgent containers, prepared competition data and model access need a smoke run on the intended execution host. Author §6 and the official MLE-bench integration describe five tasks, three runs each and a 12-hour limit. Full training and paid inference were not performed. See reading.md for source links and the 1952 paper access gap.

The registration and full split are in protocol.md and calibration.json. verification.json includes per-task validation differences and budget accounting. Raw runs and logs are in runs/. The immediate open evaluation check is an end-to-end container smoke run on a compatible host before any new method.
