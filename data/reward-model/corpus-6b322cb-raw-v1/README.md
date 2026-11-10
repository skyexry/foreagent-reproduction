# Reward model 原始数据：代码已补齐

来源为作者公开的 [PredictBeforeExecute](https://huggingface.co/datasets/zjunlp/PredictBeforeExecute)，固定 revision 为 `6b322cb88bdbcb2b2d3897ec7d0ded94a5bb2d06`。

本目录保存 26 任务的 18,438 对原始标签、全部 895 份被引用的候选代码、26 份任务描述、26 份数据报告及任务名单。本次从已有固定版本副本复用 374 份代码，按原始标签中的路径下载其余 521 份。

每份源文件的下载 URL、来源、字节数和 SHA-256 见 [MANIFEST.json](./MANIFEST.json)。974 项源文件校验通过，895 份代码共有 878 种字节内容。任务标签文件保留作者绝对路径；读取代码时按任务与文件名映射到本目录的 `solutions_subset_50/<task>/code/`。

下载格式为 `https://huggingface.co/datasets/zjunlp/PredictBeforeExecute/resolve/<revision>/<relative-path>`。`relative-path` 和本次缺失的 521 个路径已记录在[来源核查](../../../reports/reproducibility-audit-20261108/evidence/corpus-source-check.json)。

标签保持原样：49 对含非有限成绩；有限成绩中有 47 对比较的两份代码逐字相同。tweet 任务的同一组有 9 份相同代码，组成 36 对；此前只下载到其中 8 份时观察到 28 对。执行差异原因需查原运行记录。

数据清洗、内容组/轨迹分组与任务划分属于下一步。训练方案按 [Future Plan](../../../reports/reproducibility-audit-20261108/FUTURE_PLAN.md) 审阅；本轮模型调用、训练和 GPU 租用均为 0。原 `data/coverage` 与第一阶段材料保持，完整核查见[补齐结果](../../../reports/reproducibility-audit-20261108/evidence/corpus-completion.json)。
