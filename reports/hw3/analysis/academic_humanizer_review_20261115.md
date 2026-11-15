# Academic Humanizer editing pass

Source skill https://github.com/AIScientists-Dev/academic-humanizer/blob/main/SKILL.md

Version 0.3.3, retrieved 2026-11-15. Skill blob afb7d8da3cba41b47365730ceed40fa5a72d8097.

The author requested a prose revision with fewer colons and semicolons. Single-author voice, section and paragraph structure, technical definitions, mathematical expressions, numerical results, and citation keys are preservation constraints. The current local commit is the prior version. Delivery stays local at the author's request.

## Audit before editing

| Location | Pattern | Planned edit |
|---|---|---|
| Introduction, paragraphs 2 and 3 | Colon-led explanations and stacked clauses | State the execution cost and predictive-selection mechanism in direct sentences |
| Introduction, paragraph 4 | Repeated uses of provides and a long controlled-comparison sentence | Clarify each method's role and separate the comparison inputs from its purpose |
| Baseline 2.1 and 2.2 | Colon before an equation and semicolon-heavy symbol glossary | Preserve equations and symbol definitions, use complete sentences |
| Baseline 2.3 | Three phase labels followed by colons, repeated framework wording | Explain the sequence through subjects and verbs, keep the paper/code distinction |
| Baseline 2.4 | Semicolons join pseudocode actions and implementation rules | Use periods or conjunctions while preserving the algorithm and ranking rules |
| Architecture figure and captions | Colon-separated labels and semicolon explanations | Shorten labels and use sentences, retain diagram paths and parameters |
| Reproduction 3.1 | Long lists combine setup, scope, and metrics | Split sentences and make each metric's interpretation explicit |
| Reproduction 3.2 and 3.3 | Semicolon-heavy comparisons and repeated outcome descriptions | Preserve every result and reference, clarify the comparison unit |
| Future Plan | Repeated usable transitions and clause-heavy evaluation sentences | Keep the four paragraphs, express supervision and evaluation steps directly |

## Evidence check before editing

| Claim group | Existing evidence | Editing treatment |
|---|---|---|
| Agent execution cost and AIDE search | jiang2025aide and zheng2026predict Section 2.2 | Preserve attribution and scope |
| 3.2 times nodes, 6-fold speedup, about 6 percent gain | zheng2026predict Section 6 | Preserve reported, task-specific status |
| Corpus sizes and model accuracies | zheng2026predict Sections 3-4 and Table 2 | Preserve all numbers and distinction from online outcomes |
| ForeCritic supervision and integration | lee2026forecritic Sections 4.2-4.3 | Preserve cross-entropy, executed-score labels, and judge replacement |
| Process rubrics | naik2026adapra Section 3.4 | Preserve interpretation as motivation for the proposed study |
| Controller, models, tournament, execution gate | foreagentcode pinned revision c4d52cf | Preserve released-code attribution |
| Pairwise and two-task reproduction | Fixed result links, author records, and foreagentdata | Preserve sample scope, single-run status, outcomes, and diagnostics |
| Process reward improvements | Proposed controlled study | Keep future tense and research question |

## Verification after editing

Completed on 2026-11-15.

- Revised the four existing sections and diagram labels while preserving paragraph structure, technical definitions, data, and single-author voice.
- Replaced 16 prose colons and 43 semicolons across the manuscript with sentences or conjunctions. Figure labels received the same treatment. Bibliographic titles, identifiers, and template-generated figure/table labels retain their standard formatting.
- Compared the edited sources against the pre-edit snapshot. All numerical tokens, three displayed equations, inline mathematical expressions, citation commands and options, and source URLs are identical in order and content.
- Preserved the tournament's control flow, conditions, action order, and ranking semantics. Wording changes replace punctuation between actions.
- All 7 bibliography entries resolve. Authored prose uses a single-author voice.
- Desktop editor compilation and TeX Live compilation both succeeded. The exported proposal has 8 pages. The final compile log contains no warnings, overfull boxes, underfull boxes, or unresolved references.
- Visually checked all pages and the standalone architecture diagram. Adjusted Table 2 alignment and line breaks so each task's metric and numerical comparison remain readable.
- Updated the editable sources, exported proposal PDF, and standalone figure PDF/PNG. Delivery remains local.

The editing pass preserves the manuscript's existing evidence and attribution. It adds no experiments or empirical findings.
