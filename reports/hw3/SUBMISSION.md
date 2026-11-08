# HW3：代码交哪一份

**Baseline Reproduction 对应已经冻结的第一阶段原版 ForeAgent 复现。**

[下载 HW3 复现代码包](https://github.com/skyexry/foreagent-reproduction/releases/download/hw3-phase1-v1/HW3_Reproduction_Code.zip) · [固定版本代码](https://github.com/skyexry/foreagent-reproduction/tree/hw3-phase1-v1) · [复现结果与运行说明](../../phase1-reproduction/README.md)

代码包来自 `hw3-phase1-v1` 标签，包含该版本的源码、配置、核验入口、说明和报告来源文件，按原相对布局保存。新增研究接口在主分支持续开发；HW3 引用固定标签即可明确对应报告中的原版复现结果。

| 交付内容 | 包内路径 | 作用 |
|---|---|---|
| 作者 baseline 源码 | `phase1-reproduction/code/author/` | 作者固定提交 c4d52cf；模型/Agent、原淘汰赛、配置和依赖，保留许可证 |
| 本次运行适配 | `phase1-reproduction/code/runtime/` | Mac 控制器、模型网关、桥接和 GPU worker 等实际运行快照 |
| 核验脚本 | `phase1-reproduction/code/verification/` | 本机评分与配置检查的阅读副本 |
| 完整核验调用布局 | `archive/research-workspace/scripts/` | 与归档配置、来源清单和相对路径配套的可执行核验入口 |
| 来源和 AI 使用说明 | `phase1-reproduction/SOURCES.json`、`THIRD_PARTY_NOTICES.md`、`reports/hw3/AI_USAGE.txt` | 区分作者原码、运行适配与 AI 辅助 |

**Brightspace 提交：**作业第 1 页要求 PDF 和 `.py` / `.ipynb` 编程文件。代码 ZIP 用于集中下载；按 Brightspace 接收格式上传其中的编程文件，并保留配套目录/配置。仓库链接可放入报告作为来源与补充材料。

报告文件为 [v3 PDF](DM_HW3_Baseline_Reproduction_v3.pdf)，已完成 Introduction、Baseline Explanation、Baseline Reproduction；Future Plan 继续在研究方案确定后补入。代码包中的冻结报告维持该状态。

完整运行轨迹单独下载 [phase1-complete-logs.zip](https://github.com/skyexry/foreagent-reproduction/releases/download/hw3-phase1-v1/phase1-complete-logs.zip)。任务数据通过接受比赛条款后获取；完整在线重跑使用 GPU 和模型 API。源码/摘要核验命令：

```bash
python3 phase1-reproduction/verify_copy.py
```

作者原版单任务、单次 12 小时运行的官方 MCRMSE 为 **0.26640**；报告保留硬件、模型服务、网络等待等差异。后续 C0 修正与离线选择研究的证据分别保存在 `research/` 和 `experiments/clean-ranking-v1/`。
