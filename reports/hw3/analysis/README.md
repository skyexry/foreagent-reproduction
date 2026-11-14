# Proposal v3: archived online-run analysis

`build_figures.py` reads the original end-to-end run and released author journals without running candidates or querying models. Run from the repository with `MPLCONFIGDIR=/tmp/foreagent-mpl python3 reports/hw3/analysis/build_figures.py`.

- Current run: `phase1-reproduction/records/stanford-autodl-v2/logs/exp/`. Author journals: `data/historical/source_records/stanford-covid-vaccine_*/`.
- Validation observations become available at `Parsed results` timestamps. The plotted score is the controller's parsed, program-defined validation metric, not a standardized private-test trajectory. Failed nodes are marked separately.
- Breadth uses node creation times from final journals. Author timestamps use UTC; reproduction log timestamps use China Standard Time. Ten generated candidates in the final unfinished reproduction batch are excluded from retained-node curves.
- Complete-batch comparison records are deduplicated across the ten nodes that store the same batch history. Confidence counts include cache reuse. Cache and pending-entry events are restricted to the seven completed tournaments. API receipts cover the entire budget, including the unfinished batch.
- Time allocation sums generation-request elapsed durations, elapsed tournament windows (including the final unfinished window), worker execution durations, and feedback-request durations. Parallel comparison-request durations are not summed. Residual time is unassigned overhead; individual API waiting and service processing are not separately observable. The long feedback request is a subset of feedback, separated once in the chart.
- Author endpoint means and sample standard deviations use the three released final-submission scores. No AIDE run was executed for this revision.

The final program's loss pads labels from 68 to 107 positions, averages batch losses on an internal split, and uses the same three scored columns. Official grading uses the first 68 positions on private data. This code-level mismatch is documented without attributing the entire observed gap to one cause.

## Revision v4 checks

Run `audit_v4.py --answers PATH_TO_PREPARED_PRIVATE_TEST_CSV --leaderboard PATH_TO_MATERIALIZED_LEADERBOARD_CSV` after `build_figures.py`. It requires local benchmark data; a Git LFS pointer is not the materialized leaderboard. No private labels are included in this package. The program validates the 13 saved submissions against task-level submission digests and scores them retrospectively with ID alignment. It also checks first-round comparator calls for zero cache hits and exactly five new requests per completed batch, and checks logged eliminations against rank-zero candidates.

The first-round confidence rate is an auditable subset, not the full new-call rate. API receipts retain usage rather than response bodies. Cache-hit events omit ordered candidate identities; rematch results omit opponent identity. Exact reversed-cache counts and their high-confidence subset are therefore not identified.

Breadth counts at 4.35/8.10/12 hours are 62/62/82 for the reproduction, versus 54/112/183, 52/95/142, and 69/118/141 for the authors. First-round fresh high-confidence rates: reproduction 1/35; authors 16/85, 15/60, 10/65. No logged eliminated candidate received rank zero. Final validation-selected node is a debug repair.

The post-hoc best private error is 0.25669 at 2.69h; it does not replace the original validation-selected endpoint (0.26640). Best observed Beat Ratio reaches 100% at 0.44h; it uses 1,636 leaderboard scores and saturates for all subsequent valid programs. The plot is a test-oracle diagnostic of visited nodes, not a private-label-driven agent trajectory or an AIDE speedup estimate.

## Revision v5 checks

Run `python3 reports/hw3/analysis/audit_v5.py` to regenerate `figures/audit_v5.json` from the v4 online audit (requires SciPy). Rank-zero counts are [2,1,1,10,10,1,10], independently totaling 35; expected executions sum to 10.3621 versus 10 observed. Fisher's two-sided p=0.01375 is exploratory because calls are clustered within batches/runs. The observed final-selection gap is 0.00971156 MCRMSE; the test-best node reported validation 0.4638 versus the selected node's 0.4378, without establishing a causal decomposition.

The pinned task `prepare.py` samples 240 SN_filter-positive sequences from original Kaggle training data, not the Kaggle test set behind the historical leaderboard. ForeAgent paper Table 13 reports same-task Beat Ratio 1.000 ± 0.000. Accordingly, v5 compares the saturated ForeAgent endpoint and explains the cross-split numerical threshold; it does not infer an exact author saturation time.

Author run cbb2a0b0's log continues after its last journal-retained node (9.394h), ending with an execution launch around 10.336h. The journal plateau cannot establish a service interruption. No new candidate execution, training, or paid inference was run for this revision. Proposed shared metric/cache fixes and future experimental sizes are plans, not implemented results.
