# HW3 报告实验版本

## 当前版本：v3（2026-11-08）

交付：`DM_HW3_Baseline_Reproduction_v3.pdf`，8 页；对应源码为 `main.tex` 和 `baseline_reproduction.tex`，沿用现有 NeurIPS 模板。

- 保留 Introduction、Baseline Explanation 和 129 批历史条件回放：15 次作者运行、1,290 个候选；原 RNG/复赛对手身份的证据边界继续说明。
- 新增 `corpus26-v2` 原版完整执行策略的离线筛选结果：26 任务、2,600 池实例、2,164 个不同集合、7,800 次回放；单选最佳命中 20.43%（随机 12.53%）、归一化 regret 0.2810（随机 0.3674）、完整模拟执行集合最佳命中 21.60%。并列评分、任务等权、固定反馈及候选池适配条件均已说明。
- 新增 `stanford-autodl-v2` 单任务标准 12 小时端到端结果：私有集 MCRMSE 0.26640；列出作者同任务三次提交复评分、运行规模、环境与服务差异、Mac 熄屏/VPN 断连引发的请求重试等待及独立评分核验。
- Future Plan 留待后续。AI 使用原始请求补记于 `AI_USAGE.txt`。
- 现有报告更新复用已保存实验；新增 API 调用和候选训练均为 0。

验证：LaTeX 编译、PDF 文本与实验 JSON 数字核对、逐页版面检查；结果和当前源码/PDF 哈希见 `validation_v3.json`。

## 历史版本：v2

`DM_HW3_Baseline_Reproduction_v2.pdf` 与 `baseline_freeze.json` 保留原有字节。v2 的主结果为 `historical-v1` 条件历史回放；其归档来源和 SHA-256 见 `provenance/import_map.json`。当前 TeX 对应 v3；旧版本的来源以原归档和冻结记录为准。早期概率阶段执行口径保留于 `experiments/superseded/`，当前报告使用 `corpus26-v2` 完整执行策略。

## 编译

```bash
cd reports/hw3
latexmk -norc -pdf -interaction=nonstopmode -halt-on-error -outdir=build main.tex
```

`build/main.pdf` 为生成文件；交付文件为上方标注的 v3 PDF。
