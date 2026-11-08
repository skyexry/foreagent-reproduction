# 后续改进清单

当前原版单任务复现已完成，固定作者源码、参数和真实结果作为后续参照。下列项目独立登记，按具体研究问题另立协议。

| ID | 类别 | 问题与改动目标 | 验证标准 | 状态 |
|---|---|---|---|---|
| EVAL-01 | 评估工具正确性修正 | Stanford 原评分器排序后保留旧索引，keep mask 按 pandas 索引对齐，导致相同预测打乱行顺序后分数改变。独立修正版应按唯一 id_seqpos 对齐预测与答案，再应用对应 keep mask | 相同行预测在不同排列下分数一致；与独立 ID 对齐计算一致；覆盖缺失/重复/未知 ID、非有限值、缺列和错误 mask；冻结本次及作者三份提交分数保持一致 | 已复现问题并增加核验；独立评分器修正版待实现 |

EVAL-01 属于评分基础设施修正。候选生成、筛选和执行策略的效果改进另设实验。本次冻结提交的原评分和独立计算均为 **0.26640**，评估工具问题及回归目标见 [核验证据](phase1-reproduction/experiments/environment-acceptance/online-verification.json)。原评分源码和原版结果按版本保留。

原版重复性研究及 AIDE 公平在线比较登记为后续可选研究，预备设置保留在 [协议](phase1-reproduction/experiments/environment-acceptance/online-repeat-protocol.json)。当前完成标准为已走通并核验的单任务原版端到端运行。
