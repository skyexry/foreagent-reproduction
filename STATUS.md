# 当前状态

版本：`baseline-reproduction-v1` 本地冻结候选，原版固定提交 `c4d52cf99bd870d830b456ac7c0684aec1aef375`；研究仓库基点 `9442373ad020a06b691700592b0c83281b31d8c9`。工作分支为 `codex/baseline-reproduction-v1` 的归集检查点；原 main 中既有未提交工作有初始清单和迁移前快照。

## 已完成与证据

- 246 对真实 pairwise：136/246；266 次历史 API 调用；本轮重新解析采用的 246 个原始响应，重建补调采用规则及汇总一致。`experiments/coverage_retry_results.json`；原始附件校验值在 `provenance/attachments.json`。
- 条件历史重演：15 次运行、129 完整批次、1,290 候选；六类输出核对均 129/129。`experiments/historical-v1/summary.json`、`verification.json` 和排除批次账本。
- 26 任务完整执行策略：原版与 canonical 缓存方向修正版各 7,800 次，保存汇总见 `experiments/corpus26-v2/`。两者均含概率空选后的强制执行回退。
- 五任务筛选实验、机制审计和实例隔离/加锁缓存修复独立保存；版本区别见 README 和 EXPERIMENTS。
- 原固定源码、公开数据下载 URL、输入校验值、来源对应关系、HW3 NeurIPS TeX/PDF 已归集。核心脚本使用仓库相对路径；原有来源文件留存。
- 迁移预检已通过 20 项测试与全部离线复现；最终新克隆验证结果记录于 `experiments/integration-v1/validation.json`。

## 待验证范围

原历史 RNG 状态与真实复赛对手身份；11 个结构不完整批次；独立实时 LLM 重预测；新比较/汇总/早停策略；完整在线 Agent 训练及时间收益。Corpus 已查看，后续算法实验需另设评测范围。附件公开下载位置待发布时补充。

## 当前唯一下一步

完成最终独立新克隆验证，回填验证记录后，请用户审阅本地差异并确认 GitHub 推送/标签及附件发布。

完整验证命令见 README。后续聊天先读本文件、相关实验轮次与冻结清单，以 Git 提交或实验版本衔接，运行输出保存在忽略目录 `runs/`。
