# 全量 DS1 终局代价权重

850 场 C0 原轨迹逐场精确复验通过；原 52 场的 306 行反事实结果逐字段一致。全量共有 5,639 条采纳且严格有优劣的唯一查询边，已从相同前缀、seed、预算跑完相反胜者分支，原胜者分支复用精确核验后的基线。

17,877 个训练候选 pair 中，3,349 个被轨迹曝光，1,728 个得到正的平均终局代价增量（全部 pair 的 9.67%）；703 个平均增量为负，按协议取正部后权重为 1。14,528 个未曝光 pair 的三种权重均为 1。每条发生记录先计算有符号 `wrong_regret-right_regret`，按 task/pair 算术平均后取正部。`gap` 使用同一批发生记录内、按当场候选池执行分数跨度归一的两候选差值。

| 原始权重 | 最小 / 中位 / P95 / 最大 | 均值 | 有效样本数 ESS |
|---|---:|---:|---:|
| terminal | 1 / 1 / 1.10214 / 2 | 1.01935 | 17,730.41 |
| gap | 1 / 1 / 1.54650 / 2 | 1.06485 | 17,312.58 |
| shuffled | 1 / 1 / 1.10214 / 2 | 1.01935 | 17,730.41 |

ESS 定义为 `(sum(w))²/sum(w²)`。terminal 的逐任务 ESS/pair 数中位为 99.21%，范围 90.44%–99.91%。这里统计全部 prepared pair；训练阶段根据代码内容与留出任务重合情况筛除后，再在保留的训练任务内部归一并使各任务总权重相等。最终训练 ESS 由对应 fold 的样本决定。

**探索性重复 seed 诊断：**同一 pool 的两个 seed 都查询到同一边的情形共 1,005 个，其中 745 个终局增量相差超过 1e-12（74.13%），平均绝对差 0.17440。这里两个 seed 会改变上下文和后续路径，结果描述开发语料中的轨迹依赖；方法收益交由已登记的留任务训练评估检验。

输出位于 `run_1/`：

- `tasks/<task>.json`：训练端唯一所需输入，格式 `{pair: {winner, n, mean_delta, mean_gap, terminal, gap, shuffled}}`。`winner` 是已统一 higher-is-better 执行分数对应的候选 ID；三种权重均包含基数 1、处于归一前。训练 fold 按训练任务名直接打开单文件。
- `rows/<task>.jsonl`、`branches/<task>.jsonl.gz`：逐发生记录与反向分支完整轨迹。
- `receipt.json`：850 场复验、52 场逐行复验与逐任务文件 SHA-256；`readback.json` 绑定完整产物并独立回读分支分数/前缀、全部 pair 聚合及 104 个 shuffle 分层。
- `summary.json`、`diagnostics.json`：逐任务与总体诊断；二者用于审计。

shuffle 在每个 task 的 `0 / 1 / 2-3 / 4+` 曝光层内，按 pair 排序后以 `Random("20261108:<task>:<layer>")` 置换 terminal 增量。各任务独立生成；训练输入按任务物理分开。

在项目根目录可复跑（输出目录选择新名称）：

```bash
python3 -B experiments/trajectory-weighted-judge-v1/credit/build.py --output experiments/trajectory-weighted-judge-v1/credit/run_2
python3 -B experiments/trajectory-weighted-judge-v1/credit/verify.py experiments/trajectory-weighted-judge-v1/credit/run_2
python3 -B experiments/trajectory-weighted-judge-v1/credit/describe.py experiments/trajectory-weighted-judge-v1/credit/run_2
```

本次权重构建耗时 36.89 秒，CPU 本地执行；付费模型调用、GPU、候选执行与模型训练均为 0。终局权重信号较稀疏，整体权重接近均匀；匹配训练将检验该信号在固定表示下的实际作用。
