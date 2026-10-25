# 阶段 A 失败历史（只追加本轮，不改旧记录）

- `red-01`：11 failed；真实复现新 Follow-up 被 Task 8/6 拒绝、caller limit 绕过、Run/Task 并发超额、辅助计数缺失和不准确的耗尽原因。Schema 新字段尚未实现的负例另列，不冒充业务动态复现。
- `red-02`：5 failed / 2 passed / 11 deselected。两种初始 Run OS 恢复通过；两种只读 Follow-up 恢复分别消费 5、6 MODEL，超过新合同 4；混合辅助分类/Chat/Compression 的两连接竞争实际累计 9。四次接口旅程的两个变体在独立准备处使用了错误字段 `receiver_version`（真实列是 `version`），属于测试准备错误，不算有效业务 RED。修正测试准备，不更改用户目标、判据或正式源码，另存下一轮日志。

付费 Provider：0。所有运行使用确定性模型/本地 HTTP/MCP；原始日志与对应 COMMAND.json 的退出码为准。
