# 当前状态

Environment & Baselines 只验收作者 ForeAgent（提交 `c4d52cf`）及其发布配置：原始缓存行为、confidence 门槛 0.70、10 个候选、top-k=1、执行概率 0.20 和原始强制执行回退。缓存修正、R6–R8 与门槛调优统一归入后续改进实验。

版本：`baseline-reproduction-v1` 已发布冻结版本，原版固定提交 `c4d52cf99bd870d830b456ac7c0684aec1aef375`；研究仓库基点 `9442373ad020a06b691700592b0c83281b31d8c9`。已推送分支 `codex/baseline-reproduction-v1` 与标签；标签指向已审阅的 `fd55d93a1ea063e64620de4c4c87c49f517eff66`。主项目 main 工作区保留归集副本，既有未提交工作有初始清单和迁移前快照。

## 已完成与证据

- 246 对真实 pairwise：136/246；266 次历史 API 调用；本轮重新解析采用的 246 个原始响应，重建补调采用规则及汇总一致。`experiments/coverage_retry_results.json`；原始附件校验值在 `provenance/attachments.json`。
- 条件历史重演：15 次运行、129 完整批次、1,290 候选；六类输出核对均 129/129。`experiments/historical-v1/summary.json`、`verification.json` 和排除批次账本。
- 26 任务完整执行策略：原版与 canonical 缓存方向修正版各 7,800 次，保存汇总见 `experiments/corpus26-v2/`。两者均含概率空选后的强制执行回退。
- 五任务筛选实验、机制审计和实例隔离/加锁缓存修复独立保存；版本区别见 README 和 EXPERIMENTS。
- 原固定源码、公开数据下载 URL、输入校验值、来源对应关系、HW3 NeurIPS TeX/PDF 已归集。核心脚本使用仓库相对路径；原有来源文件留存。
- 独立新克隆已通过 20 项测试与全部离线复现；运行后 Git 工作区干净，85 项冻结文件及 97 个核心输入均校验通过。验证基于代码检查点 `148dbf8ebf09e57ee887699eb47ab1b1b98bd9ed`，结果记录于 `experiments/integration-v1/validation.json`。

- 发布完成：[baseline-reproduction-v1](https://github.com/skyexry/foreagent-reproduction/releases/tag/baseline-reproduction-v1)；三份附件均从 GitHub 下载后匹配原 SHA-256 和大小。`provenance/release.json` 保存下载 URL、GitHub digest 与发布时间；`experiments/integration-v1/release_attachment_verification.json` 保存验证记录。

- R6已完成：注册提交 `084ad53` 先于实现提交 `68a20ad`；7,800场同反馈配对比较，胜率汇总命中率21.2000%→22.4997%，regret 0.277534→0.279248，未达事前实用联合标准。29项测试及独立逐场/评分/区间核验通过；新增反馈/API/训练均0。证据 `experiments/round-06/report.md`、`summary.json`、`verification.json`。实验分支 `codex/r6-winrate`，本轮工作目录 `/Users/shrinn81/Documents/Codex/2026-11-01/read-this-folder-and-my-current/work/foreagent-r6`；跨工作目录用该分支提交衔接，复跑使用干净的已提交目录。

- R7已完成：注册 `bab4052` 先于实现 `865b909`；相同反馈7,800配对场景，regret 0.279248→0.269499，命中率22.4997%→22.8971%，通过事前点估计联合门槛。36测试、独立投票/证据次序/15,600评分及区间核验通过；95%任务区间仍跨0。证据 `experiments/round-07/report.md`、`summary.json`、`verification.json`。分支 `codex/r7-evidence-tiebreak`，工作目录 `/Users/shrinn81/Documents/Codex/2026-11-01/read-this-folder-and-my-current/work/foreagent-r7`；复跑使用该分支干净的已提交目录，跨worktree按提交衔接。

- R8已完成：注册f7c9440→来源补充9eb25eb（评分前恢复8条同次原API失败）→实现f0bc099→一次正式全量比较。78反馈表和6原始备份核验通过，26任务/23,400场景/70,200评分及78原生控制重演通过。GPT合并R6→R7命中率25.6843%→26.3705%，regret 0.294116→0.293416；点估计稳健性通过，regret区间跨0使联合区间标准未通过。45测试、冻结85文件及R6/R7保持；新增模型调用/训练0。证据 `experiments/round-08/report.md`、`summary.json`、`verification.json`；分支`codex/r8-gpt-feedback`，工作目录`/Users/shrinn81/Documents/Codex/2026-11-01/read-this-folder-and-my-current/work/foreagent-r8`。

## 待验证范围

原历史 RNG 状态与真实复赛对手身份；11 个结构不完整批次；独立实时 LLM 重预测；新比较/汇总/早停策略；完整在线 Agent 训练及时间收益。Corpus 已查看，后续算法实验需另设评测范围。附件下载位置已登记在发布记录。

## 当前唯一下一步

在获准使用的 Docker/GPU 主机运行作者原版的 `stanford-covid-vaccine` 单任务，用本次生成的 submission 和官方评分器取得真实分数，并核对生成、筛选和执行日志。当前状态为等待可用主机，真实分数待取得。

## 审稿复核
当前分支 audit/icml-baselines 整合环境核验和 R6–R8。实验协议在 890d688 先行提交。六档门槛、共享判断、每场单选预算下，三方法在开发集均选 0.50；八个验证任务上的 R6/R7 平均损失相同，高于修正版淘汰赛。审稿意见、修正、复跑方式和范围见 experiments/icml-review/review.md。作者基线仍为 0.70。
