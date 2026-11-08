# clean-ranking-v1：新的独立基线与排序对照

阅读入口：[先读结果](./先读结果.md)。主比较为C0修正版原淘汰赛与coverage_decision_sensitive-v1；random_pairs和coverage_random为机制控制。所有结果属于已查看26任务、单份冻结作者反馈下的开发性评估。

## 输入与独立性

- 作者代码：`c4d52cf99bd870d830b456ac7c0684aec1aef375`。
- Corpus：`6b322cb88bdbcb2b2d3897ec7d0ded94a5bb2d06`。
- 原始作者反馈：`deepseek-reasoner_1p0_pboost_cot_20251209_164656`。26份原始文件的远端ETag/commit校验见[source-remote-check.json](./source-remote-check.json)。
- 数据准备独立从原始代码、group标签和原始反馈构建：有限候选894条，按代码内容固定代表后877个；可查询原始反馈17,877对。完整清单及排除项见[prepared/source_manifest.json](./prepared/source_manifest.json)。
- 正式流程不导入R6–R8实现、作业、反馈附件或结果；只在[保护清单](./historical-protection.json)中记录旧文件哈希，最终确认原样。
- 最多20个不同候选池/任务、2个重复seed；候选上限10，缺边任务在4000次预定覆盖采样失败后逐级降低K，池内要求共同反馈完整。425池、850场，四方法共3,400评分。小任务按实际K和预算报告。

## 协议与源码

[protocol.json](./protocol.json)和[protocol.md](./protocol.md)先于新实现/评分保存。输入覆盖预检的调整与名次元数据修正见[protocol-addendum.md](./protocol-addendum.md)，初始协议保留于protocol-initial.json。正式源码/输入哈希锁见[implementation-lock.json](./implementation-lock.json)。

第一次正式运行后加强了CLI所选输入与哈希锁的绑定检查；方法、作业、预算及假设保持。第一次结果和源码保留于[preflight/formal-attempt-01](./preflight/formal-attempt-01/)，工程性复跑原因见[execution-addendum.json](./execution-addendum.json)。两次选择轨迹与主要指标必须一致。预检工具问题与失败目录保留于[preflight](./preflight/)。

C0补丁为[reproduction/clean_ranking_v1/C0.patch](../../reproduction/clean_ranking_v1/C0.patch)，生成器从固定原件构建独立overlay，原件保持。配对、复赛、原排序键和轮数保护保留；名次分组对齐实际排序键。缓存按原首次查询方向保存语义胜者，任务/报告/模型/温度隔离，门槛读取时重算；每次执行隔离提交，并从最佳节点归档复制代码/预测。

原作者grader与C0grader同输入对照、实际Agent类的受控短链路、六次真实架构短训练属于正确性检查。完整生成/API反馈和长时执行仍按独立在线协议验证。

## 复跑

在有完整固定作者原始数据的本机工作区，用新输出目录保存结果：

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -p test_clean_ranking_v1.py -v
PYTHONDONTWRITEBYTECODE=1 python3 -m reproduction.clean_ranking_v1.run \
  --prepared experiments/clean-ranking-v1/prepared --output /tmp/clean-ranking-new-results
PYTHONDONTWRITEBYTECODE=1 python3 -m reproduction.clean_ranking_v1.verify \
  --prepared experiments/clean-ranking-v1/prepared --output /tmp/clean-ranking-new-results
```

正式评价器在所有选择结束后才载入evaluation_labels。独立核验重建原始反馈身份、唯一预算、共享覆盖、主动选边优先级、并列组、逐场指标与任务等权汇总。[结果](./results/summary.json)、[核验](./results/verification.json)、[逐任务CSV](./results/per_task.csv)、[事后诊断](./results/diagnostics.json)。

安装C0到单独、匹配固定版本的作者检出：

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m reproduction.clean_ranking_v1.install /path/to/separate-author-checkout
```

默认ranking_policy为original；新策略使用agent.ranking_policy=coverage_decision_sensitive、agent.ranking_comparison_budget=13和固定ranking_seed。在线配置还需要独立模型服务、验证成绩合约、预算、候选隔离及部署预检。

## 解释范围

850场共享候选与任务，区间按任务簇计算；独立单位和覆盖限制明确记录。每场最多13条新判断，原淘汰赛可提前结束，缓存读取与预算拒绝单列；回放成本代表逻辑读取，真实token/费用/墙钟由线上实测。并列采用均匀单选期望指标，与Agent实际多候选执行策略分别解释。

主动策略假设一次新有效胜负可能改变最终选择，以总变差距离衡量敏感性；这不是可靠性校准或期望损失保证。其具体新颖性与已有主动排序方法的比较属于后续文献/机制研究，本轮主要完成可复核的负面先导。
