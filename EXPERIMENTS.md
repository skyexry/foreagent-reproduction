# 实验账本

每轮只保留研究问题、运行前预测、设置、结果、解释、下一步。详细设置和数字链接到对应协议/JSON。以下 R0–R4 为既有历史材料的归档，记录编写时已经看到结果；只有原协议明确写出的内容可称为原先固定设置。

## R0 · pairwise246-v1 · 历史，2026-10-21

- 问题：保持作者 prompt/parser/accuracy 口径，在固定 26 任务子样本上核对 pairwise 判断能力。
- 运行前预测：本次归集未发现可独立核验的量化事前预测；抽样种子及选择规则保存在 `experiments/coverage_manifest.json`。
- 设置：每任务至多 10 对，共 246 对；首轮失败的 20 对各补调一次；采用首个有效输出，266 次调用。
- 结果：136/246；同样样本作者结果 130/246。`experiments/coverage_retry_results.json`，协议及原报告在同目录。
- 解释：真实调用的小样本复现；单次公开作者结果、不同服务设置与相关样本分别解释。历史 token 费用保留已知/未知部分。
- 下一步：作为已保存证据核验；全量新预测与在线调用单独立项。

## R1 · five-task-v1 · 历史，2026-11-07

- 问题：固定反馈、候选及排列，修复缓存后筛选是否改变？
- 运行前预测：以 `experiments/tournament_replay_protocol.md` 的历史文字为依据；本账本归集时间晚于运行。
- 设置：5 个完整比较图任务；每任务 10 个十候选池 × 5 排列 × 2 pending 种子；每版本 500 次。原版对照 `cache_fixed_instance_locked-v1`。
- 结果：首位候选命中 17.4% → 16.4%；trace 校验值在 `experiments/tournament_replay_results.json`。
- 解释：筛选实验，首位 tie-break，含实例隔离/锁的修复实现；与后面的 26 任务、均匀并列评分及完整执行策略分别报告。
- 下一步：作为历史兼容性检查保存。

## R2 · mechanisms-v1 · 历史，2026-11-07

- 问题：门控、pending、缓存、停止条件、名次显示和 Agent 执行分支是否按固定代码运行？
- 运行前预测：本次归集保存已有机制案例与结论；量化事前预测未另行提供。
- 设置：受控响应、原生 batch/tournament、原 Agent AST 执行路由；1 与 128 workers 适配核对。
- 结果：18 门控、14 停止、6 路由、100 原生回放核对；另含默认/发布阈值、跨实例缓存检查；20 项既有测试通过。
- 解释：全低 confidence 会重复读取缓存直至 `round > 2*n`；并列显示 rank 与存活状态分别记录；概率空选后强制执行首个 rank-0。`experiments/foreagent_mechanism_audit.md` 和 `experiments/mechanisms-v1/audit.json`。
- 下一步：新早停/比较策略保留为未来独立实验。

## R3 · corpus26-v2 · 历史，2026-11-07

- 问题：同一公开 corpus 候选池、顺序和初始种子下，缓存方向修正如何影响选择及执行集合？
- 运行前预测：本次归集晚于全部运行；旧协议和修订保留在 `experiments/corpus26-v2/` 与 `experiments/superseded/`。
- 设置：26 任务、2,600 池实例、2,164 个不同集合，每池 3 次；每版本 7,800 次。0.7 gate、0.2 概率、Top-K=1、串行比较、hash seed 0。原版对照 `cache_direction_canonical-v1`；精确原 Agent AST 包含强制回退。
- 结果：均匀并列单选命中 20.4265% → 21.2000%；最终执行至少一个最佳 21.6026% → 22.4359%；最终空执行均为 0。`experiments/corpus26-v2/paired_comparison.json`。
- 解释：缓存方向错误被修正，提升为本 corpus 的描述性观察。21 个十候选任务及 5 个较小池任务等权；重叠样本、固定反馈、候选代码身份 stub 等适配限制保留。相同初始种子保证同版本复跑一致；跨版本 RNG 消耗可能分化。
- 下一步：冻结；新的算法改进另设协议。

## R3a · 旧执行口径 · 历史，已由 R3 完整执行结果替代

- 旧回放只做概率执行阶段，约 74% 的空选率实际是概率阶段空选；原 Agent 之后还有强制回退。
- 修订补齐原 AST 回退后重跑两版本；筛选结果保持，最终空执行为 0。`experiments/superseded/README.md` 保存旧结果及其来源/哈希。

## R4 · historical-v1 · 历史，2026-11-07

- 问题：作者真实候选批次和顺序给定后，原控制流程输出能否与保存轨迹对上？
- 运行前预测：归集晚于运行；原冻结文件 `experiments/historical-v1/FREEZE.json` 保留。
- 设置：固定 15 次真实运行的 45 份 config/journal/log；129 完整批次、1,290 候选、23,873 条历史比较记录。
- 结果：所有已覆盖的排名/轮次、排序、概率决策、回退及最终执行集合/顺序一致；87 批强制回退；11 批排除分账。
- 解释：给定历史响应序列及日志 Bernoulli 结果的条件重演；普通双方与 pending 身份交叉核验，复赛对手用演示 RNG；原 RNG 状态仍是已知缺口。历史模型真实调用次数无法由重复比较记录直接推出；本次重演调用为 0。
- 下一步：冻结为 HW3 Baseline Reproduction 的核心结论，报告版本说明见 `reports/hw3/VERSION.md`。

## R5 · baseline-reproduction-v1 · 本轮迁移核验

- 问题：独立新克隆按 README 安装并获取固定输入后，能否保持所有核心结果？
- 运行前预测：在执行最终新克隆核验前写定：20 项测试通过；pairwise 136/246、历史 129/129、corpus 两版本各 7,800 的运行/轨迹内容指纹、五任务 trace 应与归集前保存结果相同。只允许修正路径、依赖和核验脚本问题，原版算法、反馈和冻结池保持固定。
- 设置：CPython 3.12.5，隔离 venv、固定 certifi；从本地 Git checkpoint 再克隆；数据通过显式缓存与 SHA-256 验证，另测试固定公开 URL 获取。
- 结果：独立新克隆的 20 项测试与全部六类核验通过；corpus 15,600 次、历史 129 批及五任务 1,000 次结果匹配；Git 工作区干净。97 个核心输入全量校验，两个固定公开 URL 下载测试通过。证据在 `experiments/integration-v1/validation.json` 与对应日志。
- 解释：安装/输入/源码/轨迹均有独立核验；本轮新增真实 API 调用和候选训练为 0。
- 发布：用户确认后，分支与标签已推送，[Release](https://github.com/skyexry/foreagent-reproduction/releases/tag/baseline-reproduction-v1) 已发布；三份附件下载后均匹配固定哈希，证据见 `provenance/release.json`。下一步由用户选择单一研究问题。

## R6 · 相同反馈下的简单胜率汇总 · 运行前注册

- 问题：在 canonical 缓存修正版淘汰赛已经查询的同一反馈图上，简单胜率重排是否改善选择？
- 预测：task-macro uniform-tie best-hit 差值 >0；实用推进门槛为至少 +1pp 且 normalized regret 持平或下降。
- 设置：协议 `experiments/round-06/protocol.md`，机器设置 `protocol.json`，7,800 场配对作业 `jobs.jsonl`。共同使用每场 q_j 条唯一已查询反馈，合计 102,473；新增 API/训练均0。confidence>=0.7；无有效比较候选赋0.5。
- 指标：唯一主指标为并列均匀单选最佳命中率；辅助 regret、percentile、并列大小、反馈图诊断；配对任务簇 bootstrap。
- 注册记录：协议与作业先提交 `084ad53`，实现和29项测试随后提交 `68a20ad`；之后执行一次正式全量比较。原预测与注册文件校验值保持。
- 结果：7,800配对场景全部通过独立核验。主指标21.2000%→22.4997%，+1.2997pp；任务簇95%区间[-0.5291,+3.7006]pp。regret 0.277534→0.279248。方向预测得到点估计支持，实用联合标准未达到；13任务改善、1持平、12下降。
- 证据：`experiments/round-06/summary.json`、`report.md`、`verification.json`和独立轨迹附件校验值；本轮新增反馈/API/训练均0。现有corpus为已查看的探索性开发数据。
- 下一步：审阅R6收益与regret代价，为R7选择一个单独诊断问题并事先注册。新早停/主动比较/BT由其他轮次协议定义。
