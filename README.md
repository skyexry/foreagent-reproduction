# ForeAgent reproduction

复现 ForeAgent 的 pairwise 判断和候选筛选控制逻辑，为后续固定比较预算下的排序研究建立可核验基线。当前已发布冻结版本为 `baseline-reproduction-v1`；原版与两种缓存修正版分别记录。

已发布 [baseline-reproduction-v1](https://github.com/skyexry/foreagent-reproduction/releases/tag/baseline-reproduction-v1)，附三份实验附件。发布记录及固定下载地址见 `provenance/release.json`；标签固定在 `fd55d93`，后续发布元数据提交保持核心冻结文件的内容。

## 结果与证据范围

| 实验 ID | 范围 | 保存结果 | 证据 |
| --- | --- | --- | --- |
| pairwise246-v1 | 26 任务、246 对；首轮加失败补调共 266 次真实 API 调用 | 136/246 = 55.28%；同样样本上作者单次公开结果 130/246 | `experiments/coverage_retry_results.json` |
| historical-v1 | 作者 15 次真实运行；129 完整批次、1,290 候选 | rank/round、排序及最终执行均 129/129 批一致；87 批触发强制回退 | `experiments/historical-v1/` |
| corpus26-v2 | 26 任务；每版本 7,800 次离线回放；完整执行策略 | 并列均匀选一命中 20.43% → 21.20%；最终执行集合包含最佳 21.60% → 22.44% | `experiments/corpus26-v2/` |
| five-task-v1 | 5 完整图任务；每版本 500 次；只测筛选 | 排序首个候选命中 17.4% → 16.4% | `experiments/tournament_replay_results.json` |
| mechanisms-v1 | 门控、pending、缓存、停止、并列排名、执行回退 | 18 门控案例、14 停止案例、6 路由案例、100 原生回放核对 | `experiments/mechanisms-v1/audit.json` |

历史重演给定已保存判断序列及日志中的概率结果，再核对原代码输出。普通比较双方和 pending 节点身份有日志交叉核验；复赛对手采用标明的演示 RNG，原 RNG 状态仍待恢复。140 个日志批次中，6 个未完成、5 个缺失最终 journal 节点，单独列账。它证明条件控制流程一致。

Corpus 回放使用固定候选池、顺序及初始随机种子；反馈来自作者的一次公开 pairwise 运行。候选以文件名代替代码文本作唯一标识，反馈模型、prompt 与历史 Agent 轨迹的设置有区别。21 个任务池大小为 10，其余为 3/3/5/6/8；候选池重叠、重复回放相关，结果为描述性宏平均。跨版本路径变化也会改变后续 RNG 消耗。

缓存修正对这些数据的提升约为 **0.77 个百分点筛选命中、0.83 个百分点最终执行命中**。五任务实验使用另一修复实现、另一抽样和首位 tie-break 口径，单独解释。完整在线生成—筛选—训练循环、训练时间收益、新比较策略和早停策略留待后续验证。

## 目录

- 根目录：已有 pairwise 工具、选择适配器、机制核验和研究提案。
- `vendor/foreagent_upstream/`：固定作者提交的原始控制代码、配置和 MIT 许可证。
- `vendor/foreagent_variants/`：明确命名的 canonical 缓存方向修正版。
- `reproduction/{historical,corpus}/`：迁移后的回放及独立评分核验。
- `scripts/`：数据获取、统一离线复现、冻结校验和提交内容扫描。
- `experiments/`：协议、冻结输入、汇总结果；`superseded/` 保存旧执行口径说明。
- `reports/hw3/`：现有 NeurIPS TeX、模板、PDF 和实验版本对应说明。
- `provenance/`：来源映射、数据/附件校验值、迁移前快照、初始工作区状态。
- `data/`、`outputs/`：按说明获取的原始数据/附件；`runs/`：新生成的完整轨迹，均由 Git 忽略。

## 安装与数据

核验环境为 CPython **3.12.5**，macOS；核心回放使用标准库。既有 API 工具和测试使用固定版本的 certifi。完整 Agent 的 CUDA/训练环境属于后续范围。

```bash
git clone https://github.com/skyexry/foreagent-reproduction.git
cd foreagent-reproduction
git checkout baseline-reproduction-v1
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-reproduction.txt
python scripts/verify_freeze.py
python scripts/fetch_data.py --group corpus --group historical
python scripts/fetch_data.py --group corpus --group historical --check-only
```

源码固定到 `zjunlp/predict-before-execute@c4d52cf99bd870d830b456ac7c0684aec1aef375`；数据固定到 `zjunlp/PredictBeforeExecute@6b322cb88bdbcb2b2d3897ec7d0ded94a5bb2d06`。每个文件的固定下载 URL、大小和 SHA-256 见 `provenance/data_manifest.json`。gzip 条目校验解压后的内容。核心输入为 52 个 corpus 文件和 45 个历史文件；大型原始记录约数百 MB，以固定来源下载。

246 对本项目 API 原始响应由独立附件 `pairwise-246-evidence.zip` 提供。附件校验值、大小和冻结时的本地来源见 `provenance/attachments.json`；已发布的下载地址见 [Release](https://github.com/skyexry/foreagent-reproduction/releases/tag/baseline-reproduction-v1) 与 `provenance/release.json`。收到附件后运行：

```bash
python scripts/fetch_data.py --attachment pairwise --archive /path/to/pairwise-246-evidence.zip
```

另有历史日志完整包及 corpus 完整逐次轨迹包，分别保留独立附件及校验值；核心复现会重新生成轨迹。可显式使用本地缓存加速，所有输入仍逐个校验：

```bash
python scripts/fetch_data.py --group corpus --local-root /path/to/previous-repository
python scripts/fetch_data.py --group historical --local-root /path/to/author-real-batch-replay --layout historical
```

## 离线运行与核验

```bash
python -m unittest discover -s tests -v
python scripts/reproduce.py all
```

`all` 依次核验 selection、pairwise、five-task、mechanisms、historical、corpus。输入包括前述公开数据及 pairwise 附件；真实 API 调用和候选训练均为 0。仅使用公开数据时可依次执行：

```bash
python scripts/reproduce.py selection
python scripts/reproduce.py five-task
python scripts/reproduce.py mechanisms
python scripts/reproduce.py historical
python scripts/reproduce.py corpus
```

每个实验输出到 `runs/<experiment>/`。重跑前先将已有输出移动留存，统一入口要求新目录。独立核验逐次评分、强制回退公式、宏平均和保存结果；corpus 的 runs、解压后 traces、汇总 JSON 与原保存内容 SHA-256 全部相同，历史结果也逐文件匹配。`runs/corpus/verification_portable.json` 分开统计比较记录、缓存读取、每场唯一反馈数之和、全实验去重反馈数、真实 API 调用数。

既有 `run_coverage.py` 等脚本用于此前的有偿服务实验，具体记录在原协议中。本轮统一复现入口全部使用已有反馈。重建原 pairwise prompt 输入可额外运行 `fetch_data.py --group pairwise-inputs`，该组含任务说明、分析报告和所选代码。

## 版本与接续

- `original@c4d52cf`：作者原始 `world_model.py`，SHA-256 `df85087f…d79`；缓存方向等原行为保留。
- `cache_direction_canonical-v1`：`vendor/foreagent_variants/world_model_cache_direction_canonical.py`，用于 corpus26-v2，只修正缓存存取时的方向映射。
- `cache_fixed_instance_locked-v1`：`foreagent_selection.CacheFixedWorldModel`，用于 five-task-v1，同时包含实例隔离和成对并发锁。

完整固定值见 `BASELINE_FREEZE.json`。报告对应 `reports/hw3/VERSION.md`，交接从 `STATUS.md` 开始，实验历史见 `EXPERIMENTS.md`，聊天协作规则见 `AGENTS.md`。

组织方式借鉴 [vukrosic/llm-memory-env](https://github.com/vukrosic/llm-memory-env) 的逐轮实验记录、预测与结果分开、保留旧口径、快速阅读已有结果与运行入口分开的方式。这里只采用文件组织原则。原作者代码及数据来源见 `THIRD_PARTY_NOTICES.md`。

## R6：同一反馈上的简单胜率汇总

R6 本地实验分支为 `codex/r6-winrate`，注册提交 `084ad53` 先于实现与正式运行。7,800 场配对比较的主指标为21.2000%→22.4997%，regret略升，事前联合推进标准未达到。协议、作业、完整结果与独立验证见 [R6报告](experiments/round-06/report.md)。基线Release和冻结内容保留。R6复跑从干净的该分支提交开始，仅需corpus数据及已发布baseline完整轨迹附件；命令见R6报告。
