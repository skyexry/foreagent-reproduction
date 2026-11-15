# 第三部分事实核对与证据说明

核对基点：GitHub/main `a80ae9cb0ea15a6f2c3d5666528a01a3006009c5`。通过GitHub连接器回读三份主要结果，并与本机Git blob逐项匹配；重新解析246份采用响应、独立重算分数方向与标签。新训练/模型API调用为0。

页码均为PDF物理页；括号内为论文印刷页码。原文数据不经已有proposal转述：Table 2为p.5(3945)，Table 5/§6.3为p.8(3948)，Table 13为p.27(3967)，硬件为Appendix C.8 p.22(3962)。

## A. 简短事实核对表

| 层次/任务 | 实际范围与次数 | 模型及参数 | 预算、硬件与指标 | 证据 |
|---|---|---|---|---|
| 原论文pairwise | 26任务、18,438对；3次均值 | DeepSeek-V3.2-Thinking；GPT-5.1 (`gpt-5.1-2025-11-13`)；温度1.0 | micro-accuracy；API模型推理硬件未记录，论文整体实验平台见C.8 | §3.3/§4.1/Table 2，PDF pp.3–5；C.8 p.22 |
| 我的pairwise | 同一18,438对来源池，26任务最多各10对，共246对；一次样本评估，20次失败各补调一次，共266请求 | `Pro/deepseek-ai/DeepSeek-V3.2`，SiliconFlow，thinking=true，温度1.0，max_tokens8192，thinking_budget32768；具体服务快照未记录 | Python3.12.5客户端；推理硬件未记录；首轮¥20限额，补调取消该限额；总墙钟限额未设置，精确首轮起止未记录；micro-accuracy | R1；原件 `outputs/coverage-20261021/pair-*.json`、`retry-attempt-002/`；本次246响应重解析收据 |
| 原论文系统实验 | 5任务，每任务3次，按任务报告平均Beat Ratio | DeepSeek-V3.2生成、Thinking比较；发布配置另指定`gpt-4o-mini-2024-07-18`反馈；m=10,c=0.7,k=1,p_exec=0.2 | 每次12小时；Xeon Gold6138/80逻辑核，6个并行worker各分配1张RTX3090 24GB；Beat Ratio | Table5/§6.2–6.3 p.8；Table13 p.27；C.8 p.22；冻结作者config.yaml |
| 我的Stanford COVID Vaccine | **Seen**；2,160训练/240私有测试RNA序列；25,680行预测，其中16,320行的3个目标计分；1次正式运行 | 同上系统角色；生成/反馈温度0.5，比较请求温度1.0；复用作者数据报告、原算法与参数 | 43,200秒；RTX4090 24GB；原OCI/PRoot worker，Mac controller；MCRMSE、Beat Ratio | R2；原件 `phase1-reproduction/records/stanford-autodl-v2/logs/exp/{journal.json,aide.log}`及节点CSV |
| 我的Aerial Cactus Identification | **Unseen**；14,175训练/3,325私有测试图像；1次正式运行 | 同上系统角色和温度；原OCI worker Python3.11.13/torch2.2.0+cu121；独立controller Python3.12 | 43,200秒；RTX3090 24GB/15核CPU配额；controller/worker均AutoDL；ROC AUC、Beat Ratio | R3；原件在已交付完整记录包的 `records/runs/cactus-formal-v1/`，含api.jsonl、api-records、tasks及all_nodes |

Seen/Unseen采用论文相对主pairwise语料的分类；该词在此描述任务覆盖。作者并未为这套ForeAgent比较器重新训练模型。两次系统复现均以私有集作结束后的外部评分，最终程序由原内部验证规则选择。

### 来源索引

- **R1**：[最终pairwise结果](https://github.com/skyexry/foreagent-reproduction/blob/a80ae9cb0ea15a6f2c3d5666528a01a3006009c5/experiments/coverage_retry_results.json)、[固定抽样与分数标签](https://github.com/skyexry/foreagent-reproduction/blob/a80ae9cb0ea15a6f2c3d5666528a01a3006009c5/experiments/coverage_manifest.json)、[首轮评分规则](https://github.com/skyexry/foreagent-reproduction/blob/a80ae9cb0ea15a6f2c3d5666528a01a3006009c5/experiments/coverage_scoring.md)。首轮原件与补调原件路径见表格；本次重解析收据在 `evidence/pairwise-response-reparse.json`。
- **R2**：[Stanford最终结果](https://github.com/skyexry/foreagent-reproduction/blob/a80ae9cb0ea15a6f2c3d5666528a01a3006009c5/experiments/online-stanford-v2/final-summary.json)、[作者三次终点](https://github.com/skyexry/foreagent-reproduction/blob/a80ae9cb0ea15a6f2c3d5666528a01a3006009c5/experiments/online-stanford-v2/author-final-reference.json)、[原验证语义及轨迹核查](https://github.com/skyexry/foreagent-reproduction/blob/a80ae9cb0ea15a6f2c3d5666528a01a3006009c5/reports/hw3/analysis/README.md)。
- **R3**：[Aerial最终结果](https://github.com/skyexry/foreagent-reproduction/blob/a80ae9cb0ea15a6f2c3d5666528a01a3006009c5/experiments/online-cactus-v1/final-summary.json)、[作者三次原始成绩与固定来源](https://github.com/skyexry/foreagent-reproduction/blob/a80ae9cb0ea15a6f2c3d5666528a01a3006009c5/experiments/online-cactus-v1/evidence/cactus-author-comparison-reference.json)。完整记录包SHA-256为 `44b6a2a8cc37d716e1e35eff4c521e1bc0251a3c51dec96eff9abd87bf71938c`。
- **R4**：本次新增只读派生结果 `evidence/verified-facts.json`、`beat-ratio-verification.json`、`node-time-reference.json`、`runtime-comparison-coverage.json`。两个排行榜的内容均与作者固定提交LFS SHA-256完全相同；实际复用了此前已下载的校验副本。

## B. 两层结果与比较口径

两张英文表及可直接采用的英文第三部分见 `Proposal_Section3_Reproduction.md`。

- Pairwise：136/246=55.28455%；论文主结果61.5±0.2%，相差−6.21545个百分点；这是**范围不同的描述性差**。同一246对的作者一次归档为130/246=52.84553%，同输入差为+2.43902个百分点。标签方向和micro规则一致；原顺序保留、按任务最多10对的抽样改变了论文全量micro权重。
- 首轮123/246=50.00%，有效输出226/246；有效输出内123/226=54.42478%。20个失败样本各补调一次后才得到136/246；采用首轮有效结果，失败才采用补调，记录逐对证明生成输入/参数保持。两种分母和阶段分别报告。论文同等失败重试规则未记录。
- 模型表仅列有新调用原件的DeepSeek思考模式；GPT-5.1的58.8±0.3%属于论文Table2，复现准确率未记录。后续其他离线选择实验使用的GPT归档不等同于新增pairwise推理。
- 系统主要指标：Stanford BR=1636/1636=1.000；Aerial BR=1071/1221=0.8771498771，均与作者归档同值、与论文精度吻合。Aerial0.99994是原评分器五位小数值，原始AUC为0.9999375316002257；作者0.99992/0.99993/0.99991均为发布精度。
- 辅助指标来源为作者归档，区分于论文表格：Stanford MCRMSE均值0.25862，复现0.26640，高0.00778约3.0%；Aerial均值0.99992，复现0.99994，高0.00002。排行榜桶状阈值使二者BR保持。
- 共同节点定义为最终journal保存条目，含跳过候选、排除未完成且未入journal的候选。Stanford作者183/142/141→均值155.33，本次82；Aerial作者59/60/29→49.33，本次82。
- 时间统一取最终选中节点的反馈解析完成时刻减日志起点。本次Stanford3.46057h、Aerial6.85550h；作者各任务均值7.34456h、1.02225h。它们测量的是**不同运行各自最终选中方案的可用时间**；共同测试目标命中时间/测试最优时间属于另一个指标。原论文6倍提速需要共同目标及AIDE对照另行核验。

## C–D. 吻合程度与发现的问题

### 日志或源码已证实

1. **BR吻合掩盖细粒度差异。** Stanford的私有误差比作者均值高约3%，但所有终点都超过冻结排行榜的最佳分0.34198，所以BR都为1；Aerial的四个终点都落在相同排行榜阈值区间。该指标是离线准备划分的分数与历史Kaggle排行榜阈值作比较，含跨划分差异；它不是在同一Kaggle隐藏测试集上新提交并超越人类的独立证据。
2. **静态准确率与在线准确率分开。** 本次Aerial86次新比较中16次confidence≥0.7（18.60%），这是高置信覆盖率。精确代码SHA对照发现双侧均有保存预测CSV的比较为0对，测试准确率分母为0、数值未定义；原响应保存完整也需要未执行代码的测试标签才能补齐准确率。19次请求的相同代码还对应多个节点ID，文件记录保留了这项身份歧义。
3. **首轮/补调和分母改变headline accuracy。** 50.00%是首轮全样本正确率，54.42%是首轮有效输出准确率，55.28%是失败补调后全样本正确率。该246对的真实赢家位置为131/115，总选位置0的准确率为53.25%；55.28%只比这个常数基准多5对正确。数据按任务与重复方案聚类，结论保留描述性口径。
4. **Stanford内部验证口径与正式评分不同。** 最终代码把68位标签补零至107位，并把全部107位纳入batch级3列RMSE；正式评分仅在68位有效位置聚合。原内部值0.4378和私有MCRMSE0.26640衡量不同数据/计算。已有事后测试最佳保存节点0.256687在2.69h，但最终选中节点0.266399，差0.009712；该差提供选择失配证据，各原因贡献仍待隔离。
5. **Aerial原float解析器拒绝整数指标。** 两次执行成功、CSV有效，反馈工具却返回整数metric=1；原`agent.py`只接受float，因此将其置空并标为buggy。故13份成功提交对应11个原Agent有效节点，原始分类保留。另4次REPL固定10秒ready窗口失败、1次执行预算中断均留档。
6. **预算和部署影响有可观测记录。** Stanford一个反馈请求及重试耗时13,491.88秒，约占12小时预算31.2%。Mac熄屏/VPN断连为实验者在结束后确认的归因；日志证明请求耗时与重试，VPN中断的独立持续时间未记录。Aerial200个API全HTTP200，600份原文完整，31个执行结果及1个预算中断保留。
7. **正文描述与发布实现有细节差异。** 论文§6.2称十候选并行生成，发布`_improve_batch`用循环顺序调用生成。Top-1是配置的rank门槛；并列rank0候选各按0.2概率执行，全部跳过时强制执行一个。因此Aerial某一批实际执行4份候选、Stanford有批次执行2/3份，符合发布实现。相关控制规则随原版保留。
8. **节点计数待对齐。** 论文Figure4c Stanford为158.67；三份公开最终journal均值为155.33，图示计数口径待对齐。Aerial图示49.33与归档均值相符。本文表述用共同journal定义，论文Stanford图示的额外计数来源待核对。

### 待验证解释

服务商快照/采样实现变化、随机采样、候选重复与在线方案质量分布、PRoot/硬件/CPU资源对时序的影响均可能参与差异；现有日志分别确认了部分条件，因果贡献尚未量化。Stanford验证口径失配、缓存方向问题与低置信度都可能影响选择，现有证据不足以把最终误差差距全部归于其中一项。Aerial四次ready超时的具体启动耗时点仍待诊断。

## 仍需核对的具体数据

1. 原论文及本次服务端的确切DeepSeek权重/快照、部分服务端采样默认值：未记录；复现GPT-5.1静态accuracy：未记录。
2. 论文完整18,438对和三次重复的同协议新推理结果，以及精确失败输出/重试政策；本次覆盖246对、失败补调规则另有原件。
3. 在线比较器同定义的测试准确率：Aerial两侧都有CSV的直接可评分比较0对；未执行候选的测试结果仍缺。Stanford完整新响应正文、全量置信度与provider request ID未记录，已知首轮35次fresh子集仍可核验。
4. 论文Figure4c Stanford158.67与发布journal均值155.33的计数差；具体额外节点/未完成批次计入方式待核对。
5. 达到同一测试目标的逐次时间，以及相同预算下AIDE对照的本次运行：未记录。本文的最终选中方案时间与事后测试最优时间各自分开。
6. 每任务另外两次重复、另外三个论文任务的本次系统结果：未记录；单次方差、五任务平均及广泛unseen泛化保持后续验证范围。
7. 原因分解：独立VPN断开时长、Aerial ready启动分段计时、指标标准化/缓存问题对最终分数的隔离效应：未记录。

本次仅做原件回读、派生计算与写作，新增训练、模型推理和候选私有评分均为0。
