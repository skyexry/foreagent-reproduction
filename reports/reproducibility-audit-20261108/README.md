# ForeAgent 复现审计交付

**当前研究入口：[修正版原排序与新排序：本轮结果](../../experiments/clean-ranking-v1/先读结果.md)。** C0及短测试已执行；新排序平均较弱，优先诊断后再决定后续实验。R6–R8独立存档，正式输入与结果重新建立。

**本轮深入审查：[论文实验设计、比较公平性与Future Plan](./论文实验设计审查_易读版.md)。** 重点说明论文结论能支持到哪一步，以及下一项最有信息的实验。

**建议先读：[这次审计发现了什么，接下来做什么](./先读这份.md)。** 短版按“当前进度、三个重要问题、下一步”解释；详细证据和实验预算可按需查阅。

本次审计确认原版单任务冻结结果为0.2663989312，并建立17项可追踪发现及分阶段研究计划。其中作者一次Stanford运行的最佳节点漏存已由原始候选预测复评确认；本机检出与发布版本的对应关系已核清。

| 文件 | 用途 |
|---|---|
| [AUDIT_REPORT.md](./AUDIT_REPORT.md) | 执行评估、范围与忠实度、优先发现表、公平控制和覆盖/不确定性；逐项证据与修正建议 |
| [ForeCritic_精读与研究判断.md](./ForeCritic_精读与研究判断.md) | 训练配方、易读解释、八个 reviewer 问题和现有数据的用途 |
| [FUTURE_PLAN.md](./FUTURE_PLAN.md) | 本轮负面先导后的推进条件、资源方案与reward-model备选 |
| [FUTURE_PLAN_排序路线存档.md](./FUTURE_PLAN_排序路线存档.md) | 调整前原文：基线修正、R7/查询分配与 V0–V10 方案 |
| [findings.json](./findings.json) | 每项归属、状态、严重程度、观测/推断、证据、影响检查和建议 |
| [evidence/](./evidence/) | 本次重算JSON、日志、作者漏存节点原件及固定公开来源 |
| [checks/](./checks/) | 只读诊断/复评分脚本；控制响应替代模型，读取保存预测替代训练 |
| [verification.json](./verification.json) | 完成检查、范围、版本变化与待验证项 |
| [SHA256SUMS.json](./SHA256SUMS.json) | 本次交付文件的SHA-256清单；该清单自身除外 |

## 证据导航

- [完整原始数据](../../data/reward-model/corpus-6b322cb-raw-v1/README.md)：剩余521份代码已补齐，895份代码及全部原始标签/上下文的974项源文件校验通过；[来源对照](./evidence/corpus-source-check.json)与[补齐核查](./evidence/corpus-completion.json)分别记录作者原件核验及完整内容重复情况。
- [reward-model-data.json](./evidence/reward-model-data.json)：26 任务的代码/标签覆盖、相同内容组、journal 可用节点、输入文件哈希；可由 [只读脚本](./checks/reward_model_data.py) 重算。
- [forecritic-reading.json](./evidence/forecritic-reading.json)：精读来源版本、作者报告与派生数量、初始化来源、代码与权重等材料缺口。
- [online-verification.json](./evidence/online-verification.json)：484作者blob、运行参数、最终节点/代码/预测、四份双评分和行序反例。
- [diagnostics.json](./evidence/diagnostics.json)：起始945项版本背景下的原生最小反例、82节点计数、15份历史checkpoint扫描；[最终诊断](./evidence/diagnostics-final.json)更新当前来源清单哈希，数值相同。
- [candidate-scores.json](./evidence/candidate-scores.json)：13份已执行有效候选的事后外部评分，包含选择差与相关性；保持冻结最终选择。
- [author-missed-node/verification.json](./evidence/author-missed-node/verification.json)：作者95a7c811代码/元数据/预测绑定及双评分，私有误差0.256153144；[source.json](./evidence/author-missed-node/source.json)保存固定revision下载地址和原文件哈希。
- [corpus-labels.json](./evidence/corpus-labels.json)：49对NaN标签、21个NaN最佳、单次作者判断finite-only敏感性。
- [confidence.json](./evidence/confidence.json)：18,438条保存作者判断与246条复现判断的风险/置信度分层；相关性与概率校准分别解释。
- [replays.json](./evidence/replays.json)：129批条件重演、246响应重解析、两版本各7,800场；[corpus-verify.log](./evidence/corpus-verify.log)记录独立评分与冻结指纹核验。
- [publication-check.json](./evidence/publication-check.json)：新发布89d428f的元数据与本机字节一致；[copy-full-verification.log](./evidence/copy-full-verification.log)为947项含records/data及原件全量核验。

## 重跑本机轻量诊断

下列命令适用于本次检视的完整本机研究工作区。`ROOT`应含phase1-reproduction、data、scripts、vendor与reproduction目录。已发布版本的归档布局、数据获取及完整独立重建列为F17后续检查，运行前按实际布局明确路径。完整日志与数据须按phase1 README获取；私有标签由使用者单独准备。

```bash
AUDIT_PROJECT='/Users/shrinn81/Documents/Data Mining/PM Final Project/ML Agent'
AUDIT_DIR="$AUDIT_PROJECT/reports/reproducibility-audit-20261108"
STANFORD_PRIVATE='/path/to/prepared/private/test.csv'

PYTHONDONTWRITEBYTECODE=1 python3 "$AUDIT_DIR/checks/diagnostics.py" \
  "$AUDIT_PROJECT" /tmp/audit-diagnostics-new.json
PYTHONDONTWRITEBYTECODE=1 python3 "$AUDIT_DIR/checks/corpus_labels.py" \
  "$AUDIT_PROJECT" /tmp/audit-labels-new.json
PYTHONDONTWRITEBYTECODE=1 python3 "$AUDIT_DIR/checks/candidate_scores.py" \
  "$AUDIT_PROJECT" /tmp/audit-candidates-new.json "$STANFORD_PRIVATE"
```

漏存节点双评分需环境中的pandas、scikit-learn和MLE-bench依赖；本次使用已锁定验收环境，路径记录在verification.json。

```bash
AUDIT_PYTHON='/path/to/acceptance-venv/bin/python'
PYTHONDONTWRITEBYTECODE=1 "$AUDIT_PYTHON" "$AUDIT_DIR/checks/verify_missed_node.py" \
  "$AUDIT_PROJECT" "$STANFORD_PRIVATE" /tmp/audit-missed-node-new.json
```

支持回放会在临时目录创建独立结果；输入为保存数据，候选执行与LLM请求均由离线观察替代。一次运行包括129批条件重演、246份采用响应重解析和两版各7,800场，因此需要完整原数据目录。

```bash
PYTHONDONTWRITEBYTECODE=1 python3 "$AUDIT_DIR/checks/verify_replays.py" \
  "$AUDIT_PROJECT" /tmp/audit-replays-new.json
```

本次保留了起始manifest哈希、更新后manifest哈希和发布修订的映射。结果复核按源码/输入哈希和明确实验ID进行；临时路径只定位当次执行目录。新模型请求、训练、GPU租用与基线修正分别按Future Plan审阅后执行。
