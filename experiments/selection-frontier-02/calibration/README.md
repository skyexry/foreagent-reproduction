# 按裁判配置校准最终选择：留任务与留反馈重复

**结果：DS1 的配置内信号保留；温度0双向校准的优先级门槛失败。** 主结果见 [full-run-001/summary.json](full-run-001/summary.json)。策略 K 根据独立校准任务，在实际 C0 最终组 C 与同轨迹 .5 汇总 L 中选择一个。

## 固定规则与数据时序

[protocol.json](protocol.json) SHA-256：`682c0eb60e6466cbe2cb3f67681b3a161f4eb86e6b0dcab5ddacc19931733e76`。

只有当校准任务的平均 C−L ≥ .01，且删除任一训练任务后的平均 gain 均 > 0，配置开关才启用 L；其余情况选择 C。未知配置沿用 C，完成校准后获得一个配置级开关。

| 目标配置 | 每个 heldout task 的校准来源 | 评价任务与场数 |
|---|---|---|
| DS1，温度1单档 | 同档其他25任务 | 26任务，850场 |
| GPT，三份重复各自作为目标 | 另两份整档的其他25任务；先任务内平均 | 每档26任务，850场 |
| DS0，两个温度0档互为目标 | 另一档的共同9任务 | 每档共同10任务，324场 |
| DS1→DS0直接迁移敏感性 | DS1其他25任务 | 每个DS0共同10任务，324场 |

目标任务在所有校准源中均剔除；GPT 校准还完整留出目标反馈档。DS0 早档只有10任务原始文件可用，晚档有26任务，主双向结果固定在共同10任务。DS1直接迁移使用完整源配置的25个非目标任务，作为不同温度间迁移的独立敏感性；详见 `plans.json`。

该规则是在观察 DS1 与 GPT C/L 相反方向后形成，四份原档均属于开发发现。两份温度0档是结果揭晓前锁定的额外比较，任务仍来自同一开发集。校准和预测先分别封存，随后加入目标评分标签。

## 开关与实际效果

gain = 对照 regret − K regret，正值有利于 K。下表的两列分别与默认 C、总是 L 对比。

| 配置 | 启用 L 的任务 / 场数 | vs C gain | 描述性95% CI | vs 总是L gain |
|---|---|---:|---|---:|
| DS1 | 26/26；850/850 | +.021887 | [+.002141,+.044769] | 0 |
| GPT 12/10 | 0/26；0/850 | 0 | [0,0] | +.003327 |
| GPT 12/11第一份 | 0/26；0/850 | 0 | [0,0] | +.028155 |
| GPT 12/11第二份 | 0/26；0/850 | 0 | [0,0] | +.014145 |
| DS0 12/05 | 0/10；0/324 | 0 | [0,0] | +.011201 |
| DS0 12/09 | 1/10；2/324 | −.080258 | [−.240774,0] | +.006054 |
| DS0任务内先平均两档 | 同上 | −.040129 | [−.120387,0] | +.008628 |
| DS1→DS0 12/05 | 10/10；324/324 | −.011201 | [−.098207,+.050786] | 0 |
| DS1→DS0 12/09 | 10/10；324/324 | −.086312 | [−.253733,+.011052] | 0 |

DS1 的 K 等于总是 L；三份 GPT 的 K 逐场等于默认 C，增益为零精确反映这一回退。GPT task-first pooled 相对总是 L 的 gain 为 +.015209，含义是保留 C 所避免的 L 损失。各配置始终单列，聚合值作为配套说明。

DS0晚档唯一开启的任务是 **jigsaw-toxic-comment-classification-challenge**。源为早档其他9个共同任务，训练 mean gain +.027462，训练 delete-one 最小 +.017114，符合预设门槛；目标 jigsaw 两场的 gain 为 −.802581，按共同10任务等权贡献 −.080258。该反例直接保留了校准通过而目标迁移失效的情形。DS0的 K hit gain 分别为 0、−.041667；DS1→DS0敏感性分别为 +.004855、−.026292。全部逐任务结果、每个开关和训练证据见 `calibration.json` 与 `per_task.json`。

因此，DS0双向校准的“两档均启用、均受益、共同任务宏gain至少 .01”条件整体失败；判定保存为 `configuration_specific_DS1_signal_remains`。

## 成本与区间解释

C、L、K使用相同真实C0查询轨迹。任务宏平均唯一读取：DS1为11.208654；GPT pooled为9.979167；两个DS0共同任务分别为10.895、10.935。最终开关额外比较为0，本次重放新增API、训练与GPU使用均为0，计算耗时约1.97秒。校准本身依赖此前已执行任务的结果，这项来源条件随策略一并保留。

CI对**已固定的out-of-fold预测**执行10,000次成对任务bootstrap，seed 20261108093，重采样期间保持开关固定。各fold训练任务大量重叠，因此区间作为描述性统计；该过程展示的是当前存档上的校准与迁移表现。独立任务确认仍需后续样本。

## 分开核验与重建

- `calibration_verification.json`：144 folds的来源、目标任务剔除、配置内均值与训练leave-one独立核对；将每fold目标任务标签与完整留出反馈档改为极端值，144/144校准输出逐项相同。
- `prediction_verification.json`：4,696份预测核对校准开关和已封存C/L选择；14,088份目标分数及66组配对区间独立重算通过。
- `calibration.json`记录校准证据；`predictions.sealed.jsonl.gz`记录目标动作；`selection_seal.json`分别绑定二者哈希与所有源输入。
- `discovery-run-001/`先交付DS1/GPT结果；`full-run-001/`加入温度0。两阶段的共同校准和预测逐项一致。首轮独立核验曾遇到快照模块的Python路径问题，修正核验器后全部通过，记录于 `verification_attempts.json`。

在项目根目录以新输出路径重建：

```bash
python -B experiments/selection-frontier-02/calibration/experiment.py \
  --transfer-run experiments/selection-frontier-02/deepseek-transfer/run_1 \
  --output experiments/selection-frontier-02/calibration/full-run-002
python -B experiments/selection-frontier-02/calibration/verify.py \
  --run experiments/selection-frontier-02/calibration/full-run-002
```
