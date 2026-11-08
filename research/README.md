# 研究入口：Environment 与 Evals

**当前状态：离线研究接口已验收。下一步：读模块与文献，形成一套可审阅方案。**

接口像一个实验插槽：换入“决定比较谁、何时停止”的策略，沿用同一批候选、反馈预算和评分规则，比较它与 C0 的表现。

| 已固定 | 内容 |
|---|---|
| Environment | 26 个开发任务、425 候选池、850 场；每池最多 10 候选，每场最多 13 条唯一反馈 |
| 策略权限 | 查看候选 ID、已查询的反馈、剩余预算；输出下一对比较或停止 |
| Evals | 任务等权选择损失、最佳命中率、查询数、任务簇区间；统一处理并列和失败 |
| 参考 | C0 修正版原淘汰赛；随机比较示例用于接口验收和同汇总器控制 |
| 隔离 | 每场独立系统沙箱；项目数据读取、外部写入和网络受限；预算由 host 执行 |

## 现在先看什么

1. [模块卡](modules.md)：各模块做什么、当前规则、可修改位置和评价方式。
2. 围绕比较分配/早停读原始文献，形成方案卡：**哪个问题 → 哪些文献机制 → 为什么配合 → 最小实验 → 什么结果支持它**。
3. 方案审阅后，把策略交给统一运行入口；AI Scientist 的具体版本接入、代码生成工作区隔离和总实验预算另行验收。

本轮已经完成接口固定，研究方案尚待文献依据。26 个任务全部属于开发数据；方法冻结后再准备新任务确认和在线端到端验证。

## 首次准备

从 GitHub 获取代码后，用已登录的 GitHub CLI 下载同版本固定输入。附件约 57 MB，逐项绑定 1,182 个保护文件；恢复工具先检查全部内容和已有文件哈希，再补入缺失文件。

```bash
gh release download research-env-v1 --repo skyexry/foreagent-reproduction \
  --pattern research-env-v1-protected-inputs.zip --dir downloads
python3 -B scripts/restore_research_env.py \
  --archive downloads/research-env-v1-protected-inputs.zip
python3 -B -m reproduction.research_env_v1 status --json
```

已有完整本机数据时，用 `python3 -B scripts/restore_research_env.py --check-only` 核验即可。附件来源、固定版本和 SHA-256 见 [input_bundle.json](input_bundle.json)。

## 给 Codex / 实验框架的调用

在项目根目录运行，使用本机已验收的 Python 3.12.5；策略沙箱依赖 macOS `sandbox-exec`。每次选择新的输出目录编号。

```bash
# 查看当前状态，同时检查冻结文件哈希
python3 -B -m reproduction.research_env_v1 status --json

# 接口短测：3 场，用随机示例验证调用链
python3 -B -m reproduction.research_env_v1 run \
  --policy research/policies/example_random.py \
  --limit-jobs 3 \
  --output experiments/research-env-v1/runs/random-smoke-001

# 完整开发评测：换成方案对应的策略文件，使用全部 850 场
python3 -B -m reproduction.research_env_v1 run \
  --policy research/policies/example_random.py \
  --output experiments/research-env-v1/runs/random-full-001

# 独立重建轨迹和预算，再重算分数；已有评价须逐项一致
python3 -B -m reproduction.research_env_v1 evaluate \
  --run experiments/research-env-v1/runs/random-full-001
```

`run --baseline --output <新目录>` 复跑固定 C0。运行保存策略快照、每场选择/反馈轨迹、预算账本和时间；`evaluation/summary.json` 给出评价。策略失败按原定场数计入主结果。完整运行的“新策略减 C0”损失差小于 0 表示更好；解释比较分配的作用时，也要与同汇总器随机控制比较。

Codex 的外层工具沙箱可能阻止启动系统策略沙箱；此时使用应用的受审查执行权限，保持策略自身的隔离规则。首次迁移机器先跑接口测试与短测，再启动完整开发评测。

## 验收证据与成本

- [验收记录](../experiments/research-env-v1/acceptance.json)：17 项测试通过；C0 850 场、随机控制 850 场的选择、查询轨迹、账本及逐任务统计精确复现旧结果。
- C0 选择阶段约 5.40 秒，随机策略约 30.95 秒；本机 CPU 实测，另计独立评分与输入核验时间。本轮付费模型调用、训练和 GPU 租用均为 0。
- 177 项旧 clean-ranking 产物、48 项历史保护文件、946 项原始输入来源通过核验；可信代码/输入共 1,182 个哈希条目。
- 重做验收：`python3 -B experiments/research-env-v1/check_acceptance.py`；明细见 [tests.log](../experiments/research-env-v1/tests.log)。

## 机器入口

| 文件 | 用途 |
|---|---|
| [state.json](state.json) | 已验收、待完成、唯一下一步及证据哈希 |
| [registry.json](registry.json) | 模块、数据、预算、可见信息、评测契约 |
| [protected_manifest.json](protected_manifest.json) | 可信实现与输入的固定版本；策略另存快照 |
| [policies/example_random.py](policies/example_random.py) | 可运行的策略示例，定义 `decide(observation)` |
| [AGENTS.md](AGENTS.md) | 研究代理如何先形成方案、再执行实验 |
