**主线研究问题：**

在计算预算有限的情况下，ML Agent 如何更可靠、更高效地判断哪些候选方案值得实际运行？

# Inspiration and Research Question

暑假在 Industrial AI Engineering 实习中，我接触到模型从训练、封装到部署进业务系统的完整流程。由此我意识到，当算力和时间有限、候选方案又有多个时，需要决定先比较和验证哪些方案。LLM 可以根据任务、数据和代码做初步判断；但候选一多，逐一比较又会消耗大量调用，而每次的排序也未必稳定或正确。

于是我思考：能否设计一个 ML Agent，结合已有的方案判断和实验反馈，动态决定**下一步该比较哪些候选、验证哪个方案**，从而在固定预算内更高效地找到表现更好的方案？

## Literature Review and Possible Directions

本项目以发表于 ACL 2026 的 [ForeAgent](https://aclanthology.org/2026.acl-long.182/) 为研究起点。它在执行机器学习代码前，先利用 LLM 比较候选方案，再运行较有希望的方案，以减少不必要的执行。作者公开了[代码](https://github.com/zjunlp/predict-before-execute)和 [Preference Corpus](https://huggingface.co/datasets/zjunlp/PredictBeforeExecute)，使我可以尝试复现原方法、分析其局限，并在此基础上比较不同的改进方向。

ForeAgent 的系统与评测分别借助两个开源工作：它以 [AIDE](https://arxiv.org/abs/2502.13138) 的代码生成、执行与改进流程为基础，加入运行前筛选；使用 [MLE-bench](https://arxiv.org/abs/2410.07095) 的机器学习任务和评分方式检验 Agent 的最终表现。两者的实现也已公开：[AIDE 代码](https://github.com/WecoAI/aideml)、[MLE-bench 代码](https://github.com/openai/mle-bench)。

ForeAgent 的 Preference Corpus 收录了 AIDE 和 AutoMind 生成的候选代码及其真实运行结果，包含约 18,438 条两两比较记录，覆盖 26 个任务。这为检验候选判断与筛选方法提供了现成数据；但任务数量和领域覆盖有限，改进是否能推广到未见任务仍需验证。

### Improvement Directions to Discuss with the Instructor

**作者在论文中提出的后续方向：**

- **按需补充数据分析。** ForeAgent 会先生成数据报告，供 LLM 在运行代码前比较候选方案。但对图像、文本任务，仅靠报告中的基本信息可能不够。作者建议丰富报告内容；我的进一步想法是：Agent 先用基础报告判断，**只有难以选择时**，才调用工具补充信息，例如统计文本长度、查看类别分布或抽取图像样本。然后比较：这些额外信息是否让它选中实际表现更好的候选，以及提升是否值得工具调用的成本。这对应 Lec 13 的“调用工具—观察结果—更新决策”；与 Lec 14 的“按需获取证据”只是思路上的类比，不需要做 RAG。

- **改进比较与筛选流程。** ForeAgent 让 LLM 两两比较候选，并利用判断置信度筛选。作者建议探索其他推理和筛选策略。本项目可以测试：怎样提问能让比较更可靠？LLM 拿不准时，是再比较一次、保留两个候选，还是直接运行其中一个？什么时候应该停止比较？在相同 LLM 调用预算下，用候选的真实运行分数检验哪种流程选得更好。这对应 Lec 13 的推理提示和 Agent 根据判断结果决定下一步行动。

- **训练专门的 reward model。** ForeAgent 目前主要在推理时调用现成 LLM，作者将训练 reward model 留作后续方向。本项目可利用已有比较记录及运行结果训练一个代码质量判断器，检验它在未见任务上的准确率和相对 LLM 的调用成本。对应 Lec 13 的成对偏好数据与 reward model 训练；不必延伸到 PPO。

**我提出的可检验方向：**

- **提高判断稳定性。** 现有两两判断是否受代码呈现位置或比较顺序影响，在 ML 代码任务中尚需验证。本项目可交换 A/B 位置、重复部分比较，再设计汇总规则。检验判断冲突、最终选择和额外调用成本如何变化。[位置偏差研究](https://arxiv.org/abs/2306.05685)提供背景；对应 Lec 13 的偏好判断与模型评估。

- **全局排序（Pairwise Preference Learning）。** ForeAgent 用两两判断筛选要运行的候选；本项目可用 [Bradley–Terry](https://doi.org/10.2307/2334029) 汇总判断，必要时用 [Bayesian Bradley–Terry](https://arxiv.org/abs/1011.1761)估计不确定性。检验在相同调用次数下，是否更容易选中最佳候选、减少选错的损失。对应 Lec 13 的成对偏好比较；BT 是额外引入的统计排序方法。

- **主动选择比较对象。** ForeAgent 会比较候选，但未专门研究固定调用预算下该优先比较哪一对。本项目可根据已有判断选择下一对最有信息量的代码，检验相同调用次数下是否选得更准，或达到相同准确率时是否用更少调用。借鉴[主动排序研究](https://arxiv.org/abs/1606.08842)；对应 Lec 13 的工具调用成本，与 Lec 14 的按需获取证据是类比。

- **决定何时真正运行。** ForeAgent 筛选后运行选中的候选；本项目可让 Agent 在“再比较一次”和“现在执行”之间按不确定性与成本作决定。检验是否能在总时间或 GPU 预算内找到更高分的方案，而不只改善离线排名。对应 Lec 13 的 ReAct、工具调用与 Action–Observation 循环。

上述方向是备选研究问题，不预设任何方法一定优于 ForeAgent。希望与老师先确定一个主要方向，再将其余方向作为可选消融或后续扩展。

### Evaluation and Feasibility

第一阶段可用公开的 [Preference Corpus](https://huggingface.co/datasets/zjunlp/PredictBeforeExecute) 做离线评测：在相同候选集合与 LLM 调用预算下，比较 Top-1 选择准确率、选错最佳方案的损失和判断成本；若研究稳定性，再报告顺序交换后的结果变化。若方法与资源允许，再在少量 [MLE-bench](https://arxiv.org/abs/2410.07095) 任务上做端到端验证。离线效果不等于 Agent 最终效果，具体运行时间与 GPU 需求需在跑通基线后测量。

### 当前执行顺序（2026-11-07，用户确认）

当前优先复现并检查 ForeAgent baseline 的置信度门控与复赛停止机制：核对门槛、confidence 缺失/异常处理、pending 复赛、缓存复用、轮数上限、并列输出，以及比较尝试数与唯一反馈数。结合已有真实反馈与可控响应，区分固定原代码行为、离线适配条件和待验证的实时 Agent 行为。

“低置信度后优先比较新候选对、无新证据时停止、按固定判断预算选择”的改进记录为备选方向，实施顺序放在基线复现与机制检查完成之后；后续根据检查结果再确定是否开展 B1（无新证据停止）和 B2（未比较优先）实验。现有缓存方向修复与上述新策略分别记录。

已有机制归因证据见 [低置信度复赛核验](experiments/tournament_replay_attribution.md)；目前约 96% 的轮数安全退出率仅对应已运行的离线场景。

进度补记（2026-11-07）：门控边界、异常响应、pending/停止、显示名次和原 Agent 执行路由的本地验证已补齐，并核对了已有真实判断的置信度分层及原生批处理回放一致性，见 [机制验收报告](experiments/foreagent_mechanism_audit.md)。实时 Agent prompt 下的置信度分布与完整 Agent 效果仍为后续验证范围；新比较/停止策略继续保留为备选。

