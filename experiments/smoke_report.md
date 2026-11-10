# 首轮离线联调结果（2026-10-21）

本轮完成固定的 10 对真实候选比较，成功解析 10 对，答对 9 对。该小样本只验证流程，不能据此声称复现或超过论文全量 61.5% 的结果。

| 任务 | 本轮 | 作者公开的一次运行 |
| --- | --- | --- |
| leaf-classification | 5/5 | 4/5 |
| detecting-insults-in-social-commentary | 4/5 | 5/5 |
| 合计 | 9/10 | 9/10 |

- 用时：943.4 秒（约 15 分 43 秒），串行调用，无重试。
- 输入 tokens：150,873；输出 tokens：20,035；合计：170,908。
- 思考 tokens：17,040（已包含在输出 tokens 中，不重复计费）。
- 10/10 返回思考内容，10/10 结束原因为 `stop`；未发现解析失败或长度截断。
- 按响应 token 数及公开价格估算消耗：¥0.4210。这是包含缓存折扣的估价，不是账户账单或现金支付金额；代金券抵扣以平台记录为准。
- 本轮没有出现额度不足，无需为已完成的测试补充充值。

## 同样本对照

组索引为作者 ground-truth JSON 中的零起始索引；候选顺序保持不变。

| 任务 | 组索引 | 真实最佳索引 | 本轮预测 | 作者预测 | 本轮结果 |
| --- | --- | --- | --- | --- | --- |
| leaf-classification | 2 | 0 | 0 | 0 | 正确 |
| leaf-classification | 80 | 0 | 0 | 0 | 正确 |
| leaf-classification | 97 | 1 | 1 | 0 | 正确 |
| leaf-classification | 98 | 0 | 0 | 0 | 正确 |
| leaf-classification | 103 | 1 | 1 | 1 | 正确 |
| detecting-insults-in-social-commentary | 119 | 1 | 0 | 1 | 错误 |
| detecting-insults-in-social-commentary | 204 | 0 | 0 | 0 | 正确 |
| detecting-insults-in-social-commentary | 246 | 0 | 0 | 0 | 正确 |
| detecting-insults-in-social-commentary | 326 | 0 | 0 | 0 | 正确 |
| detecting-insults-in-social-commentary | 329 | 1 | 1 | 1 | 正确 |

作者参考文件名为 `alignment_<task>_n2_data-both_deepseek-reasoner_1p0_pboost_cot_20251209_164656.json`，属于公开的一次运行，不是论文三次运行的平均值。按照有序候选文件名后缀和真实分数匹配，10 对均唯一匹配，标签一致。参考提取结果及原文件哈希见 `author_reference.json`。抽样在查看作者预测前固定，不以预测是否正确作为筛选条件。

## 复现边界

- 使用作者提交 `c4d52cf99bd870d830b456ac7c0684aec1aef375` 的提示词、响应解析器和准确率函数，原样复制并核对 SHA-256；未直接运行整个官方 CLI。
- 数据版本：`6b322cb88bdbcb2b2d3897ec7d0ded94a5bb2d06`。两个任务各随机抽 5 对，种子 `20261021`。全部候选代码、任务描述及数据分析报告完整载入；真实标签和分数未作为额外评测字段传入请求。
- 模型：SiliconFlow `Pro/deepseek-ai/DeepSeek-V3.2`；温度 1.0，开启 Thinking，使用 CoT 和 prompt boost。
- 显式限制：思考 32768 tokens、最终回答 8192 tokens；与作者默认输出长度设置可能不同。所有响应正常结束，但不能据此断言服务端推理配置完全相同。
- 运行环境：本地 Python 3.12.5 + certifi，使用标准库 HTTP 调用；不是官方建议的 Python 3.10 + OpenAI SDK 环境。
- 作者 API 服务商和精确服务端快照尚未确认；本轮参考报告记录的模型名是 `deepseek-reasoner`。
- 该子集不代表全部 26 个任务。下一步应扩大任务覆盖和样本量，随后才决定是否开展全量、多次运行对比。

完整输入与响应保存在本地 `outputs/smoke-20261021/`，未上传 GitHub。可分享的指标见 `smoke_results.json`，输入版本和文件校验值见 `smoke_manifest.json`。

## 来源

- [官方代码](https://github.com/zjunlp/predict-before-execute/tree/c4d52cf99bd870d830b456ac7c0684aec1aef375)
- [固定版本的数据与作者记录](https://huggingface.co/datasets/zjunlp/PredictBeforeExecute/tree/6b322cb88bdbcb2b2d3897ec7d0ded94a5bb2d06/solutions_subset_50)
- [SiliconFlow 价格页](https://www.siliconflow.cn/pricing)：2026-10-21 核查，每百万 tokens 输入 ¥4、输出 ¥6、缓存命中输入 ¥0.4。
