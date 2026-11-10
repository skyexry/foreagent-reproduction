# ML Agent Annotated Bibliography

更新日期：2026-10-21。收录当前 [Proposal](Proposal.md) 中的全部外部参考链接，以及老师推荐的 DAGent。论文与配套代码合并记录，数据集单列；保存的是书目信息、来源链接与阅读注释，不代表已下载全文或完成复现。

根据本次 pitch 后老师的建议，项目顺序为：**复现 ForeAgent → 优化 pairwise comparison 与 ranking → 再考虑训练 reward model**。下文“项目用途”是拟议用途，不代表已有实验结果。

## 核心方法与老师推荐阅读

### 1. ForeAgent

**书目信息：** Zheng, Jingsheng; Zhang, Jintian; Luo, Yujie; Mao, Yuren; Gao, Yunjun; Du, Lun; Chen, Huajun; Zhang, Ningyu. (2026). *Can We Predict Before Executing Machine Learning Agents?* Proceedings of ACL 2026, Volume 1: Long Papers, pp. 3941–3974.

**来源：** [ACL 论文页面](https://aclanthology.org/2026.acl-long.182/)；[官方代码](https://github.com/zjunlp/predict-before-execute)；配套数据见第 3 条。

**内容注释：** 研究在运行 ML 代码前，利用任务、数据分析报告和候选方案预测两者的相对表现。作者提出 Data-centric Solution Preference 任务，构建 18,438 条成对比较，并将预测判断用于 ForeAgent 的 Predict-then-Verify 流程。它把比较器的离线判断与 Agent 的实际执行选择连接起来。

**项目用途：** 首要复现对象。先对齐比较输入、提示词、输出解析、置信度使用方式与真实标签，再研究比较和排序的改进。

**评价与边界：** 成对判断准确率、选中最佳候选的概率和端到端 Agent 表现是不同指标。论文报告的性能不能作为本项目结果；更换模型、推理参数或样本范围时，应明确属于何种复现设置。

**阅读状态：** 已核对 ACL 书目信息和摘要；具体实验口径需在复现时按正文与代码核对。

### 2. DAGent

**书目信息：** Liu, Hanwen; Sun, Yuanfu; Tan, Qiaoyu. (2026). *DAGent: Evaluate-then-Grow Planning for Deep Research Agents.* arXiv:2609.39154v1，2026-09-30。

**来源：** [arXiv 页面](https://arxiv.org/abs/2609.39154)；[老师提供的 PDF](https://arxiv.org/pdf/2609.39154)；[论文列出的代码入口](https://github.com/hanwenliu6825/DAGent)。

**内容注释：** 面向 deep research，依据已完成子任务的结果、置信度及不确定性逐批扩展有向无环任务图。节点默认传播简短 QueryDoc，必要时召回完整轨迹。DAGRPO 利用记录的依赖结构分配执行器奖励，并惩罚不符合结构要求的规划。重点阅读 §3.1 的评估与扩展循环、§3.2 的奖励构造，以及 §4 的比较设计。

**项目用途：** 老师推荐的思路参考。可借鉴“先评价已有证据，再决定下一步行动”，探索根据当前比较结果选择下一对候选、追加验证或停止比较。

**评价与边界：** 这种迁移是本项目设想，论文没有直接验证 ML 候选代码排序。DAGent 的边表示任务依赖；偏好图的边表示胜负，可能存在循环。DAGRPO 是策略强化学习方法，也不等同于训练独立的候选代码 reward model。

**阅读状态：** 已阅读摘要及 §3.1–3.2 方法部分；代码入口来自论文，尚未检查实现或复现。

## 数据与评测基础

### 3. PredictBeforeExecute Preference Corpus

**资源信息：** ZJUNLP. *PredictBeforeExecute* [数据集与配套实验资源]。与第 1 条论文配套；访问日期：2026-10-21。

**来源：** [Hugging Face 数据集与数据卡](https://huggingface.co/datasets/zjunlp/PredictBeforeExecute)。

**内容注释：** 数据卡列出完整候选池 `solutions_all/`、每任务最多 50 个候选的主实验子集 `solutions_subset_50/`，以及每任务最多 15 个候选的分析子集 `solutions_subset_15/`。另包含 Agent 运行输出、分析材料和任务资源。页面展示约 18.4k 条记录；论文摘要给出的精确成对比较数为 18,438。

**项目用途：** 第一阶段离线比较的主要数据来源；若候选 ID、任务归属和实际分数可完整关联，也可用于候选集合层面的 ranking 评测，后续可考虑构建 reward model 训练数据。

**评价与边界：** 比较记录数不等于独立候选数或任务数。训练与测试宜按任务隔离，避免相同候选通过不同配对进入两侧。用于评价的运行分数不能泄漏到比较器输入。Proposal 中“26 个任务”及候选生成来源仍需对下载版本逐项核对。

**阅读状态：** 已核对数据卡；本条不构成完整数据审计，实际文件、去重与候选集合可还原性需另行检查。

### 4. MLE-bench

**书目信息：** Chan, Jun Shern, et al. (2024; arXiv v6 revised 2025). *MLE-bench: Evaluating Machine Learning Agents on Machine Learning Engineering.* arXiv:2410.07095。

**来源：** [论文](https://arxiv.org/abs/2410.07095)；[官方 benchmark 代码](https://github.com/openai/mle-bench)。

**内容注释：** 基于 75 个 Kaggle 竞赛构建机器学习工程任务，评价 Agent 在数据处理、模型训练和实验执行等环节的能力，并利用公开排行榜建立人类表现参照。

**项目用途：** 后续少量任务端到端验证的评测基础，用来检查离线比较或排序改进能否转化为实际方案质量提升。

**评价与边界：** 完整 benchmark 的 75 个任务不等于 ForeAgent 使用的任务子集，也不等于本项目实际运行范围。执行成本、数据准备、评分方向及验证集与测试集用途都需固定；不能从离线偏好准确率推断获奖率。

**阅读状态：** 已核对论文摘要、版本信息和官方仓库入口；具体运行协议待使用时核对。

### 5. AIDE

**书目信息：** Jiang, Zhengyao; Schmidt, Dominik; Srikanth, Dhruv; Xu, Dixing; Kaplan, Ian; Jacenko, Deniss; Wu, Yuxiang. (2025). *AIDE: AI-Driven Exploration in the Space of Code.* arXiv:2502.13138。

**来源：** [论文](https://arxiv.org/abs/2502.13138)；[官方代码](https://github.com/WecoAI/aideml)。

**内容注释：** 将机器学习工程表述为代码空间中的优化，把试错组织为树搜索，通过复用和改进有希望的候选方案推进实验。

**项目用途：** 理解候选代码如何产生、执行反馈怎样进入搜索，以及运行前比较器可以插入流程的哪个位置。它是 Agent 框架背景，不是评测数据集。

**评价与边界：** 原始 AIDE 与 ForeAgent 使用的改造版本不能自动视为同一实现。若做端到端对照，应固定候选生成、执行资源和停止条件，避免把其他流程差异归因于比较器。

**阅读状态：** 已核对摘要与代码入口；尚未逐项对照 ForeAgent 与 AIDE 实现。

## Pairwise comparison 与 ranking 方法

### 6. LLM judge 的位置偏差与可靠性

**书目信息：** Zheng, Lianmin, et al. (2023). *Judging LLM-as-a-Judge with MT-Bench and Chatbot Arena.* NeurIPS 2023 Datasets and Benchmarks Track. arXiv:2306.05685。

**来源：** [论文](https://arxiv.org/abs/2306.05685)。

**内容注释：** 研究 LLM 作为回答质量评审者的能力及局限，包括位置偏差、冗长偏差、自我偏好和推理限制，并利用 MT-Bench 与 Chatbot Arena 考察评审结果与人类偏好的一致性。

**项目用途：** 为交换候选 A/B 顺序、重复比较及记录冲突提供方法背景。MT-Bench 与 Chatbot Arena 在此是该论文的评测背景，不是本项目已选用的 ML 工程 benchmark。

**评价与边界：** 对话回答的人类偏好与 ML 代码真实运行表现不同。该论文不能证明本项目模型已经存在相同幅度的偏差；需在代码比较数据上实际测量。

**阅读状态：** 已核对摘要与会议信息；具体偏差控制实验待定向精读。

### 7. Bradley–Terry 成对比较模型

**书目信息：** Bradley, Ralph Allan; Terry, Milton E. (1952). *Rank Analysis of Incomplete Block Designs: I. The Method of Paired Comparisons.* Biometrika, 39(3–4), 324–345。

**来源：** [Proposal 原 DOI](https://doi.org/10.2307/2334029)；[出版社页面](https://academic.oup.com/biomet/article-abstract/39/3-4/324/326091)；[出版社 DOI](https://doi.org/10.1093/biomet/39.3-4.324)。

**内容注释：** 成对比较建模的经典来源。标准 Bradley–Terry 模型以候选的相对强度描述两者胜负概率，用多次成对观测估计整体强度与次序；模型概述也可参照第 8 条的公开摘要。

**项目用途：** 作为汇总 LLM 两两判断的统计排序基线，检验其最终候选选择是否优于简单胜场汇总或原筛选流程。

**评价与边界：** 潜在强度排序是一项模型假设。循环偏好、稀疏或不连通的比较图、全胜候选都可能影响估计；拟合出的排名不自动等于真实执行分数排名。

**阅读状态：** 已核对出版社书目信息；原 DOI 跳转至 JSTOR 后无法读取全文，尚未精读原文。

### 8. Bayesian Bradley–Terry 推断

**书目信息：** Caron, François; Doucet, Arnaud. (2010). *Efficient Bayesian Inference for Generalized Bradley-Terry Models.* arXiv:1011.1761v1。此处按 Proposal 链接的 arXiv 版本著录。

**来源：** [论文](https://arxiv.org/abs/1011.1761)。

**内容注释：** 利用潜变量解释广义 Bradley–Terry 模型的估计方法，并构造用于贝叶斯推断的 Gibbs 采样算法。

**项目用途：** 在基础排序跑通后，考虑用后验分布描述候选强度的不确定性，为追加比较或停止比较提供依据。

**评价与边界：** 后验不确定性依赖模型、先验与观测假设，不等于 LLM 自报置信度。该文提供推断工具，并未直接提出本项目的主动比较策略；是否值得增加推断复杂度需要实验判断。

**阅读状态：** 已核对 arXiv 元数据与摘要；采样细节和适用假设待精读。

### 9. Active Ranking

**书目信息：** Heckel, Reinhard; Shah, Nihar B.; Ramchandran, Kannan; Wainwright, Martin J. (2016). *Active Ranking from Pairwise Comparisons and when Parametric Assumptions Don't Help.* arXiv:1606.08842v2。

**来源：** [论文](https://arxiv.org/abs/1606.08842)。

**内容注释：** 研究噪声成对比较下的序贯排序，包括 top-k 识别和完整排序。依据已获得的胜负观测与置信区间，决定继续比较还是停止，并分析比较次数的理论界限。

**项目用途：** 为“固定预算下下一步比较哪一对”提供理论背景；可启发基于现有证据分配比较预算的实验。

**评价与边界：** 论文排序目标基于候选击败随机对手的概率，与真实 ML 分数排名不必一致。LLM 重复判断也不一定满足所需的随机观测假设，因此不能直接套用其理论保证。

**阅读状态：** 已核对摘要与版本；算法、假设和定理条件待精读后再决定采用方式。

## Proposal 中尚未给出独立来源的名称

- **AutoMind：** Proposal 将其列为候选代码生成来源之一，但未提供论文或仓库链接。暂不猜测对应文献；后续从 ForeAgent 正文、参考文献和数据说明中确认。
- **ReAct：** Proposal 将其作为行动与观察循环的背景概念，但未给出独立引用。本次保留该引用缺口，未另行扩展文献范围。
- **Lec 13 与 Lec 14：** 属于课程材料关联，缺少课程标题、讲义版本和文件入口，暂不补造书目信息。
- **Reward model：** 当前是后续研究方向，Proposal 未指定专门训练方法论文。DAGent 的 DAGRPO 不作为这一方向的替代引用。

## 阅读顺序

先读 ForeAgent 并核对 Preference Corpus；结合 AIDE 和 MLE-bench 理解生成、执行与评分流程。接着阅读 LLM judge 偏差研究、Bradley–Terry 和 Active Ranking，分别支撑比较可靠性、判断汇总和比较预算分配。DAGent 作为动态决策参考穿插阅读；Bayesian Bradley–Terry 在确实需要排序不确定性时深入。
