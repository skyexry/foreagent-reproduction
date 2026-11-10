# 现在先做什么

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
