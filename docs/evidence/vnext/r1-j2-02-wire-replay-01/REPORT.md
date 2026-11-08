# R1-J2-02-WIRE-REPLAY-01

## 结果

**`BLOCKED_RAW_REQUEST_UNAVAILABLE`。本轮真实 Provider 请求数为 0。** 归档中的 Provider Runtime 记录保存了目标 Completion 的 `http_body_digest`，其值与任务卡冻结 SHA `0db9cac29a9c786b6d520a32863dc38e27844e58f8be469476d01d530381496f` 相同；但是没有保存当时发往 DeepSeek 的完整请求体字节。任务卡明确要求在字节不可恢复时立即停止，不能从应用请求 JSON 或 digest 重建，所以没有新建 Campaign、Grant 或 Claim，也没有尝试发送。

首次 J2-02 结果保持原 `PARTIAL`，未改写。没有新输出，不能对模型在相同输入下是否再次承诺作判断。

## 核验基线

- 原真实执行源码：`7f8df218415fbbcf4df33001fc593bd772ab880e`
- 原结果提交：`9e9f7b05afcdd51e05c4c4af605bb225c53bd2bd`
- 最近复现性审查：`04560543afa5f6df54fe63f858ea206733559ad9`
- 冻结目标 Completion：`83831aee-6414-461e-b558-76259e4875bf`
- North Star Blob：`43dabda468506717c6956e676dfad4304c4f38e6`
- AGENTS Blob：`807b928686a4dd2cac7b15b3c354b9943c93c910`
- Review Skill Blob：`d405c8d413d633824b279202cc1503dab4cf0b03`
- 当前本地工作分支基线：`codex/r1-j2-02-wire-replay-01@04560543afa5f6df54fe63f858ea206733559ad9`
- 远端状态：`REMOTE_UNVERIFIED`；本次 GitHub HTTPS 连接失败，未能读取远端 refs。

## 原始材料与可恢复性

只读核查了原 Campaign 私有归档内的 `provider_http_private.jsonl`、`assistant_calls_private.jsonl`、`turns_private.jsonl`、`domain.sqlite3` 和 `run_live_campaign.py`。

- `provider_http_private.jsonl` 第 9 条匹配目标 Completion；字段有 `request_digest`、`http_body_digest`、响应元数据及 `response_body_base64`，没有 `request_body`、`request_body_base64`、原始请求字节或等价字段。响应体 Base64 不是请求体。
- Domain 表 `assistant_runtime_spends` 对应行保存相同的 `http_body_digest` 和 `response_body` 字节；表中没有请求体字节列。
- `assistant_calls.request_json` 保存的是 Assistant 调用记录。目标 Run 有 5 条调用，其中两条 MODEL 记录分别为 49,667 和 66,122 字符的应用层 JSON；它们并非 HTTPX 实际发送的原始字节，不能重序列化后冒充原请求。
- 私有 Runner 导出保存 `http_body_digest`、响应状态/头、响应 SHA 与响应 Base64，不导出请求体内容。

证据哈希与归档 `PRIVATE_HASHES.json` 核对一致：

| 文件 | SHA-256 |
|---|---|
| `provider_http_private.jsonl` | `ef3a9d78001dc6a25048c92869fb76a0cffcbc03bafa0d9679bb2f73b4c2e9fa` |
| `assistant_calls_private.jsonl` | `d28a229a84536e49c32d0ca8a413a30cf3aa6b95cdb96439c97ef8ed126efb9a` |
| `turns_private.jsonl` | `0bd9cc43b11fe2aa434932e9bdce4edb45e5686ad28603aa8df944b18672c8cc` |
| `domain.sqlite3` | `6f423bff6b539755ac77480d32182905c660fee904df733792b5b6010c253441` |

详细字段和相等性核验见 `REQUEST_BODY_CHECK.md`。原始私有文件没有复制到 Git。

## 本次执行状态

- 发送前报文检查：停止，原始请求体字节不可恢复。
- Provider / MCP / Browser / 外部业务写入：`0 / 0 / 0 / 0`。
- 新 Campaign / Grant / Claim：均未创建。
- 官方价格、凭据及实时发送参数：未进入核验步骤；报文可恢复性门槛未满足即按任务卡停止。
- 测试：未运行。本轮仅增加失败证据文档，没有源码改动。
- 原 Campaign、原 Claim、原数据库、原 Trace、首次 PARTIAL 和冻结 Gold：未修改。

实施状态为 `ACCEPTANCE_CANDIDATE`，结论仅为本次无法执行。没有重复样本，不得据此判定表达问题是偶发或稳定。
