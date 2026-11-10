# 同模型归档重复：最终选择后处理与裁判设置

两份温度0归档对最终选择L的共同任务检验呈负收益，研究优先级判据为未通过。实际C0的裁判设置对照中，两次结果方向不同，第二项重复性判据同为未通过。全部任务沿用原开发语料。

## 登记、来源与完整性

`protocol.json`在获取温度0报告正文和计算新结果前登记。来源为作者公开数据集[zjunlp/PredictBeforeExecute](https://huggingface.co/datasets/zjunlp/PredictBeforeExecute/tree/6b322cb88bdbcb2b2d3897ec7d0ded94a5bb2d06)，固定revision `6b322cb88bdbcb2b2d3897ec7d0ded94a5bb2d06`。报告文件名标注相同DeepSeek reasoner、pboost、cot与温度0；两次日期分别2025-12-05和12-09。温度1参照为2025-12-09另一归档；时间、顺序和温度共同变化。

| 归档 | 远端报告任务数 | admitted pair | 本轮实际C0场次 |
|---|---:|---:|---:|
| 温度0，20251205_214840 | 10 | 6,407 | 324 |
| 温度0，20251209_135057 | 26 | 17,877 | 850 |

26个固定任务的远端目录均已检查。12/05归档覆盖前10个任务：aptos2019、denoising、detecting-insults、dog-breed、google-quest、jigsaw、leaf、essay-scoring、lmsys、mlsp；其余16任务缺少该精确文件名。36份可用报告全部下载并核对文件长度、Git blob或LFS SHA256及LFS pointer blob。原件位于`/private/tmp/foreagent-deepseek-transfer-04/sources/`，独立逐项来源、文件名及哈希见`fetch_2/download_manifest.json`、`metadata_manifest.json`。该manifest的`partial`表示预期52份中远端提供36份；36份可用文件均为verified，下载失败文件0。

`banks_1/`保存两个无标签银行：代码SHA→ID、原始候选左右顺序、原index/confidence、group index完整绑定；源报告的groundtruth、correct、solution scores与reasoning经投影舍去。现有任务上的pair缺失0，查询到缺失pair为0。12/05有697/6,407条显式confidence=null；12/09有1,914/17,877条。原index为0/1，冻结C0 parser按弃权处理；.5门槛下仍保留该弃权。confidence缺键默认记录数为0。

## 同一实际C0赛程的后处理检验

每个新银行独立生成.7条件下的实际C0完整路径。C为实际C0的top group；H为全候选上只用.7+有效边按legacy top_set选取；L使用同一已揭示图上的全部.5+可解析方向；T为仅在C内部按L的全对手证据打破并列。最终后处理沿用同一已揭示图与预算。

主配对差为R(C)−R(L)，正值代表L改善。每任务先平均场次，再平均两银行；bootstrap重采样完整任务，seed 20261108093、10,000次。共同10任务是两重复的主检验；12/09全26任务单次结果另列。原DS1和三次GPT均在共同10任务上重新等权汇总。

| 比较范围 | 12/05 C−L | 12/09 C−L | 两次任务内平均 |
|---|---:|---:|---:|
| 共同10任务 | −.01120109 | −.08631237 | −.04875673 |
| 各自可用任务 | 10任务同上 | 26任务−.01447044 | 任务范围分别列示 |

共同10任务pooled区间[−.17247050,+.02366659]，leave-one范围[−.06246515,+.01036765]，3任务改善、1持平、6恶化。12/09全26任务区间[−.08952446,+.03745134]，14任务改善、2持平、10恶化。原DS1在同10任务C−L为+.01321080，GPT三次任务内平均−.03001788。

共同任务的因素分解：C−H=+.01328221，H−L=−.06203894，二者之和为主差−.04875673。C−T=−.02769246，L−T=+.02106427。L与T的两种最终选择均保留预定身份，研究结论采用已登记主臂L。

12/09全26任务中，C的regret .23345311变为L的.24792354，hit .23142743变为.27043269。命中率和平均归一化损失反映不同方面，选择失败时的损失幅度会影响后者。两新银行高门槛方向分别1377/1992、3464/5617正确；新增.5方向分别984/1584、2071/3736正确，分母为有效且实际分数存在严格优劣的查询发生次数。

## 裁判设置的实际C0参照

| 相对原DS1 actual C0的收益 | 12/05 | 12/09 | 两次平均 |
|---|---:|---:|---:|
| 共同10任务 | −.00903628 | +.07278125 | +.03187248 |
| 12/09全26任务单次 | — | +.03070846 | — |

共同10任务pooled区间[−.01613318,+.10756020]、leave-one最小−.00340031；两次正收益与所有leave-one正收益条件均为未满足。12/09单次26任务区间[−.00780492,+.08368096]、leave-one最小+.00909550，作为单次描述信号保留。该对照估计完整归档裁判设置差异；温度、运行顺序和时间的独立贡献需另外识别。

## 可复算证据

- `run_1/decisions.sealed.jsonl.gz`：1,174场真实C0赛程及C/H/L/T选择，SHA `53595a89afb643578d22fb6023fe5f694a1cf8876cfbf9aa87ee9804041ce8b1`。全部选择在评分标签文件读取阻断期间生成，封存后才读取评分并加入原DS/GPT结果。
- `run_1/per_episode.jsonl`与`per_task.json`：4,696份评分、逐场主差、actual C0与DS1配对差、共同10任务匹配表。每个postprocessing臂逻辑唯一读取、cache与预算拒绝统计逐场相同。
- `run_1/summary.json`：全部C/H/L/T、因素分解、hit、预算、CI、每任务leave-one及两套预注册判据。SHA `32120ac9f600d952fdcc58457b66908e8417eeb6de24dfd267ddce7ecbbd6142`。
- `run_1/verification_1/receipt.json`：独立重建14,636条查询方向、3,522个替代选择集合、4,696份分数、928个逐任务/共同子集指标和105组CI/leave-one，全部通过。主运行另用仅revealed bank重放1,174次实际C0终局，选择、轨迹与ledger全部相同。

选择函数直接复用`../c0-final-selection/experiment.py`并保存源码快照；原DS/GPT参照绑定其`run-002`。下载沙箱首次DNS失败保留在`fetch_1/`，按授权网络权限运行`fetch_2/`，报告获取127.4秒；分析17.2秒、独立核验2.3秒。新增模型推理调用、训练与GPU均0。

复跑构建：`python3 -B experiments/selection-frontier-02/deepseek-transfer/build_banks.py fetch_2 NEW_BANK_DIR`；分析：`python3 -B experiments/selection-frontier-02/deepseek-transfer/experiment.py --banks NEW_BANK_DIR --out NEW_RUN`；核验：`python3 -B experiments/selection-frontier-02/deepseek-transfer/verify.py NEW_RUN NEW_VERIFY`。
