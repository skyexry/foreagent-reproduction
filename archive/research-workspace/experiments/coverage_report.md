# 26 任务覆盖评测（2026-10-21）

本轮从作者的 26 个任务、18,438 对候选中固定抽取 246 对；每任务最多 10 对，两个只有 3 对的任务全部使用。

- 请求结束：246/246；有效解析：226；待运行：0。
- 有效答案正确数：123/226（54.42%）。
- 有效输出率：226/246（91.87%）；全样本正确率：123/246（50.00%）。
- 全样本每任务等权平均正确率：50.90%。
- API/网络或输出错误：20。无自动重试。
- 同样本有效答案对照：本轮 123/226，作者一次公开运行 122/226。
- 配对差异：双方均对 100；仅本轮对 23；仅作者对 22；双方均错 81。
- 本轮用时：91.1 分钟；最多 16 个并发请求。
- 本轮已知 token 的估算费用：¥9.7366；包含前次 ¥0.43 预留及未知用量保守记账的累计预算占用：¥19.3001。
- 输入 tokens：3665619；输出 tokens：507965；总计：4173584。输出已包含思考 tokens。这些是已知量合计；输入/输出/总量分别有 20/20/20 次缺失，未按 0 补齐。
- 停止原因：`None`。`None` 表示未触发错误或预算停止。

## 各任务结果

作者列仅在本轮有效且成功匹配的样本上计数。错误或未完成请求不能被静默排除后宣称完成全部评测。

| 任务 | 全量比较对 | 抽取 | 请求结束 | 本轮正确/有效 | 作者正确/匹配有效 |
| --- | ---: | ---: | ---: | ---: | ---: |
| aptos2019-blindness-detection | 1225 | 10 | 10 | 6/9 | 6/9 |
| denoising-dirty-documents | 974 | 10 | 10 | 6/9 | 6/9 |
| detecting-insults-in-social-commentary | 350 | 10 | 10 | 8/10 | 5/10 |
| dog-breed-identification | 3 | 3 | 3 | 1/2 | 2/2 |
| google-quest-challenge | 1224 | 10 | 10 | 5/10 | 8/10 |
| jigsaw-toxic-comment-classification-challenge | 10 | 10 | 10 | 2/10 | 2/10 |
| leaf-classification | 136 | 10 | 10 | 7/10 | 7/10 |
| learning-agency-lab-automated-essay-scoring-2 | 190 | 10 | 10 | 6/10 | 6/10 |
| lmsys-chatbot-arena | 1220 | 10 | 10 | 7/10 | 7/10 |
| mlsp-2013-birds | 1221 | 10 | 10 | 2/9 | 3/9 |
| new-york-city-taxi-fare-prediction | 429 | 10 | 10 | 3/9 | 4/9 |
| nomad2018-predict-transparent-conductors | 3 | 3 | 3 | 3/3 | 3/3 |
| petfinder-pawpularity-score | 239 | 10 | 10 | 7/10 | 5/10 |
| plant-pathology-2020-fgvc7 | 15 | 10 | 10 | 5/10 | 6/10 |
| predict-volcanic-eruptions-ingv-oe | 1213 | 10 | 10 | 4/9 | 4/9 |
| random-acts-of-pizza | 1225 | 10 | 10 | 5/9 | 6/9 |
| spooky-author-identification | 1220 | 10 | 10 | 4/9 | 4/9 |
| stanford-covid-vaccine | 1222 | 10 | 10 | 4/8 | 5/8 |
| statoil-iceberg-classifier-challenge | 1223 | 10 | 10 | 2/9 | 4/9 |
| tabular-playground-series-dec-2021 | 275 | 10 | 10 | 3/9 | 2/9 |
| tensorflow-speech-recognition-challenge | 1011 | 10 | 10 | 6/8 | 4/8 |
| tgs-salt-identification-challenge | 880 | 10 | 10 | 5/9 | 5/9 |
| the-icml-2013-whale-challenge-right-whale-redux | 275 | 10 | 10 | 3/9 | 2/9 |
| tweet-sentiment-extraction | 210 | 10 | 10 | 5/8 | 4/8 |
| us-patent-phrase-to-phrase-matching | 1223 | 10 | 10 | 7/9 | 7/9 |
| ventilator-pressure-prediction | 1222 | 10 | 10 | 7/9 | 5/9 |

## 对照与适用范围

这不是论文全量复现。每任务近似等量抽样改变了任务权重，因此本轮准确率不能直接与论文全量 micro accuracy 61.5% 比较。主要参照是作者在同一批样本上的一次公开预测记录，不是作者三次运行的平均值；每任务最多 10 对也不足以可靠比较单个任务优劣。

采样在查看这些样本的作者预测前固定，种子为 `20261021`，每任务使用独立的 `random.Random(f"{seed}:{task}")`，保留候选顺序。全部 18,438 对标签已核对分数方向；选中的代码、任务描述和数据报告通过 SHA-256 验证。真实标签和分数只用于本地评分，不作为额外评测字段发送给 LLM，也未执行候选代码。

## 固定配置与差异

- 官方代码提交：`c4d52cf99bd870d830b456ac7c0684aec1aef375`；数据版本：`6b322cb88bdbcb2b2d3897ec7d0ded94a5bb2d06`。
- 作者提示词、解析器、准确率函数原样复用；使用 `allow_cot=True`、`prompt_boost=True`。
- 模型：SiliconFlow `Pro/deepseek-ai/DeepSeek-V3.2`，温度 1.0，开启 Thinking。
- 思考上限 32768、回答上限 8192；作者 CLI 未显式固定同样的输出限制。服务商、服务端模型快照和默认采样参数仍可能有差异。
- Python 3.12.5，标准库 HTTP + certifi；与作者推荐 Python 3.10 + OpenAI SDK 环境不同。
- 初期非流式调用出现长请求超时，随后改为流式接收并继续未派发样本，已结束的成功或失败请求均未重试。接收方式变更不改变模型、提示和采样参数；分阶段设置见结果 JSON 的 `transport_history`。本轮共有 19 个超时记录，其未知用量保留保守费用预留。
- 作者参考：`deepseek-reasoner_1p0_pboost_cot_20251209_164656`。使用有序文件名后缀及真实分数唯一匹配，并核对真实标签。
- 累计预算 ¥20；派发前预留在途请求的保守最大费用，按实际 token 释放预留；未知用量保留预留。API 错误后停止新增请求，已发送的请求仍可能完成并产生费用。估价不等同代金券或现金账单。

## 文件

- `coverage_manifest.json`：样本、完整标签计数、数据校验值。
- `coverage_author_reference.json`：作者同样本结果及原始报告校验值。
- `coverage_results.json`：逐对指标、费用和配对对照。
- 本地 `outputs/coverage-20261021/`：原始请求、响应和增量进度；不上传 GitHub。

来源：[官方代码](https://github.com/zjunlp/predict-before-execute)、[固定版数据](https://huggingface.co/datasets/zjunlp/PredictBeforeExecute/tree/6b322cb88bdbcb2b2d3897ec7d0ded94a5bb2d06)、[SiliconFlow 定价](https://www.siliconflow.cn/pricing)。
