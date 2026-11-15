# 3. Reproduction of the Baseline

## Experimental Setup

We reproduced static pairwise prediction and the complete ForeAgent workflow. The pairwise evaluation sampled 246 pairs across all 26 tasks in the released 18,438-pair corpus, with up to ten pairs per task. DeepSeek-V3.2 was accessed through SiliconFlow with thinking enabled, temperature 1.0 and the released prompts/data reports. Micro-accuracy used execution-derived labels; twenty failed requests received one retry, producing 246 adopted predictions from 266 requests.

We then ran ForeAgent once each on Stanford COVID Vaccine (seen) and Aerial Cactus Identification (unseen), with the original implementation, reports, splits and a 12-hour budget including API waits. We retained m=10, confidence threshold 0.7, Top-1 configuration and execution probability 0.2. DeepSeek-V3.2 generated code, its thinking mode compared candidates, and `gpt-4o-mini-2024-07-18` parsed feedback. Original-image PRoot workers used an RTX 4090 for Stanford and an RTX 3090 for Aerial. The Stanford controller ran on a Mac; both Aerial components ran on AutoDL. Private grading followed the original validation-based final selection.

## Results

**Table 1. Static pairwise prediction.** The same 246 reproduced decisions are compared against two reference scopes. Differences are percentage points (pp).

| Model | Reference | Reference pairs | Reference accuracy (%) | Reproduced pairs | Reproduced accuracy (%) | Difference (pp) |
|---|---|---:|---:|---:|---:|---:|
| DeepSeek-V3.2, thinking enabled | Paper, three-run mean ± SD | 18,438 | 61.50 ± 0.20 | 246 | 55.28 (136/246) | −6.22 |
| DeepSeek-V3.2, thinking enabled | Released author run, matched subset | 246 | 52.85 (130/246) | 246 | 55.28 (136/246) | +2.44 |

The first row uses different pair counts and task weights; the second matches ordered pairs and labels against one archived author run. First-attempt accuracy was 50.00% overall (123/246), or 54.42% over valid outputs (123/226). The final 55.28% includes failures-only retries. Paper reference: Table 2, PDF p. 5. A new GPT-5.1 pairwise result is unrecorded.

**Table 2. End-to-end ForeAgent results.** Beat Ratio is the fraction of leaderboard contestants with strictly worse scores. Paper results are three-run means; each reproduction is one run.

| Task | Status | Paper Beat Ratio: mean ± SD (3 runs) | Reproduced Beat Ratio (1 run) | Task score: released-author mean → reproduction |
|---|---|---:|---:|---|
| Stanford COVID Vaccine | Seen | 1.000 ± 0.000 | 1.000 | MCRMSE ↓: 0.25862 → 0.26640 |
| Aerial Cactus Identification | Unseen | 0.877 ± 0.000 | 0.87715 | ROC AUC ↑: 0.99992 → 0.99994 |

Paper Beat Ratios: Table 13, PDF p. 27. Task-score means: three released author endpoints. Aerial's raw AUC is 0.9999375316002257, rounded by the original wrapper to 0.99994. Official and independent ID-aligned scores agree. Frozen leaderboards give 1,636/1,636 contestants beaten for Stanford and 1,071/1,221 for Aerial.

Both reproductions retained 82 journal nodes, versus author-archive means of 155.33 (Stanford) and 49.33 (Aerial), using the same completed-journal definition. Final selected-program availability times were 3.46/6.86 hours, versus author means of 7.34/1.02 hours. These measure different runs' selected programs; common-target convergence is a separate metric.

## Comparison with the Original Work

Both Beat Ratios match the paper at its reported precision. Finer metrics differ: Stanford's error is about 3.0% above the author mean but within its observed range (0.24320–0.27497); Aerial's five-decimal AUC is 0.00002 higher. Neither change crosses a leaderboard threshold, so Beat Ratio stays unchanged.

The pairwise evaluation preserves the input design, label direction and micro-accuracy metric. Its 6.22-pp gap from the paper involves different samples/task weights, while the matched-subset difference is +2.44 pp. These are descriptive comparisons: tasks and programs are shared, and provider snapshots remain unresolved.

Logs establish a 13,491.88-second Stanford feedback request including retries (31.2% of its budget), a mismatch between its internal validation and official scoring, and Aerial worker-start/metric-parsing failures. Their individual effects remain unmeasured. Furthermore, none of Aerial's 86 fresh comparisons has saved submissions for both programs, leaving online test-based pairwise accuracy unidentified despite complete response records.

One run on two of five tasks supports a partial reproduction of the endpoints. Repeatability, broader generalization and the paper's AIDE-relative speedup require further controlled runs and common performance targets.

### Sources

- [Original paper](https://aclanthology.org/2026.acl-long.182.pdf): §4.1 and Table 2, PDF pp. 4–5; §6.3/Table 5/Figure 4, p. 8; Appendix C.8, p. 22; Table 13, p. 27.
- [Pairwise final results](https://github.com/skyexry/foreagent-reproduction/blob/a80ae9cb0ea15a6f2c3d5666528a01a3006009c5/experiments/coverage_retry_results.json), [sampling manifest](https://github.com/skyexry/foreagent-reproduction/blob/a80ae9cb0ea15a6f2c3d5666528a01a3006009c5/experiments/coverage_manifest.json), and [scoring protocol](https://github.com/skyexry/foreagent-reproduction/blob/a80ae9cb0ea15a6f2c3d5666528a01a3006009c5/experiments/coverage_scoring.md).
- [Stanford final run](https://github.com/skyexry/foreagent-reproduction/blob/a80ae9cb0ea15a6f2c3d5666528a01a3006009c5/experiments/online-stanford-v2/final-summary.json) and [three author endpoints](https://github.com/skyexry/foreagent-reproduction/blob/a80ae9cb0ea15a6f2c3d5666528a01a3006009c5/experiments/online-stanford-v2/author-final-reference.json).
- [Aerial final run](https://github.com/skyexry/foreagent-reproduction/blob/a80ae9cb0ea15a6f2c3d5666528a01a3006009c5/experiments/online-cactus-v1/final-summary.json) and [three author endpoints](https://github.com/skyexry/foreagent-reproduction/blob/a80ae9cb0ea15a6f2c3d5666528a01a3006009c5/experiments/online-cactus-v1/evidence/cactus-author-comparison-reference.json).
- New read-only derivations: [verified facts](evidence/verified-facts.json), [Beat Ratio checks](evidence/beat-ratio-verification.json), [node/time checks](evidence/node-time-reference.json), and [runtime comparison coverage](evidence/runtime-comparison-coverage.json).
