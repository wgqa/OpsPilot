# M2-02-HF-01 面试问答

### 为什么 `NEED_MORE` 会造成 10,003 次 Gate 记录？

历史记录始终以 stale-requery-allowed 收尾，MCP/模型预算已经到 6/8，却没有在无新动作或预算耗尽时稳定落到终态；恢复重放用随机 Trace ID 也会重复插入 Gate。能确认循环条件和另一项同 Run Probe 时间遗漏，但旧日志没有最初 Worker 异常堆栈，不能确认第一个 Worker 异常的根因。修复保留 8/6 预算，在无进展时终结为 INCONCLUSIVE，并把 Gate Trace 身份做成幂等且最多 64 条。

### 如何让模型理解意图，同时避免它扩大授权范围？

把意图识别和权限判断分层。模型可产生经严格 Schema 校验的候选 Request ID、症状或不确定度；可信程序再检查 TaskBinding、当前 Probe、Request/Event 关联和 Scope 决策。用户自然语言不能变更绑定、Scope 或 Gate。高不确定性会真实地要求澄清，但不会因此假称诊断成功。

### H 的 12 个 FAIL 是否说明安全机制失效？

不等同。H 最终是 2 PASS、12 FAIL、2 PARTIAL，但 Control Safety 与 Boundedness 都为 16/16 PASS。许多 H 输入被模型标成 high uncertainty，系统按策略澄清而没有产出冻结 Gold 期望的诊断；这表示正确处理效用不足，不能通过降低安全或把所有澄清算成功掩盖。

### 为什么要同时保留原始 Release 和重评分结果？

原始 48 条回答与工具 Trace 是不可变观察，问题出在评分器对 G8 否定句的解释。最终复评记录源 `RESULTS.json` SHA 和评分器提交，用同一批回答重新打分，不重跑 Provider/MCP。这样审阅者能同时看到错误评分、评分修复和未变化的事实轨迹。

### 真实 Web 证据证明了什么、又没有证明什么？

Edge 端真实登录后在同一 Task 提交正式纠错、新建 Run 和新 Request，通过 Provider 与 MCP 读回 403 `AUTH_ACCEPTED/SCOPE_INSUFFICIENT`，生成新的 Receipt/Draft，再用只读聊天说明未修复、未提交；前后业务投影不变。它证明了本地演示闭环和授权隔离，不证明生产 IAM，也没有创建 Scope、审批、移交队列或业务恢复。
