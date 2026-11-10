# 文献机制、最接近的工作与候选取舍

**直接竞争集中在三个不同层面。** ForeCritic 已用真实执行数据训练程序裁判；PRP 研究已在缓存的比较矩阵上测试主动选边；贝叶斯 top-k 研究已围绕选中集合设计下一问。单独提出这些做法，贡献都很有限。本项目有机会给出的是同一决策点上「追加哪条反馈会改变多少执行损失」的实证解释，以及在限定条件下可迁移的比较分配规则。

## 检索和取证范围

2026-11-08 按模块开放检索。先回读本项目的[已有审计](../../reports/reproducibility-audit-20261108/README.md)、[ForeCritic 阅读账本](../../reports/reproducibility-audit-20261108/evidence/forecritic-reading.json)和[历史书目](../../Annotated_Bibliography.md)，再从 ForeAgent 正式版、近邻引用及独立关键词查找。核对来源为 ACL Anthology（含 Findings）、AAAI、PMLR/ICML/AISTATS、JMLR、SIAM、arXiv 版本历史、作者论文/代码与项目固定提交。定向检索优先覆盖三个问题：谁能比较相同的对象、谁已做同样的分配、谁用同样的终局指标。以下为与设计有直接关系的代表作；检索的覆盖程度适合做研究立项，优先权判断限定于核实的工作。

| 查询族及实际使用的代表词 | 纳入标准 | 命中并影响决定的工作 |
|---|---|---|
| `ForeAgent ForeCritic code execution candidate selection`、`code selection by pairwise queries`、论文全名、GitHub / 模型权重 | 对象为程序；检查奖励来自逻辑判断、局部测试还是整套训练执行 | ForeAgent、ForeCritic、ExPairT-LLM、PairJudge RM。区分预测一个 pair、询问可执行反例与从池中挑一个候选 |
| `active LLM ranking pairwise selection top-k budget PRP`、`sparse comparison graph LLM aggregation`、`active evaluation NLG few pairwise comparisons` | 比较次数有成本，关注稀疏图上的排名、top-k 或 top-1 | PRP-Graph、PoE、Active Evaluation、Active Learners、Xu 等两个版本。由“提出主动选边”收窄为同一状态的效用归因 |
| `dueling bandits top-1 stopping`、`uniform opponent Borda active ranking`、`fixed budget pairwise knowledge gradient select best` | 检查观测生成假设、停止目标与最终损失 | RUCB、Heckel 等、Goldberger & Rudi、Frazier 等。只移植可观察的操作，逐项识别失效的理论前提 |
| `pairwise LLM judge position bias confidence order consistency`、`bias-aware Bayesian active top-k` | 是否做真正换位、是否有执行标签或可信锚点、偏差能否识别 | Wang 等、Xu 等 v2、ForeCritic 附录 D.3。将位置、校准与改选效应分列 |
| `ICML 2026 reviewer instructions`、`ACL Rolling Review review form` | 按主张重要性判断证据强度、对照、可复现性和局限 | 用于[方案卡的审稿自查](proposal.md)。[ICML](https://icml.cc/Conferences/2026/ReviewerInstructions) · [ARR](https://aclrollingreview.org/reviewform) |

## ForeCritic 已覆盖的内容

Lee、Yang、Liu、Liu，*Predict the Reward, Not the World: World Reward Models for ML Agents*，arXiv:2610.38439v1（2026-10-28）。以下为作者报告；此次重读正文及附录 A–E，并对照项目已有材料。正文链接指向的是 Kev 初始化模型；本次在作者文、GitHub/模型发布关键词与既有盘点中，尚待定位专属训练/集成提交、checkpoint、逐条 split IDs 和逐次 trace。研究立项可用论文协议判断重合范围，精确复现训练则依赖这些材料。[作者全文](https://arxiv.org/html/2610.38439v1) · [现有材料索引](../../reports/reproducibility-audit-20261108/evidence/forecritic-reading.json)

| 原文 | 机制／结果 | 对我们的影响 |
|---|---|---|
| §2 Def.2.1，§3，附录 A–B | 已定义选择价值、准确率与 regret；给定同样输入，模拟输出受原信息集约束，有限模型仍可能因表征、训练目标而异。理想化筛选讨论依赖分布假设 | “按最终效用评分”已有定义。此处针对冻结历史图上同一前缀增加一条反馈的已实现效用，用原执行标签判方向；它区别于再读同一个缓存条目 |
| §4.1–4.2、附录 C、表1 | Kev-9B 起步，训练 LoRA/指针头，输入任务、报告、两份代码，用执行胜者交叉熵。5,000 训练、250 开发、250 校准、500 内测、12,438 最终；同一程序能跨 pair，26任务全进训练。最终 micro 79.44%，同输入 Kev 54.53%；任务宏72.69%；两份程序均未见的501对为71.46% | 已有直接的学习裁判及程序未见子组。一套新裁判需要新任务协议、独立程序分组与等监督/预算对照。主结果的单位与我们单池最终执行损失不同 |
| §5.2–5.4，图4–5、9，附录 D | 去掉报告准确率78.55%；校准后 ECE .016。阈值.7保留72.2%判断，命中86.8%。外部候选来自10个MLE-Dojo任务、48程序、91对/182次顺序判断，其中1任务与训练重合；70.3% vs DeepSeek-V4.1-Flash 63.7%，任务重采样差异跨零；22/91对换位后改选 | 已检验新候选迁移、位置和概率可靠性。其概率来自专门的输出头；v1 自报 confidence 的含义、校准和成本另测。论文图4的61.5%是引自 ForeAgent 全库，与79.44%的 test split 不同 |
| §4.3、§5.5 表2、附录 E 算法2 | AIDE/ML-Master以相对 incumbent 的预测支持树搜索；ForeAgent 接入 .7 gate、累计 soft scores、该轮无人淘汰就停。10个任务、每任务/配置一次；共同生成模型 DeepSeek-V4.1-Flash、T=.5、每任务上限6h。ForeAgent 原裁判→ForeCritic 平均墙钟 4,111→884秒。训练约33.4 A800 GPU-h；不同方向/尺度的 native metric 均值要结合分任务图11读 | 已覆盖冠军挑战、early break 和端到端成本。其算法2与 ForeAgent 的 pending 复赛及 v1 胜率汇总都有区别；将4.7×移植到本项目需要新的系统对照 |
| §7 | 作者要求新任务/领域、一次排多候选、在线继续学习、同规模训练目标/接口比较，以及固定预算最终奖励等 | **“固定预算看最终奖励”本身已有明确议程。** 本项目先给出可核对的条件比较；如后续换裁判，只在匹配的分配、汇总与执行接口上解释增量 |

## 路线 B｜机制在当前接口能做什么

| 原始工作及精读位置 | 怎样解决问题，依赖哪些假设 | 借用、对照或放弃的理由 |
|---|---|---|
| Frazier、Powell、Dayanik (2008)，*A Knowledge-Gradient Policy for Sequential Information Collection*，§§2–4。[原文](https://optimallearning.princeton.edu/Papers/FrazierPowellDayanik_KnowledgeGradientSICON.pdf) | 按新增一次观测所带来的预期终局价值分配预算。原问题取独立正态总体与已知公共方差，有明确的信念更新 | 借用「下一条信息相对立即停止的终局价值」作为可测对象。本项目计算冻结结果实现后的损失差；没有概率后验或最优性保证 |
| Heckel、Simchowitz、Ramchandran、Wainwright (AISTATS 2018)，*Approximate Ranking from Pairwise Comparisons*，式1、§2、主动算法。另参 Shah & Wainwright 的计数对照。[主动排名](https://proceedings.mlr.press/v84/heckel18a/heckel18a.pdf) · [JMLR 原文](https://jmlr.org/papers/volume18/16-206/16-206.pdf) | 相对均匀对手的胜率给出 Borda 强度；根据排名所需精度分配比较。其成败观测、总体和随机采样模型明确 | 为给定首选抽均匀未问对手提供依据。已经观察过的边由历史路径决定；还有弃权，胜率、Borda 排名、执行效用三者可能不同。均匀未问对手只是对照 |
| Zoghi 等 (ICML 2014)，*Relative Upper Confidence Bound for the K-Armed Dueling Bandit Problem*，§4 算法1；Goldberger & Rudi (ICML 2026)，*Optimal Top-k Identification from Pairwise Comparisons*，§§3–6、5.4–5.5 与证明附录。[RUCB](https://proceedings.mlr.press/v32/zoghi14.pdf) · [ICML 2026](https://proceedings.mlr.press/v306/goldberger26a.html) · [算法与停止规则](https://arxiv.org/html/2607.08979v1) | RUCB 选可能的冠军及其上置信界对手，关注累计 dueling regret；后者在潜在效用模型中跟踪最有信息的比较，达到固定置信度才停，目标为最小期望样本数 | 借用「先选焦点，再选对手」的拆分。此处同边只有一次历史判断；在固定焦点、仅许未问边时，朴素 RUCB 的逐对初始界相同。移植 δ-correct 保证需要可重复的新抽样与相应证据模型。直接强对照为同焦点挑战当前排名最高的可问对手 |
| Mohankumar & Khapra (ACL 2022)，*Active Evaluation: Efficient NLG Evaluation with Few Pairwise Comparisons*，dueling bandit 方法、图2–4、实验及附录。[全文](https://aclanthology.org/2022.acl-long.600.pdf) | 用 dueling bandits 选要比较的 NLG 系统，累积不同文本的人评或代理评价以识别排名靠前系统；与均匀探索比较标注量 | 已有预算驱动的 top-1 评价。其动作可代表新标注，人类总体偏好定义结局；本项目需检查冻结裁判赢家与独立执行结果的错位 |
| Liusie 等 (EMNLP 2024)，*Efficient LLM Comparative Assessment: A Product of Experts Framework for Pairwise Comparisons*，§3.6、表2–3、图1及附录；Luo 等 (ACL 2024)，*PRP-Graph*，算法1、图汇总。[PoE](https://aclanthology.org/2024.emnlp-main.389.pdf) · [PRP-Graph](https://aclanthology.org/2024.acl-long.313.pdf) | PoE 使比较成为分差的概率约束，Gaussian 形式导出稀疏比较的贪婪选取，并分开对照不同汇总；PRP-Graph 将文本对比较形成图，结合检索初始分数迭代聚合 | 「固定同一图改汇总」有明确近邻。v1只有胜者/自报信心且冻结汇总、无 BM25 先验；将来若固定证据后确见系统性排名失配，可登记 v2 再对比 |
| Figueiredo Paschmann 等 (Findings EMNLP 2026)，*Active Learners as Efficient PRP Rerankers*，§§3–5、表1–3、附录预算曲线。[正式版](https://aclanthology.org/2026.findings-emnlp.1216.pdf) | 在 TREC/BEIR 检索列表上用主动排序、PAC、排序算法和 PRP-Graph 比较调用数与 NDCG@10；所有方法/预算/种子从预计算的裁判矩阵回放。顺序随机和双向判断是不同 oracle | **共享冻结矩阵回放已有明确先例。** 稀疏暖启动后性能随预算变化，说明首步与全程应分开测。该协议有检索先验、文档相关性和真实双向判断；本项目比较的是 ML 程序执行损失与弃权代价 |
| Xu、Zeng、Paisley、Zhao (2026)，arXiv:2607.02104。v1 *Ask the Right Comparison* §4、表3；v2 *When Can You Debias an LLM Judge? Identifiability Limits, a Test, and Designs for Top-k Ranking*，可识别性分析、表3、附录 A 表5。[v1](https://arxiv.org/html/2607.02104v1) · [v2](https://arxiv.org/html/2607.02104v2) | v1 直接面向 top-k 成员不确定性选边。7月18日修订将重点放在同一项目的偏差协变量与潜在质量混淆；可信标签作门控、配对呈现恢复识别，并保留 Thompson、LUCB、全局不确定性等对照 | 最接近以决策为中心的主动采样。我们的 TV 只测假设两种有效胜负使首选改变多少，缺概率及效用；本文选的焦点是当前首选；该文的 trusted anchors 自带可信真值。识别位置效应需真实换序，识别项目层偏差还需配对呈现或额外约束 |
| Wang 等 (ACL 2024)，*Large Language Models are not Fair Evaluators*，位置交换与 balanced position calibration 实验。[原文](https://aclanthology.org/2024.acl-long.511.pdf) | 比较同样回答在两种真实呈现顺序下的判断，研究位置偏差及纠正开销 | ForeAgent 构造时平衡正确位置是有意义的控制。缓存的反向查询只重映射同一胜者；检验位置要另采两次实际判断、固定其他条件 |
| Liu 等，*PairJudge RM: Perform Best-of-N Sampling with Knockout Tournament*，§5 BoN 对照、Limitation 及附录 F；Yuviler & Drachsler-Cohen (AAAI 2026)，*ExPairT-LLM*，图1、表1、query 消融与 Limitations。[PairJudge 原文](https://arxiv.org/html/2501.13007v2) · [ExPairT 原文](https://ddana.net.technion.ac.il/files/2025/11/expairt.pdf) | 前者训练成对奖励模型，通过淘汰赛做 best-of-N；后者对无状态程序问「输出哪个更合适／两程序是否等价」，用可执行的区分输入验证反例，再按比较选择程序 | 训练裁判＋淘汰赛和“对代码作主动询问”均已有直接实例。ExPairT 有新输入和程序输出作为可验证信息，v1 的 ML 候选只有固定对局；迁移需要独立可执行探针与新评价 |

## 胜者预测训练与 ForeCritic 的边界

等权学习执行胜者已有 ForeCritic §4.2 式(6)。针对 C0，候选组合用 LOLS 算法1的单步动作分叉和后续回放生成终局代价，再借用 cost-sensitive filter tree 算法2的重要性加权二分类。原有执行分差加权为必要对照。训练目标的变化、可能反例及证伪条件见[修订方案](../../experiments/selection-frontier-02/优先改动.md)。[LOLS 原文](https://proceedings.mlr.press/v37/changb15.pdf#page=3) · [Filter tree 原文](https://hunch.net/~beygel/tournament.pdf)

## 从候选到优先级

| 候选 | 最能推翻它的检查 | 当前取舍 |
|---|---|---|
| 同一前缀后衡量下一问的净执行效用；若有信号，再围绕首选随机挑战 | 共用前缀、一步读取、同汇总、任务配对；对照就停、全边随机、同首选不同对手 | **比较分配模块内已就绪的诊断**。历史轨迹已存在，可先查错改带来的损失，避免为了优化一个弱点估计而反复调参 |
| 基于置信区间的早停 | 在多个固定前缀测等成本质量曲线，另需概率模型与可靠性支持才能声称控制错误率 | 作为转向条件保留。就停先作参照；等效或安全停止需要预定容忍界及相应区间证据 |
| BT/PoE/图强度校正 | 对同样已揭示的边只换汇总；再做分配×汇总交叉对照 | 有理论动机，受冻结 scorer 约束。当前提出版本门槛，待证据支持后单立实验 |
| 训练裁判、双序投票、多裁判、改温度或提示 | 同程序和真实独立重复，训练/校准/确认隔离；匹配同一查询与推理总成本 | 与 ForeCritic、位置校准已有直接重合。当前保存反馈无法识别这些干预，先保留 C0 |
| 多模态报告、执行探针、改变 m/k 或生成器 | 共同候选、相同执行机会、独立评分与墙钟/费用预算 | 可能改善实际 Agent，但改变信息或生成总体。方法确定后再设计确认与在线验证 |

**该方案的选择依据。** 一条补问的条件价值可以用已有轨迹检验。项目层面的候选生成、裁判、汇总与执行方向见[跨模块比较](README.md)。若它经常带来净损失，研究早停有意义；若裁判在被问到的边上有信号、固定汇总却反复把正确反馈变成更差的首选，则值得单独比较汇总器。如果已有材料只支持 C0 的保守做法，发布一个能复现这种适用边界的负结果也有实证价值。必要前提与判读门槛见[方案卡](proposal.md)。

## 本轮复核分工

| 实际模型与推理强度 | 只读任务与验收 |
|---|---|
| GPT-6 Luna，medium，1 个子任务 | 检索候选、题名、版本、直接近邻和原始链接；将版本与证据缺口交主审复核 |
| GPT-6.1 Sol，high，2 个独立子任务 | 一项逐页核对 ForeAgent 正文、附录、预印本和固定源码，另一项核对 host 调用链、先导统计、池与轨迹；分别交付可定位的证据 |
| GPT-6 Astra，high，1 个独立复核子任务 | 针对同前缀设计查找归因漏洞。复核促成同焦点对照、强对手参照，及区间宽时的结束条件 |
| 主代理 GPT-6 Astra，xhigh | 主审读正式 PDF、两页 checklist、ForeCritic 方法/评估、近期竞品的修订版，核对 Git blob、保护状态和保存轨迹，裁定冲突并整合文档。近邻从 Xu v1 更新至 v2，同时按 Findings 正式版校正 PRP 研究的实际回放协议 |

阅读技能仅作取材辅助。主要判断按原始材料、固定文件或可复查的推导作出；未能取得的 ForeCritic 专属权重和逐条 split 保留为材料缺口。
