# ForeAgent tournament 离线回放（2026-11-07）

## 范围

五个完整比较图任务，每任务 10 个池，每池 10 个候选、5 种排列、2 个复赛种子，共 500 个配对场景、两版本共 1000 次 tournament。
使用作者一次公开预测，本轮 API 调用为 0，候选训练为 0。它是筛选模块的离线适配；当前模型的 246 对结果属于另一组实验。

## 结果

任务等权平均：原版最佳命中率 17.4%，修正版 16.4%，随机选择期望 10.0%；归一化排名损失分别 0.339、0.341，随机期望 0.500（越低越好）。
原版缓存身份错误均值 1.078 次/场景，修正版 0.000；选择不同的场景 87 个。
并列时使用原排序第一项；并列率分别 28.8%、30.0%。完整 JSON 同时报告并列集合均匀选取时的命中概率。

**安全退出是本轮最突出的现象。** 原版 95.8%、修正版 96.4% 的场景触发 `round_num > 2*n`。平均比较尝试分别 99.85、97.12 次，而唯一反馈只有 15.51、15.63 条。复赛反复读取同一低置信度缓存不会产生新证据。该现象依赖本轮公开反馈的置信度与离线复用设置，需要后续实时 Agent 验证。

| 任务 | 版本 | 最佳命中率 | 排名损失 | 并列率 | 唯一反馈/场景 | 缓存身份错误总数 |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| aptos2019-blindness-detection | original | 25.0% | 0.386 | 31.0% | 15.35 | 141 |
| aptos2019-blindness-detection | cache_fixed | 23.0% | 0.408 | 32.0% | 15.58 | 0 |
| leaf-classification | original | 10.0% | 0.240 | 28.0% | 14.52 | 58 |
| leaf-classification | cache_fixed | 10.0% | 0.214 | 31.0% | 14.69 | 0 |
| learning-agency-lab-automated-essay-scoring-2 | original | 30.0% | 0.248 | 20.0% | 14.17 | 79 |
| learning-agency-lab-automated-essay-scoring-2 | cache_fixed | 28.0% | 0.224 | 22.0% | 14.20 | 0 |
| random-acts-of-pizza | original | 20.0% | 0.400 | 32.0% | 15.42 | 141 |
| random-acts-of-pizza | cache_fixed | 21.0% | 0.419 | 33.0% | 15.42 | 0 |
| tweet-sentiment-extraction | original | 2.0% | 0.421 | 33.0% | 18.07 | 120 |
| tweet-sentiment-extraction | cache_fixed | 0.0% | 0.439 | 32.0% | 18.24 | 0 |

## 如何解释

- 缓存修复是身份一致性修复。选择质量的上升或下降都作为观测保留。
- 同池排列、种子和不同池共享候选，500 个场景存在依赖；上述为描述性平均，独立任务数为 5。
- 候选池由同任务已发布候选构造，尚未证明它们来自同父节点的同一轮生成。
- 原版和修正版每次均清空缓存；跨任务缓存污染被隔离，不计为本轮修复效果。
- feedback 的反向读取复用同一作者判断，不能作为真实位置交换实验。
- benchmark prompt 与实时 Agent prompt 不同；缺失 confidence 回退为 0.5，不等于校准过的实时判断。
- 此轮任务用于开发诊断。后续效果主张需要独立评测边界及更广任务覆盖。

## 复现与证据

`python3 -m unittest discover -s tests -v`

`python3 verify_foreagent_selection.py`

`python3 replay_foreagent_selection.py`

协议：`experiments/tournament_replay_protocol.md`；逐次比较：`outputs/tournament-replay-20261107/runs.jsonl`；汇总及版本/哈希：`experiments/tournament_replay_results.json`。
轨迹 SHA-256：`b12a924e90c80b62e4dbf0629d5a3d9cd36ae966feaa01c336a968c643c53075`。
