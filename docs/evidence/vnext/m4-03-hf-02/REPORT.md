# OpsPilot vNext M4-03-HF-02 验收候选报告

基线仓库为 `wgqa/OpsPilot`。指定审查基线、本地开工 HEAD 和 `origin/main` 均为 `afe3c03a756e2a60e454e0057484017448942d40`。本轮直接在 `main` 开发，没有创建分支或 PR。冻结标准及 RED 测试先于实现提交；源码提交为 `029e7399f83e1f03c8ae6c6e5afccf38256c8cff`。本报告只提出**验收候选**，不替代主 Agent 独立验收。

## 修复内容

**HF02-01：撤权后的历史读取侧路。** `list_session_event_page()` 为历史事件与 SSE 共用同一筛选逻辑：`S3_DIAGNOSIS_FROZEN` 和 `S3_HANDOFF_ACCEPTED` 只有在会话 owner 仍是对应 S3 Task 的 SUPPORT、且 `get_s3_binding()` 通过当前 Scope/Grant/Principal/Auth Policy/Integration 检查时才返回。不可变事件不删除；普通 Session 事件继续可读，`next_after` 越过隐藏记录，避免历史分页和 SSE 在隐藏事件上卡住。历史端点与 SSE 的响应筛选一致。

撤权后，S3 Task 关联的 CHAT_READONLY Run 在读取 Context Manifest 或答案 Chunks 时重新校验当前 S3 授权，失败返回 403。历史 Message 仍保留用户输入；绑定 S3 Task 的助手答案仅在读取响应中替换为固定隐藏说明，不修改数据库中的原始消息。当前授权的 owner 仍能读取这些聊天内容。审计测试还核对了 Task、Run、Inspector：未发现撤权后泄露 Receipt/Queue ID、订单号或 `HANDOFF_ACCEPTED` 的字段。同租户 APPROVER 仍只能通过既有 `/api/tasks/{id}/s3-handoff` 查看已提交回执的只读摘要；Session 事件端点沿用其 owner ACL 返回拒绝，APPROVER 不能读取诊断事件或提交新交接。

**HF02-02：授权版本严格校验。** `s3.py::_strict_positive_version()` 仅接受 `type(value) is int` 且大于零的值，不再用 `int()` 静默转换。五种版本（Scope Policy、Principal Grant、Principal、Auth Policy、Integration 配置）的 SQLite REAL 异常值在 Domain、Web 资源目录和实际 MCP 读取中均 fail-closed。直接解析测试覆盖 Python bool、float、字符串、`None`、零和负数。SQLite INTEGER affinity 会在写入时把可转换的布尔/数字文本规范成整数，存储后无法保留其原始 Python 类型；运行时解析器本身对这些非整数类型仍严格拒绝。

**HF02-03/04：SLA 新鲜取证及精确边界。** 集成用例通过本地 HTTP 服务和真实注册的 in-process MCP Server，先在 SLA 截止前用 `get_order_status`、`get_callback_delivery`、`get_receiver_processing` 取得事实并冻结 WAIT。确定性时钟推进到截止点后，旧诊断在 Evidence 仍处于 TTL 内时失效；旧诊断交接被拒，Queue/Receipt/Outbox 数量保持零。新的受控 Run 再通过同一 HTTP/MCP 路径取得新证据，关联 Task、订单、Event、授权和资源版本，并由 Domain Gate 得到 `CONTACT_RECEIVER_OPERATOR`。owner 明确确认后生成一份不可变回执；重复请求返回同一 Receipt，Queue/Receipt/Outbox 均为 `(1,1,1)`。精确边界测试覆盖 `now < deadline` 为 WAIT、`now == deadline` 与 `now > deadline` 为 CONTACT，并验证历史 WAIT 诊断字节和 digest 未改写。

## 真实运行证据

成功 Trace 位于 `TRACE.jsonl`，由 `tests/test_m4_03_hf_02.py` 的真实测试观察直接写入，不由报告生成器合成。Trace 包含事件/SSE 读取状态、普通事件游标、聊天读取状态、实际 HTTP Request ID/route/status、三种 MCP 工具名、Task/Run/Evidence ID、`observed_versions`、新鲜 CONTACT 诊断、Receipt 回放及 Queue/Receipt/Outbox 计数。MCP 使用本地测试服务与 in-process Server；没有调用外部 Provider 或付费模型。

完整原始输出保存在 `runs/`：冻结 RED、修复过程中的失败、最终定向用例、HF-01/S3/M4-02 回归、S1/S2 安全回归及全量 pytest 日志均保留。结构化命令、退出码和提交引用见 `RESULTS.json`；失败时间线见 `FAILURES.md`。

## 验证结果

| 验证 | 结果 |
|---|---:|
| HF-02 冻结定向测试（含真实 HTTP/MCP SLA 链路） | 24 passed |
| HF-01、M4-03 S3、M4-02 S3 | 50 passed |
| 既有 S1/S2 安全回归 | 104 passed |
| 完整 pytest | 316 passed |

运行环境为项目 `.venv` 的 Python 3.14.0、pytest 9.1.1、MCP 2.3.0、FastAPI 0.137.1；依赖文件未修改。首次误用全局 Python（不含 MCP 依赖）及一次测试客户端身份 Cookie 顺序问题均保留在 `FAILURES.md` 和原始日志中；切换项目环境并修正测试顺序后，新鲜定向、旧回归和全量测试通过。

## 已知边界

本项目仍是本地 SQLite Demo，不代表生产级 IAM、远端审批或多实例 SSE 授权架构。撤权隐藏的是读取响应；历史助手消息、事件和回执仍作为不可变审计数据保存在 Domain。撤权后的 SUPPORT 不能读取这些 S3 专属事实；授权恢复后，历史聊天可按当前权限再次读取，但旧 Evidence/诊断仍遵循已有版本和 SLA 当前性规则。

本轮没有改写历史 Gold、HF-01 原始运行证据、回执或既有 S1/S2 语义，没有新增依赖或付费模型调用。保护了工作区中其他预存未跟踪材料，仅准备暂存本目录交付物及明确列出的源码/测试提交。请主 Agent 独立复核后决定是否关闭 HF-02。
