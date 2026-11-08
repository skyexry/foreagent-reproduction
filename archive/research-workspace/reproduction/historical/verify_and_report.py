"""Verify replay outputs against compressed raw author journals and source hashes."""
import collections
import gzip
import hashlib
import json
import os
from pathlib import Path

ROOT=Path(os.environ['FOREAGENT_RUN_DIR'])


def dump(path,data):path.write_text(json.dumps(data,ensure_ascii=False,indent=2))


def main():
    manifest=json.loads((ROOT/'source_manifest.json').read_text())
    for item in manifest:
        path=ROOT/'source_records'/item['run']/item['file']
        h=hashlib.sha256();size=0
        if item['file']=='config.yaml':
            data=path.read_bytes();h.update(data);size=len(data)
        else:
            with gzip.open(str(path)+'.gz','rb') as f:
                while chunk:=f.read(1024*1024):h.update(chunk);size+=len(chunk)
        assert h.hexdigest()==item['sha256'] and size==item['original_bytes']
    summary=json.loads((ROOT/'summary.json').read_text())
    rows=json.loads((ROOT/'replay_results.json').read_text())
    assert len(rows)==summary['batches_replayed']==129
    by_run=collections.defaultdict(list)
    for row in rows:by_run[row['run']].append(row)
    checked_nodes=0
    for run,batches in by_run.items():
        with gzip.open(ROOT/'source_records'/run/'journal.json.gz','rt') as f:journal=json.load(f)
        nodes={n['id']:n for n in journal['nodes']}
        for row in batches:
            ids=row['generation_order']
            assert ids==sorted(ids,key=lambda x:nodes[x]['ctime'])
            assert {journal['node2parent'][x] for x in ids}=={row['parent_id']}
            for id in ids:
                assert row['replayed_rank_meta'][id]=={'rank':nodes[id]['wm_predicted_rank'],'round':nodes[id]['wm_round']}
                checked_nodes+=1
            assert set(row['replayed_final_execution'])=={x for x in ids if not nodes[x]['is_skipped']}
            assert all(row[key] for key in ['rank_and_round_match','sorted_order_matches_log',
                       'probability_decisions_match_log','forced_fallback_match_log',
                       'final_execution_matches_journal','final_execution_order_matches_log'])
    assert checked_nodes==1290
    excluded=json.loads((ROOT/'excluded_log_batches.json').read_text())
    by_reason=dict(collections.Counter(r['reason'] for r in excluded))
    verified={'raw_source_files_hash_and_size_checked':len(manifest),'runs':len(by_run),'batches':len(rows),
              'candidate_rank_round_pairs_independently_checked':checked_nodes,
              'final_execution_sets_independently_checked':len(rows),
              'excluded_batches':len(excluded),'excluded_categories':by_reason,
              'original_world_model_sha256':hashlib.sha256((ROOT/'world_model_original.py').read_bytes()).hexdigest(),
              'original_agent_sha256':hashlib.sha256((ROOT/'agent_original.py').read_bytes()).hexdigest()}
    dump(ROOT/'verification.json',verified)
    example=next(r for r in rows if 'c5d8f2ae' in r['run'] and r['batch']==1)
    dump(ROOT/'example_real_batch.json',example)
    normal=sum(r['normal_pairs_log_checked'] for r in rows)
    revival=sum(r['revival_pending_nodes_log_checked'] for r in rows)
    lines=['作者真实批次：原版排序与执行控制重演',
           '日期：2026-11-07',
           '结论：公开15次运行中可完整恢复的129批、1290个候选，排名、轮次、排序顺序和最终执行集合均与作者保存记录一致。',
           '',
           '一、检查范围与版本',
           '覆盖5任务、每任务3次，共15次实际运行。原始config、完整journal、完整aide.log已固定为压缩快照，原文本共约413.5MB。',
           '数据集版本：'+summary['dataset_revision'],
           '代码提交：c4d52cf99bd870d830b456ac7c0684aec1aef375。world_model_original.py SHA256：'+verified['original_world_model_sha256'],
           '原版缓存修复前的源码保留原样。排序调用原tournament_rank，执行控制提取原agent.py第700至767行AST，包含强制执行回退。',
           '',
           '二、实际输入和回放方法',
           '从Generated improvement candidate i/10日志恢复每批真实候选及输入顺序，使用journal中的真实代码和node2parent核对父节点，再与ctime顺序交叉检查。',
           '运行设置读取各次实际config.yaml：比较模型DeepSeek-V3.2-Thinking、温度1.0、置信度门槛0.7、候选10、TopK1、执行概率0.2。',
           '比较输入为各批保存的wm_comparison_results，按调用批次和返回位置注入历史ComparisonResult。排名与轮次作为输出核对目标，候选对象的输入仅有真实ID和代码。',
           '原控制层随机种子/RNG状态在已检公开记录中仍待补齐。复赛对手使用明确标记的演示随机序列；历史响应按位置回放，普通对局双方和复赛pending节点身份另与日志核对。',
           '因此，本实验是条件于历史响应序列的原算法状态更新验证。它与按真实复赛对手逐对检索反馈、独立重新调用模型的实验分别记录。',
           '概率执行使用日志实际记录的触发/跳过结果驱动原执行分支，强制回退由原代码自行决定，再与journal及实际执行解析日志交叉核对。',
           'API调用0次，实际训练0次；这次核对历史行为的一致性。',
           '',
           '三、结果',
           '可恢复批次：129；候选：1290；历史比较记录：23873。',
           '逐候选rank和round一致：1290/1290。',
           '完整排序顺序与执行日志一致：129/129批。',
           '概率执行决定、强制回退决定与日志一致：129/129批。',
           '最终执行集合与journal一致、执行顺序与实际解析日志一致：129/129批。',
           f'普通比较双方及结果独立日志核对：{normal}条；复赛pending节点及结果核对：{revival}条。',
           f"强制执行回退：{summary['forced_fallback_batches']}批。",
           '这里的100%表示历史结果一致率；选中池内最佳候选的命中率属于另一套真实分数评估。',
           '',
           '四、逐运行结果',
           '运行 | 日志批次数 | 完整可恢复批次 | 候选数 | 排名一致批次 | 执行一致批次']
    for r in summary['per_run']:
        lines.append(f"{r['run']} | {r['logged_batches']} | {r['verified_batches']} | {r['candidate_count']} | {r['rank_matches']} | {r['execution_matches']}")
    lines+=['','五、覆盖边界',
            '日志共出现140批，其中129批具备最终journal对应节点；其余6批日志生成未完成、5批生成节点尚缺最终journal快照，单独保存于excluded_log_batches.json。',
            '结构化比较历史记录winner位置、confidence、round、valid。复赛对手身份和原RNG状态仍需进一步从日志或作者补充材料恢复。',
            '这次对概率执行的一致性验证以日志触发结果为条件，核对的是Top-K筛选、执行对象和强制回退的处理规则。随机数本身的独立重生成属于另一层验证。',
            '',
            '六、一个实际例子',
            '运行：'+example['run']+'，第1批。',
            '输入生成顺序：'+', '.join(x[:8] for x in example['generation_order']),
            '原版重演rank-0候选：'+', '.join(x[:8] for x,v in example['replayed_rank_meta'].items() if v['rank']==0),
            '最终执行：'+', '.join(x[:8] for x in example['replayed_final_execution'])+'；此批触发强制回退，与作者日志及journal一致。',
            '',
            '七、复现与交付',
            '在本目录运行：python replay_author.py；随后运行：python verify_and_report.py。',
            'source_records/含实际配置、压缩journal和详细日志；source_manifest.json保存来源URL、原文本字节数和SHA256。',
            'replay_results.json逐批记录真实输入、原版输出、作者输出及日志核对位置；per_run.csv与summary.json为汇总。',
            'verification.json记录45份原文件的哈希核对与独立输出复核。',
            '用于报告的表述建议：We replayed the original ForeAgent ranking and execution control logic on 129 recoverable historical candidate batches from 15 released runs. Conditional on the saved comparison responses and logged probability outcomes, all 1,290 candidate ranks/rounds and all 129 final execution sets matched the released traces.']
    (ROOT/'作者真实批次原版重演结果.txt').write_text('\n'.join(lines)+'\n')
    print(json.dumps(verified,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
