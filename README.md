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

## 后续评测

1. 固定官方代码版本，核对样本、提示词、推理参数和评分口径。
2. 首轮 10 对真实样本联调已完成，扩大任务覆盖前保留固定抽样和版本记录。
3. 估算费用后扩大评测，并记录模型、样本范围和实验结果。

## 来源

- [官方代码](https://github.com/zjunlp/predict-before-execute)
- [论文](https://aclanthology.org/2026.acl-long.182/)
- [Preference Corpus](https://huggingface.co/datasets/zjunlp/PredictBeforeExecute)

下载的论文、数据和运行输出默认不纳入版本控制。
