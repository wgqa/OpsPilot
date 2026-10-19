# M2-02 面试问答

### 为什么不能看到 403 就直接生成权限申请？

403 是 HTTP 层观察，不足以说明请求通过了认证、主体有效、目标资源绑定正确，也不能说明缺少哪个 Scope。系统将在线 Probe 与实际 Authz Decision 按 request_id、TaskBinding、资源和版本关联，再由确定性 Domain Gate 判断。当前证据不完整或冲突时保持安全结果。

### Agent 如何从用户纠错中学习，而不让用户改权限？

纠错消息通过 TaskControl 进入持久 Message/Run 序列，携带控制 revision，并由新的模型调用重新调查。文本只是一条待验证线索；Domain 重新执行 Probe 并查当前授权事实。模型不能写 Grant、Policy、Scope 或审批字段。

### 为什么收窄模型工具 schema？

仅靠 system prompt 说“不要乱查”不足以限制工具边界。每个 Run 根据已有证据只暴露当前合法的下一步：先 Probe；拿到 403 后只允许用刚得到的 request_id 查询授权事实；证据齐备后不再暴露 MCP 工具。Domain 仍重复校验，预算在出站前持久登记。

### `HANDOFF_READY` 是什么？

它是当前证据支持的申请草稿状态，不代表用户已获授权、权限已变更、业务已恢复或请求已交接。M2-02 没有接收队列和 HandoffReceipt，Scope 写操作为零。

### 如何解释 A 策略的失败？

冻结 A 试次为 13 PASS、1 FAIL、2 PARTIAL。G6-H1 越界请求得到 HANDOFF_READY，因此保留 FAIL；后续代码修正的独立补充运行返回 NO_ACTION，但不替换冻结观察。G1-H1 缺原始 Trace/截图，G7-H2 的 fixture 得到 403 而非 404，均为 PARTIAL。不能把补充运行回填成原试次 PASS。

### M2-02 交付边界是什么？

交付可信的 S2 调查与冻结申请草稿，同时保留 401 S1 既有流程。没有实现审批队列、Scope 自动授权、业务恢复、HandoffReceipt 或 M2-03。独立验收由主 Agent 完成。
