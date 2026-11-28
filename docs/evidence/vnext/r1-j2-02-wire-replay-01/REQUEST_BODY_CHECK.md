# 请求体字节恢复检查

目标 Completion：`83831aee-6414-461e-b558-76259e4875bf`

要求的 SHA-256：`0db9cac29a9c786b6d520a32863dc38e27844e58f8be469476d01d530381496f`

## 结果

原始传输记录中的 `http_body_digest` 与冻结 SHA **相等**。但归档中没有 HTTP 请求体原始字节，因此不能从字节重新计算 SHA；摘要相等只证明日志记录了该摘要，不能证明可以原样重放。

## 已核查材料

| 来源 | 目标记录 | 可用内容 | 是否有原始请求体字节 |
|---|---|---|---|
| `provider_http_private.jsonl` | 第 9 条，Completion ID 精确匹配 | `http_body_digest`、应用 `request_digest`、响应状态/白名单头、响应体 SHA/Base64 | 否；无 request-body/raw-wire 字段 |
| `domain.sqlite3` → `assistant_runtime_spends` | `completion_id` 精确匹配 | `http_body_digest`、状态、Usage、`response_body` bytes | 否；Schema 无请求体列 |
| `domain.sqlite3` → `assistant_calls` | J2-02 Run 的 5 条调用 | 3 条 MCP、2 条 MODEL；MODEL 的 `request_json` 为应用层请求记录 | 否；该字段不等于 HTTPX wire bytes |
| `assistant_calls_private.jsonl` | 未发现目标 Completion ID | Assistant Call 的持久记录 | 否 |
| `turns_private.jsonl` | 未发现目标 Completion ID | 用户轮次/答案摘要 | 否 |
| 原私有 `run_live_campaign.py` | 导出逻辑已读取 | 输出 `http_body_digest` 与响应 Base64 | 未保存请求体；导出不是原始报文归档 |

目标 `assistant_runtime_spends.http_body_digest` 与私有 HTTP 记录一致，且等于冻结 SHA。`request_digest` 是不同的应用层摘要。没有把 `assistant_calls.request_json`、模型消息、响应、checkpoint 或重序列化 JSON 当作原始请求字节。

## 停止决定

任务卡要求原始字节不可恢复时立即停止，不允许手工拼装、推测或重新生成请求体。故没有创建新 Campaign、Runtime Grant、费用预留或 Claim，没有读取凭据，也没有发送请求。

原始文件仅留在私有归档；其 SHA-256 核对记录列于 `REPORT.md`。未对旧数据库、Claim、账本或日志做写入。
