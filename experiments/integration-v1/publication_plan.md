# 本地审阅与发布计划

本轮本地功能检查点：`148dbf8ebf09e57ee887699eb47ab1b1b98bd9ed`；后续提交仅记录验证、交接与发布方案。最终检查点见本地 `codex/baseline-reproduction-v1` 分支尖端。

主项目以 main 工作区形式保留归集后的待审阅文件，原来源目录和大文件保留。主项目既有 Proposal、bibliography、实验等修改在检查点中一并归档，来源由 `provenance/initial_git_status.txt`、`initial_inventory.json` 和 `pre-integration/` 区分。

建议提交顺序：

1. `research: assemble frozen ForeAgent reproduction and portable replay tools`：固定原版、缓存变体、协议、摘要、脚本、报告与来源。
2. `research: record clean-clone validation and baseline handoff`：本轮独立克隆验证证据与交接。

两项在本地归集分支保留，供跨聊天/工作目录通过 Git 提交衔接。审阅主项目差异后，可采用该分支的已验证检查点；原 main 工作区的保存和分支切换步骤根据届时 Git 状态执行。

确认后的建议标签：`baseline-reproduction-v1`，标在最终归集提交。清单内分别标识 `original@c4d52cf`、`cache_direction_canonical-v1`、`cache_fixed_instance_locked-v1`；这些是实验变体名，共享冻结标签。

确认后推送归集分支/选定主分支与标签至已配置远端；Release 说明附上本轮范围、已知缺口和校验值，并上传 `pairwise-246-evidence.zip`、历史原记录包、完整 corpus 轨迹包。随后将附件的公开 URL 补充到获取说明及附件登记，作为单独的发布元数据提交。原始归档哈希保持。

GitHub 推送、可见性修改和 Release 发布均在用户审阅本地成果后确认。
