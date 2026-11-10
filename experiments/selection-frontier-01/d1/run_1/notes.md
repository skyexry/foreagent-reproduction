# D1 execution notes

Retain C0; end this development decision and inspect influential task evidence before any new strategy.

Primary T−U: {'mean': 0.002892606936850305, 'task_cluster_95': [-0.013129629850422417, 0.023516346009228105]}

S is chain-only; U adds the recorded random edge; T adds the recorded old-active edge. Positive T−U means higher regret for T. All 850 jobs are paired, 26 tasks weighted equally. 10,000 paired task-cluster resamples use seed 20261108093; percentile interpolation matches the frozen scorer.

Selection process projects only five trace fields and seals 2,550 choices in a separate process. Evaluator opens labels and historical selected/metrics after seal, verifies 1,700 full branches first, then scores prefixes. Full protected input hashes are checked before and after analysis.

Strata report represented-task conditional means and additive contributions with all 26 tasks as denominator. Opponent-degree summaries count one focal incidence for each queried endpoint in the chain-top set. Outcome counts use the frozen 1e-12 descriptive tolerance; gain/harm decomposition uses unrounded values.

Records follow the AI Scientist numbered-run/snapshot/final_info convention through local execution. Resource use: one local CPU diagnostic; new API, training and GPU use are zero.
