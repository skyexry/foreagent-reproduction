# Environment & Baselines 验收清单

本轮为 2026-11-08 的事后核验，实验范围锁定作者提交 `c4d52cf99bd870d830b456ac7c0684aec1aef375`。原版参数及缓存行为作为基线；缓存修正、R6–R8、门槛搜索和新比较策略保留为后续研究。单任务链路验收、重复性验收和比较性验收分别报告。

## 本机可完成的验收

| ID | 验收条件 | 当前证据 |
|---|---|---|
| L1 | 固定源码、配置、运行快照和最终产物一致 | `online-verification.json`：484 个 Git 文件、12 个原运行快照文件和 370 个证据文件校验通过；运行参数逐项对照作者配置 |
| L2 | 数据版本、训练/测试隔离和评分可独立验证 | 准备后 4 个文件匹配作者 MD5；2,160/240 条序列的 ID 集互斥；原提交及作者 3 份提交分别用原评分器及独立 ID 对齐评分重算 |
| L3 | 最终分数对应原算法保留的实际节点 | 原 Journal.get_best_node() 和独立选择一致；节点代码、节点预测、best_solution、best_submission 和归档预测一致；最终 0.26639893115767516，官方显示 0.26640 |
| L4 | 原控制流程、回退和离线结果可在新目录重现 | `offline-verification.json`：新克隆及新 venv；246 对重解析、129 完整批次历史条件重演、原版 7,800 次固定池回放及独立评分通过；4 项机制测试和 5 项新增评分测试通过 |
| L5 | 环境和证据具备显式获取/复核路径 | `online-evidence.json` 固定完整证据附件的文件清单和 SHA-256；`environment.json` 记录旧环境问题及本轮新建独立环境；74 个已安装 distribution 的环境通过 pip check，关键包均从该 venv 导入；两种作者配置零调用构造见 `config-verification.json`；依赖见本目录 requirements 文件 |
| L6 | 论文、发布代码和实际运行的差异有出处 | `reading-original.md`；原数据报告输入已使用，数据报告本身来自作者历史材料；本轮验收聚焦使用该报告的原 ForeAgent 在线循环 |
| L7 | 重复运行前写明预测、控制、指标及预算 | `online-repeat-protocol.json`；状态为 prepared，执行与资源租用等待后续用户指令 |

已完成的 7 批在线淘汰赛含 1,841 条比较记录，其中 1,720 次为缓存读取；发出的 121 个比较请求对应每批内去重后合计 121 对。整次运行有 134 份成功的筛选 API 回执，包含最终未完成批次；成功回执数、缓存读取数及账单调用数采用各自口径。

本机核验新增模型调用 0 次、候选训练 0 次。完整原始日志保存在独立附件，私有评分标签单独保存于使用者依法取得的任务数据目录。

## 评分器发现及处理

作者 Stanford 评分器先排序却保留原行索引，再用答案的布尔 Series 过滤预测；pandas 会按索引对齐。只打乱同一份预测的行顺序，原评分器从 **0.2663989312** 变成 **0.6131057879**。独立评分先按唯一 `id_seqpos` 连接，再用相应答案的 `keep` 标记计算三项 RMSE，得到相同的 **0.2663989312**；双方排序并 reset_index 后，原评分器也与之相同。

已冻结的本次提交和作者三份提交，原评分与独立评分逐份一致。保留作者评分源码；核验工具会在原评分与 ID 对齐结果冲突时终止。未来评分同时保存原文件哈希、ID/列/有限值检查和两种分数，输入规范化操作作为明确的评估适配记录。新增反例覆盖重复/缺失/未知 ID、非有限预测、缺列、错误/空 mask 和行顺序变化。

## 需要租 GPU 的验收

| ID | 要解决的问题 | 预先确定的验收条件 | GPU 时间 |
|---|---|---|---|
| G1 | 新执行机上的真实环境就绪 | 固定镜像、驱动、CUDA、资源配额、数据权限、执行桥和异常回传均通过；模型端点预检成功；保持 Mac 唤醒、VPN 连通；实际 GPU、提示中的 CPU 数和配额逐项登记 | 每次租机先做短预检，单独计费 |
| G2 | 原版端到端重复性 | 三次预先编号的独立原版 12 小时运行，逐次报告有效提交、分数、轨迹、API 回执和网络中断；公布全部尝试及基础设施失败 | 3 × 12 = 36 单卡小时，另加环境准备 |
| G3 | 对作者 AIDE 执行型基线的公平比较 | 同机型/配额/镜像/服务/数据/重试规则，原版 ForeAgent 与发布的 AIDE 各三次；顺序事先交错，统一按墙钟预算终止，分别统计 API 与 GPU 成本 | 两方法合计 72 单卡小时，另加准备 |

G2 支持“单任务重复性”；G3 是主张筛选带来在线收益前的比较验收。一次 G2 原版运行与 G3 采用相同锁定设置时，可计入同一组 ForeAgent 重复。现有 v2 保留为有网络中断的历史运行，单列展示；新注册的三次构成前瞻组。

每个 12 小时正式运行含所有网络等待、重试和代码执行；环境准备时间单独记录。达到某个私有分数后的停止/加时属于另一个协议。试验结束后按原内部验证指标选出的提交评分。G2/G3 是待执行清单，本轮完成的是协议与本机核验。

作者全论文范围另含 5 任务、每方法每任务 3 次，基础正式 GPU 预算为 5 × 2 × 3 × 12 = 360 单卡小时；这是扩大范围时的成本参考。当前聚焦 Stanford 单任务。

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
