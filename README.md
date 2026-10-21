# ForeAgent 第一阶段复现

目标：复现已有候选代码的离线两两比较，对照真实标签计算准确率，再开展预算受限的比较与排序实验。

## 当前状态（2026-10-21）

- 研究方案：`Proposal.md`。
- 已通过 SiliconFlow 调通 `Pro/deepseek-ai/DeepSeek-V3.2`，启用 Thinking。
- 用户提供的首次测试结果：17 × 23 = 391；结束原因 `stop`；输入 15 tokens、输出 109 tokens（其中思考 101 tokens），总计 124 tokens。
- 已完成 10 对真实样本联调：9/10 正确，10/10 正常解析，估算费用 ¥0.42；完整对照见 [首轮报告](experiments/smoke_report.md)。尚未完成全量论文复现。
- 作者实际使用的 API 服务商尚未确认，实验应记录本项目使用的服务商和参数。

## 本地 API 检查

`check_api.py` 仅依赖 Python 标准库。

```bash
# 交互输入并保存密钥；此操作不调用 API
python3 check_api.py --save-key

# 读取已保存密钥，发起一次小额接口测试
python3 check_api.py
```

密钥保存在 `~/.config/foreagent/siliconflow.key`，是权限为 `600` 的本地明文文件，不属于仓库。未保存时，测试脚本会交互请求密钥。不要提交密钥或包含密钥的日志。

测试使用 `enable_thinking=True`、`thinking_budget=1024`、`max_tokens=256`，仅验证接口，不作为正式论文复现参数。

## 真实样本联调

```bash
python3 -m pip install -r requirements-smoke.txt
python3 prepare_smoke.py
python3 run_smoke.py        # 只检查输入，不调用 API
python3 run_smoke.py --run  # 付费调用固定的 10 对样本
```

准备脚本需要系统提供 `curl`。联调实际使用 Python 3.12.5 和标准库网络接口，而非官方建议的 Python 3.10 / OpenAI SDK 环境；作者的提示词、响应解析及准确率函数原样复用，来源见 `vendor/foreagent/README.md`。

固定抽样：`leaf-classification` 和 `detecting-insults-in-social-commentary` 各 5 对，随机种子 `20261021`，保留原候选顺序。数据版本和文件校验值保存在 `experiments/smoke_manifest.json`。标签与分数只用于本地评分，不传给 LLM。

请求使用温度 `1.0`、Thinking 开启、`--cot` 和 `--prompt-boost` 对应提示设置。为限制本次调用开销，显式设定思考上限 `32768`、回答上限 `8192`，无自动重试；这些限制及服务商差异必须在正式复现时说明。启动前按输入 UTF-8 字节数和输出上限保守预估费用，10 对总额须低于 ¥20；实际估价使用响应 token 数和公开单价，不等同平台账单。

完整请求和响应保存在被 Git 忽略的 `outputs/smoke-20261021/`。已有运行记录时脚本拒绝再次付费调用，避免误操作重复扣费。**这 10 对用于联调，不能直接与论文全量 61.5% 作复现结论比较。**

## 26 任务覆盖评测

```bash
python3 prepare_coverage.py        # 固定抽样并核对数据，不调用 LLM
python3 run_coverage.py            # 只检查完整输入及费用预留
python3 compare_coverage.py        # 匹配作者公开预测，不调用 LLM
python3 run_coverage.py --run --workers 16
python3 report_coverage.py         # 运行结束后验证并导出结果
```

官方任务清单包含 26 个任务、18,438 对候选。本轮每任务抽取最多 10 对，两个任务各只有 3 对，因此合计 246 对。输入与抽样版本见 `experiments/coverage_manifest.json`。采用任务轮流派发，避免预算提前耗尽时只测到前几个任务。

累计费用上限为 ¥20，包括前次测试向上取整的 ¥0.43。并发请求在发送前预留保守费用，返回后依据用量结算；未知用量保留预留。余额、网络等 API 错误会停止新增请求，已发送的请求仍可能完成并产生费用。没有自动充值或自动重试。预算和错误停止行为通过无网络模拟测试验证：`python3 -m unittest discover -s tests -v`。

完整请求与响应保存在本地 `outputs/coverage-20261021/`；已有记录时默认拒绝重复运行。确认上一进程结束后，可用 `--run --resume` 只继续尚未派发的样本；成功和失败的已记录请求均不会自动重试。采用流式接收，避免生成期间长时间没有返回数据而超时；分块接收测试、预算测试和恢复去重测试均不调用真实 API。初期非流式请求及后续流式请求分别保存在原始记录中，模型和提示参数不变。

作者同样本对照是一次公开运行，不等于论文三次运行平均值。近似等量抽样改变了任务权重，不能直接将这批样本的准确率与论文全量 micro accuracy 比较。

## 审计记录与评分

`python3 export_coverage_audit.py` 从原始记录生成本地 `outputs/coverage-20261021/audit/` 下的三份主文件：实际配置 `run_config.json`、固定样本与标签 `pairs_manifest.json`、逐次实际请求与响应 `attempts.jsonl`。完整输入文件及当前代码快照一并保留并校验哈希；不调用 API，不改变评分。加 `--follow` 可跟随当前批次更新，批次停止后生成结果报告；它不会启动或恢复付费请求。

[评分与缺失记录口径](experiments/coverage_scoring.md) 明确 246 对分母、失败处理、无自动重试、micro/macro 和作者对照。缺失的时间、token、失败正文和早期实现快照明确标记，不用 0 或当前版本代替。完整输入/响应仅保存在本地，被 Git 忽略；GitHub 保存脚本、固定抽样清单和实验说明。

## 后续评测

1. 固定官方代码版本，核对样本、提示词、推理参数和评分口径。
2. 首轮 10 对真实样本联调已完成，扩大任务覆盖前保留固定抽样和版本记录。
3. 估算费用后扩大评测，并记录模型、样本范围和实验结果。

## 来源

- [官方代码](https://github.com/zjunlp/predict-before-execute)
- [论文](https://aclanthology.org/2026.acl-long.182/)
- [Preference Corpus](https://huggingface.co/datasets/zjunlp/PredictBeforeExecute)

下载的论文、数据和运行输出默认不纳入版本控制。
