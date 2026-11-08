# 来源与致谢

ForeAgent 原作者：ZJUNLP，项目 [predict-before-execute](https://github.com/zjunlp/predict-before-execute)，固定提交 `c4d52cf99bd870d830b456ac7c0684aec1aef375`。原始 MIT 许可证完整保留于 `vendor/foreagent/LICENSE` 及 `vendor/foreagent_upstream/LICENSE`。后者保存原 Agent、WorldModel 及发布配置；前者保存原 grade prompt/eval。缓存方向变体从同一 WorldModel 派生，保留于单独目录；作者声明及许可证同样适用。

ForeAgent 基于 AIDE；原 Agent 源码中的相关声明保持原样。本研究工具通过替换 query/执行回调做离线控制核验。

数据：[zjunlp/PredictBeforeExecute](https://huggingface.co/datasets/zjunlp/PredictBeforeExecute)，固定 revision `6b322cb88bdbcb2b2d3897ec7d0ded94a5bb2d06`。公开来源及逐文件校验值见 `provenance/data_manifest.json`；数据的使用条款以原发布来源为准。

NeurIPS 2025 模板：沿用 HW3 既有附带 `neurips_2025.sty`，模板文件头和声明完整保留。报告继续记录 AI 辅助范围。

实验组织参考：[vukrosic/llm-memory-env](https://github.com/vukrosic/llm-memory-env)，参考其问题—预测—设置—结果—解释的账本方式；本仓库的实验数据和结论来自上述 ForeAgent 材料及本项目运行记录。

研究仓库自有文稿的授权由仓库所有者决定；上述上游许可单独保留。
