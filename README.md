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
