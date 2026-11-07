# 当前状态：作者原版 ForeAgent

- **源码已核验**：独立检出固定在 `c4d52cf99bd870d830b456ac7c0684aec1aef375`。逐文件核对工作目录与该提交，484 个 Git 文件内容一致，工作区干净；其中 Git LFS 指针按提交原样保留。
- **离线证据**：给定历史判断和日志中的概率结果，15 次作者运行中的 129 个完整批次（1,290 个候选）控制输出一致。原 RNG 状态和复赛对手身份仍有缺口。证据：`experiments/historical-v1/summary.json`。
- **单任务在线验证**：`stanford-covid-vaccine` 待运行；本次 submission 和官方得分均待取得。
- **本机 API 预检**：通过作者请求后端和硅基流动的模型名、思考开关映射，代码生成与两两筛选各实测成功一次。GPT 反馈也已实测通过：官方端点返回 gpt-4o-mini-2024-07-18，作者后端成功解析 submit_review 的五个字段。测试使用简短示例输入。回执见本机 `/Users/shrinn81/Documents/Codex/2026-11-01/read-this-folder-and-my-current/work/foreagent-local-preflight/` 下的 `code.json`、`select.json`、`feedback.json`。
- **本机数据与评分器**：Kaggle ZIP 和 4 个准备后的文件均匹配固定提交的 MD5。训练 2,160 条、测试 240 条 RNA 序列。官方 grade-sample 接受全零示例提交，得分 0.63824。证据见上述本机目录的 `data-check.json` 和 `sample-grade.txt`，数据位于 `data/stanford-covid-vaccine/prepared/`。
- **下一步**：在确认租赁实例及费用后，部署三个模型的兼容路由，在 GPU 容器中运行作者原版单任务，并对新生成的 submission 评分。
