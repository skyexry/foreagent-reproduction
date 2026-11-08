# HW3 报告实验版本

沿用现有六页 `DM_HW3_Baseline_Reproduction_v2.pdf`、`main.tex`、`baseline_reproduction.tex` 及原附带 NeurIPS 模板；本轮归集保持这些文件的原有字节。原路径与 SHA-256 见 `provenance/import_map.json`。

- Introduction / Baseline Explanation：研究动机、pairwise 与 selection 区别、原门控/pending/停止/并列及执行回退。
- Baseline Reproduction 主结果：`historical-v1` 的 15 次运行、129/129 完整批次、1,290 候选条件历史重演，包含 RNG/复赛对手身份及日志覆盖缺口。
- 246 对结果为此前小样本判断能力；26 任务 corpus26-v2 为另一离线选择效果实验。两者详细协议和汇总在仓库中分别列账，正文 Section 3 的 129/129 主张范围保持清楚。
- 缓存修正、新汇总、新早停及完整在线验证的证据层级见根 README 与 EXPERIMENTS。

可在 TeX Live/MacTeX 下重新排版：

```bash
cd reports/hw3
mkdir -p build
pdflatex -interaction=nonstopmode -halt-on-error -output-directory build main.tex
pdflatex -interaction=nonstopmode -halt-on-error -output-directory build main.tex
```

`build/main.pdf` 为新生成文件；现有 PDF 是归档交付版本。模板引用均在同目录；文献在 TeX 内，无额外 bib 数据依赖。
