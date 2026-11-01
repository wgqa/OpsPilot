# AR-02-CONN-01-HF-01 冻结验收标准

**状态：** FREE_FIX_ONLY / PROVIDER_NOT_AUTHORIZED / NO_REPLAY

**Repo / Branch：** `wgqa/OpsPilot` / `codex/ar02-live-01`

**开工 SHA：** `a2c4be7270c26b843a35fac13326b0f88f2668d0`

**参考事故前 Base：** `606adea415962f74d53db67cf55493c1bcb59bc9`

**任务卡 SHA-256：** `D5AFA4C6304C9A0AFD86C844A06E16A877B2F2DE512DA777EA1A994330C5A282`

## 冻结目标

修复专用探针的离线隔离和一次性授权失效问题。不要恢复已耗尽的单次授权，不发任何真实 Provider HTTP，不触碰生产 Agent、旧 P1 账本、S01/S02、浏览器、业务写入或 main。

## 验收矩阵

| ID | 冻结检查 | 通过条件 |
|---|---|---|
| HF01-RED-01 | 旧私有 `_transport` 替换路径 | 以本地 deterministic fake SDK/transport 显示旧代码未向 SDK 显式注入 HTTPX2 MockClient；mock 失配时默认路径会被触及的信号必须在本地即失败，不能真实触网。保留原事故日志，不再用 Provider 401 复现。 |
| HF01-GREEN-01 | 成功离线调用 | 锁定 openai/httpx2 SDK 使用显式注入的 HTTPX2 AsyncClient + MockTransport，解析合成响应/Usage；记录真实序列化请求字段、HTTPX2 路径与脱敏 Header；外部请求数为 0。 |
| HF01-GREEN-02 | URL 与模型参数 | 无 `/v1` 时路径 `/chat/completions`；有 `/v1` 时 `/v1/chat/completions`。两者皆为 POST、deepseek-flash、thinking disabled、max_tokens 64、无 tools、max_retries 0。 |
| HF01-NEG-01 | Mock/Transport 缺失或类型错误 | 在创建 OpenAI Client 前明确 fail-closed；不回退默认 HTTPX 传输。 |
| HF01-NEG-02 | endpoint、SDK 形态、proxy 环境不兼容 | 在 Client 创建/发送前 fail-closed，错误不包含密钥/代理凭据。 |
| HF01-NEG-03 | 离线失败注入 | Mock handler 抛本地 ConnectError，记录异常链；Provider/HTTP 响应数为 0。 |
| HF01-HARDSTOP-01 | send-once | 不论 marker、DB、目录存在/缺失/复制、请求摘要或环境如何，当前已耗尽授权的 send-once 都在读凭据、创建 Client、预留账本和网络调用前硬停止。不得通过删除 STOP 文件或重建 DB 获得权限。 |
| HF01-LEDGER-01 | 本地许可账本模拟 | 并发竞争最多一条 `ATTEMPT_RESERVED`；预留前崩溃没有 permit；预留后/UNKNOWN/复制账本不能重放；相同身份不同摘要拒绝。只模拟，不激活 Provider 发送。 |
| HF01-EVIDENCE-01 | 事故与历史保全 | 原始 401/request ID、实际计费 UNKNOWN、无 USD 0.01 预留、P1 UNKNOWN/USD 0.645600 与原始 SHA 只读保留；不补写虚假 reservation。 |

## 网络隔离证据边界

本机普通命令执行曾能完成外部 DNS/TCP/TLS，因此本轮不能仅凭默认工作目录声称操作系统级断网。允许执行的测试只使用显式本地 MockTransport，缺失 Mock 测试必须在创建 SDK/HTTP Client 前拒绝。若无法获得实际禁网的测试执行环境，则把“OS 级外网阻断负例”标记 `UNVERIFIED / NOT_RUN`，不得通过真实端点探测补证。

## 停止条件

任何测试试图使用默认外部 Transport、访问 Provider、读取/修改历史 P1 DB、触发真实 `send-once`、执行 MCP/浏览器或业务写入，立即停止。免费实现和可安全运行的本地测试完成后，提交 `ACCEPTANCE_CANDIDATE`；不恢复任何付费或一次性授权。
