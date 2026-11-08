# 固定位置基线与判断差异分析（2026-10-21）

本分析只读取已保存的 246 对最终采用结果、固定样本清单、作者一次公开运行与候选源码，没有新增 LLM 调用，也没有执行候选代码。首轮/补调采用规则不变。本分析为看到结果后的探索性审计，不是预注册研究。

## 1. 固定位置基线

| 方法 | 正确数 / 246 | 准确率 |
| --- | ---: | ---: |
| 始终选候选 0 | 131 | 53.25% |
| 始终选候选 1 | 115 | 46.75% |
| 等概率随机选 0/1（理论期望，未实际随机运行） | 123（期望） | 50.00% |
| 当前模型（含失败补调） | 136 | 55.28% |
| 作者同样本一次公开运行 | 130 | 52.85% |

当前模型只比始终选 0 多对 **5 对，增加 2.03 个百分点**。它在真实胜者为 1 的样本中赢回 63 对，同时在真实胜者为 0 的样本中比这个基线少对 58 对，净收益为 5。固定选 0/1 的两个规则都报告；不能只挑较弱的 46.75% 或只用 50% 当唯一比较对象。53.25% 是本样本的位置构成，不是外部验证集上的通用基线。

真实胜者位置为 0/1 的数量是 131/115。模型选择位置 0/1 的数量为 125/121（50.81%/49.19%），作者为 133/113。当前模型在真实胜者为 0 时正确 73/131（55.73%），为 1 时正确 63/115（54.78%）。描述上没有明显的总体固定位置倾向；**没有交换同一对的顺序，不能证明不存在位置敏感性**。

逐任务看，模型相对始终选 0 是 10 个任务胜、7 个平、9 个负。每任务仅 3 或 10 对，不用于任务强弱定论；不能事后为每个任务选一个最优固定位置，再把它当作独立基线。

## 2. 与作者的判断差异

| 分组 | 配对数 |
| --- | ---: |
| 双方都正确 | 106 |
| 仅我们正确 | 30 |
| 仅作者正确 | 24 |
| 双方都错误 | 86 |

双方在 192/246（78.05%）样本上选择相同；二选一且无平局时，双方都错必然也选了同一个候选。分歧 54 对，我们在其中正确 30，对方正确 24。净多 6 对不代表改进已经具有统计或实际稳定性。双方错误重合多，也可能来自共同模型、提示和输入、任务难度以及单次训练分数噪声，不能只凭重合确定原因。

仅我们正确分布在 15 个任务，仅作者正确分布在 16 个任务；双方都错覆盖 24 个任务。共同错误较多的是 jigsaw（8/10）、mlsp-birds（6/10）、tabular-dec-2021（6/10）。全任务计数见后表，避免只展示有利任务。

### 11 对原始理由抽查

选择规则：每个“我们独对／作者独对／双方都错”分组按固定 manifest 索引取前三个不同任务，再增加共同错误数最多的两个任务中的首对（并列按任务名排序），共 11 对。不是随机样本，不能把以下现象的次数外推到全部 246 对。全部 246 对的分组及候选分数保存在 coverage_analysis.json，双方原始理由与源文件哈希另存本地 qualitative_review_evidence.json。

| 索引及本轮原始回答 | 任务 | 分组 | 人工观察与证据边界 |
| --- | --- | --- | --- |
| [026](</Users/shrinn81/Documents/Data Mining/PM Final Project/ML Agent/outputs/coverage-20261021/pair-026.json>) | detecting-insults-in-social-commentary | 我们独对 | 我们强调 DeBERTa 辅助任务；作者强调 RoBERTa 的交叉验证与集成。双方注意到数据报告正例为 0，但作出不同假设。只能确认本对结果支持我们的选择，不能据此确认辅助任务的因果收益。 |
| [054](</Users/shrinn81/Documents/Data Mining/PM Final Project/ML Agent/outputs/coverage-20261021/pair-054.json>) | leaf-classification | 我们独对 | 我们重视全量数据参与交叉验证、较简单特征；作者重视 PCA、缩放和正则化。真实 log loss 为 2.46940 / 0.82331，候选 1 较好。说明相同数据特征可被赋予不同权重。 |
| [064](</Users/shrinn81/Documents/Data Mining/PM Final Project/ML Agent/outputs/coverage-20261021/pair-064.json>) | learning-agency-lab-automated-essay-scoring-2 | 我们独对 | 我们认为小样本与高分段稀少不利于复杂 stacking，作者更重视分段专用模型。实际候选 0 较好。这是选择简单方案成功的例子。 |
| [032](</Users/shrinn81/Documents/Data Mining/PM Final Project/ML Agent/outputs/coverage-20261021/pair-032.json>) | dog-breed-identification | 作者独对 | 我们偏向 ConvNeXt、ArcFace、增强等技术组合；作者强调训练与验证预处理一致性，选择候选 0。另经代码静态核对，候选 1 的 loss 内归一化/缩放与测试直接 softmax 的路径不同，概率校准值得核查，但没有运行证据证明它是低分原因。真实 log loss 为 1.02272 / 4.66835。 |
| [037](</Users/shrinn81/Documents/Data Mining/PM Final Project/ML Agent/outputs/coverage-20261021/pair-037.json>) | google-quest-challenge | 作者独对 | 我们重视句向量、GAT 与标签关联；作者重视端到端微调及文本适配。实际候选 0 较好。不能把架构与数据分析表面对应直接当作效果优势。 |
| [056](</Users/shrinn81/Documents/Data Mining/PM Final Project/ML Agent/outputs/coverage-20261021/pair-056.json>) | leaf-classification | 作者独对 | 我们强调 PCA 对相关特征的处理；作者更重视超参数调优和校准。真实 log loss 为 0.32626 / 1.86693，候选 0 较好。此例不支持将高相关性直接转成 PCA 必胜。 |
| [001](</Users/shrinn81/Documents/Data Mining/PM Final Project/ML Agent/outputs/coverage-20261021/pair-001.json>) | aptos2019-blindness-detection | 双方都错 | 双方偏向交叉验证与集成，但 QWK 为 0.86160 / 0.85794，差仅 0.00366。标签按原分数严格判定；没有多次候选训练结果，不能判断这个优势是否稳定。 |
| [012](</Users/shrinn81/Documents/Data Mining/PM Final Project/ML Agent/outputs/coverage-20261021/pair-012.json>) | denoising-dirty-documents | 双方都错 | 双方均注意到了分辨率处理问题，仍基于 RDN、训练技巧等选候选 1；实际 RMSE 为 0.29491 / 0.57001，候选 0 较好。识别一个代码问题并不等于能准确权衡最终影响。 |
| [020](</Users/shrinn81/Documents/Data Mining/PM Final Project/ML Agent/outputs/coverage-20261021/pair-020.json>) | detecting-insults-in-social-commentary | 双方都错 | 我们以 CLS pooling 作主要区分；作者依据数据报告正例为 0 推断候选 0 会崩溃。AUC 实际为 0.94972 / 0.94967，差 0.00005。报告矛盾与极小分差同时存在；不能把作者的崩溃推断视为已证实事实。 |
| [043](</Users/shrinn81/Documents/Data Mining/PM Final Project/ML Agent/outputs/coverage-20261021/pair-043.json>) | jigsaw-toxic-comment-classification-challenge | 双方都错 | 我们声称 attention 有助于补救 160 之后的信息；代码先截断到 160，再做 attention pooling，因此这条论据有明确逻辑缺口。作者则明确限定为截断窗口内的注意力优势，不能将同一错误理由归给作者。真实 AUC 为 0.98320 / 0.98297，差 0.00023。 |
| [084](</Users/shrinn81/Documents/Data Mining/PM Final Project/ML Agent/outputs/coverage-20261021/pair-084.json>) | mlsp-2013-birds | 双方都错 | 双方都因小样本、过拟合顾虑选择较简单的特征模型；实际候选 1 的多模态神经网络较好（AUC 0.76578 / 0.81260）。这是“偏爱简单方案”也会选错的反例。 |

### 可核验的问题与不能下的结论

1. **存在具体的代码约束推理错误。** case 043 候选 1 的 [MAX_LEN=160](</Users/shrinn81/Documents/Data Mining/PM Final Project/ML Agent/data/coverage/solutions_subset_50/jigsaw-toxic-comment-classification-challenge/code/solution_Automind_v3_jigsaw-toxic-comment-classification-challenge_1652fdb9-175f-4291-a2c7-d5b5bccb53fe_run_4180df23c751462c987e70ce437b7bae.py:24>)、[输入截断](</Users/shrinn81/Documents/Data Mining/PM Final Project/ML Agent/data/coverage/solutions_subset_50/jigsaw-toxic-comment-classification-challenge/code/solution_Automind_v3_jigsaw-toxic-comment-classification-challenge_1652fdb9-175f-4291-a2c7-d5b5bccb53fe_run_4180df23c751462c987e70ce437b7bae.py:64>) 和 [attention pooling](</Users/shrinn81/Documents/Data Mining/PM Final Project/ML Agent/data/coverage/solutions_subset_50/jigsaw-toxic-comment-classification-challenge/code/solution_Automind_v3_jigsaw-toxic-comment-classification-challenge_1652fdb9-175f-4291-a2c7-d5b5bccb53fe_run_4180df23c751462c987e70ce437b7bae.py:149>) 可以直接核对。池化无法访问已在 tokenizer 阶段删除的 token。这里只确认论据错误，不声称它解释了全部选错原因。
2. **技术名词与效果之间缺乏充分证据。** case 032 中，本轮把多种先进技巧当成优势；但代码里的 [训练 loss 归一化与缩放](</Users/shrinn81/Documents/Data Mining/PM Final Project/ML Agent/data/coverage/solutions_subset_50/dog-breed-identification/code/solution_Automind_v3_dog-breed-identification_117384d4-e533-40ae-9e59-4cd7799e4c93_run_9c37401733574214bc73f3e91e818bfb.py:180>) 和 [测试 softmax](</Users/shrinn81/Documents/Data Mining/PM Final Project/ML Agent/data/coverage/solutions_subset_50/dog-breed-identification/code/solution_Automind_v3_dog-breed-identification_117384d4-e533-40ae-9e59-4cd7799e4c93_run_9c37401733574214bc73f3e91e818bfb.py:512>) 使用不同变换路径，值得检查概率输出。这里只做静态风险提示，没有执行模型或确认因果。
3. **输入数据报告需要可信度检查。** insult 数据报告明确写 [Positive count: 0](</Users/shrinn81/Documents/Data Mining/PM Final Project/ML Agent/data/coverage/tasks/data_analysis/result/da_result_detecting-insults-in-social-commentary.txt:17>)；双方部分回答据此作假设，作者 case 020 甚至推断程序会崩溃。任务描述与已有高 AUC 评分使该报告的适用范围值得质疑，但现有材料不能确定报告错误的具体来源，也不能断言真实训练标签只有一类。
4. **部分配对分差非常小。** case 020 的 AUC 差 0.00005，case 043 差 0.00023，case 001 的 QWK 差 0.00366。不同任务指标单位不同，不混合比较绝对分差；这些例子提醒单次实测分数未必代表稳定排名。未更改平局阈值、标签或准确率，也没有因为分差小排除样本。
5. **不能笼统说模型只偏好复杂方案。** case 032/037 展示复杂方案被高估；case 084 则是简单方案被高估，而 case 054/064 中选简单方案成功。额外的粗代理统计：代码行数不同的 243 对中，模型选较长代码 133 对（54.73%），较长代码真实胜出 135 对（55.56%）。行数含重复代码、注释等，不能代表模型复杂度；此统计不足以支持系统性“越复杂越好”倾向。

## 结论与后续建议（未执行新实验）

这轮证明了可审计的离线比较流程能够运行；**尚未显示出明显超过简单位置基线的判别价值**。这里是证据强度判断，不是已经完成显著性检验或证明模型无效。样本内多个配对共享候选、任务，不能把 246 对都视为独立观测来作简单显著性结论。

下一步最值得查的是数据报告与代码约束是否被正确理解；如另做实验，可在独立诊断集比较位置交换一致性与输入报告可靠性。不要在这 246 对上反复调整提示后，仍将同一批当作未见测试集。当前仅完成用户要求的基线与离线差异分析，没有改 prompt、模型、标签或运行新付费实验。

## 各任务计数

所有数字为正确对数；双方都错列为配对数。

| 任务 | 样本数 | 固定 0 | 固定 1 | 本轮 | 作者 | 双方都错 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| aptos2019-blindness-detection | 10 | 7 | 3 | 6 | 6 | 4 |
| denoising-dirty-documents | 10 | 4 | 6 | 6 | 6 | 4 |
| detecting-insults-in-social-commentary | 10 | 4 | 6 | 8 | 5 | 2 |
| dog-breed-identification | 3 | 2 | 1 | 2 | 3 | 0 |
| google-quest-challenge | 10 | 5 | 5 | 5 | 8 | 2 |
| jigsaw-toxic-comment-classification-challenge | 10 | 5 | 5 | 2 | 2 | 8 |
| leaf-classification | 10 | 4 | 6 | 7 | 7 | 2 |
| learning-agency-lab-automated-essay-scoring-2 | 10 | 6 | 4 | 6 | 6 | 2 |
| lmsys-chatbot-arena | 10 | 7 | 3 | 7 | 7 | 2 |
| mlsp-2013-birds | 10 | 3 | 7 | 2 | 4 | 6 |
| new-york-city-taxi-fare-prediction | 10 | 6 | 4 | 4 | 5 | 5 |
| nomad2018-predict-transparent-conductors | 3 | 2 | 1 | 3 | 3 | 0 |
| petfinder-pawpularity-score | 10 | 6 | 4 | 7 | 5 | 3 |
| plant-pathology-2020-fgvc7 | 10 | 5 | 5 | 5 | 6 | 4 |
| predict-volcanic-eruptions-ingv-oe | 10 | 5 | 5 | 5 | 4 | 3 |
| random-acts-of-pizza | 10 | 5 | 5 | 6 | 6 | 3 |
| spooky-author-identification | 10 | 6 | 4 | 5 | 5 | 5 |
| stanford-covid-vaccine | 10 | 6 | 4 | 5 | 6 | 3 |
| statoil-iceberg-classifier-challenge | 10 | 5 | 5 | 3 | 4 | 4 |
| tabular-playground-series-dec-2021 | 10 | 6 | 4 | 4 | 3 | 6 |
| tensorflow-speech-recognition-challenge | 10 | 4 | 6 | 6 | 4 | 4 |
| tgs-salt-identification-challenge | 10 | 8 | 2 | 6 | 5 | 3 |
| the-icml-2013-whale-challenge-right-whale-redux | 10 | 4 | 6 | 4 | 2 | 5 |
| tweet-sentiment-extraction | 10 | 5 | 5 | 6 | 5 | 3 |
| us-patent-phrase-to-phrase-matching | 10 | 5 | 5 | 8 | 8 | 2 |
| ventilator-pressure-prediction | 10 | 6 | 4 | 8 | 5 | 1 |

复现分析：`python3 analyze_coverage.py`。数据来源：已有固定版本 coverage_manifest.json、coverage_retry_results.json、coverage_author_reference.json；完整案例证据位于本地 outputs/coverage-20261021/qualitative_review_evidence.json。
