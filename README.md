# ForeAgent：复现与研究

**2026-11-10 · 执行前筛选**　[HW3 审阅稿（第 8 页）](reports/hw3/HW3_Execution_Memory_Review.pdf) · [按时间回放真实验证历史](experiments/chronological-memory-v1/README.md)。136 批中 130 批具备至少三份可用历史，6 批留下可直接比较的同批执行结果。当前供审阅的下一步是对两种方法分歧的选择做配对实测。

**本轮离线候选选择研究已结束，保留 C0。** [离线结果、理由字段与后续决定](research/离线候选选择.md)

## 从这三个入口开始

| 入口 | 你想知道什么 |
|---|---|
| **[当前研究状态](research/STATUS.md)** | 已完成什么、还差什么、现在先做哪一步 |
| **[项目交接与研究接口](research/README.md)** | 新聊天先读：已尝试方向、结果、暂缓原因、备选与下一步；按需展开 Environment 与 Evals |
| **[最近实验结论](research/离线候选选择.md)** | 固定候选池的离线重排与理由信号；[此前静态裁判训练](experiments/trajectory-weighted-judge-v1/README.md) |

## HW3 提交入口

**[代码交哪份、怎么下载](reports/hw3/SUBMISSION.md)** · [HW3 固定版本](https://github.com/skyexry/foreagent-reproduction/tree/hw3-phase1-v1) · [复现代码 ZIP](https://github.com/skyexry/foreagent-reproduction/releases/download/hw3-phase1-v1/HW3_Reproduction_Code.zip)

HW3 对应第一阶段作者原版 ForeAgent 复现，标准 12 小时单任务官方 MCRMSE **0.26640**。代码包逐文件对应 `hw3-phase1-v1`；作者源码、运行适配、核验脚本及原始声明一并保留。

[第一阶段结果与运行记录](phase1-reproduction/README.md) · [报告 v3 PDF](reports/hw3/DM_HW3_Baseline_Reproduction_v3.pdf) · [完整日志附件](https://github.com/skyexry/foreagent-reproduction/releases/tag/hw3-phase1-v1)。v3 为前三节复现记录，含 Future Plan 的本轮审阅稿见页首。

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

- **HW3 源码核验：** `python3 phase1-reproduction/verify_copy.py`；配置、公开任务数据与完整轨迹说明见第一阶段入口。
- **当前离线环境：** 按 [研究环境准备](research/README.md#首次准备) 下载固定输入附件，再调用统一 `run / evaluate / status`。
- **研究固定输入：** [research-env-v1 Release](https://github.com/skyexry/foreagent-reproduction/releases/tag/research-env-v1)，约 57 MB，1,182 个文件逐项校验；原始数据与作者判断按其来源条款使用。

[详细状态历史](STATUS.md) · [实验账本](EXPERIMENTS.md) · [审计阅读入口](reports/reproducibility-audit-20261108/README.md) · [来源与许可证](THIRD_PARTY_NOTICES.md)
