# GPT 银行与跨银行分配重放

三份 GPT-5.1 原始重复反馈均已映射至 clean-ranking-v1 的 877 个代码代表、26 个任务及每份 17,877 条已接纳无序 pair。银行保留原始反馈中的两项代码顺序，以及阈值 .7 以下的可用方向。文件为 `<original GPT run>.json.gz`，结构与 DS `prepared/feedback.json` 相同，字段限定为 `order`、`predicted_best_index`、`confidence`、`source_group_index`。

| GPT run 后缀 | 有效 index | .7 有效边 | 保留的低于 .7 方向 | 原始失败恢复 |
|---|---:|---:|---:|---:|
| 20251210_154406 | 17,869 | 14,554 | 3,315 | 8 |
| 20251211_161746 | 17,876 | 14,470 | 3,406 | 0 |
| 20251211_171620 | 17,874 | 14,492 | 3,382 | 0 |

来源核验覆盖 R8 清单中全部 78 份 alignment 文件的 Git blob/LFS、字节数及已登记 SHA-256，以及 6 份原始备份、5,099 条共享记录和 8 条恢复失败记录。代码文件逐份核验完整 SHA-256，ID 为其前 20 位；映射以原始文件名和每任务唯一短后缀识别代码，银行的 `order` 沿用每条 GPT 输入的原始顺序。每条无序 pair 的 `source_group_index` 与 DS 已接纳表相同。逐文件、逐代码及恢复证据见 `mapping_audit.json`，哈希见 `manifest.json`。

R8 的 `normalize_prediction` 保留低信心方向；默认赢家行为经源码与逐记录对照核实。新旧解析结果的 8 处差异全部对应已恢复 API 失败：原始记录只有 error，R8 将 confidence 置 0，DS/C0 对缺失 confidence 使用 .5；两者的 index 均为空，最终均弃权。当前银行保留这些原始失败及 C0 字段语义。

完整来源到 gzip 已独立重建一次，三份 gzip 与映射审计均逐字节一致；另行核验任务与 pair 键、order 端点、字段白名单和 group index，见 `verification.json`。执行分数、ground truth、correct 标记、reasoning 均存于其原有来源；银行只保存上述四个策略字段。

## 跨银行分配结果

固定 gate .7、原始预算、冻结 top_set，并比较同一初始 chain 后的 coverage_random 与 valid_coverage_v1。每份银行各 850 场，合计 5,100 次选择。政策通过观察接口逐步执行；另用独立实现核对全部自适应轨迹，并核对随机赛程与历史完整随机赛程、两臂初始 chain。全部选择与轨迹先封存，然后读取评分标签。

下表 gain = coverage_random regret − valid_coverage_v1 regret，正值有利于新分配。

| GPT run 后缀 | regret gain | 任务簇 95% CI | leave-one 最小值 | hit gain |
|---|---:|---|---:|---:|
| 20251210_154406 | +.001716 | [−.016897, +.026395] | −.008216 | +.012276 |
| 20251211_161746 | +.016935 | [−.005668, +.045986] | +.005549 | +.030881 |
| 20251211_171620 | −.002024 | [−.024834, +.030987] | −.016073 | +.012388 |
| GPT task-first pooled | +.005542 | [−.013963, +.033400] | −.006247 | +.018515 |

Pooled 结果先在每任务内平均三份反馈，再对任务等权汇总。10,000 次成对任务簇 bootstrap 使用协议 seed 20261108093。Pooled 零有效度候选数从 .446154 降至 .125；任务宏平均唯一读取均为 12.115385。三份反馈来自同一开发任务集的重复记录。合并主指标区间跨 0，剔除 petfinder 后 gain 为 −.006247，保留任务异质性与依赖性解释。研究优先级需连同 DS 正式结果及协议门槛判断。

完整结果、逐任务及 leave-one 数值、逐场指标、封存选择与哈希均在 `allocation-run-001/`。该实验为已登记的跨裁判银行诊断 replay；DS 正式统一 CLI 实验由 coverage 分工保存。

## 重建

在项目根目录运行，指定保留 78 份反馈和 6 份恢复源的 R8 工作目录；每项分析为本机 CPU、零新增模型调用。

```bash
python -B experiments/selection-frontier-02/banks/build_banks.py \
  --source-root /Users/shrinn81/Documents/Codex/2026-11-01/read-this-folder-and-my-current/work/foreagent-r8
python -B experiments/selection-frontier-02/banks/replay_allocation.py \
  --output experiments/selection-frontier-02/banks/allocation-run-002
```

脚本要求重放使用新的输出目录。单次重建的实际输出哈希绑定于 `manifest.json`；每次重放的脚本、政策、输入、选择封存与结果哈希绑定于该运行目录。
