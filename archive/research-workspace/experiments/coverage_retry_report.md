# 首轮与补调结果（2026-10-21）

固定 246 对，首轮 226 对有效、123 对正确；首轮有效准确率 54.42%，有效输出率 91.87%，全样本正确率 50.00%。

经用户授权，仅对 20 个失败样本各补调一次，补调 20 个有效。总计 266 次调用，合并后 246 对有效、136 对正确：有效输出率 100.00%，有效准确率 55.28%，全样本正确率 55.28%。采用首轮有效结果；首轮失败时采用第二次有效结果。没有按对错选择重试，也没有覆盖失败。原始输入和生成参数逐对核对相同；补调采用流式接收、4 并发，旧 ¥20 阈值不再用于这 20 次补调。

同样有效样本上，作者一次公开运行正确 130/246。双方均对 106，仅本轮对 30，仅作者对 24，双方均错 86。这些是描述性差异，不能据此断言优于作者或显著优于随机猜测；同任务和重复候选造成配对依赖，没有把 246 对当独立样本做显著性检验。此样本实验不是全量论文效果复现。

所有调用的已知 token 估算费用 ¥10.2098（不含前次 smoke），另有 20 次调用用量/实际费用未知；不将其当作零费用，预算预留也不冒充账单。完整用量及缺失计数在 JSON 中。

| 任务 | 样本 | 有效 | 正确 | 作者正确（全部选中样本） |
| --- | ---: | ---: | ---: | ---: |
| aptos2019-blindness-detection | 10 | 10 | 6 | 6 |
| denoising-dirty-documents | 10 | 10 | 6 | 6 |
| detecting-insults-in-social-commentary | 10 | 10 | 8 | 5 |
| dog-breed-identification | 3 | 3 | 2 | 3 |
| google-quest-challenge | 10 | 10 | 5 | 8 |
| jigsaw-toxic-comment-classification-challenge | 10 | 10 | 2 | 2 |
| leaf-classification | 10 | 10 | 7 | 7 |
| learning-agency-lab-automated-essay-scoring-2 | 10 | 10 | 6 | 6 |
| lmsys-chatbot-arena | 10 | 10 | 7 | 7 |
| mlsp-2013-birds | 10 | 10 | 2 | 4 |
| new-york-city-taxi-fare-prediction | 10 | 10 | 4 | 5 |
| nomad2018-predict-transparent-conductors | 3 | 3 | 3 | 3 |
| petfinder-pawpularity-score | 10 | 10 | 7 | 5 |
| plant-pathology-2020-fgvc7 | 10 | 10 | 5 | 6 |
| predict-volcanic-eruptions-ingv-oe | 10 | 10 | 5 | 4 |
| random-acts-of-pizza | 10 | 10 | 6 | 6 |
| spooky-author-identification | 10 | 10 | 5 | 5 |
| stanford-covid-vaccine | 10 | 10 | 5 | 6 |
| statoil-iceberg-classifier-challenge | 10 | 10 | 3 | 4 |
| tabular-playground-series-dec-2021 | 10 | 10 | 4 | 3 |
| tensorflow-speech-recognition-challenge | 10 | 10 | 6 | 4 |
| tgs-salt-identification-challenge | 10 | 10 | 6 | 5 |
| the-icml-2013-whale-challenge-right-whale-redux | 10 | 10 | 4 | 2 |
| tweet-sentiment-extraction | 10 | 10 | 6 | 5 |
| us-patent-phrase-to-phrase-matching | 10 | 10 | 8 | 8 |
| ventilator-pressure-prediction | 10 | 10 | 8 | 5 |

本地原始记录：outputs/coverage-20261021/；补调记录：其 retry-attempt-002/ 子目录（含请求、响应、attempts.jsonl、开始/结束时间与脚本快照）。本报告在两轮结束后核对原始记录生成。首轮报告保留不变。
