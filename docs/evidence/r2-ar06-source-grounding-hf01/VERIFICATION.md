# R2-AR06-SOURCE-GROUNDING-HF01 验证记录

## 基线与范围

- Base：`codex/r2-ar06-observation-contrast-01@07675929642c2cc4057463e74d0926940e0fc1eb`
- 实施分支：`codex/r2-ar06-source-grounding-hf01`，复用 `D:\OpsPilot-LIVE-02-FIX-01-HF02`，新增 Worktree 为 0。
- 开工版本记录：`PROJECT_NORTH_STAR.md` Blob `43dabda468506717c6956e676dfad4304c4f38e6`；`AGENTS.md` Blob `807b928686a4dd2cac7b15b3c354b9943c93c910`；`.agents/skills/opspilot-slice-review/SKILL.md` Blob `d405c8d413d633824b279202cc1503dab4cf0b03`；`TASKS.md` Blob `1f08ee3a8e538d7ece4d2b2841c7c53e25737b7c`。
- 本轮只修改 Assistant 提示、S3 MCP 工具说明和新增 Fixture 测试；没有改 Gold、Rubric、Domain 事实、授权、Schema、Provider 或费用合同。
- 根因检查同时回读 `docs/learning/OPEN_SOURCE_AGENT_REFERENCES.md` 的轻量 Core、工具自主性和最小解耦约束。
- 真实 Provider 请求、Grant 创建、浏览器自动化、外部业务写入：均为 0。

## 两份历史 Trace 的根因证据

| 原始证据 | Run / 最终模型调用 | 最终输入结构 | 实际 Observation |
|---|---|---|---|
| `docs/evidence/r2-ar06-eval-01/runs/LIVE_E07-D_TRACE.json`；SHA256 `aacf15bdb81a24461b612551a23800a12c86f54a275f95185a3d24cdb34ebb59` | `run-c6be60b9-e6b0-4310-8c8f-853c00934d4f` / `assistant-call-a9450502-cda6-42ee-8505-23656f6000b6` | 最终模型输入含 6 条消息，包括完整的 Order、Delivery、Receiver 三个 ToolMessage；`tool_result_projections=[]` | Order 的 `facts.body` 字段为 `authn_event_id, contract_version, order_id, order_version, request_id, status`，没有业务 `event_id`；Delivery 与 Receiver 都为 `event-...0001`，Receiver=`QUEUED`。 |
| `docs/evidence/r2-ar06-eval-01/observation-contrast-live-20261114/OBSERVATION_CONTRAST_PROCESSED_TRACE.json`；SHA256 `fc900d753ea8dd807f558f057cb8b106f609acd6910f3d1604da091858f8085d` | `run-0905ca66-c1cb-41c6-8173-70b24fb7d361` / `assistant-call-b43305ee-3264-420a-8a8a-ebc573a9fcfa` | 最终模型输入同样含完整的三项 ToolMessage；`tool_result_projections=[]` | Order 同样没有业务 `event_id`；Delivery 与 Receiver 都为目标 Event `event-...0101`，Receiver=`PROCESSED`。 |

两次最终回答都正确区分了 `QUEUED` / `PROCESSED` 的业务结果，但错误地把订单、Delivery、Receiver 三个来源概括为共同提供相同 Event ID。

### 根因判断

- **已证实：** 实际工具结果没有把订单 Event ID 混入 Order Observation；`order_http_payload()` 在 `opspilot/domain/s3.py` 只返回订单字段和单独的 `authn_event_id`。最终模型请求也没有因预算裁剪丢掉字段。
- **已证实：** 旧 `SYSTEM` 提醒“同一订单的不同 Event 不能互相证明处理成功”，并描述 Delivery/Receiver 对指定目标 Event 的匹配规则；但没有明确规定“每个事实只能由实际返回该字段的来源支持”、Order 不提供业务 `event_id`，或 `authn_event_id` 不能当作回调 Event ID。旧 MCP 工具说明也没有说明此来源字段边界。
- **最可能的促成因素（推断）：** 模型把同一 TaskBinding/订单下的三类 Observation 过度合并为同一事件链。Trace 能证明错误回答与完整输入，不能证明模型内部具体如何推理。
- `assistant.py` 的 `_tool_message_provenance()` 捕获原始工具文本和来源 ID；`domain.assistant.sources_current()` / `s3_answer_sources_for_display()` 检查来源、作用域和当前性。检查到的链路没有对自由文本回答逐项解析并验证事实主张的通用机制。因此这是缺少字段级来源提示的问题，不是已有来源机制把事实校验过度宣称为通过。

## 最小修复

1. `opspilot/assistant.py` 的系统提示按来源字段约束事实归因：`s3_order` 只能支持实际返回的订单字段；没有业务 `event_id`；认证事件 ID 与回调 Event ID 区分；只有 Delivery 与 Receiver 分别返回相同 ID 才能说这两个来源属于同一 Event；ID 缺失、不同或无法核实时说明关联未知；没有有效本 Run 订单观察时不声称当前订单状态。
2. `opspilot/domain/s3_mcp.py` 将相同边界写入三个工具说明，使模型在选择工具时也能看到工具各自能支持哪些字段。
3. 未修改事实返回、工具选择顺序、来源校验、安全授权、最终回答或输出过滤；没有把预期答案注入模型输入，也没有把 `QUEUED` / `PROCESSED` 编成产品规则。

该修复是提示和工具说明层面的风险降低措施，不保证任意自然语言回答完全没有错误归因。

## RED / GREEN 与回归

使用仓库现成 Python 环境：`D:\学习\agent新项目\.venv\Scripts\python.exe`。所有数据库和 Checkpoint 均由 pytest 在各自隔离 `--basetemp` 创建；S3 回调 Fixture 只向本地 loopback 接收器发请求。

| 阶段 | 命令 / 结果 |
|---|---|
| 环境启动误用（保留记录） | `pytest -q tests/test_r2_ar06_source_grounding_hf01.py` 未进入测试，报 `ModuleNotFoundError: opspilot`；改用仓库解释器的 `python -m pytest`。 |
| RED，修复前 | `& 'D:\学习\agent新项目\.venv\Scripts\python.exe' -m pytest -q --basetemp='.runtime\source-grounding-red-01' tests/test_r2_ar06_source_grounding_hf01.py`：`4 failed, 1 passed`。失败项是缺少来源字段边界、无当前 Observation 时的约束；不同 Event 的工具输入隔离用例通过。 |
| GREEN，定向 Fixture | 同一测试文件，独立 basetemp：`5 passed`。覆盖 Order 不含业务 Event ID、Delivery/Receiver 同 Event 的 QUEUED 与 PROCESSED、不同 Event ID、无 TaskBinding/无当前业务 Observation、提示与 MCP Tool Schema。 |
| R2 J2 状态回归 | `tests/test_r2_ar03_integrated_journey_01.py -k j2_same_session_binding`：`2 passed, 4 deselected`，同一 Event 的 QUEUED/PROCESSED 结论路径正常。 |
| AR06 Runner 回归 | `tests/test_r2_ar06_auto_live_eval.py -k 'e07_uses_trusted_order_api or observation_contrast_executes_fixture or observation_contrast_does_not_accept_decoy'`：`3 passed, 15 deselected`。 |
| S3 当前来源回归 | `tests/test_m4_ttl_fix_01.py`：`1 passed`。 |

最终共 11 个不同的定向测试用例通过（新增 5 + J2 2 + AR06 3 + S3 TTL/MCP 1）。全仓 pytest 未运行。中间一次 GREEN 检查因测试断言的短语与提示实际措辞不一致而为 `4 passed, 1 failed`；只修正测试断言后，最终 GREEN 为 `5 passed`，产品实现未因此扩展。

## 保留限制与下一步验证建议

- 本轮离线 Fixture 证明了系统把真实来源字段和各来源说明送入模型，且当前/非当前观察结构正确；它不能证明真实 DeepSeek 一定遵循提示。
- 若需真实模型复验，建议另开探索性对照，不覆盖原始 E07 / Processed Trace：新建两个隔离 Runtime，一个使用同 Event `QUEUED`，另一个使用同 Event `PROCESSED`；每个首次 Run 最多 1 次，单例 Grant 上限 USD 0.05，合计最多 USD 0.10，不重试，保留输入、完整模型请求、原始回答和 MCP Trace。此为建议，不是本轮授权。
- 若要求对任意自然语言的字段级归因作程序保证，需要单独授权设计结构化事实主张及对应校验；本任务没有引入答案解析器、硬编码回答或输出重写。
