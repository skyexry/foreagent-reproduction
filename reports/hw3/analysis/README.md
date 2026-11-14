# Proposal v3: archived online-run analysis

`build_figures.py` reads the original end-to-end run and released author journals without running candidates or querying models. Run from the repository with `MPLCONFIGDIR=/tmp/foreagent-mpl python3 reports/hw3/analysis/build_figures.py`.

- Current run: `phase1-reproduction/records/stanford-autodl-v2/logs/exp/`. Author journals: `data/historical/source_records/stanford-covid-vaccine_*/`.
- Validation observations become available at `Parsed results` timestamps. The plotted score is the controller's parsed, program-defined validation metric, not a standardized private-test trajectory. Failed nodes are marked separately.
- Breadth uses node creation times from final journals. Author timestamps use UTC; reproduction log timestamps use China Standard Time. Ten generated candidates in the final unfinished reproduction batch are excluded from retained-node curves.
- Complete-batch comparison records are deduplicated across the ten nodes that store the same batch history. Confidence counts include cache reuse. Cache and pending-entry events are restricted to the seven completed tournaments. API receipts cover the entire budget, including the unfinished batch.
- Time allocation sums generation-request elapsed durations, elapsed tournament windows (including the final unfinished window), worker execution durations, and feedback-request durations. Parallel comparison-request durations are not summed. Residual time is unassigned overhead; individual API waiting and service processing are not separately observable. The long feedback request is a subset of feedback, separated once in the chart.
- Author endpoint means and sample standard deviations use the three released final-submission scores. No AIDE run was executed for this revision.

The final program's loss pads labels from 68 to 107 positions, averages batch losses on an internal split, and uses the same three scored columns. Official grading uses the first 68 positions on private data. This code-level mismatch is documented without attributing the entire observed gap to one cause.
