# AR-02-JOURNEY-P0-HF01 冻结验收计划

## 开工核验

- Repo：`wgqa/OpsPilot`
- Branch / Base HEAD：`codex/ar02-live-01@5a53815b0baea50d7b99afa2b0020e7f96f62517`
- 工作树：clean；本轮只使用 `D:/学习/agent新项目/.worktrees/ar02-live-01`。另一个 `codex/ar02-hf-01@88e00126aaca7af0cbfd454e8f833eae90eae39c` checkout 有未跟踪 `.tmp/`，已保留、未触碰。
- 远端状态：本次 `git ls-remote` 因 GitHub HTTPS 443 连接失败，当前远端 SHA 为 `UNVERIFIED`；本地 upstream 记录指向给定基线。
- `PROJECT_NORTH_STAR.md` Blob：`1f737712c7a36ceb34433ac09c3fbba3c3305542`；本轮已从基线实际读取 §8。
- `AGENTS.md` Blob：`32c45506cceeaa8c76a5c56bf8360ff476b58856`；本轮已从基线实际读取全文。
- `.agents/skills/opspilot-slice-review/SKILL.md` Blob：`d405c8d413d633824b279202cc1503dab4cf0b03`；本轮已实际读取 A/B/C 流程，并按 A 核对基线、合同、门禁和证据。
- 相关实现与基线证据已读取：`opspilot/assistant.py`、`assistant_mcp.py`、`domain/s3.py`、`domain/s3_mcp.py`、`tests/test_ar02_journey_p0.py`、`docs/evidence/ar-02/journey-p0/{PLAN.md,REPORT.md,RESULTS.json,FAILURES.md}`。
- 当前 P0 证据：`5a53815`；定向 38 passed；历史全量 pytest 为 489 passed / 4 failed。四个失败保持历史问题，不在本补证中调整。

## 用户目标与范围

补足两个只读行为证据：同一已绑定订单/Event 对同一处理状态问题，当前 Receiver 可查时报告 QUEUED，当前 Receiver 缺失/不可用时明确报告 UNKNOWN/无法确认；没有 TaskBinding 时即使离线模型替身提出 `get_order_status`，也不能触发订单读取，而可信绑定后相同合法请求能成功读取。

本轮只新增定向确定性测试和证据，不修改业务实现、冻结 Gold、SQLite Schema、授权语义、旧 P0 Trace/失败、费用账本或历史四个 pytest 失败。真实 Provider 请求、浏览器、审批、REPAIR、DELIVER、Handoff 与外部业务写入均要求为零。

## 冻结测试

### HF01-01 — 当前 Receiver Observation 缺失

在一个独立 SQLite 测试数据库中创建已授权的 S3 订单并完成可信绑定。使用同一 Task、同一 Event 和同一用户问题运行两次：第一次通过真实 MCP 查询获得同 Event 的 Delivery 与合法 QUEUED Receiver，答复不得称已完成；随后仅在测试准备中移除当前 Receiver 行，第二次再次查询同一问题。期待第二次 Receiver 工具结果不可用/失败、无成功的当前 Receiver Observation，持久答复明确写 UNKNOWN 或无法确认处理完成。两次工具记录应关联相同 Order/Event；不向冻结 CHECK 约束写入字面 `UNKNOWN`，不改 Schema。

### HF01-02 — 未绑定的显式订单工具提议与合法绑定正例

同一个 Session、同一订单和完全相同的问题文本先在无 TaskBinding 状态提交。确定性模型明确记录提议 `get_order_status`，但运行时向它暴露的工具列表不含该工具；该 Run 不得创建 TaskBinding、订单 MCP 调用、D2 Observation 或订单 HTTP Observation。随后通过现有受信订单绑定 API 确认同一订单，再用相同问题文本执行；该工具必须出现在本次工具列表中，且通过正式 MCP + 认证 loopback HTTP 返回 HTTP 200 和绑定订单 ID。

## 验收判断与停止线

- 新增用例保存原始 RED/GREEN 日志和真实持久 Run/Message/MCP/Observation/HTTP 关联 Trace；任何 RED 保留原样并分类。
- 运行 HF01 定向测试和适用 AR-02 P0/HF-02 回归；不重跑全量 pytest，以免把四个已记录的历史失败误写成本轮结果。
- 不允许通过模型文本、手工 SQL 业务结果、伪造工具调用记录或写入非法 Receiver 状态来满足预期。
- 若现有接口或工具边界实际触发未授权读取，停止并报告安全阻断，不擅自新增 Guard 或业务实现。
- 完成后仅提交 `ACCEPTANCE_CANDIDATE` 并推送现有隔离候选分支；等待主 Agent 复核。

## 六问摘要

1. **用户变化：** 提升缺失 Receiver 状态时的正确说明及工具边界的可核查性；不增加业务能力。
2. **Agent 决策：** 只使用确定性 FixtureModel，观察模型替身的提议；不声称真实 LLM 自主性。
3. **观察驱动：** 同一事件从 QUEUED 变为当前 Receiver 不可查询，合理答复从“排队中”变为“处理状态未知”。
4. **约束双向：** 未绑定请求必须阻止订单查询，绑定后同样合法读取必须成功。
5. **简化：** 复用现有 MCP 工具发现、可信 TaskBinding 与正式 API，不新增权限层或状态机。
6. **证据与停止：** 仅验证本计划两项；Provider、浏览器和业务写入均为零，完成证据后停止。
