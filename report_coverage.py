"""Validate saved results and export the coverage report without API calls."""
import json
from pathlib import Path

from prepare_coverage import ROOT
from run_coverage import OUTPUT


def main():
    summary = json.loads((OUTPUT / 'summary.json').read_text())
    if summary['inflight_pairs']:
        raise SystemExit('Run still has in-flight calls; wait before finalizing.')
    manifest = json.loads((ROOT / 'experiments/coverage_manifest.json').read_text())
    reference = json.loads((ROOT / 'experiments/coverage_author_reference.json').read_text())
    refs = {(m['task'], m['source_group_index']): m for t in reference['tasks'] for m in t['matches']}
    results = summary['results']
    for r in results:
        source = manifest['groups'][r['index']]
        assert (r['task'], r['source_group_index'], r['best_index']) == (source['task'], source['source_group_index'], source['best_index'])
        saved = json.loads((OUTPUT / f'pair-{r["index"]:03d}.json').read_text())['result']
        assert r == saved
        if r['error'] is None:
            assert r['correct'] == int(r['parsed']['predicted_best_index'] == r['best_index'])
            assert r['finish_reason'] == 'stop'
        author = refs[(r['task'], r['source_group_index'])]
        assert author['best_index'] == r['best_index']
        r['author_prediction'] = author.get('author_prediction')
        r['author_correct'] = author.get('author_correct')
    assert len(results) == summary['completed_pairs'] and len({r['index'] for r in results}) == len(results)
    valid = [r for r in results if r['error'] is None]
    paired = [r for r in valid if r['author_prediction'] is not None]
    usage = {k: sum(r['usage'].get(k, 0) for r in results if r['usage'])
             for k in ['prompt_tokens', 'completion_tokens', 'total_tokens', 'prompt_cache_hit_tokens', 'prompt_cache_miss_tokens']}
    comparison = {'matched_valid_pairs': len(paired), 'ours_correct': sum(r['correct'] for r in paired),
                  'author_correct': sum(r['author_correct'] for r in paired),
                  'both_correct': sum(r['correct'] and r['author_correct'] for r in paired),
                  'ours_only_correct': sum(r['correct'] and not r['author_correct'] for r in paired),
                  'author_only_correct': sum(not r['correct'] and r['author_correct'] for r in paired),
                  'both_wrong': sum(not r['correct'] and not r['author_correct'] for r in paired)}
    per_task = []
    for task in manifest['tasks']:
        records = [r for r in results if r['task'] == task['task']]
        good = [r for r in records if r['error'] is None]
        matched = [r for r in good if r['author_prediction'] is not None]
        per_task.append({**task, 'attempted': len(records), 'valid': len(good),
                         'correct': sum(r['correct'] for r in good),
                         'author_correct_on_valid': sum(r['author_correct'] for r in matched),
                         'author_matched_valid': len(matched)})
    export = {**summary, 'aggregate_usage': usage, 'paired_comparison': comparison,
              'accuracy_valid_only': sum(r['correct'] for r in valid) / len(valid) if valid else None,
              'accuracy_attempted_invalid_as_wrong': sum(r['correct'] for r in results) / len(results) if results else None,
              'per_task': per_task, 'results': results}
    (ROOT / 'experiments/coverage_results.json').write_text(json.dumps(export, ensure_ascii=False, indent=2))
    rows = [f"| {t['task']} | {t['available_pairs']} | {t['selected_pairs']} | {t['attempted']} | {t['correct']}/{t['valid']} | {t['author_correct_on_valid']}/{t['author_matched_valid']} |" for t in per_task]
    rate = f"{100 * export['accuracy_valid_only']:.2f}%" if valid else '无有效结果'
    report = f'''# 26 任务覆盖评测（2026-10-21）

本轮从作者的 26 个任务、18,438 对候选中固定抽取 246 对；每任务最多 10 对，两个只有 3 对的任务全部使用。

- 请求结束：{len(results)}/246；有效解析：{len(valid)}；待运行：{summary['pending_pairs']}。
- 有效答案正确数：{sum(r['correct'] for r in valid)}/{len(valid)}（{rate}）。
- API/网络或输出错误：{len(results)-len(valid)}。无自动重试。
- 同样本有效答案对照：本轮 {comparison['ours_correct']}/{len(paired)}，作者一次公开运行 {comparison['author_correct']}/{len(paired)}。
- 配对差异：双方均对 {comparison['both_correct']}；仅本轮对 {comparison['ours_only_correct']}；仅作者对 {comparison['author_only_correct']}；双方均错 {comparison['both_wrong']}。
- 本轮用时：{summary['elapsed_seconds']/60:.1f} 分钟；最多 {summary['workers']} 个并发请求。
- 本轮已知 token 的估算费用：¥{summary['estimated_cost_cny']:.4f}；包含前次 ¥0.43 预留及未知用量保守记账的累计预算占用：¥{summary['budget_accounted_cny_including_prior']:.4f}。
- 输入 tokens：{usage['prompt_tokens']:,}；输出 tokens：{usage['completion_tokens']:,}；总计：{usage['total_tokens']:,}。输出已包含思考 tokens。
- 停止原因：`{summary['stop_reason']}`。`None` 表示未触发错误或预算停止。

## 各任务结果

作者列仅在本轮有效且成功匹配的样本上计数。错误或未完成请求不能被静默排除后宣称完成全部评测。

| 任务 | 全量比较对 | 抽取 | 请求结束 | 本轮正确/有效 | 作者正确/匹配有效 |
| --- | ---: | ---: | ---: | ---: | ---: |
{chr(10).join(rows)}

## 对照与适用范围

这不是论文全量复现。每任务近似等量抽样改变了任务权重，因此本轮准确率不能直接与论文全量 micro accuracy 61.5% 比较。主要参照是作者在同一批样本上的一次公开预测记录，不是作者三次运行的平均值；每任务最多 10 对也不足以可靠比较单个任务优劣。

采样在查看这些样本的作者预测前固定，种子为 `20261021`，每任务使用独立的 `random.Random(f"{{seed}}:{{task}}")`，保留候选顺序。全部 18,438 对标签已核对分数方向；选中的代码、任务描述和数据报告通过 SHA-256 验证。真实标签和分数只用于本地评分，不作为额外评测字段发送给 LLM，也未执行候选代码。

## 固定配置与差异

- 官方代码提交：`{summary['upstream_commit']}`；数据版本：`{summary['dataset_revision']}`。
- 作者提示词、解析器、准确率函数原样复用；使用 `allow_cot=True`、`prompt_boost=True`。
- 模型：SiliconFlow `{summary['model']}`，温度 1.0，开启 Thinking。
- 思考上限 32768、回答上限 8192；作者 CLI 未显式固定同样的输出限制。服务商、服务端模型快照和默认采样参数仍可能有差异。
- Python {summary['python']}，标准库 HTTP + certifi；与作者推荐 Python 3.10 + OpenAI SDK 环境不同。
- 作者参考：`{reference['author_run']}`。使用有序文件名后缀及真实分数唯一匹配，并核对真实标签。
- 累计预算 ¥20；派发前预留在途请求的保守最大费用，按实际 token 释放预留；未知用量保留预留。API 错误后停止新增请求，已发送的请求仍可能完成并产生费用。估价不等同代金券或现金账单。

## 文件

- `coverage_manifest.json`：样本、完整标签计数、数据校验值。
- `coverage_author_reference.json`：作者同样本结果及原始报告校验值。
- `coverage_results.json`：逐对指标、费用和配对对照。
- 本地 `outputs/coverage-20261021/`：原始请求、响应和增量进度；不上传 GitHub。

来源：[官方代码](https://github.com/zjunlp/predict-before-execute)、[固定版数据](https://huggingface.co/datasets/zjunlp/PredictBeforeExecute/tree/{summary['dataset_revision']})、[SiliconFlow 定价](https://www.siliconflow.cn/pricing)。
'''
    (ROOT / 'experiments/coverage_report.md').write_text(report)
    print(json.dumps({'attempted': len(results), 'valid': len(valid), 'comparison': comparison, 'cost_cny': summary['estimated_cost_cny']}, ensure_ascii=False))


if __name__ == '__main__':
    main()
