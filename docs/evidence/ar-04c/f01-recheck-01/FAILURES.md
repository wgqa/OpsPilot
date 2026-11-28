# 失败与未完成项

1. **历史解释的时间指代错误。** 第二轮未调用 MCP，正确说明当前 Run 没有重查；但回答也说“上一轮没有做任何新的查询”。初始 Run 实际有 4 次 MCP，其中 3 条业务 Observation。F01 的“虚称本轮重读”未在该轮重现，来源时间表述仍未完全正确。
2. **PROCESSED 用户答复未完成。** 第四轮取得同 Event PROCESSED 后，尝试下一次模型请求被 `AR02_LIVE_PROVIDER_LIMIT` 拒绝，Run 和 Chat Attempt 为 FAILED。用户看到 `PROGRAM_LIMIT`，没有模型最终答复。该程序提示称“本说明未重新取得业务事实”，而该 Run 实际取得了新事实，存在表达歧义。
3. **工具响应形态。** 所有出站请求均含 `parallel_tool_calls=false`，但有三次响应包含多条 Tool Call。系统实际按记录时间逐条执行；原始响应保留供后续核验。
4. **测试与工程记录。** 首次新身份离线 RED 为 3/3；测试脚本在打印 RED 时遇到 Windows 控制台编码错误，pytest 原始日志已先落盘。随后免费预检 11/11、旧身份兼容 1/1。

本次未重跑、未追加 Provider 请求、未扩大预算。旧 F01、Gold、Claim 和历史结果不修改。模型对 PROCESSED 的最终推理及用户结论为 NOT_COMPLETED；浏览器、全量 pytest 均 NOT_RUN。
