# 第一阶段：作者原版 ForeAgent 复现

**状态：已完成并冻结。** 实验 `stanford-autodl-v2`，任务 `stanford-covid-vaccine`，标准 12 小时；最终官方误差 **0.26640**（越低越好）。本文件夹集中提供阅读副本，原始文件和来源均保留。

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
| `code/verification/` | 本机核验脚本的阅读副本；可执行的主项目入口见 `../scripts/` |
| `experiments/online-stanford-v2/` | 成绩、预测归档、检查点、作者参考成绩及最终方案 |
| `experiments/environment-acceptance/` | 依赖版本、独立复评分和环境核验记录 |
| `experiments/supporting/` | 246 对、129 批历史条件重演、7,800 次原版离线回放的摘要 |
| `records/stanford-autodl-v2/` | 本次完整保存记录：全部日志、API 回执、任务记录、候选代码与预测、运行快照、观察者检查点 |
| `data/public/` | 本次运行公开输入的本机副本；运行记录内的输入链接指向这里 |
| `SOURCES.json` | 每个副本的原始路径、大小、SHA-256 和输入链接对应关系 |

作者方法使用 AIDE 派生的 Python 框架。Mac 运行控制器和 API 调用，AutoDL 执行候选代码；实际使用作者镜像 rootfs + PRoot/SSH。生成、比较和反馈分别调用 DeepSeek-V3.2、DeepSeek-V3.2 Thinking、GPT-4o-mini。

本次采用原版参数与缓存行为。Mac 熄屏、VPN 断连导致一次反馈请求及重试约耗时 3 小时 45 分钟，计入 12 小时预算。硬件和模型服务差异随结果保留。当前范围为单任务、单次端到端复现；重复性和 AIDE 对比作为后续可选研究。评分器行顺序问题见主项目 [EVAL-01](../IMPROVEMENTS.md)，冻结提交已通过独立按 ID 对齐复算。

## 核对副本与来源

在本文件夹执行：

```bash
python3 verify_copy.py
python3 verify_copy.py --check-originals
```

第一条检查归集文件及内部链接；第二条同时回读本机原始来源。作者来源为 [固定 Git 提交](https://github.com/zjunlp/predict-before-execute/tree/c4d52cf99bd870d830b456ac7c0684aec1aef375)，图片/文档和许可证均按原树留存。本次归集保持代码原文及原启动布局说明；实际重跑沿用主项目 [核验指南](../experiments/environment-acceptance/README.md) 和固定作者检出，账户凭据在仓库外配置。

作者 Git 属性文件以 `.gitattributes.upstream` 原文保存，便于将 LFS 指针按原字节归档；这一命名映射在 SOURCES.json 中记录。

Git 跟踪代码、摘要和来源清单；完整 `records/` 与任务 `data/` 在本机集中保存，按独立附件管理。既有固定实验附件的原位置与校验值也记录在 SOURCES.json。当前文件夹是第一阶段复现的统一阅读入口。
