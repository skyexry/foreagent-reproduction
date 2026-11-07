# 当前状态：作者原版 ForeAgent

- **源码已核验**：独立检出固定在 `c4d52cf99bd870d830b456ac7c0684aec1aef375`。逐文件核对工作目录与该提交，484 个 Git 文件内容一致，工作区干净；其中 Git LFS 指针按提交原样保留。
- **离线证据**：给定历史判断和日志中的概率结果，15 次作者运行中的 129 个完整批次（1,290 个候选）控制输出一致。原 RNG 状态和复赛对手身份仍有缺口。证据：`experiments/historical-v1/summary.json`。
- **单任务在线验证**：`stanford-autodl-v2` 已在作者镜像内用 RTX 4090 完成真实候选训练。第一份由原算法选出的有效预测包含 25,680 个唯一 ID，官方私有集得分 **0.37879**（越低越好）。这是调试阶段的中间成绩，淘汰赛与完整预算结果另行核验。证据及可重评分的预测文件见 [first-checkpoint.json](experiments/online-stanford-v2/first-checkpoint.json)。
- **本机 API 预检**：通过作者请求后端和硅基流动的模型名、思考开关映射，代码生成与两两筛选各实测成功一次。GPT 反馈也已实测通过：官方端点返回 gpt-4o-mini-2024-07-18，作者后端成功解析 submit_review 的五个字段。测试使用简短示例输入。回执见本机 `/Users/shrinn81/Documents/Codex/2026-11-01/read-this-folder-and-my-current/work/foreagent-local-preflight/` 下的 `code.json`、`select.json`、`feedback.json`。
- **本机数据与评分器**：Kaggle ZIP 和 4 个准备后的文件均匹配固定提交的 MD5。训练 2,160 条、测试 240 条 RNA 序列。官方 grade-sample 接受全零示例提交，得分 0.63824。证据见上述本机目录的 `data-check.json` 和 `sample-grade.txt`，数据位于 `data/stanford-covid-vaccine/prepared/`。
- **下一步**：跟进同一轮 v2，核对新生成候选的真实两两筛选和执行记录，并在作者预算结束后对其最终 best submission 评分。
