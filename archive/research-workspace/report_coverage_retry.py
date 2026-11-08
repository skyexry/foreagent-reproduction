"""Validate both attempts and summarize the completed authorized retry stage."""
import json
from pathlib import Path
from export_coverage_audit import aggregate_tokens
from prepare_coverage import ROOT
from run_coverage import OUTPUT, write_json


def main():
    retry = OUTPUT / 'retry-attempt-002'
    first = json.loads((OUTPUT / 'summary.json').read_text())
    second = json.loads((retry / 'summary.json').read_text())
    assert second['completed_retries'] == second['selected_retries']
    assert first['completed_pairs'] == 246 and not first['inflight_pairs']
    expected = {r['index'] for r in first['results'] if r['error'] is not None}
    assert {r['index'] for r in second['results']} == expected
    assert len(second['results']) == len(expected)
    adopted = {r['index']: {**r, 'adopted_attempt': 1 if r['error'] is None else None} for r in first['results']}
    attempts = [json.loads(line) for line in (retry/'attempts.jsonl').read_text().splitlines()]
    assert len(attempts) == len(expected)
    for r in second['results']:
        original = json.loads((OUTPUT / f'pair-{r["index"]:03d}.json').read_text())
        saved = json.loads((retry / f'pair-{r["index"]:03d}.json').read_text())
        assert saved['result'] == r
        assert {k:v for k,v in saved['request'].items() if k != 'stream'} == {k:v for k,v in original['request'].items() if k != 'stream'}
        logs = [a for a in attempts if a['result']['index'] == r['index']]
        assert len(logs) == 1 and logs[0]['result'] == r and logs[0]['response'] == saved['response']
        if r['error'] is None:
            assert r['finish_reason'] == 'stop'
            assert r['correct'] == int(r['parsed']['predicted_best_index'] == original['result']['best_index'])
            adopted[r['index']] = {**r, 'adopted_attempt': 2}
    rows = list(adopted.values()); valid = [r for r in rows if r['error'] is None]
    correct = sum(r['correct'] for r in valid)
    reference = json.loads((ROOT/'experiments/coverage_author_reference.json').read_text())
    refs = {(m['task'],m['source_group_index']):m for t in reference['tasks'] for m in t['matches']}
    ours_only = author_only = both = neither = 0
    for r in valid:
        a = refs[(r['task'],r['source_group_index'])]
        assert a['best_index'] == r['best_index']
        ours_only += bool(r['correct'] and not a['author_correct'])
        author_only += bool(not r['correct'] and a['author_correct'])
        both += bool(r['correct'] and a['author_correct'])
        neither += bool(not r['correct'] and not a['author_correct'])
    tasks = []
    for task in first['tasks']:
        selected = [r for r in rows if r['task'] == task['task']]
        tasks.append({'task':task['task'], 'selected':len(selected), 'valid':sum(r['error'] is None for r in selected),
                      'correct':sum(r['correct'] for r in selected),
                      'author_correct':sum(refs[(r['task'],r['source_group_index'])]['author_correct'] for r in selected)})
    all_attempts = first['results'] + second['results']
    export = {'selected_pairs':246, 'total_calls':len(all_attempts),
        'first_round': {'valid':first['valid_pairs'],'correct':first['correct'],'failed':len(expected)},
        'retry': {'attempted':len(second['results']),'valid':second['valid_retries']},
        'combined': {'valid':len(valid),'correct':correct,'valid_output_rate':len(valid)/246,
                     'accuracy_valid_only':correct/len(valid) if valid else None,'accuracy_full_sample':correct/246,
                     'macro_accuracy_full_sample':sum(t['correct']/t['selected'] for t in tasks)/len(tasks)},
        'author_comparison_on_valid': {'author_correct':both+author_only,'both_correct':both,'ours_only':ours_only,'author_only':author_only,'both_wrong':neither},
        'known_cost_cny':sum(r['estimated_cost_cny'] for r in all_attempts if r['estimated_cost_cny'] is not None),
        'unknown_cost_calls':sum(r['estimated_cost_cny'] is None for r in all_attempts),
        'aggregate_tokens':aggregate_tokens(all_attempts),'per_task':tasks,'adopted_results':rows}
    write_json(ROOT/'experiments/coverage_retry_results.json',export)
    table='\n'.join(f"| {t['task']} | {t['selected']} | {t['valid']} | {t['correct']} | {t['author_correct']} |" for t in tasks)
    report=f'''# 首轮与补调结果（2026-10-21）

固定 246 对，首轮 {first['valid_pairs']} 对有效、{first['correct']} 对正确；首轮有效准确率 {first['correct']/first['valid_pairs']:.2%}，有效输出率 {first['valid_pairs']/246:.2%}，全样本正确率 {first['correct']/246:.2%}。

经用户授权，仅对 {len(expected)} 个失败样本各补调一次，补调 {second['valid_retries']} 个有效。总计 {len(all_attempts)} 次调用，合并后 {len(valid)} 对有效、{correct} 对正确：有效输出率 {len(valid)/246:.2%}，有效准确率 {correct/len(valid):.2%}，全样本正确率 {correct/246:.2%}。采用首轮有效结果；首轮失败时采用第二次有效结果。没有按对错选择重试，也没有覆盖失败。原始输入和生成参数逐对核对相同；补调采用流式接收、4 并发，旧 ¥20 阈值不再用于这 20 次补调。

同样有效样本上，作者一次公开运行正确 {both+author_only}/{len(valid)}。双方均对 {both}，仅本轮对 {ours_only}，仅作者对 {author_only}，双方均错 {neither}。这些是描述性差异，不能据此断言优于作者或显著优于随机猜测；同任务和重复候选造成配对依赖，没有把 246 对当独立样本做显著性检验。此样本实验不是全量论文效果复现。

所有调用的已知 token 估算费用 ¥{export['known_cost_cny']:.4f}（不含前次 smoke），另有 {export['unknown_cost_calls']} 次调用用量/实际费用未知；不将其当作零费用，预算预留也不冒充账单。完整用量及缺失计数在 JSON 中。

| 任务 | 样本 | 有效 | 正确 | 作者正确（全部选中样本） |
| --- | ---: | ---: | ---: | ---: |
{table}

本地原始记录：outputs/coverage-20261021/；补调记录：其 retry-attempt-002/ 子目录（含请求、响应、attempts.jsonl、开始/结束时间与脚本快照）。本报告在两轮结束后核对原始记录生成。首轮报告保留不变。
'''
    (ROOT/'experiments/coverage_retry_report.md').write_text(report)
    print(json.dumps({k:export[k] for k in ['combined','author_comparison_on_valid','known_cost_cny','unknown_cost_calls']},ensure_ascii=False))


if __name__ == '__main__':
    main()
