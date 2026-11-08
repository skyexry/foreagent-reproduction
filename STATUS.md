# 当前状态：作者原版 ForeAgent

- **源码已核验**：独立检出固定在 `c4d52cf99bd870d830b456ac7c0684aec1aef375`。逐文件核对工作目录与该提交，484 个 Git 文件内容一致，工作区干净；其中 Git LFS 指针按提交原样保留。
- **离线证据**：给定历史判断和日志中的概率结果，15 次作者运行中的 129 个完整批次（1,290 个候选）控制输出一致。原 RNG 状态和复赛对手身份仍有缺口。证据：`experiments/historical-v1/summary.json`。
- **标准 12 小时端到端结果已冻结**：`stanford-autodl-v2` 在北京时间 11 月 8 日 13:22 按预算结束。原算法从已完成的 82 个节点中保留 `84c79a8d`，官方私有集误差 **0.26640**，25,680 个预测 ID 有效；19 次完整外层迭代、7 个完整淘汰赛批次，执行了 22 份代码。作者的三次最终成绩为 0.24320、0.25768、0.27497。硬件、模型服务与网络时延有差异。根据实验者事后确认，Mac 熄屏、VPN 断连导致模型 API 请求受阻并等待重试；其中一次反馈请求及重试累计耗时 13,491.88 秒（约 3 小时 45 分钟）。该耗时计入标准 12 小时预算，压缩了实际可用于候选生成、筛选和执行的时间；13,491.88 秒为请求及重试的总耗时，VPN 中断时长单独计量仍有缺口。见[最终结果和预测哈希](experiments/online-stanford-v2/final-summary.json)、[作者最终提交复评分](experiments/online-stanford-v2/author-final-reference.json)、[首批筛选记录](experiments/online-stanford-v2/first-tournament.json)。
- **本机 API 预检**：通过作者请求后端和硅基流动的模型名、思考开关映射，代码生成与两两筛选各实测成功一次。GPT 反馈也已实测通过：官方端点返回 gpt-4o-mini-2024-07-18，作者后端成功解析 submit_review 的五个字段。测试使用简短示例输入。回执见本机 `/Users/shrinn81/Documents/Codex/2026-11-01/read-this-folder-and-my-current/work/foreagent-local-preflight/` 下的 `code.json`、`select.json`、`feedback.json`。
- **本机数据与评分器**：Kaggle ZIP 和 4 个准备后的文件均匹配固定提交的 MD5。训练 2,160 条、测试 240 条 RNA 序列。官方 grade-sample 接受全零示例提交，得分 0.63824。证据见上述本机目录的 `data-check.json` 和 `sample-grade.txt`，数据位于 `data/stanford-covid-vaccine/prepared/`。
- **实验已结束**：因 0.26640 高于 0.25862 而启动的独立加时，已按用户要求提前停止。新增完整节点 0 个，预测文件与标准提交 SHA-256 一致。最终报告使用标准 12 小时分数 **0.26640**；见[加时结束记录](experiments/online-stanford-plus4h/closure.json)。
