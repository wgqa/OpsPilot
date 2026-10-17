# M1-01 真实模型 TaskRun smoke：首次失败记录

**结果：FAIL（保留）**

首次真实模型/MCP TaskRun smoke 使用了 smoke harness 中未注册的票据编号 `INC-M1-TASK-RUN`。模型 Function Calling 与 MCP 只读调查已执行，但创建 Plan 时 Domain 拒绝了该票据，Run 未进入等待审批状态。首次运行没有执行 REPAIR、DELIVER 或其他受限写入。

首次运行的 stderr/stdout 没有被 tee 到文件，因此这里不伪称保存了逐字原始终端日志，也不补造返回码或调用 ID。失败原因由本次调试时观察到的 Plan 创建拒绝确认；这一采集缺口本身作为限制保留。

修正仅将 smoke 使用的票据改为现有 Demo fixture `INC-A-001`，没有放宽 Domain 校验或改变业务合同。之后在独立的新 Domain/checkpoint SQLite 文件上重跑成功：真实模型 5 次请求均返回 OK，MCP Client/Server 完成 4 个只读工具调用，Plan 绑定新的 TaskRun 与 control revision 2，Graph 停在审批 interrupt；审批前 config 仍为 7，未创建 ActionIntent/ActionLedger。

重跑原始日志见 [`logs/real-model-task-run.jsonl`](logs/real-model-task-run.jsonl)。此次成功是 M1-01 TaskRun smoke，不是完整人工批准业务流程；完整 S1 401→200 回归另见 [`s1-d3-smoke/REPORT.md`](s1-d3-smoke/REPORT.md)。
