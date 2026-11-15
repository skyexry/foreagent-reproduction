# Aerial Cactus：作者原版 12 小时端到端复现

**当前：正式运行结束并核验完成。** 实验 `cactus-autodl-original-v1`，scope `cactus-formal-v1`。北京时间2026-11-15 **03:34:06–15:34:06**，43,200秒预算（实际控制器记录43,199.619秒，监督器从spawn计43,205.381秒），SIGALRM正常结束；API等待、比较与训练计入同一预算。最终私有测试原始AUC **0.9999375316002257**，作者原评分函数与独立ID对齐完全一致；原MLE-bench包装器五位小数为 **0.99994**。

**2026-11-15 事后指标核对。** 在已完成运行的原选定AUC上，按作者冻结排行榜1,221队计算Beat Ratio为 **1,071/1,221 = 0.8771498771**，与作者三次归档及论文Table13的0.877±0.000吻合；五位AUC提高仍处于同一排行榜阈值区间。该派生计算复用SHA-256核验的排行榜副本，原提交/评分保持原件。[派生收据](beat-ratio-20261115.json) · [两层复现事实核对及proposal第三部分](../../reports/reproduction-section3-20261115/Reproduction_Fact_Check.md)。

## 原版口径

固定作者提交 `c4d52cf99bd870d830b456ac7c0684aec1aef375`，400 项非字节码源文件逐项一致；worker 字节与既有冻结版一致。正式配置的 16 项作者覆盖参数全部一致：12 小时、5,000 步、单候选执行上限 32,400 秒、3 草稿、10 改进候选、Top-1、置信阈值 0.7、执行概率 0.2；默认代码/反馈温度 0.5、比较温度 1.0、5 折设置保持。原版缓存、排序、回退、debug 和最佳节点保存行为保留。

数据来自作者官方固定版本归档，原 ZIP MD5 与三份准备后 CSV MD5 均匹配固定作者清单；按原 `prepare.py` 划分为 14,175 训练、3,325 留出测试。作者 DA 报告作为公开输入。评分答案与原始完整标签在 root 专用目录。

## 执行适配与披露

controller 和 worker 在同一 AutoDL 服务器，RTX 3090 24GB；worker 复用原 OCI rootfs（Python 3.11.13、PyTorch 2.2.0+cu121），通过 PRoot 执行。controller 使用独立 Python 3.12 环境；宿主 PyTorch 2.5.1、OpenAI 2.14.0 等实际版本以监督器的 `pip-freeze-start.txt` 为准。CPU 当前配额 15 核、可见逻辑核 128。数据图像由原预处理函数解压后同步到 worker。

模型名与原配置一致，DeepSeek 两种角色由 SiliconFlow 对应接口提供；GPT-4o-mini 经 Mac 的 Cisco VPN 和只允许官方 OpenAI TLS 目标的回环 SSH 转发。Mac 的供电、唤醒保持和网络转发自动重连已核对；网络中断及等待会计入正式预算。运行环境、服务端模型快照与作者历史条件分别披露。

初步 `cactus-smoke-v1` 按用户指令在约 185 秒时停止并独立归档，其首个节点遇到原 Interpreter 10 秒 ready 超时。随后同一原 worker 的三次 print/CUDA 检查成功，线程 1/15 对照对启动耗时没有改善，正式 guest 保持原设置。该首次超时的具体触发点待确认。正式候选错误由原版Agent反馈/调试；结束后的记录单列4次ready窗口异常及1个预算中断执行。

## 完整记录

服务器独立保存：原 `journal.json` 与普通/verbose 日志；所有节点代码、终端、元数据和提交；每次执行的独立 CSV 和 SHA-256；完整 API 请求/响应、请求 UUID、响应 ID 和服务端请求标识（服务提供时）；执行/反馈计时；30 秒 GPU/CPU/RAM/磁盘/API 等待监测；监督器启动/退出、worker 收尾、起止运行快照与依赖。完整 node ID 与 execution job ID 精确关联，重复代码节点也分别计时。

本机每 5 分钟只读备份运行、监督器和 worker jobs；公开输入和临时训练权重通过来源/服务器原目录衔接。凭据及连接配置保持仓库外。最终完整记录及校验清单已交付为 `complete-records.tar.gz`，14,730,919字节，SHA-256 `44b6a2a8cc37d716e1e35eff4c521e1bc0251a3c51dec96eff9abd87bf71938c`；本机位置为 `Documents/Codex/2026-11-15/new-chat-3/outputs/cactus-original-12h-20261115/`，恢复时用交付压缩包和同目录SHA256SUMS衔接。

## 最终结果与验收

| 指标 | 本次 | 作者公开三次 |
|---|---|---|
| MLE-bench五位测试分 | **0.99994** | 0.99992 / 0.99993 / 0.99991 |
| 完成journal节点 | 82 | 59 / 60 / 29 |
| 有效执行节点 | 11 | 8 / 8 / 4 |

作者分数来自固定数据revision的原始 `eval_output.json`；本次原始测试AUC另保留全精度。此为一次执行环境适配的原版运行，结果按单次描述性对照理解。原最终选择为 `cf5dfdccf9ab47eab8cee08d7727e2b7`，内部验证AUC为0.999926，提交SHA-256 `a1e1bfbe71323039d4a535d56b710a5993196b003a718e7919dc9fbc731045e5`。

最终82节点、6个完整十候选批次，32次执行中31份结果、1份预算截止中断。11个原Agent有效节点均保存CSV；另2份训练成功的CSV因整数metric=1被原float检查标为buggy，原标记与13份完整CSV同时留存。每份3325行、唯一公共ID集合、有限值和node/job/best身份通过。

200次API均HTTP200：生成83、反馈31、Thinking比较86；600份原始请求/路由请求/响应齐全，含reasoning/content、本地UUID、原响应ID与服务商返回的header ID。最终API错误及在途请求为0。执行起止/反馈耗时、30秒资源监控、143轮成功备份齐全；服务器与本机1,263份记录精确哈希一致，压缩包内同清单全部重新核验。历史scratch重复副本另存证据，保留其原字节。

结束时16项参数、6份关键作者源码、14份运行快照冻结核验全通过。4次固定10秒REPL ready异常的具体启动耗时点待后续诊断；现有证据显示硬资源余量充足，原环境/算法继续保持。末次 `f4d5be06c2a345bbb4ac1bad7d1f012e` 按预算中断，控制器/监督器/全部scope worker与GPU计算进程均退出，Mac专用转发和防休眠辅助进程已释放；AutoDL实例保持开启。

[最终摘要及完整归档SHA](final-summary.json) · [13份提交时间索引](node-submissions-index.csv) · [终局记录核验](evidence/final-recording-validation-summary.json) · [作者三次对照与原始来源](evidence/cactus-author-comparison-reference.json) · [比较器完整记录验收](evidence/first-comparator-recording-verification.json) · [运行前协议](protocol.json)。

当前唯一下一步：审阅本次结果；按用户后续要求用已保存CSV与比较器原件开展回溯分析。测试评分在正式结束后独立执行，保留原Agent选中的最终方案。

## 运行中检查点（05:28）

截至北京时间05:28，已保存三份节点提交CSV。前两份训练成功且产出3325行提交，但GPT工具响应返回整数`metric:1`，原版`agent.py`的float类型检查将其置为None并标为buggy；原行为继续保留。其后节点`6ae0dfff25a14ceb93e41f880ba44919`获原Agent接纳，验证AUC为0.9999，成为当前原选定最佳。该节点CSV、独立execution-job副本和best_submission三份文件SHA-256一致，公开样本ID、行数和有限值检查通过。此处为验证指标；测试答案在运行后的外部评分中使用。

另记录一次正式运行的原Interpreter 10秒ready窗口失败（exec_time=0）。作者三份Cactus和既有Stanford归档中该同文错误的核对计数为0，因此将本轮该项单列为执行环境时序风险；具体触发原因待确认，原参数保持。DataLoader动态类PicklingError则在作者原Cactus日志中已有同类记录，由原Agent自行debug。

[首份CSV与整数指标机制](evidence/first-csv-recording-verification.json) · [首个原Agent有效节点及最佳副本核验](evidence/first-agent-valid-node-verification.json) · [DataLoader历史对照](evidence/dataloader-pickling-diagnosis.json) · [ready窗口历史核对](evidence/repl-start-history-check.json)。
