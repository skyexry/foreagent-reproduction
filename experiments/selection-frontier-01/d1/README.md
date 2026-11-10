# D1：随机链后再问一次的实际价值

首轮完整运行已完成：850 场、425 池、26 个开发任务，共封存 2,550 个选择。完整历史分支的 1,700 次选择、原评分、逐任务汇总和查询账本均通过复验。

| 指标（任务等权） | 均值 | 95% 任务簇区间 |
|---|---:|---:|
| T−U 损失差 | +0.002893 | [−0.013130, +0.023516] |
| U 相对就停的收益 | −0.007547 | [−0.025620, +0.004617] |
| T 相对就停的收益 | −0.010440 | [−0.046039, +0.012347] |

S 为链后就停，U 为读取已存随机下一边，T 为读取已存旧主动下一边。T−U 为正表示 T 损失更高。S/U/T 的平均损失分别为 0.292431 / 0.299978 / 0.302871。

错改差 D_harm=+0.009583；少纠正差 D_missed=−0.006690，两者之和回到主差。T 同时产生更多纠正收益和更多错改损失，净差受任务组成影响。留一任务主差范围为 [−0.005088, +0.005180]；移除 Petfinder（2场）或纽约出租车任务（40场）后主差转负。

按预注册优先级，两种补问平均收益均为负，但 T 的收益区间上端高于 δ=0.01；“两种补问均弱于就停”的完整门槛尚待更多精度。留一任务会改变主差方向，当前决定为保留 C0，结束本轮开发判断。D2 的进入门槛由 `final_info.json` 原样记录。

逻辑读取总数 S/U/T 为 7,598 / 8,448 / 8,448；物理新增 API、训练、GPU 使用均为 0。本机运行约 2.86 秒，上限 600 秒。

## 证据与复跑

- `run_1/experiment.py`：执行前保存的完整脚本快照；`experiment.py` 为本轮入口。
- `run_1/command.json`、`selection_command.json`：主命令、子进程命令、环境、时间与脚本哈希。
- `run_1/sealed_selections.jsonl`、`selection_seal.json`：先封存的选择及哈希。
- `run_1/projected_full_traces.jsonl`：按五个公开字段投影的完整历史轨迹。
- `run_1/full_length_verification.json`：完整轨迹及历史评分复验。
- `run_1/per_job_evidence.jsonl`、`per_task.jsonl`：逐场及26行逐任务统计，包括原单位收益与池跨度。
- `run_1/diagnostics.json`、`strata.json`、`leave_one_task_out.json`：翻转、有效/弃权、相同/不同下一边、所有池大小与留一诊断。
- `run_1/final_info.json`、`notes.md`、`stdout.log`：摘要、解释及日志。
- `run_1/input_manifest.json`、`output_manifest.json`：输入与全部产物哈希。
- `audit.py`、`audit_1.json`：结果回读审计及收据，重算任务均值、主区间、留一、自然控制与账本。

从本目录执行：

```bash
python3 -B experiment.py --out_dir=run_2
python3 -B audit.py run_1
```

`run_2` 仅示范新的输出名称；本轮成功分析次数为1。目录冲突会保留既有产物。

## 解释范围

26 个任务均为已检查过的开发数据，两种 seed 为配对重复。任务簇区间反映任务组成波动；裁判重采样、训练重复和新任务漂移另需证据。效用按池内跨度归一化；逐任务原单位收益与跨度用于观察窄池和异常大跨度的影响。`final_info.json` 中 `raw_utility_gains` 的跨任务机械均值混合了不同计分单位，解释与引用应使用 `per_task.jsonl` 中的同任务原单位值。

这次采用 AI Scientist 的编号目录、脚本快照、`final_info.json` 和 notes 记录形式，由本地脚本执行。原生 launcher 集成为后续独立工作。
