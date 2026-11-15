# HW3 citation and detail review — 2026-11-15

Scope: the active main.tex, baseline_explanation.tex, baseline_reproduction.tex, and the two citations in the unchanged future_plan.tex. This pass edits the first three sections and checks the complete bibliography.

## Claim-to-source checks

| Reference | Verified source and necessary role | Decision |
| --- | --- | --- |
| Jiang et al. (2025), AIDE | arXiv:2502.13138 metadata and Sections 3.1–3.2: program-tree search, draft/debug/improve, history summaries | Retained as the primary source for the search framework; removed ForeCritic's redundant citation from the opening definition. |
| Zheng et al. (2026), ForeAgent | ACL Anthology metadata (authors, 2026, pp. 3941–3974) and supplied 34-page PDF: Sections 2–4, 6; Tables 2, 5, 13; Appendix B | Retained for task definitions, corpus, report augmentation, model roles and paper results. Added section/table locators where helpful. |
| Chan et al. (2024), MLE-bench | arXiv:2410.07095 metadata and abstract: Kaggle-derived ML-engineering benchmark | Retained at the benchmark description. The reference explicitly uses the 2024 arXiv publication year; the ICLR version is a later 2025 revision. |
| ForeAgent authors (2026a), source code | GitHub commit c4d52cf99bd870d830b456ac7c0684aec1aef375; agent.py, world_model.py, agent config and competition specifications | Retained for controller order, sequential generation, tournament/rematches/ranks, execution probability/fallback, feedback model and task metrics. These details are attributed to the released code. |
| ForeAgent authors (2026b), execution archive | Hugging Face revision 6b322cb88bdbcb2b2d3897ec7d0ded94a5bb2d06, agent_runs/ForeAgent | Added for archived node/time calculations. The pinned directory was verified through the public HF API: 15 run directories, including the three Stanford and three Aerial runs. |
| Lee et al. (2026), ForeCritic | arXiv:2610.38439 metadata and Sections 4.2–4.3: cross-entropy on executed test-score winners; replacement of ForeAgent's judge in the confidence-gated tournament | Retained as the outcome-supervised comparator. Parent-context matching is this proposal's design, rather than a claim about ForeCritic's original input. |
| Naik et al. (2026), AdaPRA | arXiv:2610.33245 metadata and Sections 3.3–3.4: rubrics, trajectory/workspace review, executable checks | Retained for process-quality supervision motivation. The proposed pre-execution revision scorer is this project's adaptation. |

The five paper records' author names, titles, identifiers and years were checked against primary pages. ForeAgent's ACL metadata was also checked against the local paper. All seven bibliography entries are cited; every citation key resolves.

## Reproduction evidence

Six linked GitHub records were verified at fixed commit a80ae9cb0ea15a6f2c3d5666528a01a3006009c5: coverage_manifest.json, coverage_retry_results.json, the two final-summary.json files, online-stanford-v2/author-final-reference.json, and online-cactus-v1/evidence/cactus-author-comparison-reference.json. The returned Git blob identifiers agree with the available archive evidence.

Numbers were cross-checked against [verified facts](../../reproduction-section3-20261115/evidence/verified-facts.json) and [node/time calculations](../../reproduction-section3-20261115/evidence/node-time-reference.json). The paper's 61.5% full-corpus result is separated from 130/246 author predictions and 136/246 reproduced predictions on the matched sample. Paper Beat Ratios are distinguished from the separately computed author endpoint-score means.

Saved nodes include skipped candidates retained in the journal. Availability time is completion of feedback parsing for each run's own final selected program. It is distinct from the paper's AIDE-relative speedup. The paper's Stanford count (158.67) remains distinct from the archived-journal mean (155.33); the unresolved discrepancy is disclosed.

## Notation and algorithm

The requested X/Y structure is preserved. Reasoning cot belongs to a text space, while only the predicted winner is binary. This follows the meaning described in the source prose despite its inconsistent printed Equation (4).

The tournament now initializes state, handles an empty advanced list, batches pending rematches, records decisive wins and elimination rounds, and defines stable sorting and displayed-rank ties. The end-of-round stopping condition allows at most 2m+1 rounds. Published Top-1 selection and the released rank-zero probability/fallback rule remain distinct.

## Validation

Desktop-editor compilation and local PDF export succeeded. The seven-page PDF was rendered and inspected. Compilation logs contain no undefined citations/references or overfull boxes. Tables and key values were read back from the PDF. Authored prose uses single-author wording; “We” appears only in the cited paper's official title.
