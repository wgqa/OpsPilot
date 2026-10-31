# AR-02-LIVE-01 P0 失败记录

所有日志保存在 `runs/`，未覆写历史失败。

| 记录 | 原始结果 | 归因 | 后续处理 |
|---|---|---|---|
| `red-freeze-01.log` | 系统 Python 3.14 下 9 项均因缺少 `langchain` 而失败，退出码 1。 | 测试环境选择错误，不是源码结果。 | 切换到 D 盘项目 `.venv` 中已锁定的 Python 环境，随后用同一 RED 测试重跑。 |
| `red-frozen-02.log` | 9 failed，退出码 1。包含缺少显式实验作用域/模型绑定、未传 `thinking`，以及实验账本模块不存在等失败。 | 有效源码 RED：旧 Provider 工厂和 Worker 尚无本任务 P0 保护/全局账本。 | 保留原日志；实现限定范围的工厂、持久账本及 Worker 接线。 |
| `green-focused-01.log` | 14 passed / 2 failed。上限错误码仍叫 MODEL；正式 Worker 确定性用例实际执行 3 次模型 dispatch，而测试误写成 2 次。 | 一处产品错误码命名、一处测试低估了 Knowledge 工具往返的真实模型次数。 | 改为 Provider 限额语义；按 FixtureModel 实际调用/持久 assistant_calls 修正断言。 |
| `green-focused-04.log` | 20 passed / 1 failed；费用结算断言仍按旧 `$1.32/M` 输出价期待 10 micro USD，当前 Flash 费率下真实公式为 9 micro USD。 | 费用预检更正后的测试快照问题。 | 以 2026-11-01 官方 Flash `$1.20/M` 峰时输出价修正断言，并重新运行 focused-final。 |
| `regression-ar02-01.log` | 65 passed；早于补充的边界测试及费用价格更正。 | 中间结果，不作为最终验证。 | 原样保留；以 `regression-final.log` 为本轮最后回归结果。 |
| `regression-ar02-02.log` | 69 passed；仍早于官方价格重新核对及最终新增拒绝路径测试。 | 中间结果，不作为最终验证。 | 原样保留；以 `regression-final.log` 为本轮最后回归结果。 |

另有中间通过日志 `green-focused-02.log`、`green-focused-03.log`、`green-focused-05.log`。它们均未取代本轮最终运行。pytest 原始日志有少数空行尾随空格，按原始证据要求没有清洗；`git diff --cached --check` 对源码和文档通过，原始 `runs/*.log` 单独排除。测试没有发出真实 Provider 请求、没有运行浏览器，也没有进行 S1/S2 业务写入。
