# 本轮封存输出独立核查

`audit_outputs.py` 对已有 opponents、second-opinion、c0-budget 产物进行只读核验，收据为 `receipt.json`。核验沿用冻结 C0 作为原程序执行入口，另行实现反馈解析、排名、线性方程求解、直接评分和汇总，研究假设与已有实验文件保持原样。

| 对象 | 核验内容 | 结果 |
|---|---|---|
| 6份反馈银行 | 95,792条记录的文件哈希、任务/pair键、原序端点、来源group index、字段与缺失来源标记 | 通过 |
| 随机对照赛程 | 850场的独立seed链与未问边随机后缀 | 精确一致 |
| Opponents | 5,100张图的legacy、hard/soft shrink、hard/soft Colley；手写Gaussian消元，12张图另用有理数精确解 | 所有选择一致 |
| Opponents分数 | 全部评分、55组主效应/交互及其任务簇CI、leave-one最小值 | 一致 |
| Second opinion | 5,100场原链弃权、backup银行/边、被替代新边、救回方向、三臂选择与成本；24组效应CI | 一致 |
| C0 budget | 6银行4,574场短cap真实C0重新运行，完整轨迹前缀、选择、读取数；49组分数/成本CI | 一致 |

第二意见的逻辑账本合计：13,046次backup读取对应13,046条让出的新边，救回7,719条原弃权，66,024次总读取。Sham保留注册的名义调用预算，用于拆解牺牲新边的机会成本。

六银行场数分别为：DS和3份GPT各850；DS0早档324；DS0晚档850。核查对照包含各自完整可用人群，DS0早档采用其原始10任务范围。

核验用时约41.53秒，逐项输入与脚本哈希、有理数Colley数值、计数及范围见 `receipt.json`。第一次核验将银行字段白名单按四个核心字段写得过紧，DS0还带有合法来源字段 `source_row`、`missing_source_pair`；扩充审计白名单并核对所有缺失标记为false后完整通过。原始失败保留于 `audit_outputs.log`，通过日志为 `audit_outputs-002.log`。

`audit_judge_ds1.py` 另核验 judge-intervention 的DS1阶段：独立构造四折hash资格、D/A变化银行、冻结O与全部实际D/A轨迹、实现曝光量和分数，收据为 `judge_DS1_receipt.json`。它以DS1已完成的封存前缀哈希绑定来源，允许原实验继续生成其他银行。原型D/A使用执行标签构造oracle反馈，其用途沿用原注册诊断定位。

DS1结果全部通过：850条原冻结O精确一致；143,016次全银行资格/变化门控检查；6,800条D/A自适应实际路径及曝光量精确一致；7,650份逐折评分与6组任务宏效应CI/LOO重算一致。四折对每条pair地址恰好覆盖一次。该阶段核验耗时约48.97秒。

重做核验：

```bash
python -B experiments/selection-frontier-02/verification/audit_outputs.py
python -B experiments/selection-frontier-02/verification/audit_judge_ds1.py
```
