# 当前状态：Cactus 原版 12 小时复现完成

**2026-11-15 · 最新 HW3 报告已推送，仓库提交入口检查完成。** 用户授权后将报告及架构图提交 `18f1e0f`、`36a49d0` 推送到 `main`。GitHub API 回读确认远端为 `36a49d042332dbbedd7e8b473806c0db08c73ace`，[当前 PDF](reports/hw3/HW3_Process_Reward_Proposal_20261115.pdf) 与本地 Git blob `12245b093023629adf1a6ce402cf551787acb693` 一致。目录结构可沿用，首页 `README.md`、`reports/hw3/SUBMISSION.md` 与版本说明仍以 v3 / Stanford 单任务为入口，建议对齐当前 process-reward 报告、pairwise 子样本和 Stanford / Cactus 两任务复现。HW3 唯一下一步为更新这三个导航入口，历史报告和冻结版本继续留存。

**2026-11-15 · HW3 英文润色完成。** 按 academic-humanizer 0.3.3 逐段润色四节正文与架构图标签，将正文 16 处冒号、43 处分号改为自然句式，保留段落结构和单作者口吻。数值、3 个展示公式、数学记号、引文与来源链接逐项对照一致，7 条参考文献解析通过。桌面编译及 TeX Live 编译通过，8 页 PDF 与架构图已检查，最终日志零警告。交付[PDF](reports/hw3/HW3_Process_Reward_Proposal_20261115.pdf)及[润色核查记录](reports/hw3/analysis/academic_humanizer_review_20261115.md)。本轮文件保留本地。HW3 下一步为用户审阅润色稿，研究任务沿用现有交接。

**2026-11-15 · HW3 proposal 已转向 process-based reward。** 修改 `reports/hw3/main.tex` 与 `future_plan.tex`：保持 ForeAgent baseline 和现有复现，研究父程序到候选修改的过程质量监督对 Improvement 筛选及等预算最终成绩的作用；ForeCritic 式结果监督为对照。已核对 ForeAgent、ForeCritic、AdaPRA 原文，桌面 LaTeX 编译成功；[八页 PDF](reports/hw3/HW3_Process_Reward_Proposal_20261115.pdf) 已导出并核对。新增实验、训练和付费推理均为 0。正文与表格已统一单作者口吻（I / this project / reproduced），八页 PDF 已同步并回读核对。 本轮补齐前三节的过程/结果监督同输入对照、data report 来源、controller 与完整锦标赛规则、复现任务指标及节点/时间比较表；逐项核对 7 条参考文献与固定代码/数据链接，区分论文结果、作者归档与本次计算。修正 cot 文本类型；桌面编译和八页逐页检查通过。 新增[ForeAgent 发布实现架构图](reports/hw3/figures/foreagent_architecture.pdf)及可编辑 TikZ 源码，置于 Baseline Explanation 第 3 页；逐项核对论文第 3.4/6 节与固定源码的分支、模型、锦标赛、执行 gate 和 journal。按用户反馈将全文否定与限制式表述改为直接陈述，保留实验范围及控制条件；8 页排版回读和 7 项引文解析通过。本轮按用户明确选择保留本地提交，GitHub 同步由后续明确指令安排。 HW3 下一步：用户审阅过程标签来源与对照设计。项目研究其余任务按现有研究交接继续。

**2026-11-15 · Proposal第三部分：两层复现事实核对完成。** 回读原论文、GitHub和原始响应/journal后形成独立英文草稿及两张结果表：静态DeepSeek思考模式136/246=55.28%，论文全量61.5%（范围差异−6.22pp），同246对作者一次归档52.85%（+2.44pp）；Stanford/Aerial单次12h的Beat Ratio分别1.000/0.87715，与论文各任务三次均值精度吻合。新增只读核验补齐Aerial BR=1071/1221；86次在线比较中双侧均留存CSV的对数为0，在线测试准确率保持未定义。区分论文、作者归档与单次复现，披露重试/指标失配/部署差异及单次覆盖范围。新增训练/模型调用/候选私有评分均0，现有报告正文保持。当前唯一下一步：用户审阅第三部分并确认整合。 [英文正文](reports/reproduction-section3-20261115/Proposal_Section3_Reproduction.md)。

**2026-11-15 · Cactus 原版 12 小时复现完成。** 北京时间03:34–15:34按43,200秒预算结束；原流程选中方案的原始私有测试AUC为 **0.9999375316**，作者评分函数与独立ID对齐评分完全一致，按原MLE-bench五位规则为 **0.99994**（作者公开三次0.99992/0.99993/0.99991）。最终82节点、11有效节点、6批锦标赛；13份提交CSV、200次完整API记录（含86次比较）、请求标识与计时全部保存，服务器与本机1,263文件逐项哈希一致。保留原算法/参数及两份整数指标被原逻辑拒绝的提交；披露PRoot/模型服务/网络适配与4次ready启动超时。末次执行按预算中断并留档，实验worker/GPU进程已退出，AutoDL实例保持开启。当前唯一下一步：审阅本次结果，按用户后续要求开展已保存节点与比较器记录的回溯分析。 [结果、协议与归档](experiments/online-cactus-v1/README.md)。

**2026-11-15 · Proposal v6 协议与披露修订。** Future Plan 明确单次运行内最多两次修订、下一批次验证/保留/回退，静态版由复现证据一次修订后冻结，演化版同初始化；四小时依据、局部随机种子控制、三对 pilot 方向一致判据及留出标签隔离已写清。主要比较为演化版 vs 共享修复 baseline，静态对照检验持续修订增益。正文和 AI_USAGE 统一披露 Codex 实质起草及 Claude 草稿/审阅贡献，旧离线工作另列历史。前三节仅小修，12页编译和版面核验通过，无溢出/未定义引用；本轮无实验或付费推理。唯一下一步：审阅 v6，并确认教师对课题、baseline 与课程 AI 披露要求的认可；实验尚未启动。 [PDF](reports/hw3/HW3_Harness_Evolution_Proposal_20261115_v6.pdf)。

**2026-11-15 · Proposal v5 审阅修订。** 核实 rank-0 组为 2/1/1/10/10/1/10，期望执行 10.36 次、实际 10 次；首轮新调用 Fisher 双侧 p=0.0137（调用聚类，探索性）。Table 6 区分规则一致与置信度偏低；以论文同任务 ForeAgent Beat Ratio 1.000±0.000 对照并解释跨划分排行榜阈值。选择差距 0.00971 与验证口径问题关联但不作因果归因；补单位成本及第3节总结。Future Plan 聚焦比较器指导与批量策略演化，统一验证/缓存修复作为共享前提；三配对种子、4小时窗口和计入适配的总预算。12页编译通过，无溢出或未定义引用；无新增训练/付费调用。当前下一步：用户审阅 v5，并向老师确认课题和 baseline；拟议实验尚未启动。 [PDF](reports/hw3/HW3_Harness_Evolution_Proposal_20261115_v5.pdf)。

**2026-11-15 · Proposal v4。** 修正记号、命中时间概率目标、架构图三色与标签、阴影说明和 comparator 请求温度 1.0。日志核对等待前节点 62 vs 作者 54/52/69，等待结束 62 vs 112/95/118；恢复后生成请求均值 330s（此前 195s）。缓存为零的首轮高置信率 1/35 vs 作者 41/210；未发现淘汰节点进入 rank 0；缓存反向命中精确计数缺有序身份日志，未声称影响小。已用现存答案对 13 份保存提交做事后评分：Beat Ratio 0.44h 达 100%；最低测试误差 0.25669 在 2.69h，原验证选择终分仍为 0.26640，最佳节点来自 debug。新增测试曲线和匹配度表；11 页编译通过、无溢出/未定义引用；本轮无训练/付费推理。下一步：用户审阅 v4，确定首个 harness 演化实验。 [PDF](reports/hw3/HW3_Harness_Evolution_Proposal_20261115_v4.pdf)。


**2026-11-15 · Proposal v3 rubric 对齐。** 新增记号表、双目标公式、架构图、源码版锦标赛伪代码、设置差异表、节点分解、比较器行为与时间/搜索轨迹图。仅分析原端到端日志：最佳已解析验证分在 3.46h；82 保留节点（22 执行、13 有效、9 失败），另有末批 10 个候选未入最终 journal；七完整批 1,841 比较记录、51 高置信、1,720 缓存命中、1,308 pending 条目。最终程序验证按 107 位补零标签计算，官方仅前 68 位；明确验证/测试口径。报告作者范围内终分与更少节点，未推断 AIDE 加速比。9 页 PDF 编译无警告，图表和数字回读通过；新增执行/付费调用为 0。当前下一步：用户审阅 v3 并选择首个 harness 实验。 [PDF](reports/hw3/HW3_Harness_Evolution_Proposal_20261115_v3.pdf)。


**2026-11-15 · Proposal v2。** 按用户意见重写 Baseline Explanation：任务目标、AIDE 基础、预测式筛选动机与输入、执行反馈闭环、可变状态与固定 harness。Reproduction 按实验设置、主要结果、与作者对比分节；报告 0.26640 相对作者均值 0.25862 高约 3.0%，删除效率对照待验证表述、哈希/源码数量/完整路径等归档细节。仅端到端复现，无新增实验。7 页 PDF 编译和分页检查通过，无引用或排版警告。当前下一步为用户审阅新版。 [PDF](reports/hw3/HW3_Harness_Evolution_Proposal_20261115_v2.pdf)。


**2026-11-15 · Harness evolution proposal 全文替换。** 主问题统一为 “Can harness evolution make machine learning agents search more efficiently?”；四节英文稿均已更新，复现正文仅报告 Stanford 12 小时真实端到端运行（MCRMSE 0.26640），移除旧离线回放与候选池实验；Future Plan 改为技能演化、生成—筛选协同、搜索控制及含适应成本的在线验证计划。NeurIPS 模板编译为 7 页，引用/交叉引用及排版检查通过；本轮新增实验、训练和付费模型调用均为 0。当前写作下一步：用户审阅全文，确定首个 harness 演化实验；历史研究记录继续保留。 [PDF](reports/hw3/HW3_Harness_Evolution_Proposal_20261115.pdf) · [LaTeX](reports/hw3/HW3_Harness_Evolution_Proposal_20261115_LaTeX.zip)。


**2026-11-14 · World Reward Models 论文精读已形成 Word 版。** [精读文档](reports/World_Reward_Models_论文精读_20261114.docx)覆盖问题、理论、训练配方、配对实验、Agent 接入和本项目关联；关键数字按 21 页 PDF 正文与附录核对，Word 中文显示与分页已检查。本轮新增研究实验和模型调用为 0；研究下一步沿用 [当前交接](research/README.md)。

**2026-11-14 · Proposal 两节初稿已完成。** [英文 Introduction 与 Baseline Explanation](reports/Proposal_Introduction_Baseline_20261114.md)及[可编辑 Word 版](reports/Proposal_Introduction_Baseline_20261114.docx)按固定 GPU／墙钟预算定义研究问题，技术细节覆盖 ForeAgent 预测输入、数据报告、门控淘汰赛及执行规则。Word 版含论文 Figure 2(e) 流程图。验证：三页渲染逐页检查，章节、公式文字、嵌入图片和关键数字回读通过；新增模型调用、训练、GPU 租用均为 0。本轮写作下一步：用户审阅初稿并反馈修改意见。

**2026-11-14 · baseline 论文精读已交付审阅。** [结构化笔记](reports/ForeAgent_论文精读_20261114.md)区分论文结果、证据评价和作者版代码细节；核对 34 页 PDF、Table 13–15 及本地实现。验证：笔记章节、PDF 链接与关键数字复算通过；新增模型调用、训练、GPU 租用均为 0。本轮写作下一步：用户审阅后撰写 proposal 的 Introduction 与 Baseline Explanation。

**2026-11-10 · DeepSeek comparison skill 与 HW3 审阅稿。** 12 个任务各抽 2 对作者已评分代码，96 次真实判断全部有效。原提示判对 32/48，加 skill 为 31/48；换位后仍选同一份代码的为 20/24 和 17/24。继续使用原提示。这批数据上准确率差 −2.1 个百分点，95% 任务区间为 −16.7 至 +12.5。见[协议、实测与复核](experiments/deepseek-comparison-skill-v1/README.md)。[HW3 新审阅稿](reports/hw3/HW3_Research_Progress_Review.pdf)已更新前三节与当前研究进展。下一步是阅读相关论文，再从[老师的方向建议](research/advisor-suggestions.md)中选择有依据的方向；HW3 大改时围绕研究问题和有用的证据组织正文。

**2026-11-10 · 同任务跨运行实验已完成。** [结果、协议与复核](experiments/run-heldout-history-v1/README.md)。在两组可见成绩数相同的条件下，DeepSeek 的选择损失依次为 C0 0.2642、允许参考同源草稿 0.2554、只参考其他运行 0.2654；GPT 为 0.2725、0.2551、0.2724。425 池中 287 池有足够其他运行历史；单看这些池结论相同。全部 17,000 条选择已独立复算。保留 C0，收尾这版检索器的跨运行先导。建议下一项：在作者已评分的代码对上检验老师的比较 skill，固定模型、预算并做 A/B 换位；本轮只做离线跨运行实验。下列历史轮次承接各自当时的证据。

**2026-11-10 · 老师方向与 corpus 离线实测。** [逐条答复](research/advisor-directions.md) · [排名诊断、embedding 排序与同任务对照](experiments/embedding-rerank-v1/README.md)。DeepSeek C0 下，真实第一、第二落到第 4 名及以后的任务等权概率为 50.3%、66.8%。跨任务向量检索融合使损失从 0.2642 升至 0.2871；同任务用裁判所挑参考样例则降至 0.2250。当前优先用作者 corpus 按原始生成运行隔离相似代码，复核同任务收益及泛化。下列各轮的下一步以其记录日期为准。

**2026-11-10 · 改选对补分与 HW3 润色**　[HW3 审阅稿](reports/hw3/HW3_Execution_Memory_Review.pdf) · [预测文件审计与 GPU 预算](experiments/paired-prediction-audit/README.md)。80 个已知改选对中，0 对两边都有预测；32 对重算出单边官方分数（28 个 C0、4 个记忆端点），48 对双方均缺。下一步供审阅：Stanford 与 Statoil 各 3 对，单边补跑 6 份约 0.24–0.45 卡时，或同条件重跑 12 份约 0.47–0.90 卡时（按历史中位数、上四分位数折算，不含准备）。报告第 1–3 节由 Claude Opus 5.5 润色，第 8 页 Future Plan 逐字及渲染像素核对一致。

**2026-11-10 · C0 与执行记忆的 CPU 回放**　[HW3 审阅稿，第 8 页](reports/hw3/HW3_Execution_Memory_Review.pdf) · [逐批结果与复核](experiments/c0-memory-switch-v1/README.md)。16 次运行、136 批中，按归档裁判判断可完整还原 C0 的有 128 批，加入记忆后 80 批改选；另有 1 批虽无法还原唯一首选，仍可确定改选。接口可接受的 130 批合计 81 改、48 同、1 未知。80 个具体改选对中，双方都有可用旧验证分的为 0。下一步：审阅报告后，在预定任务、相同划分与训练预算下实测分歧对。

- **2026-11-10，首次版本归并与持续同步规则。** 以远端 `09b301d` 为基点归并本地最新研究，保留原版 / HW3 发布材料与远端独有测试；交接入口为 [research/README.md](research/README.md)。[AGENTS.md](AGENTS.md)已写入每轮结束更新入口、验证、提交、推送及远端回读的持续授权。大型逐场 / 编码产物和补充公开输入通过校验附件衔接，范围与恢复说明见 [归并记录](provenance/first-alignment-20261110/README.md)。84 项现有测试、第一阶段副本核验与保护输入核验通过；本轮新增研究实验、训练和模型调用均 0。旧同步快照作为历史保留。

- **2026-11-10，跨聊天交接入口已整理。** [research/README.md](research/README.md)汇总原版 / C0 的角色、已测方向的结果与收尾原因、ForeCritic 定位、最新五类备选及待开展的 Top-1 / Top-2 诊断；当前保留 C0，下一轮方案待选定。历史条目的“下一步”按原阶段保留，当前衔接从研究入口读取。本轮仅编辑交接文档；39 个本地文件链接检查通过，原环境操作说明逐字保留，`python3 -B -m reproduction.research_env_v1 status --json` 返回保护输入 verified，新增实验 / 训练 / 模型调用均 0。GitHub main 核为 `09b301d`，本机及本地 origin/main 仍为 `9442373`，发布与版本归并待执行。

- **2026-11-08，研究范围聚焦固定 corpus 上的离线选优。** 两个已登记的离线终选试验各覆盖四份归档、3,400 场。全局名次重排在 DeepSeek/GPT 合并的收益为 −0.02138/−0.00924；理由下标冲突破同分为 +0.00046/0。均保留 C0，生成和在线测试后置。独立重建全部重排选择，核对原始理由字段与保护数据。用户决定本轮到此结束，原拟的理由分析已撤下。[离线证据与停止条件](research/离线候选选择.md)

- **2026-11-08，静态裁判训练完成，保留 C0。** 26 个开发任务、104 次拟合和 17,000 场离线选择。终局加权相对等权的归一化收益为 0.00116，95% 任务簇区间 [−0.00232, 0.00448]。3,400 份 C0 原轨迹精确复现，72,896 个逐臂胜者经独立重建。本机基点 `9442373`，远端 main `09b301d`。下一步是登记并搭建生成方式 × 验证方式的等预算真实执行对照。固定输入可用 `python3 -B -m reproduction.research_env_v1 status --json` 核验。[收据与结果](experiments/trajectory-weighted-judge-v1/README.md) · [研究路线](research/研究路线.md)

- **研究方案纠正。** 普通执行监督两两裁判与 ForeCritic 重合，现归为基线。已有实验支持优先改善胜者判断；候选机制为 C0 单点反事实终局代价加权。小规模回放已验证该信号可以与两候选分差区分。下一步是匹配训练与留任务评估，方法收益尚待实测。[修订方案、文献与对照](experiments/selection-frontier-02/优先改动.md)

- **2026-11-08，模块改动顺序已确定。** 真实覆盖策略、置信门槛与汇总、C0 最终重排、第二意见、按裁判留出配置和缩短预算均已对照。六份裁判归档的实际 C0 部分理想化干预显示，减少已采纳错判和补足弃权都能降低开发集损失，GPT 上前者的机会更大，DeepSeek 上两者相近。结束本轮参数搜索；下一步实现执行监督的胜者预测原型、固定原弃权掩码检验其真实输出。原版、C0 与现有默认选择保留。覆盖策略完成官方 850 场 run/evaluate，附各分支独立核验；新增付费模型调用、候选训练、GPU 均0。[一页决定](experiments/selection-frontier-02/优先改动.md) · [完整记录](experiments/selection-frontier-02/README.md)

- **2026-11-08，首轮子代理离线实验完成。** D1 主动减随机的一步损失差 +0.00289，95%任务簇区间 [−0.01313, +0.02352]；保留 C0。J1 固定稀疏赛程和弃权，评价端纠正已问边胜者的平均收益 +0.17864 [0.11545, 0.26237]，73场选得更差。独立脚本重建原始赛程、选择与分数；哈希与配对区间核验通过，新增训练、付费研究 API 与 GPU 均为0。下一步建议登记最佳候选的有效比较覆盖诊断。[两项实验及运行记录](experiments/selection-frontier-01/README.md)

- **2026-11-08，研究范围更新：先比较各模块对最终成绩和成本的影响，再定优化方向。D1 保留为比较分配模块的候选诊断。** [一页结论](research/selection-study-v1/README.md)连接 ForeAgent 实验覆盖、ForeCritic 与主动排名近邻、单步效用诊断及转向门槛。通过 `git ls-remote` 及远端 Git tree 核对，研究文档写入前 337 个发布文件与远端 main 对应 blob 相同；本机保留原 Git 基点。只读 `status --json` 核验保护输入，阶段一 `verify_copy.py` 默认范围 529 项通过，逐场回读既有两臂轨迹确认 850/850 场共享前缀。本轮只更新研究文档、导航及进度；新实验、训练和研究 API 调用均为零。

- **研究材料已同步 GitHub（research-publication-v1，2026-11-08）**：[私有仓库首页](https://github.com/skyexry/foreagent-reproduction)按“当前状态、研究设计、最近实验结论”导航。研究源码/证据发布提交 `5f545087f9ce71453d79214bb6b1ea93f730132a`，337 项发布文件与本机来源逐项一致，774 项其他原有文件保留；两份 CRLF CSV 的上传换行转换已在后续提交修正。约 57 MB 的固定输入发布于 `research-env-v1`，HW3 新增约 15 MB 的原版代码包；二者重新下载后 SHA-256 一致。HW3 标签及既有报告/日志附件保持原版本。证据见 `provenance/research-publication-v1/`，提交指引见 `reports/hw3/SUBMISSION.md`。新增模型调用/训练/GPU 租用均 0；当前研究下一步仍为模块与文献研究、完整方案卡。

- **离线研究接口已验收（research-env-v1，2026-11-08）**：统一入口 [research/README.md](research/README.md)。固定候选、反馈可见范围、比较/早停动作、外部预算、并列与失败评价；提供 `run/evaluate/status`。17 项契约/系统隔离测试通过，C0 850 场与随机控制 850 场逐场复现已保存选择、查询与统计。177 项旧产物、48 项历史文件、946 项源输入核验通过；新增模型调用/训练/GPU 租用均 0。证据：`experiments/research-env-v1/acceptance.json`、`tests.log`、`research/protected_manifest.json`。26 任务明确为开发集；真实在线与 AI Scientist 原生适配作为独立后续验收。**当前唯一下一步：围绕已固定模块读原始文献，形成可审阅方案卡。**

- **源码已核验**：独立检出固定在 `c4d52cf99bd870d830b456ac7c0684aec1aef375`。逐文件核对工作目录与该提交，484 个 Git 文件内容一致，工作区干净；其中 Git LFS 指针按提交原样保留。
- **离线证据**：给定历史判断和日志中的概率结果，15 次作者运行中的 129 个完整批次（1,290 个候选）控制输出一致。原 RNG 状态和复赛对手身份仍有缺口。证据：`experiments/historical-v1/summary.json`。
- **标准 12 小时端到端结果已冻结**：`stanford-autodl-v2` 在北京时间 11 月 8 日 13:22 按预算结束。原算法从已完成的 82 个节点中保留 `84c79a8d`，官方私有集误差 **0.26640**，25,680 个预测 ID 有效；19 次完整外层迭代、7 个完整淘汰赛批次，执行了 22 份代码。作者的三次最终成绩为 0.24320、0.25768、0.27497。硬件、模型服务与网络时延有差异。根据实验者事后确认，Mac 熄屏、VPN 断连导致模型 API 请求受阻并等待重试；其中一次反馈请求及重试累计耗时 13,491.88 秒（约 3 小时 45 分钟）。该耗时计入标准 12 小时预算，压缩了实际可用于候选生成、筛选和执行的时间；13,491.88 秒为请求及重试的总耗时，VPN 中断时长单独计量仍有缺口。见[最终结果和预测哈希](experiments/online-stanford-v2/final-summary.json)、[作者最终提交复评分](experiments/online-stanford-v2/author-final-reference.json)、[首批筛选记录](experiments/online-stanford-v2/first-tournament.json)。
- **本机 API 预检**：通过作者请求后端和硅基流动的模型名、思考开关映射，代码生成与两两筛选各实测成功一次。GPT 反馈也已实测通过：官方端点返回 gpt-4o-mini-2024-07-18，作者后端成功解析 submit_review 的五个字段。测试使用简短示例输入。回执见本机 `/Users/shrinn81/Documents/Codex/2026-11-01/read-this-folder-and-my-current/work/foreagent-local-preflight/` 下的 `code.json`、`select.json`、`feedback.json`。
- **本机数据与评分器**：Kaggle ZIP 和 4 个准备后的文件均匹配固定提交的 MD5。训练 2,160 条、测试 240 条 RNA 序列。官方 grade-sample 接受全零示例提交，得分 0.63824。证据见上述本机目录的 `data-check.json` 和 `sample-grade.txt`，数据位于 `data/stanford-covid-vaccine/prepared/`。
- **实验已结束**：因 0.26640 高于 0.25862 而启动的独立加时，已按用户要求提前停止。新增完整节点 0 个，预测文件与标准提交 SHA-256 一致。最终报告使用标准 12 小时分数 **0.26640**；见[加时结束记录](experiments/online-stanford-plus4h/closure.json)。

- **本机剩余验收已完成（environment-baselines-local-v1）**：新克隆及新 venv 重现 246 对结果、129 个完整历史批次及原版 7,800 次回放；4 项机制测试、5 项独立评分反例测试通过。新增独立 Mac 控制器/评分环境通过 `pip check`，完成两种作者配置的零调用构造与公共参数一致性核验。最终提交和作者三份提交的原评分与独立 ID 对齐分数一致。完整证据见[本机核验与剩余清单](experiments/environment-acceptance/README.md)、`offline-verification.json`、`online-verification.json`、`environment.json`、`config-verification.json`。本轮新增模型调用 0、候选训练 0；固定源码及既有基线参数保持原版本。
- **评分器边界已实测并加核验**：作者原 Stanford 评分器在打乱行顺序后因 pandas 索引对齐改变分数；原始冻结提交与独立按 ID 对齐的 MCRMSE 一致，仍为 **0.26640**。保留作者评分源码，新核验工具检查 ID、列、有限值和两种评分的一致性；反例及具体数值见上述清单。
- **本阶段已完成（2026-11-08 用户明确范围）**：以已完成并核验的 Stanford 单任务、单次标准 12 小时原版端到端运行作为复现验收，成绩 **0.26640**。原版重复性与 AIDE 公平在线对比转为后续可选研究；当前剩余必需 GPU 验收项为 0。硬件/执行适配、服务快照、Mac 熄屏及 VPN 断连等待、历史 RNG 缺口继续随结果披露。
- **后续 GPU 验收协议**：`environment-baselines-online-repeat-v1` 已准备，G1 新主机预检后可开展重复运行；资源租用及付费执行按用户后续明确指令执行。

- **HW3 报告 v3 已更新（2026-11-08）**：保留 129 批历史回放，新增 corpus26-v2 原版离线选择质量和 Stanford 标准 12 小时端到端结果；Future Plan 留待后续。交付 `reports/hw3/DM_HW3_Baseline_Reproduction_v3.pdf`（8 页）。LaTeX 编译、实验数字回读及逐页版面检查完成，验证记录见 `reports/hw3/validation_v3.json`；新增 API/训练均 0。
- **第一阶段材料已集中归集（phase1-reproduction-v1）**：统一入口为 [phase1-reproduction/README.md](phase1-reproduction/README.md)。归集固定作者代码、实际运行适配代码、完整在线日志/候选/预测、成绩与本机核验记录；原件保留，945 项副本/链接及原始来源逐项校验通过，来源和 SHA-256 见 SOURCES.json。完整记录和公开输入按本机附件管理，代码与摘要纳入 Git。
- **GitHub HW3 材料已发布（hw3-phase1-v1）**：默认 main 已整理为报告、phase1-reproduction 与历史 archive 三个入口；完整日志、v3 PDF、SHA256SUMS 作为 Release 附件上传并重新下载校验通过。发布收据见 `provenance/hw3-release.json`。仓库维持原私有设置，报告 Future Plan 按原范围待补；新增实验 API/训练均为 0。
- **严格复现审计已完成（foreagent-review-20261108-v1）**：交付[审计报告](reports/reproducibility-audit-20261108/AUDIT_REPORT.md)、[验证与Future Plan](reports/reproducibility-audit-20261108/FUTURE_PLAN.md)及17项结构化发现。最终0.2663989312、484作者blob、当前947项完整归集及原件核验通过；246响应、129批、两版本各7,800回放与9项既有测试通过。新增原生反例覆盖方向缓存、跨上下文缓存、低confidence复读、早期最佳漏存和提交残留检查。作者95a7c811原代码/元数据/CSV已从固定revision取得，双评分0.256153144，对比发布最终0.257679528，确认漏存端点的实际差异0.001526384。13份有效候选事后排序ρ=0.2363、选择差0.009712；公开corpus49对含NaN，finite-only对一份作者判断影响+0.0547pp。发布89d428f的README/SOURCES/附件清单与本机字节一致。原版与冻结输出保持；本轮新增模型调用、训练、GPU租用均0。基线修正与高成本实验按Future Plan供审阅。
- **审计阅读版已简化**：新增[先读这份](reports/reproducibility-audit-20261108/先读这份.md)，用具体例子解释复现进度、三个重要错误和后续顺序；交付README优先指向短版。原审计结论和数值保持，新增模型调用/训练均0。
- **论文实验设计深入审查已完成（experimental-design-review-v1）**：新增[易读审稿意见](reports/reproducibility-audit-20261108/论文实验设计审查_易读版.md)。Table13重算净提升约4.44pp，其中约80.6%来自仙人掌任务，去掉该任务的事后敏感性差约1.075pp；Figure4中2h71.6%、6h74.1%体现“较早达到较好水平”与“自身峰值收敛”的区别。将同候选/同反馈预算的机制对照、收益区间、静态→在线迁移和语义护栏归因列为主要实证问题；总体SD的混合重建与原表吻合，精确汇总仍待脚本。Future Plan已优先收拢为固定R7汇总下的新比较分配，并加入覆盖控制；当前26任务作开发，固定方法后盘点新任务。新增模型调用/训练/GPU均0。
- **ForeCritic 精读与 reward model 计划已更新（forecritic-reading-20261108-v1）**：交付[精读与研究判断](reports/reproducibility-audit-20261108/ForeCritic_精读与研究判断.md)，核对正文、附录 A–E、表格和图示说明；作者训练/集成结果按论文报告引用，专属脚本、权重与 split 等待定位。只读盘点确认26任务、895候选ID、18,438对，49对含非有限分数；本机374份代码、367种字节内容覆盖2,746对有限分数比较，补全还差521份。tweet任务8份代码完全相同，组成28对、左右胜者各14；执行差异原因待核。16份journal共有186个已执行finite非buggy内部指标节点。当前[Future Plan](reports/reproducibility-audit-20261108/FUTURE_PLAN.md)以任务隔离的训练先导为优先候选，选择损失加权和执行路由据结果推进；旧排序方案按原文存档。新增训练/模型调用/GPU租用均0，历史基线与输出冻结。
- **本轮交付检查完成**：数据盘点重复运行字节一致；469个输入哈希、11项论文文本、56个本机链接与50项交付哈希核验通过。旧计划存档与调整前字节一致；验证收据为 `reports/reproducibility-audit-20261108/evidence/forecritic-validation.json`。
- **完整原始语料已补齐（foreagent-corpus-completion-20261108-v1）**：按用户追问核实获取渠道与重复记录来源，原8份tweet代码和原标签从作者固定revision下载后逐字节对齐。余下521份已下载至独立的[reward-model数据目录](data/reward-model/corpus-6b322cb-raw-v1/README.md)，现有895份代码、878种字节内容、871种AST；974项源文件哈希通过，旧469项输入哈希保持。完整语料中47对finite比较的代码相同，其中tweet一组9份形成36对；原28对是先前已下载8份的局部结果。原始标签与成绩保持，原因待原执行日志核实；新增训练、模型调用、GPU租用均0。来源、缺失清单和完整核查见审计目录的`evidence/corpus-source-check.json`、`evidence/corpus-completion.json`。
- **研究定位已按用户明确意见调整**：直接基于 ForeAgent 研究用执行数据学习方案裁判；ForeCritic 放在相关工作与可选对照的位置。主比较为同一正确执行/筛选链路中的原 LLM 裁判与学习裁判，排序/停止改变另列因素。数据质量、任务泛化与成本作为可信评估要求；具体训练目标或接口改动根据 ForeAgent 的诊断选择。Future Plan 与阅读导航已同步，新增实验为0。
- **基线修正与短测试方案已具体化（baseline-short-tests-plan-20261108-v1）**：按用户当前排序/筛选方向，下一步为正确工作基线和短时验收，见[具体方案](reports/reproducibility-audit-20261108/BASELINE_SHORT_TEST_PLAN.md)。本轮回跑5项独立评分、4项原机制核查全部通过；原行为核查与修正版验收分开。已静态识别现有Transformer/LSTM/CNN＋LSTM代表候选，并找到已有Python3.11/PyTorch2.2环境。拟做3候选×2seed、训练目标约5秒/次、进程上限60秒/次的CPU短跑，另核查标签访问、指标、数据划分与新输出绑定。修改方案待审阅，真实候选短跑/新算法/模型调用/GPU租用均0；原版与冻结输出保持。Future Plan优先顺序同步为可信基线→短时验收→固定裁判的比较分配，reward model保留备选。
- **AI Scientist 接入就绪度核查完成（ai-scientist-readiness-20261108-v1）**：按当前排序/比较分配主线回读复现、审计、C0短测试方案及R7实现；回跑5项评分、4项原机制、7项R7、11项离线选择检查，共27项通过。已有独立评分、方向语义缓存修复与R7纯函数可复用；完整C0、真实候选短跑、清洗/划分/池协议、逐对查询与外部预算接口及AI Scientist薄适配仍待实现。首轮建议固定裁判和R7，在保存作者反馈上比较随机、覆盖后随机与同覆盖后主动补问；离线接口准备可随C0准备推进，在线验证以执行链路验收为前置。AI Scientist官方源码固定核对到1de1dbc；需独立模型/Aider预检、全局预算、标签与评分隔离、完整代码快照和失败日志保全。检查回执与分阶段验收见[ai-scientist-readiness.json](reports/reproducibility-audit-20261108/evidence/ai-scientist-readiness.json)。本轮研究代码修改、模型调用、候选训练与GPU租用均0。
- **clean-ranking-v1已完成**：C0独立补丁、12项新反例、6次成功的三架构五秒级CPU训练及2次20步标签对照、实际Agent类受控集成均通过；同输入原版/C0对照确认最佳节点保存修正。原始作者反馈远端revision/ETag核验26份，重新建立425池、850配对场景、3,400评分。C0原排序选择损失0.26416/最佳命中23.67%，新主动分配0.29073/19.27%；损失差+0.02657，95%任务簇区间[-0.02394,0.09881]。独立核验与工程性复跑轨迹/指标一致；R6–R8的48文件哈希保持，仅作历史保护。本轮新增付费模型调用/GPU租用为0。完整在线API/任意候选脚本隔离/验证预测独立重算合约作为后续验收。见[易读结果](experiments/clean-ranking-v1/先读结果.md)。
- **当前唯一下一步**：固定本轮负面先导，核查Petfinder单池与胜率汇总对主动选边的适配，登记下一个单因素诊断；真实在线实验另审阅预算。
