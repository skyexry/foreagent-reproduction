# 旧执行口径保留

这里保存补齐强制回退之前的两版本汇总：候选池/顺序/seed 与 corpus26-v2 相同。旧 `actual_empty_execution` 等字段只对应概率执行阶段；新 v2 以精确原 Agent AST 加入强制回退并重跑，最终空执行为 0。筛选指标及排名轨迹与旧版一致。

旧结果属于历史记录；当前完整执行结论使用 `experiments/corpus26-v2/`。逐文件来源及校验值见 `source_map.json`，完整旧轨迹仍保存在原来源目录。
