# 老师给 ForeAgent 项目的研究建议

根据组会后的转述整理，供读论文和选题时对照。

**先确认排序值得改。** 用作者记录的执行成绩找出每批真正的第一、第二名，再看当前裁判把它们排在哪里。老师特别问的是「top1-2 是不是被排到 4 以后」。如果好方案经常被排得很靠后，就有理由把研究重点放在排序上。

| 研究方向 | 老师提出的问题 |
|---|---|
| **读清 ForeCritic** | 它训练的是 reward model，还是强化学习中的 critic？监督来自整份方案的最终成绩（outcome reward），还是中间步骤的质量（process reward）？论文是否用了 GRPO？ |
| **设计 reward** | 除了给最终结果打分，能否在 token、一次行动（action）或一个推理步骤（reasoning step）上定义不同的奖励？哪种粒度适合这个任务？ |
| **去掉 critic 与 relative group advantage** | 如果考虑训练策略，能否用同组候选的相对表现来估计 advantage，从而省去单独的 value critic？讨论时需明确老师所指的 critic 具体是哪一个组件。 |
| **Stronger teacher model** | 更强的 teacher 能否提供更可靠的候选比较或监督信号？ |
| **Retrieval / ranking** | 能否把候选选择当作检索与排序问题，用代码 embedding 检索相关方案，或用 embedding reranker 给候选重新排序？ |
| **DeepSeek Thinking 的 comparison skills** | 能否给 DeepSeek 一套可重复使用的比较方法，让它更准确地判断同一任务中哪份代码会跑得更好？ |

老师还提醒了两个贯穿各方向的问题：

- **失败复盘。** 这轮具体为什么失败？下一轮怎样避免重犯同一种错误？
- **泛化。** 作者 corpus 覆盖的任务是否太少或偏向某些类型？在这些任务上有效的方法，换一类任务还能否成立？
