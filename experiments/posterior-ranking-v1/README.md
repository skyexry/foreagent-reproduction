# Fixed-odds posterior ranking v1

**Decision: retain C0.** One preregistered posterior aggregator increased normalized regret on DS1 and pooled GPT. The fixed promotion gate failed. This completes the bounded test; the result supports keeping the existing final selector for this development benchmark.

## Frozen comparison

Protocol registered at `2026-11-08T13:47:07.827785+00:00`, SHA-256 `c0329efda4c2f015d48f650913028e1bda57b003298cb0986685782658e384f0`. The model and gate were fixed before implementation, posterior selection, and score loading. The complete set of 3,400 selection rows was then persisted and hashed before scoring.

- Same 850 jobs, 26 previously inspected development tasks, DS1 (`DS`) and three archived GPT banks; exactly the actual original C0 trace, selected `C` set, query budget and ledger per episode.
- Evidence: unique queried pairs with a valid winner and finite confidence at least 0.7. The ranker consumes accepted winner/loser indices only. Confidence magnitude above threshold, rejected feedback, unqueried pairs, code and raw response text supply zero likelihood terms.
- One uniform prior over complete best-to-worst orders; accepted results are conditionally independent with fixed odds 2:1 (`p=2/3`). Each order has unnormalized weight `2**number_consistent`. These are prespecified modeling assumptions rather than calibrated judge accuracy.
- Primary `E`: smallest exact posterior expected rank, equivalent largest expected rank percentile. Secondary descriptive `B`: largest posterior probability of being first. Exact integer ties return all maximizers; scoring averages uniformly over the returned set.
- Controls: original `C` set; `R`, accepted win fraction with zero-degree value 1/2; `H`, frozen `top_set`, which uses accepted win fraction and then accepted degree. Both R and H were preregistered so the conventional degree tie rule remains explicit.

## Results

Positive gain means lower regret under E. Regret is normalized inside each pool by its observed utility range and then averaged within task and across tasks. GPT pooling averages the three banks within each task first. Best hit is probability under the same uniform selected-tie convention.

| Bank | C0 regret | E regret | C0−E gain [95% task CI] | C0 → E best hit |
|---|---:|---:|---:|---:|
| DS1 | 0.264162 | 0.285541 | -0.021379 [-0.093279, +0.028375] | 23.6738% → 20.6699% |
| 20251210_154406 | 0.276388 | 0.272783 | +0.003605 [-0.003150, +0.010330] | 28.2060% → 28.7141% |
| 20251211_161746 | 0.253559 | 0.276883 | -0.023324 [-0.066700, +0.003632] | 30.5208% → 28.9103% |
| 20251211_171620 | 0.287512 | 0.295502 | -0.007989 [-0.030926, +0.009706] | 25.7238% → 25.8173% |
| GPT task-first pooled | 0.272486 | 0.281723 | -0.009236 [-0.030980, +0.004860] | 28.1502% → 27.8139% |

The paired bootstrap uses 10,000 task resamples and fixed seed 20261108093. These intervals describe this previously inspected development set. The tasks, pools and GPT archives provide repeated conditional measurements; they are not fresh independent confirmation.

Primary gain versus R: DS1 **+0.005648**, pooled GPT **−0.006187**. Versus conventional H: DS1 **+0.006870**, pooled GPT **−0.009926**. Thus the observed advantage over H on DS1 changes direction on GPT. Secondary P(best) gains versus C0 are **−0.022148** on DS1 and **−0.010471** on pooled GPT; it remains a descriptive secondary result.

Leave-one-task primary C0−E extremes: DS1 **[−0.029841, +0.010150]**; pooled GPT **[−0.011009, +0.000013]**. This shows sensitivity to the task mix and provides no basis for a positive stable aggregate claim. All 26 omitted-task values and all three individual GPT bank results are in `summary.json`.

| Bank | E selected-set changes | Episode regret improved / tied / worsened |
|---|---:|---:|
| DS1 | 304 / 850 | 179 / 546 / 125 |
| GPT 20251210_154406 | 222 / 850 | 123 / 628 / 99 |
| GPT 20251211_161746 | 216 / 850 | 101 / 634 / 115 |
| GPT 20251211_171620 | 217 / 850 | 116 / 633 / 101 |

Counts and task macro gains use different weighting; more improved episodes can coexist with a worse task macro result.

## Cost and checks

Every arm reuses the same reads. Task macro unique / accepted reads are **11.20865 / 6.02500** for DS1 and **9.97917 / 7.48526** for pooled GPT. Incremental posterior computation used **11.8293 CPU seconds** over 3,400 episodes, about **3.48 ms/episode**. Per-bank means range from 3.44 to 3.49 ms; p95 is at most 3.67 ms and observed maximum 4.08 ms. This times the posterior calculation only; JSON input/output, validation, and scoring are separate overhead. Added API calls, candidate training, GPU and data collection are all zero.

Exact subset dynamic programming computes forward prefix weights and backward continuation weights. Appending candidate j multiplies by `2**number_of_accepted_prefix_wins_against_j`. Every consistent accepted edge is counted when its loser is appended. Multiplying forward weight, append factor and backward weight gives exact position marginal mass. Runtime is O(n²·2ⁿ), with arbitrary-precision integer numerators for n≤10.

`validation.json` records **840** exact permutation comparisons: every absent/forward/reverse-edge graph through n=4 and fixed random graphs at n=5,6. Empty-graph uniform ties, a symmetric three-cycle, a two-candidate 2:1 posterior, reversed-graph expected-rank symmetry, rank-mass conservation and partition-function agreement passed. All **3,400 C and H selected sets**, C0 traces/ledgers, C/H episode regret and hit values, and all five C/H bank macro results matched existing receipts. An algebraically independent direct scoring formula also matched. Parent-owned independent verification is stored separately under `verification/` when complete.

## Reproduce and inspect

The initial run used Python 3.12.5. The protocol records source versions and hashes. `selection_seal.json` binds the implementation, validation and selection artifact; `SOURCES.json` repeats input provenance and runtime details. Run stages in order on a fresh copy of this experiment folder with generated outputs removed:

```bash
python3 -B experiments/posterior-ranking-v1/experiment.py select
python3 -B experiments/posterior-ranking-v1/experiment.py score
```

The select stage requires a fresh output seal; it freezes selections before the score stage opens labels. The frozen input files are read-only. Outputs are confined to this folder.

## Interpretation limits

This experiment isolates final aggregation conditional on C0's adaptive query and confidence mask. The fixed independent 2:1 likelihood simplifies correlated judge errors and can favor different rankings under sparse evidence. The result pertains to this one model and one odds value. Online candidate generation, query allocation, stopping changes, new tasks and execution outcomes remain separate questions. Existing baseline code and default selection remain C0.
