# 第一阶段：作者原版 ForeAgent 复现

**状态：已完成并冻结。** 实验 `stanford-autodl-v2`，任务 `stanford-covid-vaccine`，标准 12 小时；最终官方误差 **0.26640**（越低越好）。本文件夹集中提供阅读副本，原始文件和来源均保留。完整日志见下方 Release 附件。

## 从这里开始看

1. **先看结果**：[final-summary.json](experiments/online-stanford-v2/final-summary.json)。抓住 82 个保存节点、22 份实际执行代码、7 个完整淘汰赛批次和最终分数。
2. **再看 Agent 怎样决策**：[agent.py](code/author/mle-bench/agents/aide/aide/agent.py)。先读 `search_policy()`，再读 `step()`，最后读 `_improve_with_world_model()`；筛选细节在 [world_model.py](code/author/mle-bench/agents/aide/aide/world_model.py) 的 `tournament_rank()`。
3. **看这次怎样连接 Mac 和 GPU**：[controller.py](code/runtime/controller.py) 加载作者配置并调用原流程；[bridge.py](code/runtime/bridge.py) 传送代码和结果；[worker.py](code/runtime/worker.py) 在 GPU 上调用作者 Interpreter。
4. **把代码和真实过程对起来**：[aide.log](records/stanford-autodl-v2/logs/exp/aide.log) 按时间记录行动；[journal.json](records/stanford-autodl-v2/logs/exp/journal.json) 保存候选和父子关系。最终生成的机器学习方案可直接看 [final_solution.py](experiments/online-stanford-v2/final_solution.py)，评分输出见 [official-grade.txt](experiments/online-stanford-v2/official-grade.txt)。

## 文件怎么分

| 位置 | 内容 |
|---|---|
| `code/author/` | 作者 c4d52cf 固定提交的 484 个文件；原许可证和 Git LFS 指针一并保留 |
| `code/runtime/` | 本次标准运行的冻结适配代码及协议 |
| `code/verification/` | 本机核验脚本的阅读副本；可执行的归档入口见 `../archive/research-workspace/scripts/` |
| `experiments/online-stanford-v2/` | 成绩、预测归档、检查点、作者参考成绩及最终方案 |
| `experiments/environment-acceptance/` | 依赖版本、独立复评分和环境核验记录 |
| `experiments/supporting/` | 246 对、129 批历史条件重演、7,800 次原版离线回放的摘要 |
| `records/stanford-autodl-v2/` | 本次完整保存记录：全部日志、API 回执、任务记录、候选代码与预测、运行快照、观察者检查点 |
| `data/public/` | 本次运行公开输入的本机副本；运行记录内的输入链接指向这里 |
| `SOURCES.json` | 每个副本的原始路径、大小、SHA-256 和输入链接对应关系 |

作者方法使用 AIDE 派生的 Python 框架。Mac 运行控制器和 API 调用，AutoDL 执行候选代码；实际使用作者镜像 rootfs + PRoot/SSH。生成、比较和反馈分别调用 DeepSeek-V3.2、DeepSeek-V3.2 Thinking、GPT-4o-mini。

本次采用原版参数与缓存行为。Mac 熄屏、VPN 断连导致一次反馈请求及重试约耗时 3 小时 45 分钟，计入 12 小时预算。硬件和模型服务差异随结果保留。当前范围为单任务、单次端到端复现；重复性和 AIDE 对比作为后续可选研究。评分器行顺序问题见主项目 [EVAL-01](../IMPROVEMENTS.md)，冻结提交已通过独立按 ID 对齐复算。

## 下载完整日志与核验

[下载完整日志 ZIP（37.5 MB）](https://github.com/skyexry/foreagent-reproduction/releases/download/hw3-phase1-v1/phase1-complete-logs.zip) · [全部附件及校验值](https://github.com/skyexry/foreagent-reproduction/releases/tag/hw3-phase1-v1) · [附件清单](RELEASE_ASSETS.json)

日志 ZIP 包含本次完整保存的 **408 个原始文件和 5 个输入链接**。公开任务数据由使用者按 Kaggle 条款单独获取，私有答案与账户凭据保留在仓库外。

从仓库根目录执行：

```bash
# 核对 Git 中的源码、摘要和文档
python3 phase1-reproduction/verify_copy.py
# 下载日志（也可通过浏览器点击上方链接）
gh release download hw3-phase1-v1 --repo skyexry/foreagent-reproduction \
  --pattern phase1-complete-logs.zip --dir downloads
# 核对 ZIP、恢复完整记录，再逐文件核对
python3 phase1-reproduction/verify_copy.py \
  --restore-records downloads/phase1-complete-logs.zip
```

恢复后即可打开上方 aide.log 和 journal.json。`--data` 用于已有公开数据的完整核验；`--check-originals` 适用于仍能访问 SOURCES.json 中原始本机路径的环境。默认检查 Git 材料，`--records` 检查下载后的完整轨迹，输入链接按元数据验证，实际训练数据按独立获取流程准备。

作者来源为 [固定 Git 提交](https://github.com/zjunlp/predict-before-execute/tree/c4d52cf99bd870d830b456ac7c0684aec1aef375)，许可证和原始字节保留。作者 Git 属性文件以 `.gitattributes.upstream` 原文保存，命名映射记入 SOURCES.json。

## 进一步复跑

`code/runtime/` 和 `code/verification/` 是实际代码的阅读快照，保留原启动布局。完整本机复评分/历史回放入口在 [归档研究工作区](../archive/research-workspace/README.md)，其中相对布局和冻结清单原样保留；独立评分命令可从 [核验指南](../archive/research-workspace/experiments/environment-acceptance/README.md) 进入。作者的固定 Git 检出、任务数据和模型凭据作为显式运行输入。

公开输入可通过接受比赛条款后下载 `stanford-covid-vaccine.zip`，使用作者固定提交的 prepare.py 准备；4 个数据 MD5 与独立核验见 [online-verification.json](experiments/environment-acceptance/online-verification.json)。原 ZIP MD5 为 `16ec2b3aa849804b7ab68a3bd043d00c`。本机原有 `data/public/` 副本按来源清单保留。

当前完成标准为单任务原版端到端复现。源码、摘要和来源清单随 Git 发布，完整轨迹通过 Release 附件保存；历史文件见仓库 archive，原件持续保留。
