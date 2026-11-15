# R2-AR04-REMAINING-LIVE-01 — 准入复核

- 实施状态：`ACCEPTANCE_CANDIDATE`
- 准入结论：`HOLD`，不得据此发起真实 Provider 请求。
- Repository / Branch：`wgqa/OpsPilot` / `codex/r2-ar04-remaining-live-gate-01`
- Previous candidate Base / reviewed HEAD：`fa4cd8a7ea6dd36babccbbfc5fcdb7a179729fd3` / `9412c05bd095d3f4abba58e7a23a076633654e6b`
- 远端只读核对：GitHub branch ref 的 HEAD 为 `9412c05bd095d3f4abba58e7a23a076633654e6b`，父提交为 `fa4cd8a7ea6dd36babccbbfc5fcdb7a179729fd3`。
- 本轮 Provider 请求：0；费用：USD 0；外部 MCP：0；生产数据库写入：0。

## 核验基线

本轮复用上一候选的隔离 Worktree 和历史 Mock 证据。治理文件、Skill 与适用合同此前已从候选 HEAD 实际读取，并由 Runner 冻结校验再次核对：

| 文件 | Blob |
|---|---|
| `PROJECT_NORTH_STAR.md` | `43dabda468506717c6956e676dfad4304c4f38e6` |
| `AGENTS.md` | `807b928686a4dd2cac7b15b3c354b9943c93c910` |
| `.agents/skills/opspilot-slice-review/SKILL.md` | `d405c8d413d633824b279202cc1503dab4cf0b03` |
| `docs/baseline/v1.0-implementation-baseline.md` | `30e18d7ddbade7cdf7712d035d6fd8488bcb9676` |
| `opspilot/domain/chat.py` | `f78ff94586af56b94b9585c5e7f8abeb5b006ad6` |
| `opspilot/assistant.py` | `288559c6e9b77549939501f4cedb1a8097a79918` |

Candidate Base-to-HEAD changes are confined to the prior `docs/evidence/r2-ar04-remaining-live-gate-01/` evidence. No production code, frozen questions, Gold, historical trace, or accepted Mock result changed in this admission review. The new artifacts in this folder are additional evidence only.

## 官方模型与价格

官方 DeepSeek 文档在本轮重新读取，别名 `deepseek-flash` 仍记录为 V4.1-Flash-1017。峰值费率：缓存命中输入 $0.006/M、未命中输入 $0.30/M、输出 $1.20/M；预算按全部缓存未命中计算。完整带日期快照见 [PRICE_SNAPSHOT.json](PRICE_SNAPSHOT.json)。本轮输入与来源证据聚合 SHA-256：`f277985ce5e73e4fe4b64ea8877067398f795731ad0100c6d8c5b74f5c2b8468`。这只是官方文档证据；没有调用认证模型列表或 Provider API，因此不是 Provider 实际版本响应。

当前主仓库 `.env` 安全加载结果仅记录配置存在性与 URL 非敏感组成：API Key 存在但值未记录；模型为 `deepseek-flash`；URL 为 `https://api.deepseek.com/v1`。`.env` 未提供模型配置版本、价格版本及 Assistant Service Identity；离线 Runner 在隔离配置中明确补入任务专用非敏感值。凭据有效性没有经过联网验证。

## 预算重算

| 请求类型 | 单请求保守预留 | 槽位 | 合计 |
|---|---:|---:|---:|
| 摘要：12,000 输入 + 1,024 输出 | $0.004829 | 4 | $0.019316 |
| 回答：12,000 输入 + 512 输出 | $0.004215 | 2 | $0.008430 |
| 实际用途请求合计 | — | 6 | $0.027746 |
| 两个隔离 Grant 的最坏共享预留 | — | — | $0.028974 |
| 硬上限 | — | — | $0.060000 |

峰值价格和微美元向上取整下低于硬上限，剩余 $0.031026。没有因预算缩小 Case 或 Token 上限。

## 阻断项

### 1. 配置 URL 路径与 Runner allowlist 不匹配

用主目录 `.env` 的 URL 和 OpenAI SDK，经 `httpx.MockTransport` 实际构造请求，路径为 `/v1/chat/completions`。复用 Runner 的底层校验器只接受 `/chat/completions`，返回 `PROVIDER_ENDPOINT_OR_METHOD_MISMATCH`。校验发生在全局账本 `start_send` 和底层 HTTP transport 调用之前；因此当前路径会安全停发，但真实请求无法通过该 Runner。可重复脚本：`verify_endpoint_path_mock.py`。

建议后续在评测 Runner 中把允许路径与冻结的 base URL 明确绑定，或以受控方式规范化为官方根 URL；保留 HTTPS、域名、端口、方法、query/fragment 的严格校验。不得在本轮顺手改写已验收 Runner。

### 2. `tool_choice=none` 下的意外工具调用仍可到达 Assistant

官方 API 文档将 `tool_choice=none` 定义为不调用工具，当前 Mock 请求也确实设置该值。但防御路径尚不可靠：`run_abc_eval.py` 先用 `finish_reason != "stop"` 匹配标准的 `finish_reason="tool_calls"`，因此先记录 `PROVIDER_OUTPUT_NOT_COMPLETE`；后面的 `UNEXPECTED_TOOL_CALL` 特殊分支不会执行，包含 `tool_calls` 的 Provider 响应仍会返回给 Assistant。`run_assistant` 运行之后才检查 `tool_observation`，不足以防止工具已被调度。冻结 Mock Answer 请求实际包含 8 个工具 Schema，其中有 7 个本地 stdio MCP 工具和 `memory_remember` 本地工具；probe 本身没有进入完整 Agent graph 或调用工具，因此没有 MCP/Memory 副作用；它证明响应可离开 transport 到达 Assistant model client，完整意外工具调用注入尚未运行。

`probe_unexpected_toolcall_mock.py` 以 MockTransport 重现：请求 `tool_choice=none`，模拟响应 `finish_reason=tool_calls`，返回给 Assistant 的响应仍包含工具调用。Probe 没有执行任何 MCP；它证明异常防护当前不能保证未来真实异常响应绝不触发 MCP。建议后续在 Runner transport 收到响应后、返回 Assistant 前识别 `finish_reason=tool_calls` 或非空 `message.tool_calls`，持久记录原始响应并停发，且不把工具调用对象交给 Assistant；再用完整 Assistant/Domain Mock 验证零工具派发。

### 3. Review Task 与 Runner 授权 Task 不一致

本卡任务号是 `R2-AR04-REMAINING-LIVE-01`，但被复用 Runner 的冻结常量仍为 `R2-AR04-REMAINING-LIVE-GATE-01`。当前授权 Proposal 按本卡任务号填写，经 `validate_authorization_manifest` 在授权发送标志校验前就以 `NEW_TASK_SPECIFIC_LIVE_AUTHORIZATION_REQUIRED` 拒绝。Proposal 本来就不可执行；该结果也暴露出未来授权的 Task ID 需要主 Agent/用户明确对齐，Runner 不能静默把两个任务 ID 视为同一个。

## 已通过与仍未证明

- 新鲜零费用 Runtime Grant/Runner preflight：原 Runner 报 `READY_FOR_NEW_LIVE_AUTHORIZATION`；它只证明隔离 Mock 配置、Grant 绑定和预算可构造，不覆盖上述两个实发边界。
- 已验收两 Case Mock 回归：11/11 测试通过；6 个 Mock 请求、两组 29 条历史、来源映射、预算、撤权和 UNKNOWN 门禁均按既有结果验证。既有 Mock 证据未覆盖或改写。
- 固定 Q02-B `finish_reason=length` Trace 回放：1/1 通过，摘要持久化与回答仍被阻断；测试生成的追加行单独存档，冻结 Trace 已逐字节还原。
- 主目录 `.env` 的 `/v1` 路径执行 Mock URL 检查，复现 Runner 路径拒绝；Provider 请求仍为 0。
- 意外 `tool_calls` Mock 响应探针复现工具调用进入 Assistant 响应对象；没有实际工具/MCP 执行。
- 初始摘要回复 ID、请求/响应 Digest 与来源 Trace 通过 `SOURCE_MANIFEST` 与 Runner 冻结校验；Gold 不进入请求由既有 transport 内容检查及 Mock 测试保证。
- 最终回答内容在正常文本响应下由 `response_payload.choices[0].message.content` 原样记录，未由 Runner 补写；原始 Provider 响应也记录于 trace。未来真实回答尚未发生，L3 仍未评测。
- API Key 有效性、Provider 实际解析版本、账户扣费金额未验证；本轮明确不进行这些需要真实调用的检查。意外 `tool_calls` 尚未经完整 Assistant/Domain 注入测试；在 Runner 传输层先行阻断前，不应以 `tool_choice=none` 的正常模型行为替代安全保证。

## 测试与复核命令

详见 [TEST_RUN.txt](TEST_RUN.txt)。全部测试与探针均离线；探针退出码 0 表示成功复现并报告预期的阻断/缺陷，不表示 Live Gate 通过。

## Skill 六问与双向验收

1. **用户可见行为：** 本任务只判断历史回忆实验是否可安全执行，不声称改善 Agent 业务体验或 L3 记忆质量。
2. **Agent 决策空间：** 历史回忆轨道固定 `tool_choice=none`；只读调查能力在本任务不运行。意外工具响应路径仍有可调度性风险。
3. **观察与下一步：** 实际 configured URL 已通过 Mock 观察到 `/v1/chat/completions`；Runner 目前在出站前拒绝。需先修复兼容 gate，再重新观察。
4. **硬边界：** 六请求预算和成本计算有效，但当前 endpoint path 阻断 live；工具异常防护未满足零外部 MCP 条件。
5. **复用与删除：** 复用 Assistant/Domain、Runtime Grant、共享账本、来源校验与已通过 Mock。没有新增 Memory、平台或第二套授权系统。
6. **证据与停止线：** 证据足以识别两个确定阻断；没有真实 Provider 调用或语义结果。停止在准入 HOLD，不签发有效授权。

实施方向：已验证静态/API 配置与完整 Mock 的既有能力；本轮没有接入业务外部工具；效果没有真实模型 L2/L3 证明。验收条件应覆盖 URL route 和异常工具响应完整调用链。

**实施方验收：** 候选证据完整、零 Provider/零费用/零 MCP；但新付费复测准入未通过。**Disposition: HOLD**。只在独立修复并重跑离线 gate、且获得新的付费授权后，才能进入 Live。
