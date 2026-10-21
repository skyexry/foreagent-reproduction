# ForeAgent 第一阶段复现

目标：复现已有候选代码的离线两两比较，对照真实标签计算准确率，再开展预算受限的比较与排序实验。

## 当前状态（2026-10-21）

- 研究方案：`Proposal.md`。
- 已通过 SiliconFlow 调通 `Pro/deepseek-ai/DeepSeek-V3.2`，启用 Thinking。
- 用户提供的首次测试结果：17 × 23 = 391；结束原因 `stop`；输入 15 tokens、输出 109 tokens（其中思考 101 tokens），总计 124 tokens。
- 尚未下载和核对完整评测数据，尚未运行真实比较样本；接口成功不代表论文结果已复现。
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

## 下一步

1. 固定官方代码版本，核对样本、提示词、推理参数和评分口径。
2. 在 10–20 对真实样本上检查输出解析、失败处理和 token 用量。
3. 估算费用后扩大评测，并记录模型、样本范围和实验结果。

## 来源

- [官方代码](https://github.com/zjunlp/predict-before-execute)
- [论文](https://aclanthology.org/2026.acl-long.182/)
- [Preference Corpus](https://huggingface.co/datasets/zjunlp/PredictBeforeExecute)

下载的论文、数据和运行输出默认不纳入版本控制。
