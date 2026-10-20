# 有限 Worker 故障审计（注入前冻结）

只核对旧两次WORKER_RETRY_EXHAUSTED历史记录，以及当前源码的异常分类、Fence与持久重试边界。不重新运行旧业务，不改用户库、调度器或M3源码。

两项确定性注入在各自独立合成测试库，调用真实`worker._process_run`与`record_worker_run_failure`，用patch让`_process_run_inner`在模型/MCP之前抛出明确异常。它们是故障注入，不能冒充真实Provider/MCP、过去故障的根因复现，或完整Scheduler时序测试。

1. RuntimeError：预期映射WORKER_RUN_FAILED，可重试状态持久化；三次重试预留后下一次归BLOCKED/WORKER_RETRY_EXHAUSTED。直接驱动wrapper不测试实际backoff等待，检查next_attempt_at记录、同Run重试数、Outbox和0业务副作用。
2. TaskControlError(TASK_CONTROL_STALE)：预期非重试BLOCKED，不能执行模型/MCP或业务动作。

每项最多按上述既有界限驱动；保留每步Run/Retry/Outbox/Worker owner与epoch。无Provider或MCP请求是预期事实，不是模型成功。旧记录只有generic code而无原始exception class/stack时，最终必须ROOT_CAUSE_NOT_PROVEN；相同终态不能证明同一根因。
