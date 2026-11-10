# Valid-edge coverage and J1 diagnostic

Preregistered source: `../protocol.json`, SHA-256 `797f6c92ed5f2b824526017734017175e9cc624613d423c84893b1aa7aed9e37`, sections `coverage_diagnostic`, `allocation`, `decision_unit`, `criteria` and `cost`. This implementation note is written before executing the new policy.

Hypothesis: allocating the four post-chain comparisons toward candidates with sparse accepted evidence improves valid coverage and task-macro normalized regret. First use exactly the frozen Random(seed)-shuffled input-ID chain. Subsequently sort unseen normalized pairs, shuffle with the same RNG state, and take the first maximum of `(zero-valid endpoints, -min valid degree, -sum valid degree, -sum queried degree)`. Stop only at original unique budget or exhaustion; frozen .7 gate and `top_set` are retained. Outcomes of observed feedback may affect subsequent coverage; utility labels never enter decisions.

Controls: frozen `coverage_random` all 850 jobs with equal budget and verified chain prefix; actual C0 separately as a whole-procedure comparison. Real v1 CLI 3-job smoke, inspect statuses, then 850-job CLI plus independent evaluate. Preserve failures in new directories; use reviewed shell escalation if the outer sandbox prevents nested sandbox execution. Max 600s per run, zero models/training/GPU.

Analysis: task-macro paired regret gain (control minus policy), best-hit, reads, valid degree/zero degree, 10,000 task bootstrap seed 20261108093, leave-one-task-out, per-task and per-episode records. Promotion also requires independent generator-bank replays and the common protocol thresholds.

J1 diagnostic uses the existing all-correct-direction-on-valid-edges oracle exclusively for attribution, checks saved J1 selections, and records best-node queried/valid degree, correct direct victories, undefeated competitors, lack of distinguishing evidence and degree-tiebreak suppression. Includes all 850 jobs and each preregistered J1 outcome subset. This diagnostic reads scores after the policy run has sealed choices.
