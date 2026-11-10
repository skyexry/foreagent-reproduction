# 固定赛程的门槛、汇总与裁判设置对照

主结论：按预注册主赛程，四个候选的研究优先级判据均为未通过。全部26任务属于已查看开发集。

主输出为 `all_banks_run_2/summary.json`。收益定义为 baseline regret − intervention regret，正值表示改善。26任务等权；同任务内先平均池/种子，三次GPT再在同任务内平均；10,000次任务簇bootstrap，seed 20261108093。

| 单一改变/组合 | DS收益 | DS 95%区间 | GPT三次任务内平均收益 |
|---|---:|---|---:|
| gate .7→.5 | +.00613303 | [−.03274984,+.05407536] | −.00190612 |
| Beta(1,1) smoothing，gate .7 | +.00022392 | [−.00064374,+.00131548] | −.00024600 |
| gate .5＋smoothing | +.00603906 | [−.03253760,+.05394181] | −.00230621 |
| DS→GPT裁判设置，gate .7/raw | — | — | −.03595253，区间[−.09354593,+.01288536] |

DS gate/smoothing/组合的leave-one收益最小值分别−.01214553、−.00022316、−.01224326；三者DS均值均小于.01。GPT gate三次收益为−.00617398、+.00364968、−.00319405；smoothing为−.00106332、+.00020678、+.00011855。GPT设置替换三次收益全部为负，pooled leave-one范围[−.04797712,−.01675599]。

主图gate放宽后，DS新接受方向的严格准确率53.73%，GPT三次汇合52.03%；分子、分母、逐边判断见macro counts和`per_edge.jsonl`。这是相同完整查询图上的重汇总。raw规则沿用d=0记.5与valid degree tie-break；smoothing为(w+1)/(d+2)，再按valid degree并保留全部并列。

## 强控制与实际C0参照

- 原actual C0 regret .26416156；主coverage_random .7/raw为.27678483，主图.5/raw为.27065180，相对actual C0收益−.00649024。
- random_pairs图gate收益+.02178471，区间[−.00978232,+.06619720]；相对actual C0收益+.01173052，区间[−.01388219,+.04210032]。
- C0已揭示unique-edge trace重汇总gate收益+.05013657，区间[+.00369387,+.12055674]；相对actual C0收益+.02188701，区间[+.00214133,+.04476865]，leave-one最小+.01515628。这是原.7条件下生成的固定轨迹，后处理改变同时涉及原C0淘汰汇总与新门槛；完整.5 tournament需单独登记和重跑。
- 每个coverage_random/random_pairs臂11,004逻辑唯一读取；actual C0和C0固定trace均10,574。任务等权均值12.11538和11.20865，差额430总读取，全部逐场保留。固定trace臂的cache/denial为0；actual C0保留原过程cache和预算拒绝统计。
- DS直接gate vs smoothing的smoothing相对gate收益−.00590912，区间[−.05364740,+.03287738]。smoothing收益在gate .5减去在.7的difference-in-differences为−.00031789，区间[−.00163537,+.00084299]；GPT均值交互为−.00015409，区间[−.00121854,+.00100502]。

## 验证与复算

`all_banks_run_2/verification_1/receipt.json`通过：21,250个选择在阻断execution label文件读取、历史metrics投毒后逐字节封存一致；独立整数交叉比较、全部逐场评分、754逐任务行、29宏行和57组bootstrap/leave-one重建一致。850实际C0整套程序、1,700原固定图选择及78个既有任务汇总均复现。输入和输出SHA逐项核对。

`selections.sealed.jsonl`在execution label读取和join前写出；`per_episode.jsonl`保存每场每臂选择/评分/覆盖/成本；`per_task.json`、`contrasts.json`和`leave_one_task_out.json`保存主要推断。`paired_differences_1/`额外物化全部57对比×850场配对差和每个对比全部26项leave-one值，并核对任务宏差与主输出一致。

三份GPT bank的任务、17,877无序pair键和代码身份签名与DS一致；保留各bank原左右顺序并按raw index映射方向。原始文件、代码身份、缺失与异常的核验由`../banks/manifest.json`和`mapping_audit.json`绑定。

运行前快照、协议、命令、失败日志及结果哈希随每次输出保留。`ds_run_1`为DS先行；`all_banks_run_1`在输入manifest相对路径转换处失败，选择/评分前退出；修复Path.resolve后用新目录`all_banks_run_2`完成。新增API、候选训练、GPU均0；最长单次分析12.4秒。

复跑：`python3 -B experiments/selection-frontier-02/factorial/experiment.py --out NEW_NAME --bank BANK1 --bank BANK2 --bank BANK3`；省略bank运行DS。验证：`python3 -B experiments/selection-frontier-02/factorial/verify.py experiments/selection-frontier-02/factorial/all_banks_run_2 NEW_VERIFY_NAME`。
