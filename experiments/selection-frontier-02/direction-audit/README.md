# 低置信方向来源与固定 C0 赛程审计

**DS 在实际 C0 赛程上的收益包含可测的方向信息；四 bank 的整体结果呈现模型及候选池大小依赖。当前方法选择沿用原主协议，本目录用于解释。**

独立核查覆盖 71,508 个 bank-pair、4×850 场。主审计先登记 [protocol.json](protocol.json)（SHA `a917d39958175ae06ae55b1719ca9d71209f8658eeb22db7fa383140950d9d6a`），再从 [c0-final-selection 的封存文件](../c0-final-selection/run-001/decisions.sealed.jsonl.gz)读取赛程。结果采用 [run-003](run-003/)，主审计用时 17.09 秒；模型调用、训练与 GPU 均为 0。

## 来源核查：归档预测与完整原回答

每 bank 有 17,877 个候选对。按代码字段定义审计：

- 本次 bank builder 从作者 alignment 的 `prediction.best_index` 和 `prediction.confidence` 映射方向，字段缺失时 confidence 默认 .5。固定 `response_values` 对合法 index 与 confidence 再严格解析；null、非法 confidence、非法 index 继续作为弃权。
- 本仓库上游 `parse_pairwise_response` 也将缺失或转 float 失败的 confidence 设为 .5。因此，**alignment 中存在数值 confidence=.5，证明的是归档字段存在；完整模型输出中的显式 confidence 需要进一步原文证据。** 原始 alignment 生成解析过程的完整追溯程度取决于 raw-response 可用性。
- DS 的 `data/author_reference` 与三个 GPT alignment 均保留解析后的 `prediction`；完整 `raw_response` 目前仅在首个 GPT bank 的 6 个任务备份可核查。5,013 个 admitted backup pair 的端点顺序全部与 bank 一致。
- DS reasoning 中确有 JSON 片段；其中一部分与归档预测一致，另一部分可能属于中间反思。按照父代理指示，reasoning JSON 全部作为旁证字段，严格 E 只接纳完整 raw-response 末个合法 JSON 的匹配判决。[口径修订](schema_supplement.json)

| bank | 全 bank 新增 [.5,.7) 对数 | 有完整 raw 显式匹配 | 实际 C0 trace 新增 edge-episodes | trace 中 raw 显式匹配 | trace 中 exact .5 |
|---|---:|---:|---:|---:|---:|
| DS | 5,633 | 0 | 3,624 | 0 | 130 |
| GPT 154406 | 3,315 | 1,057 | 2,318 | 564 | 42 |
| GPT 161746 | 3,406 | 0 | 2,408 | 0 | 39 |
| GPT 171620 | 3,382 | 0 | 2,382 | 0 | 30 |

以上新增判决的 alignment `prediction` 均含合法显式 index 与数值 confidence；本次映射阶段的 missing-confidence/default 路径计数为 0，已记录 error/fallback 标记计数为 0。首 GPT 的 8 个已恢复原始失败均保持弃权；另外两个 GPT bank 各 1、3 个异常解析记录也保持弃权。完整 raw 缺失的记录，其更早解析默认情况标为“归档字段层可核查，完整原回答待补证”。

DS 的 5,633 个新增 pair 中，3,049 个 reasoning 片段与归档匹配，741 个 reasoning 的末个 index-JSON 与归档存在差异；这组数值描述中间内容与最终归档的关系。严格 E 的接纳逻辑由完整原回答决定。

来源逐 pair 记录：[source_audit.sealed.jsonl.gz](run-003/source_audit.sealed.jsonl.gz)；计数见 [source_counts.json](run-003/source_counts.json)、[source_trace_counts.json](run-003/source_trace_counts.json)；来源文件 SHA 见 [input_sha256.json](run-003/input_sha256.json)。

## 固定图上的方向负对照

各 bank 沿用它自身真实 C0 .7 所产生的 unique trace；同一 bank 内，所有 arm 固定完全相同的查询边、次序和读取成本。原主实验 C/H/L 含义保持一致：

| arm | 最终选择规则 |
|---|---|
| C | 实际 C0 原淘汰赛最终 top |
| H | 所有候选；仅 .7+ 有效方向；原胜率、有效度、并列规则 |
| L | 所有候选；所有解析有效 .5+ 方向；同一汇总器 |
| E | 保留 H；低边仅完整 raw 原文可证实显式合法 index/confidence、与归档一致且无记录异常时接纳 |
| E_archive | 保留 H；低边仅要求 alignment prediction 显式合法字段且无记录异常，属于较弱来源条件 |
| N32 | 保留 H；接纳与 L 完全相同的低边，低边赢家改为确定种子的公平随机方向，预先固定 32 次结果的平均 |

N32 每条低边按 `(version, replicate, job_id, unordered_pair)` 的 SHA256 派生随机种子，高边方向保持固定。所有 32 组最终并列集合先封存，再首次读取 `evaluation_labels.json` 评分。原 archive 包含历史 score/groundtruth 字段，选择代码只访问路径、prediction、response 字段。每个集合按均匀并列评分。

4 bank 每臂的总 unique reads 分别为 DS 10,574；GPT 9,495、9,498、9,463。独立重建的 C/H/L 逐任务 regret、hit 共 **624 个数值**与原主实验精确匹配。[选择封存](run-003/selection_seal.json) · [核验](run-003/verification.json)

## 主要量化发现

下表为 26 个任务等权 normalized regret。GPT pooled 先在每个任务内平均三 bank，再对任务平均。

| bank | C | H | L | 严格 E | N32 |
|---|---:|---:|---:|---:|---:|
| DS | .264162 | .292411 | .242275 | .292411 | .282963 |
| GPT 154406 | .276388 | .276435 | .279715 | .275486 | .275562 |
| GPT 161746 | .253559 | .255225 | .281714 | .255225 | .260476 |
| GPT 171620 | .287512 | .283729 | .301658 | .283729 | .284373 |
| GPT task-first pooled | .272486 | .271797 | .287696 | .271480 | .273470 |

**DS：** C−L gain **+.021887**，95% 任务簇区间 **[+.002141,+.044769]**，leave-one **[+.015156,+.025627]**。拆开看，C→H gain −.028250，H→L gain +.050137。固定低边接纳后，真实方向对公平方向的优势 **N32−L=+.040689**，区间 **[+.010601,+.076467]**，leave-one **[+.028148,+.045567]**；32 个公平方向样本逐一比较均有利于真实 L，优势范围 [.016277,.070223]。真实低方向的改善超出了本次公平填边对照的均值。

H→N32 仅由固定低边加公平方向带来的平均 gain 为 +.009448，区间 [−.023898,+.053161]。图填边与汇总规则确实能改变输出；DS 中 L 的主要方向优势还需与这部分结构变化区分。

**GPT pooled：** C−L gain **−.015209**，区间 **[−.042510,+.006730]**，leave-one **[−.018021,−.006199]**。真实方向对公平方向的优势 **N32−L=−.014225**，区间 **[−.037723,+.004458]**，leave-one **[−.016701,−.005616]**。32 个公平样本中，真实 L 优于公平结果的样本为 3/32；三个独立 GPT bank 分别为 5/32、3/32、1/32。此处的“32次”描述已指定负对照的 Monte Carlo 敏感性。

新增低边的严格方向准确率，按实际 C0 trace edge-episode 计：DS **2041/3624=56.32%**；三个 GPT bank **1233/2318=53.19%**、**1227/2408=50.96%**、**1185/2382=49.75%**。这些 queried 低边恰好都为效用严格比较，true tie 计数为 0。数据对同一 pair、同一候选池的重复使用依照任务簇统计处理。[source_accuracy.json](run-003/source_accuracy.json)

## 池大小与来源敏感性

**任务等权使少量 episode 的小池任务具有完整任务权重。** 840 场 n=10 对应 21 个任务，10 场 n<10 对应 5 个任务。以下分解同时保留完整分母与条件分母：

| 指标 | DS n=10 全26贡献 | DS 小池全26贡献 | GPT pooled n=10 全26贡献 | GPT pooled 小池全26贡献 |
|---|---:|---:|---:|---:|
| C−L | +.014573 | +.007314 | +.001612 | −.016821 |
| N32−L | +.013538 | +.027150 | +.001121 | −.015346 |

在 21 个 n=10 任务上重新等权：DS C−L **+.018043**，区间 [−.001634,+.039689]；N32−L **+.016762**，区间 [−.001960,+.036330]。GPT pooled 相应为 **+.001996**、**+.001387**，两区间均跨 0，逐任务剔除也跨越 0。小池任务上 pooled GPT 的实际方向优势为 **−.079799**，区间 [−.154718,−.009228]。因此，26任务整体上的模型差异与池大小、任务构成共同相关；“GPT 低置信方向普遍有害”同样超过本轮证据范围。[pool_size_sensitivity.json](pool_size_sensitivity.json)

严格 E 在 DS 和后两个 GPT bank 与 H 相同，原因是完整 raw-response 可用性；首个 GPT bank 的 E 只补入 564 个可直接核查的低 edge-episodes。这种来源可用性由模型、任务和存档决定，因此 E 是证据保守性检查。较弱 E_archive 与 L 逐场相同，说明归档字段合法性筛选本身保留了全部新增边。

在看到主审计结果后，追加了一项明确标为 source-informed 的保守敏感性：删除所有 confidence 恰为 .5 的新增边，包括真实显式 .5。新 arm V 的选择再次先封存再评分。DS C−V=**+.023320**，区间 [+.002922,+.046686]，leave-one 全正；GPT pooled C−V=**−.015509**，区间 [−.042584,+.006363]，leave-one 全负。DS 的局部收益与 GPT 的整体反向均保留，已知 default=.5 口径对主要方向差异的解释份额较小。[该敏感性协议与结果](default-half-run-001/)

## 证据边界与复核

本审计支持：DS 的特定已归档 C0 .7 赛程上，低置信方向相对公平方向具有信息；同时，置信度接纳、有效图形状和汇总 tie-break 均参与最终选择。结果属于已查看的开发任务，原 .7 赛程先冻结、再重汇总，覆盖范围是这些已揭示历史对局。主协议上的实际算法、跨 bank 优先级及新的任务确认仍分别验收；新增 E、N32、V 只承担解释职责。

复跑主审计使用全新目录：

```bash
python3 -B experiments/selection-frontier-02/direction-audit/audit.py --output experiments/selection-frontier-02/direction-audit/new-run
python3 -B experiments/selection-frontier-02/direction-audit/check_and_summarize.py
```

主审计依赖 manifest 指定的作者归档本机路径；实际读取文件均记录 SHA。每次分析预算 600 秒。

早期 run-001 保留收到 reasoning 证据口径指示前的 E 实现；run-001 与 run-002 均在最终交叉核验的包装层读取处出现 KeyError，失败日志保留。run-003 修正 `per_task['by_bank']` 路径并完成全部核验。全部命令、版本、失败和附加诊断见 [execution_receipt.json](execution_receipt.json)。
