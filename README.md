# ForeAgent：复现与研究

本仓库记录 ForeAgent 的复现与候选选择研究。当前 HW3 报告包含静态 pairwise 预测和两个任务的端到端复现，Future Plan 探索 process-based reward 对候选选择及相同预算下最终成绩的作用。

## HW3 当前提交

**[最新报告 PDF · 2026-11-15](reports/hw3/HW3_Process_Reward_Proposal_20261115.pdf)** · **[GitHub 提交链接](https://github.com/skyexry/foreagent-reproduction)**

报告共 8 页，包含 Introduction、Baseline Explanation、Baseline Reproduction 和 Future Plan。

| 材料 | 入口 |
|---|---|
| 报告源码与架构图 | [LaTeX 主文件](reports/hw3/main.tex) · [报告目录](reports/hw3/) · [ForeAgent 架构图](reports/hw3/figures/foreagent_architecture.pdf) |
| ForeAgent 复现代码 | [固定作者源码](phase1-reproduction/code/author/) · [运行适配](phase1-reproduction/code/runtime/) · [核验与运行说明](phase1-reproduction/README.md) |
| 静态 pairwise 预测 | [246 对抽样清单](experiments/coverage_manifest.json) · [预测结果](experiments/coverage_retry_results.json) |
| Stanford COVID Vaccine | [最终成绩](experiments/online-stanford-v2/final-summary.json) · [运行记录与核验](phase1-reproduction/README.md) |
| Aerial Cactus Identification | [结果与运行说明](experiments/online-cactus-v1/README.md) · [最终成绩](experiments/online-cactus-v1/final-summary.json) |

静态预测覆盖 26 个任务的 246 对候选，准确率为 **136/246 = 55.28%**。端到端复现对 Stanford 和 Aerial Cactus 各运行一次，每次预算 12 小时。

| 端到端任务 | 测试成绩 | Beat Ratio |
|---|---|---|
| Stanford COVID Vaccine（seen） | MCRMSE **0.26640**，越低越好 | **1.000** |
| Aerial Cactus Identification（unseen） | ROC AUC **0.99994**，越高越好 | **0.87715** |

报告第 3 节将本次复现与论文结果逐项比较。原论文的端到端实验覆盖五个任务，每个任务运行三次。Process-based reward 的标签设计、训练和对照实验列于第 4 节 Future Plan。

## 研究导航

| 入口 | 你想知道什么 |
|---|---|
| **[当前研究状态](research/STATUS.md)** | 已完成什么、还差什么、现在先做哪一步 |
| **[项目交接与研究接口](research/README.md)** | 新聊天先读：已尝试方向、结果、暂缓原因、备选与下一步；按需展开 Environment 与 Evals |
| **[最近实验结论](research/离线候选选择.md)** | 固定候选池的离线重排与理由信号；[此前静态裁判训练](experiments/trajectory-weighted-judge-v1/README.md) |

## 文件夹怎样配合

```text
research/                 组织研究：状态、模块卡、接口规则、可替换策略
reproduction/             实现方法：C0 与离线研究环境
experiments/              保存证据：每轮协议、运行记录、结果与验收
reports/                  解释结论：HW3 报告、审计与论文分析
phase1-reproduction/      冻结原版：作者代码、运行适配、第一阶段结果
tests/                    验证正确性与接口契约
scripts/                  数据恢复与核验工具
provenance/               来源、版本和发布收据
archive/                  历史工作区
```

研究按“**模块与文献 → 方案 → 实验 → 结论**”推进。当前全部 26 个离线任务是开发数据；方法确定后再开展新任务确认与在线端到端验证。历史方案和审计保留各轮状态，当前优先级以研究入口为准。

## 复跑与附件

- **冻结原版源码核验：** `python3 phase1-reproduction/verify_copy.py`；配置、公开任务数据与完整轨迹说明见第一阶段入口。
- **当前离线环境：** 按 [研究环境准备](research/README.md#首次准备) 下载固定输入附件，再调用统一 `run / evaluate / status`。
- **研究固定输入：** [research-env-v1 Release](https://github.com/skyexry/foreagent-reproduction/releases/tag/research-env-v1)，约 57 MB，1,182 个文件逐项校验；原始数据与作者判断按其来源条款使用。

[详细状态历史](STATUS.md) · [实验账本](EXPERIMENTS.md) · [审计阅读入口](reports/reproducibility-audit-20261108/README.md) · [来源与许可证](THIRD_PARTY_NOTICES.md)

## 历史提交与研究记录

`hw3-phase1-v1` 保存 2026-11-08 的 Stanford 第一阶段快照及 v3 报告，提供当时的固定代码和完整日志。

[第一阶段提交说明](reports/hw3/SUBMISSION.md) · [固定版本](https://github.com/skyexry/foreagent-reproduction/tree/hw3-phase1-v1) · [代码 ZIP](https://github.com/skyexry/foreagent-reproduction/releases/download/hw3-phase1-v1/HW3_Reproduction_Code.zip) · [v3 PDF](reports/hw3/DM_HW3_Baseline_Reproduction_v3.pdf) · [完整日志附件](https://github.com/skyexry/foreagent-reproduction/releases/tag/hw3-phase1-v1)

<details>
<summary>2026-11-10 的研究记录</summary>

**2026-11-10 · 老师方向与 corpus 离线实测。** [逐条答复](research/advisor-directions.md) · [排名诊断、embedding 排序与同任务对照](experiments/embedding-rerank-v1/README.md)。DeepSeek C0 下，真实第一、第二落到第 4 名及以后的任务等权概率为 50.3%、66.8%。跨任务向量检索融合使损失从 0.2642 升至 0.2871；同任务用裁判所挑参考样例则降至 0.2250。当前优先用作者 corpus 按原始生成运行隔离相似代码，复核同任务收益及泛化。下列各轮的下一步以其记录日期为准。

**2026-11-10 · 改选对补分与 HW3 润色**　[HW3 审阅稿](reports/hw3/HW3_Execution_Memory_Review.pdf) · [预测文件审计与 GPU 预算](experiments/paired-prediction-audit/README.md)。80 个已知改选对中，0 对两边都有预测；32 对重算出单边官方分数（28 个 C0、4 个记忆端点），48 对双方均缺。下一步供审阅：Stanford 与 Statoil 各 3 对，单边补跑 6 份约 0.24–0.45 卡时，或同条件重跑 12 份约 0.47–0.90 卡时（按历史中位数、上四分位数折算，不含准备）。报告第 1–3 节由 Claude Opus 5.5 润色，第 8 页 Future Plan 逐字及渲染像素核对一致。

**2026-11-10 · C0 与执行记忆的 CPU 回放**　[HW3 审阅稿，第 8 页](reports/hw3/HW3_Execution_Memory_Review.pdf) · [逐批结果与复核](experiments/c0-memory-switch-v1/README.md)。16 次运行、136 批中，按归档裁判判断可完整还原 C0 的有 128 批，加入记忆后 80 批改选；另有 1 批虽无法还原唯一首选，仍可确定改选。接口可接受的 130 批合计 81 改、48 同、1 未知。80 个具体改选对中，双方都有可用旧验证分的为 0。下一步：审阅报告后，在预定任务、相同划分与训练预算下实测分歧对。

**本轮离线候选选择研究已结束，保留 C0。** [离线结果、理由字段与后续决定](research/离线候选选择.md)

</details>
