# 保留 C0，封存本轮文本信号

本轮只检验一个预先固定的后处理规则：在 C0 原第一组出现并列、且已接受的查询边存在“保留 reasoning 最后一个明确 JSON 方向与归档方向相反”的情况下，对组内候选扣除疑似冲突的净胜票；保留最小惩罚候选，平手继续保留。flag 表示文本一致性疑点；中间推理 JSON 也可能产生这一疑点。

## 实际结果

26 个已查看开发任务、每个裁判档 850 场。指标为任务等权 normalized regret 和并列均匀选择的最佳命中率。GPT 合并先在每个任务内平均三个裁判档，再等权平均任务。

| 口径 | C0 regret | 文本 regret | 32 次 sham 平均 regret | 文本相对 C0 gain | 任务 bootstrap 95% CI |
|---|---:|---:|---:|---:|---|
| DS | 0.264161563 | 0.263701556 | 0.264110125 | 0.000460006 | [0, 0.001380019] |
| GPT 三档合并 | 0.272486461 | 0.272486461 | 0.272486461 | 0 | [0, 0] |

DS 命中率保持 0.236738400；GPT 合并保持 0.281502340。DS 文本相对 sham gain 为 0.000408568，95% CI [0, 0.001225705]。DS 收益集中在 `tgs-salt-identification-challenge` 一个任务；移除该任务后收益为 0。预设 DS 门槛为 0.01，并要求 GPT 正向、超过 sham、区间及逐任务移除稳定；本轮据此保留 C0，结束这一精确文本信号的尝试。

## 暴露量与变化

| 裁判档 | 唯一 accepted 查询边 | 明确 reasoning 方向 | 方向冲突 | C0 并列场 | 改变场 |
|---|---:|---:|---:|---:|---:|
| DS | 3349 | 1986 | 3 | 243 | 1 |
| GPT 20251210_154406 | 4348 | 0 | 0 | 148 | 0 |
| GPT 20251211_161746 | 4253 | 0 | 0 | 145 | 0 |
| GPT 20251211_171620 | 4213 | 0 | 0 | 135 | 0 |

3400 场中，选择集合保持 3399 场；改变的 1 场 regret 改善，恶化 0 场、regret 持平 0 场。GPT 结果反映该明确 JSON 信号在现有归档中的覆盖量为 0，跨模型有效性仍属于待验证范围。

聚焦诊断使用唯一 accepted 严格优劣 pair，并条件于可提取明确 reasoning 方向：DS 方向一致组正确 1247/1983（62.88%），冲突组 0/3（0%）。这是原始条件统计，样本量与选择条件决定解释范围；冲突标记的因果作用仍需独立证据。逐任务和 confidence 区间分层见 `diagnostics.json`。

## 封存、映射和标签可见性

`protocol.json` 在选择与评分前写入。原审计 71508 行均缺 `reasoning_last_json_index`，本轮从固定 `source_file/source_row` 的 `prediction.reasoning` 恢复，并复用原审计的最后一个平面 JSON 提取器。逐行核对源 SHA、候选路径后缀对应 ID 的顺序、归档 index/confidence、JSON presence 和原审计混合 mismatch 字段；仅严格整数 0/1 的方向差异形成 flag，confidence 差异单独保留原选择。

源 JSON 文档同时含有 gold 字段，`json.loads` 会将文档整体装入内存；选择代码仅取 `prediction.reasoning`、归档预测字段及 `solutions.path`，gold 字段在选择阶段保持未访问。单独的 `evaluation_labels.json` 在 `flags.sealed.jsonl.gz`、`selections.sealed.jsonl.gz` 和 `selection_seal.json` 写入后打开。因此本轮采用字段访问层面的隔离；原研究 host 的进程级隔离属于另一机制。

首次 pre-score 检查发现旧 reference 的 `selected` 为分臂字典，改为核对 `selected.C` 后重新执行；同时加上原审计输入源 SHA 核验。该尝试停在评分之前，规则与指标保持预注册口径。成功执行源码留在 `run.executed.py`。3400 份 C0 第一组与轨迹逐项一致；独立回读校验了 3400 份文本选择、108800 份 sham 选择及任务等权 C0/文本指标，见 `receipt.json`。

## 成本与复现

成功主运行包含源文本提取、封存和评分：8.48 秒 wall，10.45 秒 CPU；独立验证 3.07 秒 wall。首次 pre-score 检查与文件整理用时单独保留为未计时部分。新增模型调用 0、训练 0、GPU 0 小时、付费 $0。部署到同一反馈计划时仅处理已有 rationale，新增推理调用为 0；在线文本留存和运行时需按实际环境核验。

```bash
python -B experiments/rationale-tiebreak-v1/verify.py
```

主要产物：`summary.json`、`receipt.json`、`protocol.json`、`selection_seal.json`、`per_task.json`、`diagnostics.json`。本目录限定于这一固定方法的离线记录。
