# AR-02-LIVE-01-HF-02 冻结验收计划

**状态：** 冻结 RED/GREEN 标准；仅免费诊断与修复获批
**Base / Branch：** `204cd2ec1dc292954e1c0b09da129fcab4476d57` / `codex/ar02-live-01`
**North Star / AGENTS / Skill blobs：** `1f737712c7a36ceb34433ac09c3fbba3c3305542` / `32c45506cceeaa8c76a5c56bf8360ff476b58856` / `d405c8d413d633824b279202cc1503dab4cf0b03`

## 范围与不变量

- 只调查 AR-02-LIVE-01 P1 S01 的连接失败并修复 Run、Chat Attempt、程序提示的不一致。
- 冻结 S01/S02 输入、原始 Gold、Provider UNKNOWN dispatch、USD 0.645600 预留及旧证据只读保留。
- 不发送 Chat Completions，不重新执行 S01/S02，不运行浏览器，不执行业务写入，不清空/重置/结算 UNKNOWN 账本。
- 所有 Provider 协议测试使用 `httpx.MockTransport`、伪造 key 和本地响应；TLS 网络诊断仅做 DNS/TCP/TLS 握手，不发送 HTTP。

## 冻结验收标准

| ID | 检查 | 通过条件 |
|---|---|---|
| HF02-A1 | 当前锁定 SDK 的实际请求路由与传输 | `httpx.MockTransport` 捕获完整 URL、POST、路径、脱敏授权头存在状态和请求体；分别覆盖根 URL 与 `/v1` base URL。再用锁定 OpenAI SDK 默认 HTTPX2 transport 做本地对照，核对 P1 捕获钩子的类型兼容性与单一路径匹配。 |
| HF02-A2 | 本地连接失败注入 | `httpx.MockTransport` 在 HTTPX transport 阶段抛出 `ConnectError`；另以默认 HTTPX2 MockTransport 确认锁定 SDK 的异常包装。保存异常类型链、目标 host/path、没有响应的事实；不得连接真实 Provider。 |
| HF02-B1 | Worker Assistant Run 故障闭环 | 通过真实本地 MCP/Assistant Runtime 和实际 SDK MockTransport 触发连接错误；Run `FAILED`，Chat Attempt `FAILED`，错误类/完成时间/Run 关联有效；不产生 Chat Answer。 |
| HF02-B2 | UNKNOWN 预算与重放 | 实验 dispatch 保持 `UNKNOWN`、预留 645600 micro USD、结算 0；同一失败收尾重复调用不新增 dispatch、答案或限制消息，且不发第二个请求。 |
| HF02-C1 | 程序提示 | `/messages` 将说明标为 `PROGRAM_LIMIT`；文案清楚表示连接失败及本次未完成，不展示底层 `ASSISTANT_STOP`/异常类；内部 Run blocked_reason、Attempt error_class 和 Dispatch error_code 保留审计信息。 |
| HF02-R1 | 正常路径与恢复 | 已有 AR-02 本地零工具/Knowledge 成功路径、Assistant MCP 路径和 Worker/Chat 可恢复重试测试继续通过。 |

## 失败归因与停止线

- 历史 P1 仅证明应用 SDK 抛出 `OpenAIConnectionError`、HTTP 捕获器零观测、dispatch 为 UNKNOWN；不能据此证明请求未离开进程或供应商未计费。
- 若本轮网络诊断不可用，则保留未证实层级；若 MockTransport 或本地测试失败，记录 RED 和原始日志后最小修复，不以付费重跑补证。
- 遇到需要真实 Completion、真实 S01/S02、参数/模型变化或解除未知账本的要求即停止并交主 Agent。

## 证据文件

- `REPORT.md`：实现与连接归因。
- `RESULTS.json`：命令/状态/退出码/证据等级。
- `FAILURES.md`：本轮及环境错误保留。
- `TRACE/`：SDK MockTransport 和本地 Runtime 的实际捕获。
- `runs/`：原始命令日志。
