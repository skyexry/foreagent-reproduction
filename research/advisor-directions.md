# 给老师的答复：ForeCritic、reward 与离线排序

依据 2026-11-10 本轮用户转述的老师问题整理。此前 GitHub 的[交接页](https://github.com/skyexry/foreagent-reproduction/blob/d8baa97b8adef4f2a6b798f15404a73cc0e0d844/research/README.md)把 reward、teacher、GRPO、embedding、skills 汇成五类备选，把真实前两名的诊断列成“待开展”，首页却优先安排真实日志的 GPU 补跑。执行记忆是此前用户同意试的一个实验。跨任务 CodeT5、邻居数、融合权重及以下先导门槛均由本项目选择，未归为老师指定的方法。

| 老师提出的问题 | 答复及证据 |
|---|---|
| ForeCritic 训练 reward model 还是 critic？ | 论文称其为 World Reward Model。就训练行为而言，它是成对偏好模型。输入同任务的两个程序，用谁实际跑得更好作为标签，以交叉熵训练 LoRA 和选择头，预测哪份会赢。输出是相对胜率。传统 actor–critic 的 value critic 则估计策略从某状态出发的未来回报。[ForeCritic §4.2](https://arxiv.org/html/2610.38439v1#S4) |
| Outcome reward、process reward、process-based GRPO？ | ForeCritic 的监督来自程序的最终执行结果。它的偏好训练使用监督学习。GRPO 是另外一种策略优化算法，既能接最终结果奖励，也能接步骤奖励；选择 GRPO 本身不能决定奖励粒度。[ForeCritic](https://arxiv.org/html/2610.38439v1) · [DeepSeekMath §4.1](https://arxiv.org/html/2402.03300v3#S4) |
| Token、action、reasoning 能否各给 reward？还有哪些定义？ | 可以设计不同目标。当前 corpus 直接支持整份程序的输赢、任务内相对名次和实际分差。比较/执行等 action 可研究终局选择损失与实际成本。要判断哪一步推理值得奖励，还需要可核实的步骤评分、过程标注或受控干预。将同一个终局分广播给所有 token，监督来源仍是 outcome。已有日志含理由文本，两两比较的 ground truth 不能自动标注理由中每一步。以前已测执行分差、终局代价对**训练损失的加权**，其作用与训练过程奖励模型分别评价。[原训练协议](../experiments/trajectory-weighted-judge-v1/protocol.json) |
| Stronger teacher model？ | 可作为生成判断、理由或蒸馏标签的 teacher。先在相同 corpus 代码对上对照执行胜者，测准确率、A/B 换位稳定性和成本，然后决定是否蒸馏。现有多裁判归档可做基线；更强 teacher 的受控蒸馏仍待做。 |
| 能不能去掉 critic？Relative group advantage？ | 若是策略训练中的 value critic，GRPO 用同一提示多次采样的组内回报估计相对 advantage，仍需定义 reward 和更新哪个策略。若指执行前的成对裁判，可以直接用检索排名出结果。这轮实测纯跨任务检索，额外裁判读取数为零，选优损失 0.3338，原 DeepSeek C0 为 0.2642。该对照检验了后一个含义；GRPO 策略训练仍待做。[GRPO 原文](https://arxiv.org/html/2402.03300v3#S4) · [离线实测](../experiments/embedding-rerank-v1/run-001/summary.json) |
| Embedding reranker、embedding based ranking system、retrieval/ranking？ | 已实现并测了两种用法。同一版本的 CodeT5 为代码编码，从已评分参考程序检索相似样例，按样例在各自任务的相对名次预测候选表现。① 只用检索给所有候选排序。② 用检索名次和 C0 完整排名各占一半重排全部候选。所有目标任务的分数均在排名后用于评价。主要测试按任务留出。[实现与对照](../experiments/embedding-rerank-v1/README.md) |
| Skills for DeepSeek Thinking used for comparison？ | 可把 ML 工程比较经验写成明确的提示步骤，例如找出 A、B 实际改动的训练步骤，引用代码证据，按任务指标判断其可能影响，再给出胜者。用同一 DeepSeek、相同代码对、两种顺序及相同生成预算对照原提示，用 corpus 执行结果评分。改提示会产生新的判断；以往对旧理由做破同分是另一项已完成实验。Skills 对照仍待做。[已有理由实验](../experiments/rationale-tiebreak-v1/README.md) |
| Corpus 任务覆盖少，会有 bias、泛化问题吗？ | 有这个风险。18,438 对共享 895 份原始代码，来自 26 个任务。此次清掉非有限及重复内容后使用 877 份，按任务等权、检索时留出整个目标任务，并排除相同语法树。26 个任务早已用于开发，结论覆盖这批任务。固定方案之后，新的任务和新的代码来源才提供外部泛化证据。[语料来源](https://huggingface.co/datasets/zjunlp/PredictBeforeExecute) · [全部逐任务结果](../experiments/embedding-rerank-v1/run-001/per_task.json) |
| 真实 Top‑1、Top‑2 有没有排到第 4 名以后？值得做吗？ | 有。按实际 C0 预算，24 个有足够候选的任务、846 场、423 个不同池，任务等权并在并列组内均匀分配位置。真实第一/第二在第 4 名及以后分别是 50.3% / 66.8%（DeepSeek）；两者同时在前三之外为 31.2%。按严格“第 5 名起”是 39.1% / 54.7%。即使在前三里总能挑到最好，仍损失池内分数跨度的 8.46%。排序有实质空间。[诊断](../experiments/embedding-rerank-v1/README.md) |
| 总结失败原因，下轮如何避免？ | 旧线性裁判的终局加权仅改变 28/850 场选择，14 场变好、14 场变差；旧理由规则在 DeepSeek 仅触发 1/850 场。此次跨任务检索改变了排序，但 DeepSeek 使用真实邻居成绩和打乱成绩的损失相差约 0.0001。由此可确认的是该表示和规则下的**成绩信号很弱**；是否由于截断、任务差异或相似度定义，仍需逐项辨别。下轮优先在相同候选、相同可见标签预算上对照真实分数与打乱分数、同任务参考与跨任务参考，并保留逐任务结果和成本。只有提取到可复现的增量，才投入更贵的 teacher、训练或真实运行。[历史训练结果](../experiments/trajectory-weighted-judge-v1/README.md) · [本轮结果](../experiments/embedding-rerank-v1/README.md) |

同任务补充对照已经实跑。DeepSeek 在原 C0、随机挑同任务历史、裁判挑同任务历史三种条件下的损失依次为 0.2642、0.2322、0.2250。GPT 为 0.2725、0.2339、0.2181。这个方案允许读取少量已揭开的本任务参考分。它最接近“在作者 corpus 上用 retrieval 和 ranking 改选”的建议，也是目前更值得复核的版本。多轮搜索中的自我强化、同源代码和未见任务的泛化仍要分别检验。[实验、数据范围与区间](../experiments/embedding-rerank-v1/README.md)
