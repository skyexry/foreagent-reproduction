# 四臂训练与封存

固定规格见 `model_spec.json`。使用 CodeT5-small 冻结的 512 维代码、任务上下文向量，训练 1,024 参数线性裁判。四臂共享表示、样本、训练任务内标准化、零初始化与 80 步全批量 Adam，差异仅为监督样本权重。每个任务在每臂中的总权重为一，随后对 25 个训练任务取平均。

`data.py` 按 heldout task 逐折加载其余任务的标签与权重文件。训练对经过同内容检查及目标任务字节 / canonical AST 内容过滤。标准化使用筛除后训练对涉及的唯一代码向量和 25 个训练任务向量；目标输入仅应用训练参数。推断覆盖 `code_files.json` 的全部 18,224 对。代码 ID 用于索引和确定平局规则。

```bash
python3 -B experiments/trajectory-weighted-judge-v1/train/fit.py --freeze-spec-only
python3 -B experiments/trajectory-weighted-judge-v1/train/fit.py
python3 -B experiments/trajectory-weighted-judge-v1/train/verify.py
```

`oof_predictions.jsonl.gz` 每行保存 task、canonical pair、四臂 winner 和 ties。`prediction_seal.json` 绑定预测、训练源码、表示、credit 收据及逐折模型 / 训练对清单的 SHA-256。`verify.py` 独立检查内容过滤、模型参数与全部封存方向；执行效用由独立评价阶段接入。

模型容量与解释范围：这是冻结小型公开编码器上的线性先导。代码截断、任务上下文与编码器资源见 representation 收据。26 个任务为开发任务，训练折相互重合；字节和 AST 检查之后仍可能存在改名或局部编辑的近重复。执行标签的来源和历史运行差异也会影响学习信号。

`preflight_checks.json` 记录训练封装验收，其中包含两次三候选 / 两维合成优化器检查；实际语料采用 26 折 × 4 臂，共 104 次拟合。

本次执行已完成 104 次实际语料拟合，共 8,320 次优化步骤，训练与封存耗时 17.1169 秒；两次合成检查另计。每折保留 16,648–17,868 对、827–874 个唯一训练候选。26 折累计移除 150 个同内容监督对（按训练折重复计数），目标任务跨任务 byte / AST 重合移除数为 0。全部 18,224 对完成封存；四臂精确平局频数均为 0。独立方向回算、模型参数、逐折训练边界与内容过滤检查通过，收据为 `verification.json`。训练产物约 3.75 MB，其中压缩预测为 140,976 字节。
