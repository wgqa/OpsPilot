# M1-HF-01 面试问答

**问：恢复时为什么不能只看 LangGraph Checkpoint？**
答：Checkpoint 记录 Graph 位置，动作事务在 Domain SQLite。数据库提交后进程可能尚未收到响应就退出，Graph 状态会落后。恢复必须校验同一 Plan 的 Ledger、VerificationReceipt、冻结报告、DeliveryRecord 和 TicketEntry，才能继续或仅收尾。

**问：Checkpoint 缺失为什么不能直接重新 `ainvoke`？**
答：缺失可能是首次保存前崩溃，也可能是已有状态损坏，或 Probe/动作已经发出但结果未知。实现只允许校验通过的初始 INVESTIGATE Run 冷启动，并检查租户、owner、控制版本、输入来源、Attempt/预算和业务阶段。发现 Plan/动作痕迹就阻断，未知动作结果保持 `ACTION_OUTCOME_UNKNOWN`。

**问：如何避免恢复时重复应用关键纠错？**
答：从原 Message 与 `task_run_inputs` 只读加载，核对 source、digest、序号、high-water、control revision；不再调用 apply。Prompt 继续标记 `USER_INPUT_UNTRUSTED`，因此纠错不会变成 Evidence 或权限。

**问：Worker 如何避免一个坏 Run 阻塞其他 Run？**
答：每个 Run 有独立异常边界，worker owner/epoch fence 保护失败记录；可恢复错误持久退避，配置或授权问题以受控码收口。旧 fence 仍 fail-stop，避免旧进程改写新状态；health 显示 Worker 实时状态。

**问：真实模型或业务系统是否经过验证？**
答：没有调用外部 Provider 或业务系统。确定性替身捕获实际组装的 Prompt；本地 MCP stdio Server 被启动并读取 tools/list，本轮没有 tools/call。结论限于本地 SQLite Demo。

**问：M1-HF-01 PASS 是否意味着 M2 可启动？**
答：不意味着。它只报告 HF-01～HF-10 冻结测试通过。M2 放行属于主 Agent 审查决定；第三方 `BLOCK_M2` 在那之前有效。
