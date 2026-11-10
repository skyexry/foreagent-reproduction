# ML Agent 项目交接：ForeAgent / ForeCritic

**2026-11-10 · 改选对补分与 HW3 润色**　[HW3 审阅稿](../reports/hw3/HW3_Execution_Memory_Review.pdf) · [预测文件审计与 GPU 预算](../experiments/paired-prediction-audit/README.md)。80 个已知改选对中，0 对两边都有预测；32 对重算出单边官方分数（28 个 C0、4 个记忆端点），48 对双方均缺。下一步供审阅：Stanford 与 Statoil 各 3 对，单边补跑 6 份约 0.24–0.45 卡时，或同条件重跑 12 份约 0.47–0.90 卡时（按历史中位数、上四分位数折算，不含准备）。报告第 1–3 节由 Claude Opus 5.5 润色，第 8 页 Future Plan 逐字及渲染像素核对一致。

**2026-11-10 · C0 与执行记忆的 CPU 回放**　[HW3 审阅稿，第 8 页](../reports/hw3/HW3_Execution_Memory_Review.pdf) · [逐批结果与复核](../experiments/c0-memory-switch-v1/README.md)。16 次运行、136 批中，按归档裁判判断可完整还原 C0 的有 128 批，加入记忆后 80 批改选；另有 1 批虽无法还原唯一首选，仍可确定改选。接口可接受的 130 批合计 81 改、48 同、1 未知。80 个具体改选对中，双方都有可用旧验证分的为 0。下一步：审阅报告后，在预定任务、相同划分与训练预算下实测分歧对。 研究问题保持开放：执行记忆列为首个实验，裁判改进、何时执行、生成与搜索是后续选项。以下保留各轮记录。

**状态核对：2026-11-10。固定候选池的离线选优研究已收尾，默认保留 C0；下一轮处于选题讨论阶段，具体方法与实验方案待选定。** 新聊天先读本页“项目快照—已尝试方向—备选与下一步”，再按证据链接展开。以下结论由历史聊天与本机实验记录交叉核对；各实验文档中的“下一步”保留其阶段含义，当前决策以本页及 [研究状态](STATUS.md) 为入口。

## 项目快照

- **主线问题：** 在有限预算下，ML Agent 怎样利用候选比较与执行反馈，更可靠地决定获取什么证据、运行哪份方案？项目仓库：[skyexry/foreagent-reproduction](https://github.com/skyexry/foreagent-reproduction)。
- **三个版本：** 作者原版用于忠实复现；C0 是修正已确认错误、保留原淘汰赛策略的工作基线；新方法在 C0 上做同条件比较。原版 Stanford 单任务标准 12 小时的官方 MCRMSE 为 **0.26640**，越低越好；该成绩归属作者原版流程。C0 已通过短训练与受控集成验收。[原版材料](../phase1-reproduction/README.md) · [C0 修正与短测](../experiments/clean-ranking-v1/先读结果.md)
- **已有证据分层：** 真实 API 子样本为本项目 **136/246（55.28%）**、作者同样本 **130/246（52.85%）**，评价两两判断；历史 129 批为条件回放；主研究环境为 **26 个开发任务、425 池、850 场**的冻结反馈离线选优。三者与单任务在线成绩分别报告。[原版覆盖表](selection-study-v1/baseline.md) · [实验账本](../EXPERIMENTS.md)
- **共同评价：** 任务等权归一化选择损失（低为好）、最佳候选命中率、查询量及任务簇区间；并列按均匀选择计算期望。C0 在主 DeepSeek 归档上的选择损失 **0.26416**、命中率 **23.67%**。表中“收益”统一为对照损失减方法损失，正值有利；“损失差”另标方向。
- **适用范围：** 现有 26 任务均已参与开发分析；留任务训练衡量本轮微调的任务迁移，前瞻泛化留给方法冻结后的新任务。离线反馈读取数、CPU 耗时与真实 API / 训练费用分别计量。C0 的短链路验收、历史答案干预和离线收益，各自对应不同证据层级。

## 已尝试方向、结果与暂缓原因

| 方向与具体实现 | 已观察结果 | 当前决定与原因 | 证据 |
|---|---|---|---|
| **正确性修正：C0**；缓存方向/上下文、最佳节点保存、提交隔离、评分入口等 | 三架构共 6 次短训练、标签对照及真实 Agent 类受控集成完成；同输入验证最佳节点保存修正 | **保留为工作基线**，后续把修复收益与方法收益分别归因 | [修正与验收](../experiments/clean-ranking-v1/先读结果.md) |
| **早期胜率汇总：R6 / R7 / R8**；简单胜率、按有效比较数破同分、跨 GPT 反馈复验 | 旧 7,800 场中 R6→R7 命中率 22.50%→22.90%，损失 0.27925→0.26950；GPT 合并损失差区间仍跨零 | **历史存档**；后续按用户要求从原始数据独立建立 C0 与新评测，旧轮次数字保留各自协议口径 | [历史账本](../EXPERIMENTS.md#r6--相同反馈下的简单胜率汇总--运行前注册) |
| **主动选边与补覆盖**；先覆盖后主动补问、优先补有效比较稀缺者、D1 再问一步 | 首轮主动策略损失 0.29073、命中 19.27%，C0 为 0.26416 / 23.67%；D1 主动减随机损失差 +0.00289，95% 区间 [−0.01313,+0.02352]；后续有效覆盖改善，选择收益随裁判变化 | **结束这些先导，保留 C0**；覆盖增加与最终选择改善之间仍需新的机制解释 | [首轮](../experiments/clean-ranking-v1/先读结果.md) · [D1](../experiments/selection-frontier-01/d1/README.md) · [补覆盖](../experiments/selection-frontier-02/README.md) |
| **置信度 / 弃权 / 第二意见**；改门槛、终选加入低信心边、弃权时换裁判、跨任务校准 | 低信心终选在原 DeepSeek 收益 +0.02189，GPT 合并 −0.01521，额外 DeepSeek 运行亦反向；第二意见的效果取决于裁判及所替代的新边 | **暂缓通用启用规则**；正结果依赖具体反馈运行，跨运行校准也出现错误放行 | [跨裁判模块对照](../experiments/selection-frontier-02/README.md) |
| **排序汇总**；胜率先验、Colley 对手强度、固定可靠性假设的全局后验名次 | 门槛与汇总跨裁判筛选表现不稳定；同一 C0 轨迹的后验重排收益 DeepSeek **−0.02138**、GPT 合并 **−0.00924**，两组区间跨零 | **结束本次重排先导**；固定反馈下这些实现平均收益较弱。BT / Bayesian BT 的直接匹配实验仍列待测范围 | [模块对照](../experiments/selection-frontier-02/README.md) · [整体重排](离线候选选择.md) |
| **比较预算 / 停止**；现在停与再问一次、把 C0 读取上限缩为 n−1 | D1 随机 / 主动补问相对就停的平均收益均为负、区间跨零；缩短上限平均节约约 2–3 次读取，两组损失代价的区间上界均超过容忍值 0.01 | **保留原预算**；节约与质量风险需共同满足门槛；“比较还是实际执行”的动态预算分配留作独立问题 | [D1](../experiments/selection-frontier-01/d1/README.md) · [预算实验](../experiments/selection-frontier-02/README.md) |
| **轻量裁判训练**；冻结 CodeT5-small＋线性头，等权 / 分差 / 终局代价 / 打乱权重四臂，逐任务留出 | 等权损失 0.36573，终局加权 0.36457，均高于 C0；加权相对等权收益 **0.00116**，95% 区间 [−0.00232,+0.00448]，推进尺度 0.01 | **结束此表示与加权先导**；打乱权重对照相近。表示能力、长输入覆盖和权重信号是待区分解释；更强裁判与完整微调仍属开放范围 | [训练、覆盖与成本](../experiments/trajectory-weighted-judge-v1/README.md) |
| **已有理由辅助破同分**；理由显式候选下标与最终赢家冲突时调整并列选择 | DeepSeek 850 场只改变 **1 场**，收益 **0.00046**，最佳命中率持平；三份 GPT 共 2,550 场选择完全相同 | **按用户决定收尾**；信号触发面过窄，原拟的进一步理由事实分析已撤下 | [理由实验与复核](../experiments/rationale-tiebreak-v1/README.md) · [完整方案](离线候选选择.md) |

**裁判质量诊断：** J1 在评价端纠正已问边胜者，损失改善 0.17864，同时有 73/850 场变差；后续真实 C0 的局部答案干预显示，纠正已采纳错判和补足弃权都有改善空间。这支持研究判断与证据质量；可实现模型的实际收益和成本由独立实验测量。[J1](../experiments/selection-frontier-01/README.md) · [C0 局部干预](../experiments/selection-frontier-02/README.md)

**下轮保留的教训：** 先测新增信号的覆盖与潜在选择收益，再实现复杂规则；同时检查跨任务、跨反馈运行与等预算对照。小裁判中的表示、截断、监督权重需分别诊断。每项结论限定到对应实现、语料和预算，其他方法保持各自待测状态。

## ForeCritic、备选方向与唯一下一步

**ForeCritic 的位置：** 已完成相关工作精读。它依据真实执行胜负，用监督交叉熵更新 LoRA 和选择头，学习成对 outcome preference；RL 的 value critic、过程奖励和策略训练分别属于其他机制。本项目已训练的是上述轻量线性先导，ForeCritic 9B 配方的本机复现属于待开展工作。普通执行标签监督可作为训练基线，贡献需落到更具体的机制、泛化或成本收益。[精读与数据审计](../reports/reproducibility-audit-20261108/ForeCritic_精读与研究判断.md)

**最新聊天列出的五类备选，均处于方向讨论：** reward 定义与粒度（outcome / process、token / action / reasoning）、更强 teacher 与蒸馏、GRPO / relative group advantage、embedding 初筛＋精排或案例检索、DeepSeek Thinking 的结构化比较流程 / skills。按需补充数据分析、真正 A/B 换位与重复判断、比较—执行切换，以及生成 / 搜索树改进，也保留为待检验问题。[生成与执行的历史方案](研究路线.md)

**此前提出的诊断备选：定位好候选在哪一步丢失。** 最新讨论提出先看真实 Top-1 / Top-2 是否经常排到第 4 名及以后，并结合并列名次、执行分差、任务 / 裁判分层与成本判断潜在价值；这项汇总诊断处于待开展状态。固定旧池的两项终选先导维持收尾决定，新的诊断和方法按新方案登记。

方案卡需写明失效机制、文献依据、具体改动、等预算基线、数据划分、最小实验、推进 / 停止条件与费用。方法冻结后的新任务与在线确认、AI Scientist 固定版本原生适配、代码生成工作区隔离与全局预算，按各自协议验收。现有离线 host 已验收，AI Scientist 借鉴的记录格式与原生系统接入分别标注。

## 历史聊天导航与交接维护

| 聊天 | 主要用途 |
|---|---|
| [🌟 审计基线复现与未来计划](codex://threads/01a1b9d9-3e10-7733-9d36-6b604e12e63b) | 原版 / C0 的角色、六类已测改进、ForeCritic、最新五类备选与 Top-1 / Top-2 诊断讨论 |
| [设计 ForeAgent 模块优化方案](codex://threads/01a1badd-df04-7041-b061-9a5fb0e87f80) | 各模块实验、整体排序与理由信号，以及用户收尾决定 |
| [梳理 DM Final Project 复现进度](codex://threads/01a19593-03ae-7fd3-9bcc-2c02273aa368) | 原版流程、HW3 与早期 R6–R8；各数字按历史协议理解 |
| [对比 ML Agent 项目进度](codex://threads/01a1c373-12e7-7203-b9a2-6091313e01ae) | GitHub 发布范围与本地后续研究的差异 |

每轮结束更新本页的当前决定、方向表和唯一下一步；详细协议与原始结果保留在实验目录，以链接接续。新聊天从本页恢复，再按本轮问题查证据。

**首次版本对齐（2026-11-10）：** 以 GitHub main `09b301d` 为基点归并本地后续研究；已发布的原版 / HW3 材料与远端独有测试按原版本保留。较大逐场轨迹通过 [版本附件与校验清单](../provenance/first-alignment-20261110/README.md) 恢复。此后每轮开始检查并拉取，结束更新本页、验证、提交、推送并核对实际远端；持续授权与具体要求见[根协作规则](../AGENTS.md#每轮结束的交接与-github-同步)。旧 Git 基点与未提交工作区的状况保留在历史记录中。

## 离线 Environment 与 Evals：按需操作

[当前方案、结果与成本](离线候选选择.md) · [原版实验覆盖表](selection-study-v1/baseline.md) · [早期相关工作](selection-study-v1/literature.md)

接口像一个实验插槽：换入“决定比较谁、何时停止”的策略，沿用同一批候选、反馈预算和评分规则，比较它与 C0 的表现。

| 已固定 | 内容 |
|---|---|
| Environment | 26 个开发任务、425 候选池、850 场；每池最多 10 候选，每场最多 13 条唯一反馈 |
| 策略权限 | 查看候选 ID、已查询的反馈、剩余预算；输出下一对比较或停止 |
| Evals | 任务等权选择损失、最佳命中率、查询数、任务簇区间；统一处理并列和失败 |
| 参考 | C0 修正版原淘汰赛；随机比较示例用于接口验收和同汇总器控制 |
| 隔离 | 每场独立系统沙箱；项目数据读取、外部写入和网络受限；预算由 host 执行 |

## 现在先看什么

1. [模块卡](modules.md)：各模块做什么、当前规则、可修改位置和评价方式。
2. [离线选优方案](离线候选选择.md)说明如何只更换终选、复用归档理由并对齐评价；[生成与真实执行路线](研究路线.md)留作后续研究。
3. [首轮比较分配](../experiments/selection-frontier-01/README.md)、[跨裁判模块实测](../experiments/selection-frontier-02/README.md)、[静态加权裁判训练](../experiments/trajectory-weighted-judge-v1/README.md)记录已完成的先导。

当前 26 个任务全部属于开发数据。AI Scientist 具体版本接入与工作区隔离另行验收；方法冻结后再规划新任务和在线验证。机器状态中的环境验收字段对应原版收据。原验收脚本重新运行会从收据生成 state.json；最新研究决定可随时从本节与方案卡读取。

## 首次准备

从 GitHub 获取代码后，用已登录的 GitHub CLI 下载同版本固定输入。附件约 57 MB，逐项绑定 1,182 个保护文件；恢复工具先检查全部内容和已有文件哈希，再补入缺失文件。

```bash
gh release download research-env-v1 --repo skyexry/foreagent-reproduction \
  --pattern research-env-v1-protected-inputs.zip --dir downloads
python3 -B scripts/restore_research_env.py \
  --archive downloads/research-env-v1-protected-inputs.zip
python3 -B -m reproduction.research_env_v1 status --json
```

已有完整本机数据时，用 `python3 -B scripts/restore_research_env.py --check-only` 核验即可。附件来源、固定版本和 SHA-256 见 [input_bundle.json](input_bundle.json)。

## 给 Codex / 实验框架的调用

在项目根目录运行，使用本机已验收的 Python 3.12.5；策略沙箱依赖 macOS `sandbox-exec`。每次选择新的输出目录编号。

```bash
# 查看当前状态，同时检查冻结文件哈希
python3 -B -m reproduction.research_env_v1 status --json

# 接口短测：3 场，用随机示例验证调用链
python3 -B -m reproduction.research_env_v1 run \
  --policy research/policies/example_random.py \
  --limit-jobs 3 \
  --output experiments/research-env-v1/runs/random-smoke-001

# 完整开发评测：换成方案对应的策略文件，使用全部 850 场
python3 -B -m reproduction.research_env_v1 run \
  --policy research/policies/example_random.py \
  --output experiments/research-env-v1/runs/random-full-001

# 独立重建轨迹和预算，再重算分数；已有评价须逐项一致
python3 -B -m reproduction.research_env_v1 evaluate \
  --run experiments/research-env-v1/runs/random-full-001
```

`run --baseline --output <新目录>` 复跑固定 C0。运行保存策略快照、每场选择/反馈轨迹、预算账本和时间；`evaluation/summary.json` 给出评价。策略失败按原定场数计入主结果。完整运行的“新策略减 C0”损失差小于 0 表示更好；解释比较分配的作用时，也要与同汇总器随机控制比较。

Codex 的外层工具沙箱可能阻止启动系统策略沙箱；此时使用应用的受审查执行权限，保持策略自身的隔离规则。首次迁移机器先跑接口测试与短测，再启动完整开发评测。

## 验收证据与成本

- [验收记录](../experiments/research-env-v1/acceptance.json)：17 项测试通过；C0 850 场、随机控制 850 场的选择、查询轨迹、账本及逐任务统计精确复现旧结果。
- C0 选择阶段约 5.40 秒，随机策略约 30.95 秒；本机 CPU 实测，另计独立评分与输入核验时间。本轮付费模型调用、训练和 GPU 租用均为 0。
- 177 项旧 clean-ranking 产物、48 项历史保护文件、946 项原始输入来源通过核验；可信代码/输入共 1,182 个哈希条目。
- 重做验收：`python3 -B experiments/research-env-v1/check_acceptance.py`；明细见 [tests.log](../experiments/research-env-v1/tests.log)。

## 机器入口

| 文件 | 用途 |
|---|---|
| [state.json](state.json) | 已验收、待完成、唯一下一步及证据哈希 |
| [registry.json](registry.json) | 模块、数据、预算、可见信息、评测契约 |
| [protected_manifest.json](protected_manifest.json) | 可信实现与输入的固定版本；策略另存快照 |
| [policies/example_random.py](policies/example_random.py) | 可运行的策略示例，定义 `decide(observation)` |
| [AGENTS.md](AGENTS.md) | 研究代理如何先形成方案、再执行实验 |
