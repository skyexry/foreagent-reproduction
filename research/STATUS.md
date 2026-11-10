# 现在先做什么

**2026-11-10 · 同任务跨运行实验已完成。** [结果、协议与复核](../experiments/run-heldout-history-v1/README.md)。在两组可见成绩数相同的条件下，DeepSeek 的选择损失依次为 C0 0.2642、允许参考同源草稿 0.2554、只参考其他运行 0.2654；GPT 为 0.2725、0.2551、0.2724。425 池中 287 池有足够其他运行历史；单看这些池结论相同。全部 17,000 条选择已独立复算。保留 C0，收尾这版检索器的跨运行先导。建议下一项：在作者已评分的代码对上检验老师的比较 skill，固定模型、预算并做 A/B 换位；本轮只做离线跨运行实验。下列历史轮次承接各自当时的证据。

**2026-11-10 · 老师方向与 corpus 离线实测。** [逐条答复](../research/advisor-directions.md) · [排名诊断、embedding 排序与同任务对照](../experiments/embedding-rerank-v1/README.md)。DeepSeek C0 下，真实第一、第二落到第 4 名及以后的任务等权概率为 50.3%、66.8%。跨任务向量检索融合使损失从 0.2642 升至 0.2871；同任务用裁判所挑参考样例则降至 0.2250。当前优先用作者 corpus 按原始生成运行隔离相似代码，复核同任务收益及泛化。下列各轮的下一步以其记录日期为准。

**2026-11-10 · 改选对补分与 HW3 润色**　[HW3 审阅稿](../reports/hw3/HW3_Execution_Memory_Review.pdf) · [预测文件审计与 GPU 预算](../experiments/paired-prediction-audit/README.md)。80 个已知改选对中，0 对两边都有预测；32 对重算出单边官方分数（28 个 C0、4 个记忆端点），48 对双方均缺。下一步供审阅：Stanford 与 Statoil 各 3 对，单边补跑 6 份约 0.24–0.45 卡时，或同条件重跑 12 份约 0.47–0.90 卡时（按历史中位数、上四分位数折算，不含准备）。报告第 1–3 节由 Claude Opus 5.5 润色，第 8 页 Future Plan 逐字及渲染像素核对一致。

**2026-11-10 · C0 与执行记忆的 CPU 回放**　[HW3 审阅稿，第 8 页](../reports/hw3/HW3_Execution_Memory_Review.pdf) · [逐批结果与复核](../experiments/c0-memory-switch-v1/README.md)。16 次运行、136 批中，按归档裁判判断可完整还原 C0 的有 128 批，加入记忆后 80 批改选；另有 1 批虽无法还原唯一首选，仍可确定改选。接口可接受的 130 批合计 81 改、48 同、1 未知。80 个具体改选对中，双方都有可用旧验证分的为 0。下一步：审阅报告后，在预定任务、相同划分与训练预算下实测分歧对。

**交接更新（2026-11-10）：** 当前结论、各方向收尾原因、最新备选与下一轮待决定事项集中在 [项目交接](README.md)。本地最新研究按 [首次归并记录](../provenance/first-alignment-20261110/README.md) 与 GitHub 对齐；日常交接与推送按[根规则](../AGENTS.md)执行。

**保留 C0，结束两个固定终选先导。** 全部已采纳胜负重排的跨裁判收益为负；理由下标冲突破同分只改变了原 DeepSeek 的一场。按用户决定，本轮到此收尾，原拟的理由分析已撤下。[方案、成本与停止条件](离线候选选择.md)

| 阶段 | 当前状态 | 证据 |
|---|---|---|
| 原版复现 | 已冻结：Stanford 单任务，标准 12 小时，官方误差 0.26640 | [第一阶段](../phase1-reproduction/README.md) |
| C0 修正与短测试 | 已验收；原排序与主动比较先导分别保存 | [先读结果](../experiments/clean-ranking-v1/先读结果.md) |
| Environment 与 Evals | 已验收：17 项契约/系统隔离测试；C0 与随机对照各 850 场精确复现旧结果 | [验收记录](../experiments/research-env-v1/acceptance.json) |
| 文献与研究方案 | 已完成比较分配方向的审读与候选设计；已核对 850/850 场的起始反馈相同 | [原论文及模块覆盖](selection-study-v1/baseline.md) · [文献与候选比较](selection-study-v1/literature.md) |
| 第一轮子代理实验 | D1 与 J1 均完成；独立核对 2,550 份前缀选择、494 个逐任务数值及区间 | [实验目录](../experiments/selection-frontier-01/README.md) · [独立核验](../experiments/selection-frontier-01/verification/receipt.json) |
| 固定模块评测 | 六份裁判归档和部分理想化干预定位了胜者判断与弃权的改进空间 | [模块对照](../experiments/selection-frontier-02/README.md) |
| 静态裁判训练 | 四臂训练先导未达门槛，保留 C0 | [结果](../experiments/trajectory-weighted-judge-v1/README.md) |
| 固定候选池离线排序 | 在相同 C0 轨迹上完成整体重排与理由冲突破同分；26 个开发任务，各方法组 3,400 场，旧基线输入和评价保持冻结 | [实验与复核](离线候选选择.md) |
| AI Scientist 原生接入 | 后续：固定框架版本、代码生成工作区隔离、全局预算与适配验收 | [接口范围](README.md) |
| 新任务 / 在线验证 | 方法冻结后按单独协议与预算执行 | [评测口径](modules.md) |

当前离线实验接口的可修改模块是“决定比较谁、何时停止”。策略通过统一接口操作候选；固定反馈、预算和评分由外部提供。26 个任务全部属于已查看的开发数据。

选题同时考虑候选生成、裁判、比较分配、排名汇总和实际执行。D1 未触发新的主动挑战或统一早停。J1 表明裁判方向有影响，73 场的反向变化进一步提示需要检查弃权、边覆盖与汇总的相互作用。

机器状态：[state.json](state.json)。当前代码/输入核验：`python3 -B -m reproduction.research_env_v1 status --json`。
