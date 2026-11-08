# 研究仓库协作

每个聊天开始时执行 `pwd`、`git branch --show-current`、`git status --short --branch`；读取当前阶段的 `README.md` 和 `STATUS.md`。以当前文件与运行证据确认状态。

采用最小必要修改。原版固定源码、冻结池和保存反馈按版本留存；实验口径或算法改变时建立新的实验 ID，并说明与旧版差异。新实验先记录问题、预测、控制项、评分和停止规则，再执行。历史补记明确标注事后归档。

Environment & Baselines 的运行入口为 README 指定的作者独立检出及其中的 `mle-bench/run_agent.py`。在线有偿 API、完整训练、远端推送、可见性调整和 Release 按本轮用户授权执行；基线 `baseline-reproduction-v1` 已经用户确认完成发布；后续操作继续依各轮明确授权执行。

跨 worktree 用明确 Git 提交衔接，记录分支、提交和实验 ID，再开始后续修改。同一目录同时工作时，先在聊天中声明各自修改的文件；已有未提交内容通过 `git diff` 核对归属。

结束时更新 `STATUS.md` 的实际进展、证据路径、验证命令/结果和当前唯一下一步；更新相关实验记录。区分执行成功、输出一致与已验证的研究结论。大文件通过固定 URL 或附件及校验值衔接，账户配置保留在仓库外。

本轮范围：归集、可复现性验证、冻结基线。新排序、比较选择和早停作为后续工作。不同缓存修复实现使用各自名称。

2026-11-08 用户已授权固定离线 Environment 与 Evals；当前研究入口为 `research/README.md`，机器入口为 `research/registry.json` 和 `research/state.json`。调用约定见 `research/AGENTS.md`；原版在线复现入口与历史实验继续按原版本留存。

GitHub 研究材料已发布于 `5f545087f9ce71453d79214bb6b1ea93f730132a`，收据见 `provenance/research-publication-v1/`。本机研究工作目录保留原 Git 基点与未提交内容；后续 Git 操作先核对远端新版本，使用独立分支或检出衔接。HW3 提交版本固定为 `hw3-phase1-v1`。
