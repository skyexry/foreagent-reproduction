# HW3 · ForeAgent Baseline Reproduction

本仓库归集 DATS-SHU-200 Data Mining HW3 的原版基线复现材料。当前完成 **Introduction、Baseline Explanation、Baseline Reproduction**；报告 v3 的 **Future Plan 按此前安排待补**。第一阶段原版单任务复现已完成并冻结。

## 先看这三项

| 入口 | 内容 |
|---|---|
| **[HW3 报告 PDF · v3](reports/hw3/DM_HW3_Baseline_Reproduction_v3.pdf)** | 8 页，沿用 NeurIPS 模板；[直接下载 PDF](https://github.com/skyexry/foreagent-reproduction/releases/download/hw3-phase1-v1/DM_HW3_Baseline_Reproduction_v3.pdf) |
| **[第一阶段代码与实验记录](phase1-reproduction/README.md)** | 按“结果 → 决策代码 → 运行适配 → 日志”阅读 |
| **[完整实验日志 ZIP](https://github.com/skyexry/foreagent-reproduction/releases/download/hw3-phase1-v1/phase1-complete-logs.zip)** | 37.5 MB，408 个原始文件及 5 个公开输入链接；含所有候选、journal、API 回执、观察者检查点和运行快照 |

完整附件及校验值见 [Release](https://github.com/skyexry/foreagent-reproduction/releases/tag/hw3-phase1-v1)、[SHA256SUMS.txt](https://github.com/skyexry/foreagent-reproduction/releases/download/hw3-phase1-v1/SHA256SUMS.txt) 和 [RELEASE_ASSETS.json](phase1-reproduction/RELEASE_ASSETS.json)。

## 当前复现结果

| 证据层次 | 结果 | 解释 |
|---|---|---|
| 真实 pairwise 子样本 | 136/246，55.28% | 26 任务子样本；首轮及重试分别记录 |
| 作者历史控制流程 | 129/129 完整批次，1,290 个候选一致 | 给定历史判断及概率动作的条件重演；原 RNG/复赛对手身份缺口保留 |
| 原版固定候选池选择 | 26 任务，7,800 次离线回放；最佳命中 20.43%，regret 0.2810 | 随机参考 12.53%、0.3674；真实分数仅用于评分 |
| 原版单任务端到端 | `stanford-covid-vaccine`，12 小时，官方 MCRMSE **0.26640** | 82 个保存节点、22 次代码执行、7 个完整淘汰赛批次 |

详见 [在线结果](phase1-reproduction/experiments/online-stanford-v2/final-summary.json)、[离线摘要](phase1-reproduction/experiments/supporting/corpus-original-7800.json) 和 [独立核验](phase1-reproduction/experiments/environment-acceptance/online-verification.json)。

源码固定在作者提交 `c4d52cf99bd870d830b456ac7c0684aec1aef375`，保留 confidence=0.70、10 候选、top-k=1、执行概率 0.20、原缓存及空选回退。Mac 运行控制器和 API 调用，AutoDL 在作者镜像 rootfs + PRoot 中执行代码。环境、服务与历史运行有差异；Mac 熄屏/VPN 断连导致一次请求及重试约耗时 3 小时 45 分钟，计入预算。冻结成绩已由原评分器和独立 ID 对齐计算共同确认。

## 目录

```text
phase1-reproduction/       第一阶段源码、运行适配、结果、来源清单
reports/hw3/               报告 PDF、TeX、NeurIPS 样式、AI 使用记录
archive/research-workspace/ 原研究工作区、早期脚本与历史实验
STATUS.md                 当前阶段、证据和下一步
EXPERIMENTS.md            当前 HW3 所用实验索引
tests/                    日志恢复工具的回归检查
```

原始文件保留；[归档对应表](archive/ARCHIVE_MAP.json)记录旧路径与当前路径。历史改进实验按原版本归档，当前 HW3 基线采用作者原版。

## 本机快速核验

Python 3.11+，以下核验使用标准库，新增模型调用和训练均为 0：

```bash
git clone https://github.com/skyexry/foreagent-reproduction.git
cd foreagent-reproduction
python3 phase1-reproduction/verify_copy.py
python3 -m unittest discover -s tests -v
```

读取完整日志：先从上方链接下载 ZIP，或使用已登录的 GitHub CLI；恢复工具同时验证 ZIP 和每个文件的 SHA-256：

```bash
gh release download hw3-phase1-v1 --repo skyexry/foreagent-reproduction \
  --pattern phase1-complete-logs.zip --dir downloads
python3 phase1-reproduction/verify_copy.py \
  --restore-records downloads/phase1-complete-logs.zip
```

恢复后打开 `phase1-reproduction/records/stanford-autodl-v2/logs/exp/aide.log` 和 `journal.json`。任务原始数据按 Kaggle 条款单独获取；日志附件保留公开输入链接元数据，数据准备说明见第一阶段 README。完整在线重跑需要 GPU 和模型 API，按单独运行协议开展。

## HW3 提交材料

- 报告：[v3 PDF](reports/hw3/DM_HW3_Baseline_Reproduction_v3.pdf)。当前前三部分完成，Future Plan 待补；完整 HW3 以四部分报告为准。
- 编程材料：[作者原版代码](phase1-reproduction/code/author/mle-bench/agents/aide/aide/)、[实际运行适配](phase1-reproduction/code/runtime/)、[核验脚本阅读副本](phase1-reproduction/code/verification/)。原型与核验工作区在 archive 中保留原相对布局。
- TeX：[main.tex](reports/hw3/main.tex)、[baseline_reproduction.tex](reports/hw3/baseline_reproduction.tex)、[NeurIPS 模板](reports/hw3/neurips_2025.sty)。
- AI 使用：[AI_USAGE.txt](reports/hw3/AI_USAGE.txt)。版本与已有 PDF 验证见 [VERSION.md](reports/hw3/VERSION.md)。

课程要求在 Brightspace 提交 PDF 和编程文件；本仓库提供对应代码与证据。原作者致谢及许可证见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。仓库当前可见性沿用原设置。
