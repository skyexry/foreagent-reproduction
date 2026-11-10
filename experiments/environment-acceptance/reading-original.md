# 原版基线文献与实现对照

2026-11-08 定向复核。阅读范围是当前原版生成—筛选—执行—评分的必要方法及评估章节。原先更广的参考文献记录保留在仓库 `Annotated_Bibliography.md`；Bradley–Terry、Active Ranking 和 DAGent 对应后续研究。

| 来源及位置 | 本阶段采用的约束 | 代码/本次证据 |
|---|---|---|
| [ForeAgent 正文 §6.2–6.3、附录 C.6/C.8](https://aclanthology.org/2026.acl-long.182.pdf) | 生成 10 个候选、0.7 门控、top-1；AIDE 对照、12 小时、3 次独立运行；调参单独研究 | 固定 `mle-bench/agents/aide/config.yaml`、`aide/agent.py`、`aide/world_model.py`；`online-verification.json` |
| [AIDE Algorithm 1、§3.2、§4.1](https://arxiv.org/html/2502.13138v1) | draft/debug/improve 构成搜索树；内部验证用于搜索，外部 holdout 用于最终评估 | `Journal.get_best_node()` 与独立最小验证误差选择一致；私有评分保持在控制器输入之外 |
| [MLE-bench §2.2–2.3、§3](https://arxiv.org/html/2410.07095v6) | 按任务评分；披露模型、硬件、联网和运行预算；多次运行；奖牌阈值是 benchmark 口径 | 官方原评分器与独立按 ID 连接的 MCRMSE 对照；记录数据版本和执行适配 |

论文叙述与可执行细节分层：论文称候选并行生成，固定代码 `_improve_batch` 中实际逐个调用；本次沿用发布代码。top-k 在代码中指显示名次组，并列 rank 0 可含多个候选；0.20 按候选概率执行，空选后强制执行第一位 rank 0。pending 复赛、轮数停止和原缓存方向行为按发布代码保留。

本次执行适配：控制器/API 在 Mac，候选在 AutoDL 的原 OCI rootfs + PRoot/SSH 中运行；4090 对比历史 3090；源代码按宿主 cpu_count()//6 产生 21 核提示，而执行配额为 16 核、作者历史提示为 13 核。原版 v2 使用作者镜像内 instructions 和 worker 的 data_preview；首个 prompt 差异记录在证据附件 actual-first-prompt-audit.json。DeepSeek 名义型号对应，但历史服务商及权重快照的一致性仍有缺口。

因此，现有结果支持适配环境中的单任务原版链路复现。原论文的跨任务平均、相对 AIDE 的提升和加速主张由 G2/G3 及扩大任务范围另行验证。候选模型结构和参数量由生成过程产生；公平比较匹配生成器、请求设置及资源机会，并把生成代码的参数量作为观察量。
