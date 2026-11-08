# ForeAgent 复现审计与研究判断

审计日期：2026 年 11 月 8 日。审计 ID：`foreagent-review-20261108-v1`。对象是 `phase1-reproduction` 的实际冻结内容及其清单指向的直接证据。本报告对应新增审计文件；原始源码、配置、输出和预测保持原字节。

## 1 执行评估

**你的复现足以支持“适配环境中原版 ForeAgent 单任务单次端到端链路成立”，最终 MCRMSE 为 0.2663989312。** 来源、发布参数、Journal 所选节点、节点代码与预测、官方评分和独立 ID 对齐评分均完成回读。起始清单945项与原件一致；发布更新后947项再次全量核验，484个作者Git blob一致；246 对重解析、129 批条件重演、两个版本各 7,800 次固定池回放完成独立重跑。此结论覆盖当前明确的第一阶段验收。

**作者发布基线需要几项正确性修正，之后再承担方法比较的基准角色。** 影响潜力最高的是批次最佳提交漏更新、缓存方向、提交残留，以及评分和标签的数值契约。新确认的作者 Stanford 案例将 journal 中 0.1583 的最佳内部节点留在最终提交之外，发布节点内部值为 0.1645；从固定作者数据版本找回漏存节点后，代码与身份核对通过；双评分得到0.256153144，对比发布提交0.257679528，确认端点误差差异0.001526384。你的冻结最终代码与预测通过绑定检查。评分器已知行序错误对冻结四份最终提交的影响已被双评分核验排除。

**未来研究的强证据起点是“什么证据足以支持下一次比较或执行”与“内部验证是否可信”。** 新诊断发现，7 个在线批次全部到轮数上限，3 批全部比较均低于置信度门槛；13 个有效候选的内部/外部排序相关性为 0.2363。当前证据为主动比较、风险校准和验证契约提供研究动机。修正错误的价值首先体现在可靠基线，方法贡献还需公平对照和独立任务验证。

## 2 审计范围与版本

| 对象 | 精确版本或状态 | 本次核验 |
|---|---|---|
| 论文 | Zheng 等，Can We Predict Before Executing Machine Learning Agents?，ACL 2026，DOI 10.18653/v1/2026.acl-long.182；34页定稿含附录A–E | 核对正文、方法/评价及相关补充材料，重点§3–6、C.3–C.9与提示模板；PDF Table13/14页做图像核对 |
| arXiv | 2601.05930v2，2026-04-07；v1为2026-01-09 | 核对官方版本页；历史阅读PDF字节哈希仍待来源记录补充 |
| 作者仓库 | https://github.com/zjunlp/predict-before-execute；`c4d52cf99bd870d830b456ac7c0684aec1aef375` | GitHub确认提交；本机固定检出、归集484 blob逐字节比对；LFS过滤关闭后固定检出状态干净 |
| 作者数据 | Hugging Face `zjunlp/PredictBeforeExecute` revision `6b322cb88bdbcb2b2d3897ec7d0ded94a5bb2d06` | 公开比较数据、作者判断、历史45份记录和三份最终提交按既有来源清单与哈希核验 |
| 镜像 | `johnsonzheng03/predict-before-execute@sha256:451d8519af279052a9edfdd499267a2f3df5f969a8439d9192a1f9265fb5c220` | 核验保存摘要和运行快照；本次GPU重建作为未来G1任务 |
| 复现主检出/发布修订 | 本机 `main@9442373ad020a06b691700592b0c83281b31d8c9`，带既有修改；发布 `hw3-phase1-v1@89d428fec8e950266efc5476fb79b59a8cadb0c0` | 发布README、SOURCES、附件清单与当前本机字节相同；详见已解决F17；审计文件另行清单 |
| 在线实验 | `stanford-autodl-v2`，北京时间2026-11-08 01:22:02.252—13:22:02.252 | 12小时截止信号迟0.01623秒；1任务、1次；完整保存82节点、22执行、19外层迭代、7完整批次 |
| 独立延续 | 阈值触发的plus4h为单独历史实验，后被停止 | 标准12小时产物保留；延续新增完整节点0，预测哈希相同；原结果仍按原截止时间报告 |
| 支持实验 | pairwise246、historical-v1、corpus26-v2 | 各自估计对象在下表说明；R6–R8只回读记录供未来计划定位 |

论文与代码来源：[ACL定稿及补充材料](https://aclanthology.org/2026.acl-long.182.pdf)、[arXiv版本记录](https://arxiv.org/abs/2601.05930)、[固定作者提交](https://github.com/zjunlp/predict-before-execute/commit/c4d52cf99bd870d830b456ac7c0684aec1aef375)。ACL另附checklist链接访问返回404/工具不可用，已记录为材料缺口。

### 基线的实际任务

ForeAgent 是 AIDE 派生的搜索控制框架。它调用现成 LLM 生成 draft、debug 和 improve 代码；improve 阶段生成多个候选，WorldModel读取任务、数据分析报告和两段代码，预测相对优劣，淘汰赛与执行策略决定实际执行对象。候选在独立Python解释器中训练自己的任务模型，反馈模型解析日志，Journal按内部验证指标保留最佳。WorldModel自身在本阶段通过API推理；候选神经网络结构由生成过程产生。

论文主张的审计坐标集中为：18,438对的61.5%准确率；五任务、三次、12小时的AIDE比较；6×加速与更广搜索。§6.2描述并行生成和top-1，发布实现的具体差异见F08/F09。Table13的0.695→0.739对应约+4.4个百分点、+6.3%相对变化。§5.4/Discussion6.1把72.2%代理一致率引向上界，F16讨论其论证范围。[论文位置](https://aclanthology.org/2026.acl-long.182.pdf)

| 组成/实验 | 实现 | 已执行与评估 | 所支持的结论 |
|---|---|---|---|
| corpus采样、修复、真实执行与标签构建 | 作者源码存在 | 本项目使用发布数据；本次核对19k量级记录的连接/数值，原始构建流程重建仍待资源 | 检验保存数据和控制流程；语料生成有效性需原始构建产物 |
| pairwise判断 | 作者prompt/parser；本机服务映射 | 246对，首轮226有效、20对各补一次，共266请求；136正确；作者同样本130正确 | 固定小样本上的真实判断；always-index-0=131也需并列报告 |
| 作者历史控制 | 原淘汰赛与Agent执行AST | 15次运行、129完整批、1,290候选、23,873比较记录，129/129条件一致；11批覆盖排除分账 | 给定保存反馈与概率决策的控制状态一致；原始复赛对手/RNG恢复待证据 |
| 固定池离线 | 原版与canonical缓存修正版 | 每版7,800；原版hit20.4265%，随机12.5321%；原版执行至少一最佳21.6026% | 该固定静态反馈与池构造下的选择质量；候选为身份stub，执行为读保存效用 |
| 在线完整循环 | 发布配置与原算法；Mac控制/API，4090/PRoot/SSH执行 | 单次Stanford，最终有效25,680行，真实评分16,320位置，0.2663989312 | 适配系统端到端可用与单次外部成绩 |
| 本机验收 | 数据/源码/配置/评分与复制核验 | 本次重新执行、回读；机制4测试与评分5测试通过 | 固定产物的一致性与指定边界行为 |
| 新重复、AIDE在线对照、新早停/主动策略 | 有预备协议或方向 | 作为后续待审阅工作 | 未来验证依赖；当前基线验收保持既定范围 |

### 忠实度逐项核对

| 维度 | 代码、设置与证据 | 审计判断 |
|---|---|---|
| 数据/划分 | Stanford prepare从原有训练数据抽10%，只从SN_filter>0取240序列，random_state=0；训练2160；四个prepared文件MD5匹配；ID与精确sequence交集均0；public test无目标列 | 当前直接标签隔离通过。相似RNA、公开数据记忆及数据报告溯源分别待查；SN质量分布差异会影响内部/外部误差比较 |
| 任务模型 | 最终代码22维输入、GCN(64)×2、CNN(128)×3、双向LSTM(128)、线性5输出；dropout与BatchNorm按生成代码运行 | 候选架构为搜索产物，复现框架无需预先匹配某一固定网络；新loss消融需固定同一网络与参数量 |
| 优化/训练 | Adam lr=.001，ReduceLROnPlateau patience3/factor.5；5折各30epoch，另80/20 split最终40epoch；batch16；最低内部validation保存checkpoint | 保存输出与最终方案吻合；推断另clip[-2,2]；F06说明mask、聚合、后处理与反馈选值的差异 |
| 生成/反馈 | code DeepSeek-V3.2 temp .5；feedback gpt-4o-mini-2024-07-18 temp .5；后端默认max_tokens8192 | 发布配置一致；DeepSeek经硅基流动映射，历史服务/权重快照同一性待证据 |
| WorldModel | DeepSeek-V3.2-Thinking temp1，gate.7，p=.2，10候选、Top-k名次组1、max_workers128 | 参数忠实；缓存与异常处理等作者行为原样保留 |
| 搜索/停止 | draft3、debug_prob1、debug_depth20、节点cap5000、12h、单次执行timeout32400秒 | 参数一致；5000以journal节点计，19外层迭代与82节点分别报告；硬截止会留未完成批次 |
| 随机性 | 任务数据split=0；最终候选np/torch seed42、cuDNN deterministic；Agent随机包顺序、pending和Bernoulli缺初始RNG记录 | 控制器seed、任务网络seed、API采样与线程调度分别说明；独立重复仍有必要 |
| 模型选择 | good且executed节点按内部metric；当前最小值0.4378；最终节点代码/预测哈希一致 | 当前冻结绑定通过；F01为发布实现的另一路径缺陷 |
| 外部评价 | 三目标MCRMSE，按private keep评分；官方与独立连接复算一致 | F03保护当前最终评分；事后候选评价保持诊断属性 |
| 执行环境 | 作者镜像rootfs+PRoot，Python3.11.13/torch2.2.0+cu121/RTX4090；Mac控制验收3.11.5，锁定74 distributions | 这些是有意平台适配；旧控制器依赖冲突与历史worker完整包/driver状态分别记录 |

具体源位置：[prepare.py:11](</Users/shrinn81/Documents/Data Mining/PM Final Project/ML Agent/phase1-reproduction/code/author/mle-bench/mlebench/competitions/stanford-covid-vaccine/prepare.py:11>)；[final_solution.py:218](</Users/shrinn81/Documents/Data Mining/PM Final Project/ML Agent/phase1-reproduction/experiments/online-stanford-v2/final_solution.py:218>)；[config.yaml:1](</Users/shrinn81/Documents/Data Mining/PM Final Project/ML Agent/phase1-reproduction/code/author/mle-bench/agents/aide/config.yaml:1>)；[backend_openai.py:43](</Users/shrinn81/Documents/Data Mining/PM Final Project/ML Agent/phase1-reproduction/code/author/mle-bench/agents/aide/aide/backend/backend_openai.py:43>)；[run.py:201](</Users/shrinn81/Documents/Data Mining/PM Final Project/ML Agent/phase1-reproduction/code/author/mle-bench/agents/aide/aide/run.py:201>)；[online-verification.json:1](</Users/shrinn81/Documents/Data Mining/PM Final Project/ML Agent/reports/reproducibility-audit-20261108/evidence/online-verification.json:1>)；[environment.json:1](</Users/shrinn81/Documents/Data Mining/PM Final Project/ML Agent/phase1-reproduction/experiments/environment-acceptance/environment.json:1>)。

## 3 按优先级排列的发现

P1：可能改变指标、最终产物、结论或研究选择，先处理。P2：影响机制解释、稳健性或第三方可复现性，随后处理；F17版本锚已补齐并核验。“已确认”指表述中的代码行为或证据边界；私有成绩与泛化影响另列待检验。归属2仅表示作者固定快照包含问题，具体历史引入者可继续追溯。

| ID / 级别 | 发现 | 归属 / 证据状态 | 影响与主张 | 证据 | 验证与行动 |
|---|---|---|---|---|---|
| F01 / P1 | 批次内较早出现的最佳节点可能漏存 | 作者实现 / 已确认 | 作者一份端点私有0.257680→0.256153；当前复现绑定通过；最终 checkpoint；k=2 消融；相对 AIDE 表现 | [agent.py:785](</Users/shrinn81/Documents/Data Mining/PM Final Project/ML Agent/phase1-reproduction/code/author/mle-bench/agents/aide/aide/agent.py:785>)；[diagnostics.json:1](</Users/shrinn81/Documents/Data Mining/PM Final Project/ML Agent/reports/reproducibility-audit-20261108/evidence/diagnostics.json:1>) | 已复评分漏存节点；按每次执行维护原子checkpoint |
| F02 / P1 | 无序缓存键与有方向索引混用 | 作者实现 / 已确认 | 反向缓存换错胜者；固定池hit修正+0.7735pp；筛选正确性；离线和在线候选选择 | [world_model.py:314](</Users/shrinn81/Documents/Data Mining/PM Final Project/ML Agent/phase1-reproduction/code/author/mle-bench/agents/aide/aide/world_model.py:314>)；[world_model.py:323](</Users/shrinn81/Documents/Data Mining/PM Final Project/ML Agent/phase1-reproduction/code/author/mle-bench/agents/aide/aide/world_model.py:323>) | 方向反例与配对回放；胜者身份映射并独立版本化 |
| F03 / P1 | Stanford 评分器对 CSV 行顺序敏感 | 作者实现 / 已确认 | 同预测乱序原评分0.266399→0.613106；冻结四份双评分一致；最终分数、奖牌与历史任务比较 | [grade.py:38](</Users/shrinn81/Documents/Data Mining/PM Final Project/ML Agent/phase1-reproduction/code/author/mle-bench/mlebench/competitions/stanford-covid-vaccine/grade.py:38>)；[grade.py:53](</Users/shrinn81/Documents/Data Mining/PM Final Project/ML Agent/phase1-reproduction/code/author/mle-bench/mlebench/competitions/stanford-covid-vaccine/grade.py:53>) | shuffle/坏ID/非有限值；ID连接评分与原评分并列 |
| F04 / P1 | 同批多次执行共享 submission 残留 | 作者实现 / 已确认 | 前一CSV残留可通过当前候选存在检查；真实频率待查；候选有效性、checkpoint 与代码/预测绑定 | [agent.py:531](</Users/shrinn81/Documents/Data Mining/PM Final Project/ML Agent/phase1-reproduction/code/author/mle-bench/agents/aide/aide/agent.py:531>)；[agent.py:722](</Users/shrinn81/Documents/Data Mining/PM Final Project/ML Agent/phase1-reproduction/code/author/mle-bench/agents/aide/aide/agent.py:722>) | A写B漏写完整链路；每候选隔离/验证新预测 |
| F05 / P1 | 公开 corpus 含 49 对非有限分数标签 | 作者实现 / 已确认 | 49对含NaN，21个NaN最佳标签；单作者记录finite-only +0.0547pp；pairwise ground truth、校准和 corpus 质量 | [group.py:77](</Users/shrinn81/Documents/Data Mining/PM Final Project/ML Agent/phase1-reproduction/code/author/prepare_bench_subset/group.py:77>)；[group.py:122](</Users/shrinn81/Documents/Data Mining/PM Final Project/ML Agent/phase1-reproduction/code/author/prepare_bench_subset/group.py:122>) | 全量finite与分母复核；异常准入和合法零分分开 |
| F06 / P1 | 候选内部验证偏离官方目标且选择信号较弱 | 设计/解释 / 已确认 | 36.45%位置为补零标签；13候选排序ρ=.2363，事后选择差.009712；Agent 最终选择；验证—测试一致性；方法收益归因 | [final_solution.py:145](</Users/shrinn81/Documents/Data Mining/PM Final Project/ML Agent/phase1-reproduction/experiments/online-stanford-v2/final_solution.py:145>)；[final_solution.py:287](</Users/shrinn81/Documents/Data Mining/PM Final Project/ML Agent/phase1-reproduction/experiments/online-stanford-v2/final_solution.py:287>) | 固定网络mask对照；统一split/metric/聚合契约 |
| F07 / P2 | 缓存复读直至轮数安全退出 | 设计/解释 / 已确认 | 在线7/7到轮数上限；1,720/1,841记录为缓存复用；筛选效率、停止规则、置信度门控的实际作用 | [world_model.py:543](</Users/shrinn81/Documents/Data Mining/PM Final Project/ML Agent/phase1-reproduction/code/author/mle-bench/agents/aide/aide/world_model.py:543>)；[world_model.py:555](</Users/shrinn81/Documents/Data Mining/PM Final Project/ML Agent/phase1-reproduction/code/author/mle-bench/agents/aide/aide/world_model.py:555>) | 同反馈预算停止/新对消融；衡量实际时间和费用 |
| F08 / P1 | Top-k 实际指显示名次组并带概率与强制回退 | 论文—代码歧义 / 已确认 | Top-1可执行多个或通过强制回退执行；p=.2含义有别；方法叙述、k 消融、执行预算 | [world_model.py:629](</Users/shrinn81/Documents/Data Mining/PM Final Project/ML Agent/phase1-reproduction/code/author/mle-bench/agents/aide/aide/world_model.py:629>)；[world_model.py:653](</Users/shrinn81/Documents/Data Mining/PM Final Project/ML Agent/phase1-reproduction/code/author/mle-bench/agents/aide/aide/world_model.py:653>) | 并列/概率/回退反例；组名次与exact-k分别报告 |
| F09 / P2 | 候选生成在发布代码中串行进行 | 论文—代码歧义 / 已确认 | 候选生成串行带前序计划；改变并行度也改变候选分布；实现忠实度与加速主张 | [agent.py:368](</Users/shrinn81/Documents/Data Mining/PM Final Project/ML Agent/phase1-reproduction/code/author/mle-bench/agents/aide/aide/agent.py:368>)；[agent.py:402](</Users/shrinn81/Documents/Data Mining/PM Final Project/ML Agent/phase1-reproduction/code/author/mle-bench/agents/aide/aide/agent.py:402>) | 串行记忆vs并行提示；各阶段耗时与多样性 |
| F10 / P2 | 响应校验与全局缓存上下文不足 | 作者实现 / 已确认 | 异常类型/越界响应和跨阈值缓存反例成立；实发频率待查；门控正确性、异常服务稳健性、缓存复用 | [world_model.py:244](</Users/shrinn81/Documents/Data Mining/PM Final Project/ML Agent/phase1-reproduction/code/author/mle-bench/agents/aide/aide/world_model.py:244>)；[world_model.py:287](</Users/shrinn81/Documents/Data Mining/PM Final Project/ML Agent/phase1-reproduction/code/author/mle-bench/agents/aide/aide/world_model.py:287>) | schema/上下文/并发反例；严格验证、重算gate |
| F11 / P1 | 置信度有区分信号，概率校准仍有明显差距 | 设计/解释 / 已确认 | 高置信度组平均c与实际准确率有差距；在线3批全低confidence；门控可靠性与跨分布迁移 | [confidence.json:1](</Users/shrinn81/Documents/Data Mining/PM Final Project/ML Agent/reports/reproducibility-audit-20261108/evidence/confidence.json:1>)；[diagnostics.json:1](</Users/shrinn81/Documents/Data Mining/PM Final Project/ML Agent/reports/reproducibility-audit-20261108/evidence/diagnostics.json:1>) | 任务隔离coverage-risk；校准与新反馈验证 |
| F12 / P1 | 现有证据对应不同估计对象与独立单位 | 设计/解释 / 已确认 | 1×1在线、条件回放、重叠静态池与246对对应不同估计对象；跨任务性能、相对 AIDE 收益、重复性与统计置信度 | [protocol-v2.json:1](</Users/shrinn81/Documents/Data Mining/PM Final Project/ML Agent/phase1-reproduction/code/runtime/protocol-v2.json:1>)；[historical-129-batches.json:1](</Users/shrinn81/Documents/Data Mining/PM Final Project/ML Agent/phase1-reproduction/experiments/supporting/historical-129-batches.json:1>) | 按task/run统计；独立任务与重复前瞻确认 |
| F13 / P1 | 系统效果与筛选机制贡献需要不同公平控制 | 设计/解释 / 已确认 | 同墙钟系统比较合理；候选数、DA、推理与筛选机制需控制；ForeAgent 相对 AIDE 与新方法相对基线的因果解释 | [config.yaml:1](</Users/shrinn81/Documents/Data Mining/PM Final Project/ML Agent/phase1-reproduction/code/author/mle-bench/agents/aide/config.yaml:1>)；[config.json:1](</Users/shrinn81/Documents/Data Mining/PM Final Project/ML Agent/reports/reproducibility-audit-20261108/evidence/config.json:1>) | 同池同信息同预算；匹配AIDE/随机/R7控制 |
| F14 / P2 | 部分评估函数采用容易误读的分母与指标名称 | 作者实现 / 已确认 | 失败从accuracy分母排除；precision@k为严格有序前缀；pairwise accuracy 的可比较性；listwise 指标解读 | [report.py:7](</Users/shrinn81/Documents/Data Mining/PM Final Project/ML Agent/phase1-reproduction/code/author/grade/util/report.py:7>)；[runner.py:124](</Users/shrinn81/Documents/Data Mining/PM Final Project/ML Agent/phase1-reproduction/code/author/grade/util/runner.py:124>) | 全/有效双分母与交换顺序反例；显式指标名 |
| F15 / P2 | 服务、随机状态和历史环境仍有复现缺口 | 复现专属 / 已确认 | 原RNG/服务快照有缺口；单次重试等待占预算31.23%；数值重复性、墙钟效率、公平比较 | [run_agent.py:71](</Users/shrinn81/Documents/Data Mining/PM Final Project/ML Agent/phase1-reproduction/code/author/mle-bench/run_agent.py:71>)；[agent.py:129](</Users/shrinn81/Documents/Data Mining/PM Final Project/ML Agent/phase1-reproduction/code/author/mle-bench/agents/aide/aide/agent.py:129>) | G1环境/随机/服务快照；新cohort记录所有尝试 |
| F16 / P2 | 经验现象的理论和因果外推需要收紧 | 设计/解释 / 已确认 | 经验一致率、定性案例与跨模型观测的理论/因果外推需控制；理论上界、机制因果解释、外推与泛化 | [reading-original.md:1](</Users/shrinn81/Documents/Data Mining/PM Final Project/ML Agent/phase1-reproduction/experiments/environment-acceptance/reading-original.md:1>) | 补推导/盲评/控制；将结论限定在已识别证据 |
| F17 / P2 | 本机/发布修订区别已核清 | 复现专属 / 已解决并核验 | 新发布89d428f与本机三份元数据字节相同；947项全量校验通过 | [publication-check.json](./evidence/publication-check.json) | 引用发布修订与附件；完整独立重建作为后续验收 |

## 4 覆盖与剩余不确定性

本次检视了来源清单、全部归集摘要、配置/运行快照、主控制器和worker、Agent/WorldModel/Journal/Interpreter关键路径、Stanford划分与评分、最终训练方案及日志、作者数据分组和评价辅助函数。45份作者历史文件由原核验程序重读校验并条件重演；固定26任务图及两版本各7,800场重新运行；18,438对标签和保存作者判断逐项连接；13份有效候选预测按ID独立计算。其他任务的特定预处理/评分器完成库存识别；其原始私有数据与逐任务数值正确性属于后续逐任务验收项。

已验证：作者漏存节点代码/身份与双评分、复制与源码版本、发布配置、真实运行节点计数和API成功回执、最后提交绑定、四份最终分数、9项现有测试、指定最小反例、F05的数据影响及F06事后候选评价。本次新增付费API、GPU租用、候选训练均为0。新文件只包含审计与诊断；原版及已保存输出保持。

以下材料或实验决定剩余结论，分别有具体下一步：

| 待确认事项 | 当前证据状态 | 最小补充材料/检查 |
|---|---|---|
| 漏存节点95a7c811的真实私有影响 | **已量化：0.257679528→0.256153144**，代码/身份/预测与双评分核对通过 | 修正incumbent后的完整搜索路径作为后续反事实实验 |
| 提交残留是否真实发生 | 精确文件检查反例确认；历史发生率待证 | 每次执行前后的文件哈希/新鲜度，尤其同批多执行 |
| F05对论文三次均值的影响 | 一份18,438判断已测；另外两份待资料 | 三次原始模型判断和绘表汇总 |
| 原始标签稳定性/语料筛选效应 | NaN异常已确认；每个候选通常保存单个效用 | 原执行种子、训练/修复/筛选记录；对近分候选小规模重复 |
| 数据报告的“verified”来源与内容 | 当次确实读取作者DA报告，部分统计与公开数据相符 | 原profile脚本、stdout、human-pass记录与报告生成请求；词义/因果推断另行审查 |
| 公开任务/数据的预训练污染 | 来源公开；当前split标签隔离通过 | 服务/模型快照、数据时间/去污染测试、新任务与描述去标识控制；现有材料支持“风险待查” |
| 作者全套论文结果与6×时间含义 | 保存部分轨迹及论文图表；完整绘图统计代码待定位 | AIDE全部轨迹、time-to-target定义、所有失败/删失尝试与token/账单记录 |
| 服务一致性和真实CPU配额 | 4090、128可见cores、提示21cores可核对；16core配额来自既有文字记录 | 历史quota/affinity/cgroup原始输出；未来G1直接捕获；权重revision待服务方证据 |
| 跨任务泛化与方法优势 | 现有26任务已被开发反复查看；在线1任务1次 | 预注册新任务/新反馈的分组外验证与公平重复 |
| 第三方重建当前phase1 | 已核验发布89d428f元数据与当前本机一致；947项全量通过 | 从已发布修订与附件做完整独立重建/入口检查；审计文件独立归档 |

原始日志中的“普通比较身份”和“pending节点身份”能局部交叉核对；历史复赛对手采用演示RNG，因此129/129的解释保持“给定响应序列及已观察动作的状态重演”。它证明实现一致性，原始随机轨迹恢复有明确证据缺口。

### F16的具体论证判断

经验代理的一致率取决于数据分布、划分、候选及测量噪声。Rice定理讨论一般程序语义的可判定性，要推出这个有限随机基准上的数值准确率上界，还需要额外假设与证明。论文的该数字可作为经验参照；若要使用理论上界，需要明确随机变量、信息集和可证假设。

定性“human intuition”案例适合作为机制例子，广义人类优势判断需要盲评样本和比较协议。不同模型的尺寸、预训练与推理方法共同变化，尺寸对比识别的是配置组合的观察差异。任务“seen/unseen”也需区分研究者开发可见与基础模型训练可见。这些问题改变解释强度，代码与经验结果的局部价值仍可独立评估。

## 5 公平比较的控制矩阵

| 研究问题 | 应匹配的条件 | 允许成为结果的差异 | 必需对照与指标 |
|---|---|---|---|
| 哪种系统在12h内更实用 | 数据/可见信息规则、GPU与CPU配额、生成/反馈端点、运行日期分块、外部评价、12h、同重复/失败规则 | 比较请求数、生成候选数、执行数和实际token成本 | 发布ForeAgent、corrected ForeAgent、作者AIDE；MCRMSE、有效率、达到同一目标的时间、AUC及成本 |
| 筛选策略是否更好 | 同一sibling候选池、同一DA与任务信息、反馈服务、唯一查询预算、同执行数和输出评价 | 比较对象和选择结果 | 随机、固定轮转/新对、R7胜率、corrected tournament；top-1、simple regret、query数/令牌/时间 |
| 报告信息是否提供增益 | 相同模型、候选、提示长度尽量匹配、相同请求预算 | 报告语义是否匹配当前任务 | 正确DA、打乱/错配DA、仅统计、代码-only；全分母准确率、风险与成本 |
| 验证目标是否更可靠 | 同网络与参数量、初始权重/seed、序列split、epoch/优化器、训练数据访问 | mask、SSE聚合或checkpoint准则中的一个因素 | 原107位目标、68-mask目标；统一外部MCRMSE及val/test排序/方向一致性 |
| 新方法能否泛化 | 方法及门槛开发预算、任务/trajectory隔离、冻结选法、同服务与重复规则 | 新任务/领域中的表现变化 | 当前开发26任务与独立新任务分别报告；任务簇区间、每任务差值、失败率 |

系统框架本身通过已有LLM推理，固定参数量并非所有比较的首要控制。控制生成器与比较模型、其服务快照和推理预算更贴近系统问题；记录生成候选参数量/训练资源作为机制结果。训练loss消融则固定同一网络，参数完全匹配。新聚合器/门槛/主动策略每个方法享有同等开发任务与调参次数，最终评估阶段按冻结设置执行。

在线效率应以相同质量目标的time-to-target加删失记录评价，同时记录墙钟、GPU执行区间、token/API费与重试等待。执行结果的exec_time合计约3,242.55秒（0.901小时），它包含被记录代码的执行时段，GPU采样也只是设备快照。用这些量估计纯GPU计算量时需保留测量差异。缓存读1,720次对应历史判断复用，新增模型反馈为121次；两种计数有不同成本意义。

下一份文档提供依赖顺序、修正边界和三条研究方向：[验证与Future Plan](./FUTURE_PLAN.md)。每条发现的可读详情见下方；结构化记录保存在 [findings.json](./findings.json)。

## 6 逐项证据与影响检查

### F01 批次内较早出现的最佳节点可能漏存

- **归属与状态：**作者实现；行为与一条真实轨迹端点影响已确认；P1。
- **观测：**精确方法反例保留旧incumbent。15份作者轨迹中2批满足漏更新触发条件，其中1份最终保存身份与journal最优不同：Stanford ...01abb886的95a7c811内部0.1583、私有0.256153144；发布f35059cb内部0.1645、私有0.257679528。已下载原节点代码/元数据/CSV并核对，双评分一致。你的最终节点、代码与预测一致。
- **影响边界：**已确认这条历史轨迹的已执行最佳内部节点被漏存，私有误差增加0.001526384。该数值是保存端点的差异；修正incumbent后后续搜索的反事实路径仍待新实验。另一个Statoil触发在后续被新最佳覆盖。
- **证据：**[agent.py:785](</Users/shrinn81/Documents/Data Mining/PM Final Project/ML Agent/phase1-reproduction/code/author/mle-bench/agents/aide/aide/agent.py:785>)；[diagnostics.json:1](</Users/shrinn81/Documents/Data Mining/PM Final Project/ML Agent/reports/reproducibility-audit-20261108/evidence/diagnostics.json:1>)；[author-final-reference.json:1](</Users/shrinn81/Documents/Data Mining/PM Final Project/ML Agent/phase1-reproduction/experiments/online-stanford-v2/author-final-reference.json:1>)；[verification.json:1](</Users/shrinn81/Documents/Data Mining/PM Final Project/ML Agent/reports/reproducibility-audit-20261108/evidence/author-missed-node/verification.json:1>)；解压作者aide.log第312469行为最后保存f35059cb，第450880行为执行95a7c811、第451765行为判定有效。
- **最小影响检查：**漏存节点代码/身份/原预测与双评分检查已完成；随后扩展其他运行的已发布端点绑定，并检查同批多执行的提交来源。
- **建议修正：**新修正版在每次有效执行后更新 incumbent，按节点归档复制对应预测；增加“较早最佳、随后较差/失败、跨 cutoff”反例。原版结果单独保留。

### F02 无序缓存键与有方向索引混用

- **归属与状态：**作者实现；行为/证据已确认；优先级 P1。
- **观测：**原生 A/B 查询返回 A 胜；B/A 命中缓存后变成 B 胜，模型后端仅调用一次。重跑固定 corpus：uniform-tie hit 20.4265%→21.2000%，执行集合含最佳 21.6026%→22.4359%。
- **影响边界：**差值为当前依赖样本上的描述性效果；新在线运行的结果方向待测。两个版本可能消耗不同 RNG 序列。
- **证据：**[world_model.py:314](</Users/shrinn81/Documents/Data Mining/PM Final Project/ML Agent/phase1-reproduction/code/author/mle-bench/agents/aide/aide/world_model.py:314>)；[world_model.py:323](</Users/shrinn81/Documents/Data Mining/PM Final Project/ML Agent/phase1-reproduction/code/author/mle-bench/agents/aide/aide/world_model.py:323>)；[diagnostics.json:1](</Users/shrinn81/Documents/Data Mining/PM Final Project/ML Agent/reports/reproducibility-audit-20261108/evidence/diagnostics.json:1>)；[replays.json:1](</Users/shrinn81/Documents/Data Mining/PM Final Project/ML Agent/reports/reproducibility-audit-20261108/evidence/replays.json:1>)。
- **最小影响检查：**用相同任务/候选/反馈比较原版与规范方向版；分别记录方向冲突、查询数、rank、执行集合和 regret。
- **建议修正：**以代码身份保存胜者并映射当前位置，缓存带上下文与配置指纹；发布独立 corrected ID。

### F03 Stanford 评分器对 CSV 行顺序敏感

- **归属与状态：**作者实现；行为/证据已确认；优先级 P1。
- **观测：**同一冻结预测打乱行序后，原评分 0.2663989312→0.6131057879；按 ID 连接评分保持 0.2663989312。当前提交和作者三份提交的双评分逐份一致。
- **影响边界：**冻结四份分数的影响已排除；其他历史提交的行序影响需逐份检查。此实现位于作者 vendored MLE-bench，缺陷的最初引入提交待溯源。
- **证据：**[grade.py:38](</Users/shrinn81/Documents/Data Mining/PM Final Project/ML Agent/phase1-reproduction/code/author/mle-bench/mlebench/competitions/stanford-covid-vaccine/grade.py:38>)；[grade.py:53](</Users/shrinn81/Documents/Data Mining/PM Final Project/ML Agent/phase1-reproduction/code/author/mle-bench/mlebench/competitions/stanford-covid-vaccine/grade.py:53>)；[online-verification.json:1](</Users/shrinn81/Documents/Data Mining/PM Final Project/ML Agent/reports/reproducibility-audit-20261108/evidence/online-verification.json:1>)。
- **最小影响检查：**对保存预测做 shuffle、重复/缺失/未知 ID、NaN/Inf、列/keep-mask 反例；比较原评分和 ID 评分。
- **建议修正：**新评估入口按唯一 ID 连接、验证有限值并绑定 keep；保留原评分并记录双方输出。当前独立核验已提供保护。

### F04 同批多次执行共享 submission 残留

- **归属与状态：**作者实现；行为/证据已确认；优先级 P1。
- **观测：**Agent.step 在外层迭代开始清空目录；同一淘汰赛内每个候选前沿用目录。原生 _post_process_node 在前一候选 CSV 仍存在、当前候选没有写文件的反例中保持 is_buggy=False。
- **影响边界：**完整接受还取决于执行异常与反馈模型的判定。真实发生频率及归档预测误绑定待逐候选写入来源核对。
- **证据：**[agent.py:531](</Users/shrinn81/Documents/Data Mining/PM Final Project/ML Agent/phase1-reproduction/code/author/mle-bench/agents/aide/aide/agent.py:531>)；[agent.py:722](</Users/shrinn81/Documents/Data Mining/PM Final Project/ML Agent/phase1-reproduction/code/author/mle-bench/agents/aide/aide/agent.py:722>)；[agent.py:769](</Users/shrinn81/Documents/Data Mining/PM Final Project/ML Agent/phase1-reproduction/code/author/mle-bench/agents/aide/aide/agent.py:769>)；[bridge.py:97](</Users/shrinn81/Documents/Data Mining/PM Final Project/ML Agent/phase1-reproduction/code/runtime/bridge.py:97>)；[diagnostics.json:1](</Users/shrinn81/Documents/Data Mining/PM Final Project/ML Agent/reports/reproducibility-audit-20261108/evidence/diagnostics.json:1>)。
- **最小影响检查：**A 成功写 CSV；B 正常退出却省略写入；用受控反馈走完整 parse→post-process→artifact 路径。再核对真实多执行批次写入时间/哈希。
- **建议修正：**候选执行前创建独立输出目录并清空候选提交，成功后验证新产物再归档；共享工作缓存与预测目录分别管理。

### F05 公开 corpus 含 49 对非有限分数标签

- **归属与状态：**作者实现；行为/证据已确认；优先级 P1。
- **观测：**18,438 对逐项连接核对发现 Google Quest 一份 NaN 候选参与 49 对，其中 21 对把 NaN 候选标为最佳。一份保存的作者判断为 11,312/18,438=61.3516%；去除这些对后为 11,292/18,389=61.4063%，+0.0547 pp。246 对子样本涉及 0 对；corpus26-v2 已排除此候选。
- **影响边界：**这份记录上的均值影响很小；其他两次论文判断及其他指标的影响待获得原始记录量化。
- **证据：**[group.py:77](</Users/shrinn81/Documents/Data Mining/PM Final Project/ML Agent/phase1-reproduction/code/author/prepare_bench_subset/group.py:77>)；[group.py:122](</Users/shrinn81/Documents/Data Mining/PM Final Project/ML Agent/phase1-reproduction/code/author/prepare_bench_subset/group.py:122>)；[grading.py:40](</Users/shrinn81/Documents/Data Mining/PM Final Project/ML Agent/phase1-reproduction/code/author/prepare_bench_subset/util/grading.py:40>)；[groups_google-quest-challenge_n2.json:1](</Users/shrinn81/Documents/Data Mining/PM Final Project/ML Agent/data/coverage/solutions_subset_50/google-quest-challenge/ground_truth/groups_google-quest-challenge_n2.json:1>)；[corpus-labels.json:1](</Users/shrinn81/Documents/Data Mining/PM Final Project/ML Agent/reports/reproducibility-audit-20261108/evidence/corpus-labels.json:1>)。
- **最小影响检查：**给所有实际 score 加 finite 检查，重建标签清单与分母；分别重算每个保存判断版本。
- **建议修正：**把数值有效性纳入 corpus 准入；NaN 单独列为执行/指标失败。检查 zero-score-as-bug 默认值对合法零分的影响。

### F06 候选内部验证偏离官方目标且选择信号较弱

- **归属与状态：**设计/解释；行为/证据已确认；优先级 P1。
- **观测：**最终代码把 68 个标签位置补零至 107，训练/验证对全部位置计算损失，补零位置占 36.45%；验证平均 batch RMSE，最终反馈采用 20% holdout 的 best-epoch 0.4378，另报 CV 均值 0.4618。13 份有效候选事后 Spearman=0.2363；内部所选外部 0.266399，同集合事后最优 0.256687，差 0.009712。
- **影响边界：**选择差距是已执行集合上的事后 oracle 诊断。损失遮罩、训练质量筛选、验证采样和模型改变的各自贡献待控制实验。
- **证据：**[final_solution.py:145](</Users/shrinn81/Documents/Data Mining/PM Final Project/ML Agent/phase1-reproduction/experiments/online-stanford-v2/final_solution.py:145>)；[final_solution.py:287](</Users/shrinn81/Documents/Data Mining/PM Final Project/ML Agent/phase1-reproduction/experiments/online-stanford-v2/final_solution.py:287>)；[final_solution.py:366](</Users/shrinn81/Documents/Data Mining/PM Final Project/ML Agent/phase1-reproduction/experiments/online-stanford-v2/final_solution.py:366>)；[final_solution.py:396](</Users/shrinn81/Documents/Data Mining/PM Final Project/ML Agent/phase1-reproduction/experiments/online-stanford-v2/final_solution.py:396>)；[final_solution.py:443](</Users/shrinn81/Documents/Data Mining/PM Final Project/ML Agent/phase1-reproduction/experiments/online-stanford-v2/final_solution.py:443>)；[agent.py:839](</Users/shrinn81/Documents/Data Mining/PM Final Project/ML Agent/phase1-reproduction/code/author/mle-bench/agents/aide/aide/agent.py:839>)；[candidate-scores.json:1](</Users/shrinn81/Documents/Data Mining/PM Final Project/ML Agent/reports/reproducibility-audit-20261108/evidence/candidate-scores.json:1>)。
- **最小影响检查：**固定网络、序列 split、seed、epoch 与优化器，比较 all-107 与真实 68-mask；以全验证集累积 SSE 后计算 MCRMSE；分别报告 SN_filter 子组。
- **建议修正：**先建立 metric/split/mask/checkpoint 合约及机器可读输出；修正版中对齐候选内部目标。现有冻结训练方案继续标作原始输出。

推断后处理补充：[final_solution.py:507](</Users/shrinn81/Documents/Data Mining/PM Final Project/ML Agent/phase1-reproduction/experiments/online-stanford-v2/final_solution.py:507>)将预测裁剪到[-2,2]，内部验证使用原始输出。统一评价契约应让内部验证与实际提交采用同一后处理。

### F07 缓存复读直至轮数安全退出

- **归属与状态：**设计/解释；行为/证据已确认；优先级 P2。
- **观测：**恒低置信度 10 候选反例产生 21 轮、294 条记录、13 次新后端反馈。真实 7 个完整批次均到安全上限；1,841 条记录含 1,720 缓存读取（93.43%），121 个新请求；3 批全部比较都未通过门控。
- **影响边界：**这是有限轮数设计下的信息停滞，代码会按既定安全规则结束。缓存复读本身通常很便宜；可节约的 API、墙钟时间与最终性能分别实测。
- **证据：**[world_model.py:543](</Users/shrinn81/Documents/Data Mining/PM Final Project/ML Agent/phase1-reproduction/code/author/mle-bench/agents/aide/aide/world_model.py:543>)；[world_model.py:555](</Users/shrinn81/Documents/Data Mining/PM Final Project/ML Agent/phase1-reproduction/code/author/mle-bench/agents/aide/aide/world_model.py:555>)；[world_model.py:606](</Users/shrinn81/Documents/Data Mining/PM Final Project/ML Agent/phase1-reproduction/code/author/mle-bench/agents/aide/aide/world_model.py:606>)；[diagnostics.json:1](</Users/shrinn81/Documents/Data Mining/PM Final Project/ML Agent/reports/reproducibility-audit-20261108/evidence/diagnostics.json:1>)；[online-verification.json:1](</Users/shrinn81/Documents/Data Mining/PM Final Project/ML Agent/reports/reproducibility-audit-20261108/evidence/online-verification.json:1>)。
- **最小影响检查：**记录每轮新增唯一反馈、状态变化与耗时；比较只停复读、优先新对和原版，固定反馈预算。
- **建议修正：**先增加可观察性；将无新证据停止和新对优先分别立项，以信息与成本收益决定保留。

### F08 Top-k 实际指显示名次组并带概率与强制回退

- **归属与状态：**论文—代码歧义；行为/证据已确认；优先级 P1。
- **观测：**配置 Top-k=1 仍可能让多个 rank-0 候选各以 p=0.2 执行；全未触发时强制执行第一位 rank-0。真实批次执行数含 2、3；全部低置信度的批次也进入执行。唯一 rank-0 时，无论概率结果如何，最终都执行该节点。
- **影响边界：**按候选数理解 top-k 或把 0.2 理解为整个批次执行率，会改变成本与方法含义。当前复现跟随发布代码。
- **证据：**[world_model.py:629](</Users/shrinn81/Documents/Data Mining/PM Final Project/ML Agent/phase1-reproduction/code/author/mle-bench/agents/aide/aide/world_model.py:629>)；[world_model.py:653](</Users/shrinn81/Documents/Data Mining/PM Final Project/ML Agent/phase1-reproduction/code/author/mle-bench/agents/aide/aide/world_model.py:653>)；[agent.py:697](</Users/shrinn81/Documents/Data Mining/PM Final Project/ML Agent/phase1-reproduction/code/author/mle-bench/agents/aide/aide/agent.py:697>)；[agent.py:744](</Users/shrinn81/Documents/Data Mining/PM Final Project/ML Agent/phase1-reproduction/code/author/mle-bench/agents/aide/aide/agent.py:744>)；[diagnostics.json:1](</Users/shrinn81/Documents/Data Mining/PM Final Project/ML Agent/reports/reproducibility-audit-20261108/evidence/diagnostics.json:1>)。
- **最小影响检查：**对 singleton、并列组、全概率失败、全低 confidence 做执行集合与计数核对；原版和 exact-one 语义分别测。
- **建议修正：**报告明确组名次和回退语义。精确 Top-k 属于独立算法变体，k=2 结论需在 F01/F04 修复后再评。

### F09 候选生成在发布代码中串行进行

- **归属与状态：**论文—代码歧义；行为/证据已确认；优先级 P2。
- **观测：**_improve_batch 逐个请求，并把前面计划加入后续提示；在线日志按此流程执行。比较请求才使用线程池。
- **影响边界：**并行生成会同时改变延迟、可见计划和候选分布，属于方法变更；它对论文加速解读的影响需独立控制。
- **证据：**[agent.py:368](</Users/shrinn81/Documents/Data Mining/PM Final Project/ML Agent/phase1-reproduction/code/author/mle-bench/agents/aide/aide/agent.py:368>)；[agent.py:402](</Users/shrinn81/Documents/Data Mining/PM Final Project/ML Agent/phase1-reproduction/code/author/mle-bench/agents/aide/aide/agent.py:402>)；[agent.py:423](</Users/shrinn81/Documents/Data Mining/PM Final Project/ML Agent/phase1-reproduction/code/author/mle-bench/agents/aide/aide/agent.py:423>)；[world_model.py:420](</Users/shrinn81/Documents/Data Mining/PM Final Project/ML Agent/phase1-reproduction/code/author/mle-bench/agents/aide/aide/world_model.py:420>)。
- **最小影响检查：**同一生成预算比较串行带计划记忆与并行统一提示；记录候选多样性、token、延迟和固定池质量。
- **建议修正：**本复现标明采用串行发布实现；效率实验同时报告生成、比较、执行、反馈和传输耗时。

### F10 响应校验与全局缓存上下文不足

- **归属与状态：**作者实现；行为/证据已确认；优先级 P2。
- **观测：**原生测试接受 confidence=1.2、Infinity、True、越界 winner；缺 winner 时默认为 0。跨实例、跨任务/阈值复用缓存时，0.65 在第二个 0.7 gate 下仍沿用旧 valid=True。
- **影响边界：**实际单任务运行中这些异常的出现次数与同对竞争请求影响待核对；每任务独立进程降低跨任务污染机会。
- **证据：**[world_model.py:244](</Users/shrinn81/Documents/Data Mining/PM Final Project/ML Agent/phase1-reproduction/code/author/mle-bench/agents/aide/aide/world_model.py:244>)；[world_model.py:287](</Users/shrinn81/Documents/Data Mining/PM Final Project/ML Agent/phase1-reproduction/code/author/mle-bench/agents/aide/aide/world_model.py:287>)；[world_model.py:356](</Users/shrinn81/Documents/Data Mining/PM Final Project/ML Agent/phase1-reproduction/code/author/mle-bench/agents/aide/aide/world_model.py:356>)；[audit_foreagent_mechanisms.py:88](</Users/shrinn81/Documents/Data Mining/PM Final Project/ML Agent/audit_foreagent_mechanisms.py:88>)；[diagnostics.json:1](</Users/shrinn81/Documents/Data Mining/PM Final Project/ML Agent/reports/reproducibility-audit-20261108/evidence/diagnostics.json:1>)。
- **最小影响检查：**严格类型、范围、有限值与必需字段反例；跨任务/模型/阈值缓存与并发反向同对测试；对原始回执统计异常频率。
- **建议修正：**新修正版先验证 schema，缓存存原始有效判断并重新应用当前 gate；实例隔离、完整上下文键和同对锁分别验证。

### F11 置信度有区分信号，概率校准仍有明显差距

- **归属与状态：**设计/解释；行为/证据已确认；优先级 P1。
- **观测：**一份作者静态反馈中 c≥0.7 的 10,531 对准确率 65.38%，平均 c=73.62%；你的子样本高置信度 162 对准确率 62.96%，平均 c=74.54%。当前在线 3/7 批全部比较均低于门槛。
- **影响边界：**这些是相关静态样本上的描述性风险；当前在线 sibling 分布中的校准与错误拒绝代价需要新反馈或补全候选结果。
- **证据：**[confidence.json:1](</Users/shrinn81/Documents/Data Mining/PM Final Project/ML Agent/reports/reproducibility-audit-20261108/evidence/confidence.json:1>)；[diagnostics.json:1](</Users/shrinn81/Documents/Data Mining/PM Final Project/ML Agent/reports/reproducibility-audit-20261108/evidence/diagnostics.json:1>)；[world_model.py:360](</Users/shrinn81/Documents/Data Mining/PM Final Project/ML Agent/phase1-reproduction/code/author/mle-bench/agents/aide/aide/world_model.py:360>)。
- **最小影响检查：**按任务隔离校准/测试，报告 coverage-risk、Brier、ECE 与高置信度错误；去除 F05 对后作敏感性检查。
- **建议修正：**把 c 当待验证分数；先测试静态 0.7 gate 和开发集拟合校准器，再进入独立任务评估。

### F12 现有证据对应不同估计对象与独立单位

- **归属与状态：**设计/解释；行为/证据已确认；优先级 P1。
- **观测：**在线为 1 任务×1 次；历史 129/129 为给定反馈及日志概率结果的条件重演；7,800 次固定池回放复用 26 任务、2,600 池实例与重叠候选；246 对为真实调用子样本，always-index-0 为 131/246，模型 136/246。记录已披露这些边界。
- **影响边界：**单次可用性、离线选择质量、总体 pairwise 能力与端到端系统优越性需要各自证据。
- **证据：**[protocol-v2.json:1](</Users/shrinn81/Documents/Data Mining/PM Final Project/ML Agent/phase1-reproduction/code/runtime/protocol-v2.json:1>)；[historical-129-batches.json:1](</Users/shrinn81/Documents/Data Mining/PM Final Project/ML Agent/phase1-reproduction/experiments/supporting/historical-129-batches.json:1>)；[protocol.json:1](</Users/shrinn81/Documents/Data Mining/PM Final Project/ML Agent/experiments/corpus26-v2/protocol.json:1>)；[replays.json:1](</Users/shrinn81/Documents/Data Mining/PM Final Project/ML Agent/reports/reproducibility-audit-20261108/evidence/replays.json:1>)。
- **最小影响检查：**以 task 和独立 online run 为统计单位；候选池内配对、跨任务汇总；为新任务及新 API 反馈另设前瞻协议。
- **建议修正：**保持当前单任务验收结论；对泛化或优越性新增匹配重复实验、任务簇区间和明确 estimand。

### F13 系统效果与筛选机制贡献需要不同公平控制

- **归属与状态：**设计/解释；行为/证据已确认；优先级 P1。
- **观测：**两种发布配置共享 code/feedback/search/时间设置，零调用构造通过；ForeAgent 额外生成候选、使用报告和比较模型。你的在线模型服务、硬件与网络条件也有变化。
- **影响边界：**同墙钟比较可以回答系统效用；机制归因仍同时受到候选数量、提示信息、额外推理和调参机会影响。
- **证据：**[config.yaml:1](</Users/shrinn81/Documents/Data Mining/PM Final Project/ML Agent/phase1-reproduction/code/author/mle-bench/agents/aide/config.yaml:1>)；[config.json:1](</Users/shrinn81/Documents/Data Mining/PM Final Project/ML Agent/reports/reproducibility-audit-20261108/evidence/config.json:1>)；[actual-first-prompt-audit.json:1](</Users/shrinn81/Documents/Data Mining/PM Final Project/ML Agent/phase1-reproduction/records/stanford-autodl-v2/actual-first-prompt-audit.json:1>)。
- **最小影响检查：**先做固定 sibling 池中的随机单选/同预算聚合/原版/修正版；再在同硬件、同服务、同预算的新在线 cohort 比较。
- **建议修正：**按研究问题分别匹配墙钟、token、唯一反馈和执行次数；明确额外信息及调参预算；保存成本—效用曲线。

### F14 部分评估函数采用容易误读的分母与指标名称

- **归属与状态：**作者实现；行为/证据已确认；优先级 P2。
- **观测：**aggregate_metrics 仅对含 numeric accuracy 的结果求平均；1 次正确+1 次失败的反例报告 100%。precision_at_k 实现严格有序前缀匹配；这与通常的 top-k 集合重合比例含义不同。
- **影响边界：**作者完整三次主表里实际失败率、分母和 listwise 汇总方式需要原记录及绘表代码核验；当前复现246对补调后有效率100%。
- **证据：**[report.py:7](</Users/shrinn81/Documents/Data Mining/PM Final Project/ML Agent/phase1-reproduction/code/author/grade/util/report.py:7>)；[runner.py:124](</Users/shrinn81/Documents/Data Mining/PM Final Project/ML Agent/phase1-reproduction/code/author/grade/util/runner.py:124>)；[eval.py:40](</Users/shrinn81/Documents/Data Mining/PM Final Project/ML Agent/phase1-reproduction/code/author/grade/util/eval.py:40>)；[diagnostics.json:1](</Users/shrinn81/Documents/Data Mining/PM Final Project/ML Agent/reports/reproducibility-audit-20261108/evidence/diagnostics.json:1>)。
- **最小影响检查：**逐运行并列输出 planned、attempted、valid、correct 与 full-denominator accuracy；给交换 top-2 顺序的集合构造反例。
- **建议修正：**指标改名 exact-prefix@k，另报标准 precision@k；服务失败率与条件准确率并列，失败处理事先固定。

### F15 服务、随机状态和历史环境仍有复现缺口

- **归属与状态：**复现专属；行为/证据已确认；优先级 P2。
- **观测：**作者外层 seed 字段用于重复任务/日志，调用链没有向 Agent 注入该 seed；Agent 内 shuffle/choice/Bernoulli、LLM temperature 与线程调度均影响轨迹。新运行留存模型回执与镜像摘要，历史权重快照和 RNG 状态较少。一次反馈及重试 13,491.88 秒，占12小时31.23%；旧控制器依赖存在事后冲突，新验收环境已独立锁定。
- **影响边界：**每次请求的可用随机种子、模型服务差异、CPU 配额及网络延迟对分数影响待前瞻控制。长等待的 VPN 原因为实验者事后说明；日志直接支持请求含重试耗时。
- **证据：**[run_agent.py:71](</Users/shrinn81/Documents/Data Mining/PM Final Project/ML Agent/phase1-reproduction/code/author/mle-bench/run_agent.py:71>)；[agent.py:129](</Users/shrinn81/Documents/Data Mining/PM Final Project/ML Agent/phase1-reproduction/code/author/mle-bench/agents/aide/aide/agent.py:129>)；[agent.py:167](</Users/shrinn81/Documents/Data Mining/PM Final Project/ML Agent/phase1-reproduction/code/author/mle-bench/agents/aide/aide/agent.py:167>)；[controller.py:49](</Users/shrinn81/Documents/Data Mining/PM Final Project/ML Agent/phase1-reproduction/code/runtime/controller.py:49>)；[model_gateway.py:14](</Users/shrinn81/Documents/Data Mining/PM Final Project/ML Agent/phase1-reproduction/code/runtime/model_gateway.py:14>)；[environment.json:1](</Users/shrinn81/Documents/Data Mining/PM Final Project/ML Agent/phase1-reproduction/experiments/environment-acceptance/environment.json:1>)；[final-summary.json:1](</Users/shrinn81/Documents/Data Mining/PM Final Project/ML Agent/phase1-reproduction/experiments/online-stanford-v2/final-summary.json:1>)。
- **最小影响检查：**G1 先保存实际 worker 包/driver/cgroup/affinity、服务 revision、请求参数、RNG/hash seed；同环境开展独立重复并记录所有启动尝试。
- **建议修正：**记录重复编号与真实 seed 的区别；使用稳定控制器与有界、可观测重试；失败/补跑规则在新协议中先固定。

依赖补充：作者[requirements.txt](</Users/shrinn81/Documents/Data Mining/PM Final Project/ML Agent/phase1-reproduction/code/author/mle-bench/agents/aide/requirements.txt:1>)列出scikit-learn1.2.2，而[评分器](</Users/shrinn81/Documents/Data Mining/PM Final Project/ML Agent/phase1-reproduction/code/author/mle-bench/mlebench/competitions/stanford-covid-vaccine/grade.py:3>)使用1.4新增的root_mean_squared_error；本机验收1.4.2已成功。按文本requirements重装与按固定镜像/验收锁定环境运行需要分别核验。

### F16 经验现象的理论和因果外推需要收紧

论文定位：[ACL PDF](https://aclanthology.org/2026.acl-long.182.pdf) 第7页§5.3–5.4/Discussion6.1、第15页B.3、第21页C.3。

- **归属与状态：**设计/解释；行为/证据已确认；优先级 P2。
- **观测：**当前静态验证信号、定性案例、不同模型配置的观测各自回答局部问题。有限样本的一致率、模型尺寸对比与任务归属都需要相应统计和干预设计。
- **影响边界：**作者经验性上界表述、因果推理归因及广义泛化解释超出这些观测直接识别的范围；这项判断针对论证强度。
- **证据：**[reading-original.md:1](</Users/shrinn81/Documents/Data Mining/PM Final Project/ML Agent/phase1-reproduction/experiments/environment-acceptance/reading-original.md:1>)。
- **最小影响检查：**72.2% 按经验代理一致率重算并给区间；人类比较补样本/盲评协议；尺寸效应在共同训练与推理条件下控制；明确 seen 指 corpus 可见还是模型训练可见。
- **建议修正：**使用经验一致率、相关证据和任务级迁移措辞；基于假设写出可证定理，或用预注册控制实验建立更强结论。

### F17 本机检出与已发布修订的版本区别已核清

- **归属与状态：**复现版本追踪；已解决并核验；P2历史记录。
- **观测：**本机仍为main@9442373且phase1跟踪0文件；发布收据给出hw3-phase1-v1对应89d428f。只读认证gh API确认已发布README、SOURCES、RELEASE_ASSETS与当前本机字节完全相同。新清单947项含完整records/data和原件全部通过。
- **版本关系：**起始manifest SHA256为`bdf1bf53c25b439c7bdaf8adf0bd57a3cbe98dd0a9796a79ddca771e469b5d36`，更新后为`43080d024af67643d48c2ec0282811bb64e755a000d1228bc3a236bb1ed71fe6`。数值审计基于已核对的固定代码/实验产物，发布布局更新作为另一项版本记录。
- **证据：**[发布回执](../../provenance/hw3-release.json)、[本次发布字节核对](./evidence/publication-check.json)、[最新全量校验](./evidence/copy-full-verification.log)。GitHub连接器访问该私有仓库返回404，核对经本机已认证gh的GET完成。
- **后续检查：**从发布修订与Release附件执行完整独立重建及启动入口核验。本次新审计文件单独归档。
