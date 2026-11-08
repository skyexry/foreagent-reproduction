# Environment & Baselines：作者原版 ForeAgent

本阶段验证 [ForeAgent 作者仓库](https://github.com/zjunlp/predict-before-execute/tree/c4d52cf99bd870d830b456ac7c0684aec1aef375) 的发布配置。运行目录使用作者仓库的独立检出。获取相同源码：

```bash
git clone https://github.com/zjunlp/predict-before-execute.git foreagent-author-only
cd foreagent-author-only
git checkout --detach c4d52cf99bd870d830b456ac7c0684aec1aef375
git rev-parse HEAD
git status --short
```

入口为作者源码下的 `mle-bench/run_agent.py`。本次只用 `mle-bench/experiments/splits/stanford-covid-vaccine.txt`，保留发布配置的 10 个候选、confidence 0.70、top-k=1、执行概率 0.20、原始缓存和空选后的执行回退。

验收需要同一次运行的候选生成记录、筛选记录、实际执行记录和 submission，以及官方 MLE-bench 评分输出。任务数据和 Git LFS 实体文件在执行机准备。当前证据及下一步见 [STATUS.md](STATUS.md)。

## 当前验收与本机核验

当前原版单任务复现阶段已完成：标准 12 小时端到端运行取得有效官方分数 **0.26640**，已完成本机核验。验收证据及范围见 [Environment & Baselines 验收清单](experiments/environment-acceptance/README.md)。评分器行顺序问题列入[后续改进清单](IMPROVEMENTS.md)；原版重复性与 AIDE 在线对比作为后续可选研究归档。

本机核验显式接收固定源码、运行附件、准备后数据和作者提交路径；核验命令、独立环境依赖锁及附件校验值均在上述清单中。本轮聚焦原版，参数沿用作者发布配置。
