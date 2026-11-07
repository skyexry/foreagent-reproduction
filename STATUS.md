# 当前状态：作者原版 ForeAgent

- **源码已核验**：独立检出固定在 `c4d52cf99bd870d830b456ac7c0684aec1aef375`。逐文件核对工作目录与该提交，484 个 Git 文件内容一致，工作区干净；其中 Git LFS 指针按提交原样保留。
- **离线证据**：给定历史判断和日志中的概率结果，15 次作者运行中的 129 个完整批次（1,290 个候选）控制输出一致。原 RNG 状态和复赛对手身份仍有缺口。证据：`experiments/historical-v1/summary.json`。
- **单任务在线验证**：`stanford-covid-vaccine` 待运行；本次 submission 和官方得分均待取得。
- **下一步**：确定可租用且支持 Linux/amd64 Docker 和 NVIDIA GPU 的执行机，核对任务数据与模型端点后运行作者代码，再用官方评分器核对本次 submission。预算和实例尚待确定。
