# HW3 实验索引

本页只列当前报告使用的作者原版证据。历史问题、预测、协议和 R6–R8 记录按原文保留在 [旧实验账本](archive/research-workspace/EXPERIMENTS.md)。

| 实验 | 设置与结果 | 证据 |
|---|---|---|
| pairwise246-v1 | 26 任务、246 对，136 对正确；历史服务设置及重试口径单列 | [结果](phase1-reproduction/experiments/supporting/pairwise-246.json) |
| historical-v1 | 15 次作者运行的 129 完整批次、1,290 候选；给定历史判断/动作后输出一致 | [摘要](phase1-reproduction/experiments/supporting/historical-129-batches.json) |
| corpus26-v2 原版 | 固定候选池与判断，7,800 回放；单选最佳命中 20.43%，regret 0.2810 | [结果](phase1-reproduction/experiments/supporting/corpus-original-7800.json) |
| stanford-autodl-v2 | 单次 12 小时原版端到端，官方误差 0.26640 | [结果](phase1-reproduction/experiments/online-stanford-v2/final-summary.json) |
| environment-baselines-local-v1 | 独立环境、新目录离线重现、原/独立评分对照，模型调用/训练 0 | [验收](phase1-reproduction/experiments/environment-acceptance/acceptance-summary.json) |

单任务复现完成标准按用户确认范围执行。重复性、AIDE 对比和新策略分别作为未来实验。完整轨迹通过 Release 附件获取，每条记录的来源与哈希见第一阶段 SOURCES.json。
