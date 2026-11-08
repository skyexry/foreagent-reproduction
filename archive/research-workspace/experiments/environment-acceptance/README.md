# Environment & Baselines 验收清单

本轮为 2026-11-08 的事后核验，实验范围锁定作者提交 `c4d52cf99bd870d830b456ac7c0684aec1aef375`。原版参数及缓存行为作为基线；缓存修正、R6–R8、门槛搜索和新比较策略保留为后续研究。2026-11-08 用户确认当前完成标准为单任务原版端到端链路及其本机核验；该阶段已完成。重复性研究与 AIDE 在线比较作为后续可选研究，当前剩余必需 GPU 验收项为 0。

## 本机可完成的验收

| ID | 验收条件 | 当前证据 |
|---|---|---|
| L1 | 固定源码、配置、运行快照和最终产物一致 | `online-verification.json`：484 个 Git 文件、12 个原运行快照文件和 370 个证据文件校验通过；运行参数逐项对照作者配置 |
| L2 | 数据版本、训练/测试隔离和评分可独立验证 | 准备后 4 个文件匹配作者 MD5；2,160/240 条序列的 ID 集互斥；原提交及作者 3 份提交分别用原评分器及独立 ID 对齐评分重算 |
| L3 | 最终分数对应原算法保留的实际节点 | 原 Journal.get_best_node() 和独立选择一致；节点代码、节点预测、best_solution、best_submission 和归档预测一致；最终 0.26639893115767516，官方显示 0.26640 |
| L4 | 原控制流程、回退和离线结果可在新目录重现 | `offline-verification.json`：新克隆及新 venv；246 对重解析、129 完整批次历史条件重演、原版 7,800 次固定池回放及独立评分通过；4 项机制测试和 5 项新增评分测试通过 |
| L5 | 环境和证据具备显式获取/复核路径 | `online-evidence.json` 固定完整证据附件的文件清单和 SHA-256；`environment.json` 记录旧环境问题及本轮新建独立环境；74 个已安装 distribution 的环境通过 pip check，关键包均从该 venv 导入；两种作者配置零调用构造见 `config-verification.json`；依赖见本目录 requirements 文件 |
| L6 | 论文、发布代码和实际运行的差异有出处 | `reading-original.md`；原数据报告输入已使用，数据报告本身来自作者历史材料；本轮验收聚焦使用该报告的原 ForeAgent 在线循环 |
| L7 | 当前复现与后续研究的边界明确 | 当前单任务阶段已完成；`online-repeat-protocol.json` 按用户范围调整为 optional_future_research，保留后续可选研究设置 |

已完成的 7 批在线淘汰赛含 1,841 条比较记录，其中 1,720 次为缓存读取；发出的 121 个比较请求对应每批内去重后合计 121 对。整次运行有 134 份成功的筛选 API 回执，包含最终未完成批次；成功回执数、缓存读取数及账单调用数采用各自口径。

原版内部验证由候选代码及反馈解析产生，最终节点选择保留原算法口径；本阶段用统一私有评分评估外部表现。内部验证值 0.4378 与私有误差 0.26640 分别报告。

本机核验新增模型调用 0 次、候选训练 0 次。完整原始日志保存在独立附件，私有评分标签单独保存于使用者依法取得的任务数据目录。

## 评分器发现及处理

作者 Stanford 评分器先排序却保留原行索引，再用答案的布尔 Series 过滤预测；pandas 会按索引对齐。只打乱同一份预测的行顺序，原评分器从 **0.2663989312** 变成 **0.6131057879**。独立评分先按唯一 `id_seqpos` 连接，再用相应答案的 `keep` 标记计算三项 RMSE，得到相同的 **0.2663989312**；双方排序并 reset_index 后，原评分器也与之相同。

已冻结的本次提交和作者三份提交，原评分与独立评分逐份一致。保留作者评分源码；核验工具会在原评分与 ID 对齐结果冲突时终止。未来评分同时保存原文件哈希、ID/列/有限值检查和两种分数，输入规范化操作作为明确的评估适配记录。新增反例覆盖重复/缺失/未知 ID、非有限预测、缺列、错误/空 mask 和行顺序变化。

## 当前完成结论与后续可选研究

当前原版单任务复现已完成：固定源码/参数，完成一次 12 小时的生成、筛选、执行、反馈调试和最终评分，并通过上述本机核验。当前剩余必需 GPU 验收项为 **0**。

原版重复性研究（原 G2）与 AIDE 公平在线比较（原 G3）保留为后续可选研究，预备预算和控制设置见 `online-repeat-protocol.json`。G1 为将来另开 GPU 运行时的主机预检。现有 v2 就是本阶段冻结的真实端到端复现结果，环境适配和网络中断说明随结果保留。

评分器行顺序问题登记为 [EVAL-01](../../IMPROVEMENTS.md)，归入评估工具正确性修正。当前采用原评分与独立按 ID 对齐的复算进行核验，独立修正版作为后续实现。

## 本机重跑

核心离线核验：Python 3.12，`requirements-reproduction.txt`。在线产物核验：Python 3.11，`requirements-macos-controller.txt`（macOS arm64，含完整解析后的固定版本）。运行命令中的输入目录均显式传入，账户凭据保持在运行器外。

```bash
python3.11 -m venv .venv-acceptance
.venv-acceptance/bin/python -m pip install -r experiments/environment-acceptance/requirements-macos-controller.txt
.venv-acceptance/bin/python -m pip check
.venv-acceptance/bin/python scripts/verify_online_baseline.py \
  --source "$FOREAGENT_SOURCE" \
  --run "$FOREAGENT_RUN" \
  --data-root "$STANFORD_DATA" \
  --references "$AUTHOR_REFERENCES" \
  --output runs/online-acceptance.json
python -m unittest discover -s tests -p 'test_online_baseline.py' -v
```

变量含义：`FOREAGENT_SOURCE` 为作者固定 Git 检出；`FOREAGENT_RUN` 为校验后解压的 v2 证据附件根目录；`STANFORD_DATA` 含 `prepared/public/` 与 `prepared/private/`；`AUTHOR_REFERENCES` 含三次作者运行名的子目录及对应 submission.csv。原始 Kaggle ZIP 需接受比赛条款后自行获取，按作者 prepare.py 生成数据；4 个 MD5 见固定源码 competition/checksums.yaml。ZIP 的 MD5 为 `16ec2b3aa849804b7ab68a3bd043d00c`。

作者提交下载链接及 SHA-256 见 `../online-stanford-v2/author-final-reference.json`，均指向固定数据集 revision。新在线附件的位置和 SHA-256 见 `online-evidence.json`；当前为本机独立附件，公开下载地址待发布时补充。核验无需在线 API 或 SSH。
