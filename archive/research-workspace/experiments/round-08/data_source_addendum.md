# R8 数据来源补充：恢复8条原始失败记录

原注册提交f7c9440要求完整对覆盖。按此规则核验时，20251210_154406的6个alignment文件缺少8对，其余两份覆盖完整；初次失败报告保存于initial_structure_failure.json，方法评分尚未开始。

随后在同一数据revision的per_task_results/grade_results_<task>_n2.json原始备份中找到完整记录。6个原始文件共5,107条，与对应alignment中共有的5,099条记录，其候选身份、胜者与confidence全部逐条一致。缺少的8条全部为真实记录的API 400错误，request ID日期为20251210，与原报告的GPT-5.1/temperature1/2025-12-10T15:44:06运行一致。原始记录完整保留候选顺序和group_index；没有借用其他运行的判断。

追加来源：recovery_sources.json固定6份公开原始备份的URL、字节、Git/LFS及SHA-256；recovery_proofs.json记录共有数据逐条对齐；recovered_feedback.json保留8条原始错误、候选身份及每记录哈希。

这8条按原协议已规定的失败反馈处理：winner=None、confidence=0，由固定WorldModel后端错误分支缓存，实际查询时仍占q_j。它们是已有调用的失败记录恢复，未生成新的模型偏好，新增模型调用为0。

本补充在任何R8方法评分前单独提交。原protocol.md/protocol.json/data_manifest.json/jobs.jsonl及其注册哈希保持，26任务、23,400场景、70,200评分、预测、指标、预算和方法全部保持。数据核验的完整对覆盖以78份alignment加8条有原始证据的记录共同满足。初始完整性失败如实留存。

核心复现使用Git中的紧凑恢复记录；可运行python reproduction/round08/recovery.py --fetch重新下载并核验全部原始备份。大型备份位于忽略目录data/round08-recovery，原来源始终保留。
