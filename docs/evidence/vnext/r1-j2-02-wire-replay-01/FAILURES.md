# 失败与停止记录

## BLOCKED_RAW_REQUEST_UNAVAILABLE

**触发条件：** 归档保存了匹配冻结 SHA 的 `http_body_digest`，但没有保存目标 Completion 实际发送的完整 HTTP 请求体字节。

**影响：** 无法证明新请求体逐字节等于原请求体，不能执行一次真实模型重复采样；J2-02 的重复性仍未知。

**处理：** 按任务卡立即停止。没有重建请求、读取凭据、创建新 Campaign/Grant/Claim、发送 Provider 请求或执行工具。旧 J2-02 PARTIAL 和旧账本均保留。

**结果：** 这是原始请求体未归档造成的实验复现阻断；未发现新的产品代码失败。没有重试或替代报文方案。
