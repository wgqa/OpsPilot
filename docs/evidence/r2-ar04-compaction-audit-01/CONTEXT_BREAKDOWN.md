# Context Breakdown：Token、来源与实际输入

**范围：** 固定 Base `d8e30bcb82557e370f8fec664803a952b8d06e14`；隔离 Domain/Checkpoint；确定性 Fixture Model。Token 均为 `tiktoken:cl100k_base:0.14.0` 应用估算，不是 Provider 计费量。

## 计数口径

- `B` 是配置输入预算；`R` 是助手路径对工具 Schema、系统提示、WORK_CONTEXT 和 1,024 Token 工具结果预留的合计；`E=max(0,B-R)` 是压缩选择预算。`RESULTS.json` 中 C06 在首批材料报错前没有返回预算 Manifest，因此实际 `B/E/R` 留空，配置上限仍记录为 12,000。
- `F` 是 Domain Chat 在优先级分配前的完整候选估算。最终模型请求的 `prompt_estimated_tokens`、Schema 估算和 8 Token 序列化/消息开销组成 `estimated_after`。这两个估算口径不同，不把 `estimated_after-F` 当成压缩净节省。
- Manifest 的 `TRUSTED_CONTROL` 数值与最终请求的完整 `prompt_estimated_tokens` 相同；它是实际模型消息集合的聚合估算。`HISTORICAL_SUMMARY` 是该聚合中的子项，不能再相加。`CURRENT_TASK_STATE`、`CURRENT_FACTS`、`RECENT_INTERACTION` 等是来源分类/分配记录；消息内容已由聚合 prompt 计数，逐类估算为 0 不代表那些最近消息没有发送。
- `excluded_blocks` 记录整块排除；`excluded_sources` 记录块内按 Token 预算排除的来源消息。`RECENT_WINDOW` 在生成候选前裁去较旧消息，因而未必产生逐源 `excluded_sources` 记录。

## 每例预算与模型输入

| Case | Strategy | W | B | R | E | F | Trigger | Prompt + schema + overhead = after | Summary calls | Raw/selected history Token |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| C01 | HYBRID | 16384 | 7000 | 3813 | 3187 | 385 | 否 | 1585 + 1214 + 8 = 2807 | 0 | 64 / 18 |
| C02 | HYBRID | 16384 | 12000 | 5216 | 6784 | 1712 | 否 | 4567 + 1214 + 8 = 5789 | 0 | 1419 / 1373 |
| C03 | HYBRID | 16384 | 6919 | 5208 | 1711 | 1712 | 是 | 4068 + 1214 + 8 = 5290 | 1 | 1419 / 546 |
| C04 | ROLLING_SUMMARY | 16384 | 12000 | 4175 | 7825 | 1712 | 是 | 4051 + 1214 + 8 = 5273 | 1 | 1419 / 546 |
| C05 | RECENT_WINDOW | 16384 | 12000 | 5208 | 6792 | 903 | 否 | 3606 + 1214 + 8 = 4828 | 0 | 1421 / 548 |
| C06_USER_OVERSIZE | ROLLING_SUMMARY | 16384 | 未观测 | 未观测 | 未观测 | 7572 | 是 | 未发送 | 0 | 7233 / 未观测 |
| C06_ASSISTANT_EXCERPT | ROLLING_SUMMARY | 16384 | 12000 | 4185 | 7815 | 8113 | 是 | 4036 + 1214 + 8 = 5258 | 2 | 7820 / 556 |
| C07 | ROLLING_SUMMARY | 16384 | 12000 | 4190 | 7810 | 8857 | 是 | 6299 + 1214 + 8 = 7521 | 2 | 8568 / 2727 |
| C08_BASE | HYBRID | 16384 | 12000 | 5203 | 6797 | 5626 | 否 | 8468 + 1214 + 8 = 9690 | 0 | 5333 / 5287 |
| C08 | HYBRID | 16384 | 10839 | 6709 | 4130 | 5626 | 是 | 5541 + 2709 + 8 = 8258 | 1 | 5333 / 1949 |
| WP3_INFORMATION_RETENTION | ROLLING_SUMMARY | 16384 | 12000 | 4177 | 7823 | 35388 | 是 | 7221 + 1214 + 8 = 8443 | 2 | 35095 / 4450 |

`Raw history Token` 是测试结束时保存的消息快照估算，包含模型回答；`selected history Token` 只计入本次最终模型调用选中的原始消息。序号以 `RESULTS.json` 为准。

## Context Manifest 分块明细

### C01

证据：[`case_traces/C01.json`](case_traces/C01.json)。

| Context Block | Token | 状态 | 来源/解释 |
|---|---:|---|---|
| `TRUSTED_CONTROL` | 1585 | SELECTED | 最终模型请求全部消息的聚合 prompt 估算；其中已含摘要和历史消息。 |
| `CURRENT_TASK_STATE` | 0 | SELECTED | 无当前 Task/MCP/Memory 来源；详见该块状态。 |
| `CURRENT_FACTS` | 0 | SELECTED | 无当前 Task/MCP/Memory 来源；详见该块状态。 |
| `RECENT_INTERACTION` | 0 | SELECTED | 原始消息序号 1；消息 Token 已计入聚合 prompt，本分类的独立估算为 0。 |
| `HISTORICAL_SUMMARY` | 0 | NOT_APPLICABLE | 无当前摘要 |
| `EXTERNAL_GUIDANCE` | 0 | EMPTY | 无当前 Task/MCP/Memory 来源；详见该块状态。 |
| `PRIOR_READONLY_FOLLOWUP` | 0 | EMPTY | 无当前 Task/MCP/Memory 来源；详见该块状态。 |
| `TOOL_SCHEMA` | 1214 | SELECTED | 当前 Canonical tools/list Schema (8 tools: propose_controlled_auth_investigation, read_session_professional_outcomes, search_project_knowledge, list_scoped_protocol_documents, compare_scoped_protocols, read_scoped_protocol_excerpt, load_protocol_upgrade_skill, memory_remember)。 |

预算：`B=7000`，`R=3813`，`E=3187`；最终输入估算：`prompt=1585 + schema=1214 + 8 = 2807`。
本次选中的原始消息序号：`1`。
最终 Manifest 没有整块或逐源预算排除记录；策略窗口外历史见保留序号与策略说明。

### C02

证据：[`case_traces/C02.json`](case_traces/C02.json)。

| Context Block | Token | 状态 | 来源/解释 |
|---|---:|---|---|
| `TRUSTED_CONTROL` | 4567 | SELECTED | 最终模型请求全部消息的聚合 prompt 估算；其中已含摘要和历史消息。 |
| `CURRENT_TASK_STATE` | 0 | SELECTED | 无当前 Task/MCP/Memory 来源；详见该块状态。 |
| `CURRENT_FACTS` | 0 | SELECTED | 无当前 Task/MCP/Memory 来源；详见该块状态。 |
| `RECENT_INTERACTION` | 0 | SELECTED | 原始消息序号 1…29（29 条）；消息 Token 已计入聚合 prompt，本分类的独立估算为 0。 |
| `HISTORICAL_SUMMARY` | 0 | NOT_APPLICABLE | 无当前摘要 |
| `EXTERNAL_GUIDANCE` | 0 | EMPTY | 无当前 Task/MCP/Memory 来源；详见该块状态。 |
| `PRIOR_READONLY_FOLLOWUP` | 0 | EMPTY | 无当前 Task/MCP/Memory 来源；详见该块状态。 |
| `TOOL_SCHEMA` | 1214 | SELECTED | 当前 Canonical tools/list Schema (8 tools: propose_controlled_auth_investigation, read_session_professional_outcomes, search_project_knowledge, list_scoped_protocol_documents, compare_scoped_protocols, read_scoped_protocol_excerpt, load_protocol_upgrade_skill, memory_remember)。 |

预算：`B=12000`，`R=5216`，`E=6784`；最终输入估算：`prompt=4567 + schema=1214 + 8 = 5789`。
本次选中的原始消息序号：`1…29（29 条）`。
最终 Manifest 没有整块或逐源预算排除记录；策略窗口外历史见保留序号与策略说明。

### C03

证据：[`case_traces/C03.json`](case_traces/C03.json)。

| Context Block | Token | 状态 | 来源/解释 |
|---|---:|---|---|
| `TRUSTED_CONTROL` | 4068 | SELECTED | 最终模型请求全部消息的聚合 prompt 估算；其中已含摘要和历史消息。 |
| `CURRENT_TASK_STATE` | 0 | SELECTED | 无当前 Task/MCP/Memory 来源；详见该块状态。 |
| `CURRENT_FACTS` | 0 | SELECTED | 无当前 Task/MCP/Memory 来源；详见该块状态。 |
| `RECENT_INTERACTION` | 0 | SELECTED | 原始消息序号 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29；消息 Token 已计入聚合 prompt，本分类的独立估算为 0。 |
| `HISTORICAL_SUMMARY` | 347 | SELECTED | summary:context-summary-bcc6a3ea-e2c9-4a3d-a339-50864372bccf |
| `EXTERNAL_GUIDANCE` | 0 | EMPTY | 无当前 Task/MCP/Memory 来源；详见该块状态。 |
| `PRIOR_READONLY_FOLLOWUP` | 0 | EMPTY | 无当前 Task/MCP/Memory 来源；详见该块状态。 |
| `TOOL_SCHEMA` | 1214 | SELECTED | 当前 Canonical tools/list Schema (8 tools: propose_controlled_auth_investigation, read_session_professional_outcomes, search_project_knowledge, list_scoped_protocol_documents, compare_scoped_protocols, read_scoped_protocol_excerpt, load_protocol_upgrade_skill, memory_remember)。 |

预算：`B=6919`，`R=5208`，`E=1711`；最终输入估算：`prompt=4068 + schema=1214 + 8 = 5290`。
本次选中的原始消息序号：`18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29`。
最终 Manifest 没有整块或逐源预算排除记录；策略窗口外历史见保留序号与策略说明。

压缩批次：
- 覆盖 `[1, 17]`；输入估算 1177 Token；来源序号 `1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17`；父摘要 `无`；结果 `SUCCEEDED`。

### C04

证据：[`case_traces/C04.json`](case_traces/C04.json)。

| Context Block | Token | 状态 | 来源/解释 |
|---|---:|---|---|
| `TRUSTED_CONTROL` | 4051 | SELECTED | 最终模型请求全部消息的聚合 prompt 估算；其中已含摘要和历史消息。 |
| `CURRENT_TASK_STATE` | 0 | SELECTED | 无当前 Task/MCP/Memory 来源；详见该块状态。 |
| `CURRENT_FACTS` | 0 | SELECTED | 无当前 Task/MCP/Memory 来源；详见该块状态。 |
| `RECENT_INTERACTION` | 0 | SELECTED | 原始消息序号 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29；消息 Token 已计入聚合 prompt，本分类的独立估算为 0。 |
| `HISTORICAL_SUMMARY` | 348 | SELECTED | summary:context-summary-b0585bbe-23e6-4e47-aca7-f60cb232b62a |
| `EXTERNAL_GUIDANCE` | 0 | EMPTY | 无当前 Task/MCP/Memory 来源；详见该块状态。 |
| `PRIOR_READONLY_FOLLOWUP` | 0 | EMPTY | 无当前 Task/MCP/Memory 来源；详见该块状态。 |
| `TOOL_SCHEMA` | 1214 | SELECTED | 当前 Canonical tools/list Schema (8 tools: propose_controlled_auth_investigation, read_session_professional_outcomes, search_project_knowledge, list_scoped_protocol_documents, compare_scoped_protocols, read_scoped_protocol_excerpt, load_protocol_upgrade_skill, memory_remember)。 |

预算：`B=12000`，`R=4175`，`E=7825`；最终输入估算：`prompt=4051 + schema=1214 + 8 = 5273`。
本次选中的原始消息序号：`18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29`。
最终 Manifest 没有整块或逐源预算排除记录；策略窗口外历史见保留序号与策略说明。

压缩批次：
- 覆盖 `[1, 17]`；输入估算 1177 Token；来源序号 `1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17`；父摘要 `无`；结果 `SUCCEEDED`。

### C05

证据：[`case_traces/C05.json`](case_traces/C05.json)。

| Context Block | Token | 状态 | 来源/解释 |
|---|---:|---|---|
| `TRUSTED_CONTROL` | 3606 | SELECTED | 最终模型请求全部消息的聚合 prompt 估算；其中已含摘要和历史消息。 |
| `CURRENT_TASK_STATE` | 0 | SELECTED | 无当前 Task/MCP/Memory 来源；详见该块状态。 |
| `CURRENT_FACTS` | 0 | SELECTED | 无当前 Task/MCP/Memory 来源；详见该块状态。 |
| `RECENT_INTERACTION` | 0 | SELECTED | 原始消息序号 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29；消息 Token 已计入聚合 prompt，本分类的独立估算为 0。 |
| `HISTORICAL_SUMMARY` | 0 | NOT_APPLICABLE | 无当前摘要 |
| `EXTERNAL_GUIDANCE` | 0 | EMPTY | 无当前 Task/MCP/Memory 来源；详见该块状态。 |
| `PRIOR_READONLY_FOLLOWUP` | 0 | EMPTY | 无当前 Task/MCP/Memory 来源；详见该块状态。 |
| `TOOL_SCHEMA` | 1214 | SELECTED | 当前 Canonical tools/list Schema (8 tools: propose_controlled_auth_investigation, read_session_professional_outcomes, search_project_knowledge, list_scoped_protocol_documents, compare_scoped_protocols, read_scoped_protocol_excerpt, load_protocol_upgrade_skill, memory_remember)。 |

预算：`B=12000`，`R=5208`，`E=6792`；最终输入估算：`prompt=3606 + schema=1214 + 8 = 4828`。
本次选中的原始消息序号：`18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29`。
最终 Manifest 没有整块或逐源预算排除记录；策略窗口外历史见保留序号与策略说明。

### C06_USER_OVERSIZE

证据：[`case_traces/C06_USER_OVERSIZE.json`](case_traces/C06_USER_OVERSIZE.json)。

最终模型调用未发生。内部异常 `ContextBudgetExceeded: SUMMARY_SOURCE_EXCEEDS_COMPRESSION_BUDGET (6176 > 6000 tokens)`；触发为 `是`，判定记录 `SOURCE_DERIVED_TRIGGER_TRUE_THEN_FIRST_BATCH_BUDGET_ERROR`。本例没有可用的最终 Context Manifest。

### C06_ASSISTANT_EXCERPT

证据：[`case_traces/C06_ASSISTANT_EXCERPT.json`](case_traces/C06_ASSISTANT_EXCERPT.json)。

| Context Block | Token | 状态 | 来源/解释 |
|---|---:|---|---|
| `TRUSTED_CONTROL` | 4036 | SELECTED | 最终模型请求全部消息的聚合 prompt 估算；其中已含摘要和历史消息。 |
| `CURRENT_TASK_STATE` | 0 | SELECTED | 无当前 Task/MCP/Memory 来源；详见该块状态。 |
| `CURRENT_FACTS` | 0 | SELECTED | 无当前 Task/MCP/Memory 来源；详见该块状态。 |
| `RECENT_INTERACTION` | 0 | SELECTED | 原始消息序号 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29；消息 Token 已计入聚合 prompt，本分类的独立估算为 0。 |
| `HISTORICAL_SUMMARY` | 317 | SELECTED | summary:context-summary-e1834e1e-8297-449b-8ec8-be811a56683e |
| `EXTERNAL_GUIDANCE` | 0 | EMPTY | 无当前 Task/MCP/Memory 来源；详见该块状态。 |
| `PRIOR_READONLY_FOLLOWUP` | 0 | EMPTY | 无当前 Task/MCP/Memory 来源；详见该块状态。 |
| `TOOL_SCHEMA` | 1214 | SELECTED | 当前 Canonical tools/list Schema (8 tools: propose_controlled_auth_investigation, read_session_professional_outcomes, search_project_knowledge, list_scoped_protocol_documents, compare_scoped_protocols, read_scoped_protocol_excerpt, load_protocol_upgrade_skill, memory_remember)。 |

预算：`B=12000`，`R=4185`，`E=7815`；最终输入估算：`prompt=4036 + schema=1214 + 8 = 5258`。
本次选中的原始消息序号：`18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29`。
最终 Manifest 没有整块或逐源预算排除记录；策略窗口外历史见保留序号与策略说明。

压缩批次：
- 覆盖 `[1, 2]`；输入估算 6000 Token；来源序号 `1, 2`；父摘要 `无`；结果 `SUCCEEDED`。
- 覆盖 `[1, 17]`；输入估算 1122 Token；来源序号 `1, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17`；父摘要 `context-summary-c5824485-0605-4f49-a0df-9ca716fd85ce`；结果 `SUCCEEDED`。

### C07

证据：[`case_traces/C07.json`](case_traces/C07.json)。

| Context Block | Token | 状态 | 来源/解释 |
|---|---:|---|---|
| `TRUSTED_CONTROL` | 6299 | SELECTED | 最终模型请求全部消息的聚合 prompt 估算；其中已含摘要和历史消息。 |
| `CURRENT_TASK_STATE` | 0 | SELECTED | 无当前 Task/MCP/Memory 来源；详见该块状态。 |
| `CURRENT_FACTS` | 0 | SELECTED | 无当前 Task/MCP/Memory 来源；详见该块状态。 |
| `RECENT_INTERACTION` | 0 | SELECTED | 原始消息序号 22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32, 33；消息 Token 已计入聚合 prompt，本分类的独立估算为 0。 |
| `HISTORICAL_SUMMARY` | 400 | SELECTED | summary:context-summary-608e9fef-16f4-4aad-8aff-102a192538e6 |
| `EXTERNAL_GUIDANCE` | 0 | EMPTY | 无当前 Task/MCP/Memory 来源；详见该块状态。 |
| `PRIOR_READONLY_FOLLOWUP` | 0 | EMPTY | 无当前 Task/MCP/Memory 来源；详见该块状态。 |
| `TOOL_SCHEMA` | 1214 | SELECTED | 当前 Canonical tools/list Schema (8 tools: propose_controlled_auth_investigation, read_session_professional_outcomes, search_project_knowledge, list_scoped_protocol_documents, compare_scoped_protocols, read_scoped_protocol_excerpt, load_protocol_upgrade_skill, memory_remember)。 |

预算：`B=12000`，`R=4190`，`E=7810`；最终输入估算：`prompt=6299 + schema=1214 + 8 = 7521`。
本次选中的原始消息序号：`22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32, 33`。
最终 Manifest 没有整块或逐源预算排除记录；策略窗口外历史见保留序号与策略说明。

压缩批次：
- 覆盖 `[1, 20]`；输入估算 5674 Token；来源序号 `1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20`；父摘要 `无`；结果 `SUCCEEDED`。
- 覆盖 `[1, 21]`；输入估算 1032 Token；来源序号 `1, 15, 17, 19, 21`；父摘要 `context-summary-0f86feaa-98ba-4a4e-ab5f-b5f3ec41471a`；结果 `SUCCEEDED`。

### C08_BASE

证据：[`case_traces/C08_BASE.json`](case_traces/C08_BASE.json)。

| Context Block | Token | 状态 | 来源/解释 |
|---|---:|---|---|
| `TRUSTED_CONTROL` | 8468 | SELECTED | 最终模型请求全部消息的聚合 prompt 估算；其中已含摘要和历史消息。 |
| `CURRENT_TASK_STATE` | 0 | SELECTED | 无当前 Task/MCP/Memory 来源；详见该块状态。 |
| `CURRENT_FACTS` | 0 | SELECTED | 无当前 Task/MCP/Memory 来源；详见该块状态。 |
| `RECENT_INTERACTION` | 0 | SELECTED | 原始消息序号 1…29（29 条）；消息 Token 已计入聚合 prompt，本分类的独立估算为 0。 |
| `HISTORICAL_SUMMARY` | 0 | NOT_APPLICABLE | 无当前摘要 |
| `EXTERNAL_GUIDANCE` | 0 | EMPTY | 无当前 Task/MCP/Memory 来源；详见该块状态。 |
| `PRIOR_READONLY_FOLLOWUP` | 0 | EMPTY | 无当前 Task/MCP/Memory 来源；详见该块状态。 |
| `TOOL_SCHEMA` | 1214 | SELECTED | 当前 Canonical tools/list Schema (8 tools: propose_controlled_auth_investigation, read_session_professional_outcomes, search_project_knowledge, list_scoped_protocol_documents, compare_scoped_protocols, read_scoped_protocol_excerpt, load_protocol_upgrade_skill, memory_remember)。 |

预算：`B=12000`，`R=5203`，`E=6797`；最终输入估算：`prompt=8468 + schema=1214 + 8 = 9690`。
本次选中的原始消息序号：`1…29（29 条）`。
最终 Manifest 没有整块或逐源预算排除记录；策略窗口外历史见保留序号与策略说明。

### C08

证据：[`case_traces/C08.json`](case_traces/C08.json)。

| Context Block | Token | 状态 | 来源/解释 |
|---|---:|---|---|
| `TRUSTED_CONTROL` | 5541 | SELECTED | 最终模型请求全部消息的聚合 prompt 估算；其中已含摘要和历史消息。 |
| `CURRENT_TASK_STATE` | 0 | SELECTED | 无当前 Task/MCP/Memory 来源；详见该块状态。 |
| `CURRENT_FACTS` | 0 | SELECTED | 无当前 Task/MCP/Memory 来源；详见该块状态。 |
| `RECENT_INTERACTION` | 0 | SELECTED | 原始消息序号 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29；消息 Token 已计入聚合 prompt，本分类的独立估算为 0。 |
| `HISTORICAL_SUMMARY` | 404 | SELECTED | summary:context-summary-3ef840ec-f9a8-49c2-b8e2-a111eaff9a89 |
| `EXTERNAL_GUIDANCE` | 0 | EMPTY | 无当前 Task/MCP/Memory 来源；详见该块状态。 |
| `PRIOR_READONLY_FOLLOWUP` | 0 | EMPTY | 无当前 Task/MCP/Memory 来源；详见该块状态。 |
| `TOOL_SCHEMA` | 2709 | SELECTED | 当前 Canonical tools/list Schema (9 tools: propose_controlled_auth_investigation, read_session_professional_outcomes, search_project_knowledge, list_scoped_protocol_documents, compare_scoped_protocols, read_scoped_protocol_excerpt, load_protocol_upgrade_skill, audit_schema_padding_readonly, memory_remember)。另加未调用合成 Schema `audit_schema_padding_readonly`；描述增加 1452 Token。 |

预算：`B=10839`，`R=6709`，`E=4130`；最终输入估算：`prompt=5541 + schema=2709 + 8 = 8258`。
本次选中的原始消息序号：`18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29`。
最终 Manifest 没有整块或逐源预算排除记录；策略窗口外历史见保留序号与策略说明。

压缩批次：
- 覆盖 `[1, 17]`；输入估算 3688 Token；来源序号 `1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17`；父摘要 `无`；结果 `SUCCEEDED`。

### WP3_INFORMATION_RETENTION

证据：[`case_traces/WP3_INFORMATION_RETENTION.json`](case_traces/WP3_INFORMATION_RETENTION.json)。

| Context Block | Token | 状态 | 来源/解释 |
|---|---:|---|---|
| `TRUSTED_CONTROL` | 7221 | SELECTED | 最终模型请求全部消息的聚合 prompt 估算；其中已含摘要和历史消息。 |
| `CURRENT_TASK_STATE` | 0 | SELECTED | 无当前 Task/MCP/Memory 来源；详见该块状态。 |
| `CURRENT_FACTS` | 0 | SELECTED | 无当前 Task/MCP/Memory 来源；详见该块状态。 |
| `RECENT_INTERACTION` | 0 | SELECTED | 原始消息序号 19, 21, 23, 25, 27, 28, 29；消息 Token 已计入聚合 prompt，本分类的独立估算为 0。 |
| `HISTORICAL_SUMMARY` | 525 | SELECTED | summary:context-summary-09e9cba4-71d0-42cf-8f36-0c359f8f2f4e |
| `EXTERNAL_GUIDANCE` | 0 | EMPTY | 无当前 Task/MCP/Memory 来源；详见该块状态。 |
| `PRIOR_READONLY_FOLLOWUP` | 0 | EMPTY | 无当前 Task/MCP/Memory 来源；详见该块状态。 |
| `TOOL_SCHEMA` | 1214 | SELECTED | 当前 Canonical tools/list Schema (8 tools: propose_controlled_auth_investigation, read_session_professional_outcomes, search_project_knowledge, list_scoped_protocol_documents, compare_scoped_protocols, read_scoped_protocol_excerpt, load_protocol_upgrade_skill, memory_remember)。 |

预算：`B=12000`，`R=4177`，`E=7823`；最终输入估算：`prompt=7221 + schema=1214 + 8 = 8443`。
本次选中的原始消息序号：`19, 21, 23, 25, 27, 28, 29`。
逐源排除：seq 26 (ASSISTANT, RECENT_INTERACTION, INPUT_TOKEN_BUDGET); seq 24 (ASSISTANT, RECENT_INTERACTION, INPUT_TOKEN_BUDGET); seq 22 (ASSISTANT, RECENT_INTERACTION, INPUT_TOKEN_BUDGET); seq 20 (ASSISTANT, RECENT_INTERACTION, INPUT_TOKEN_BUDGET); seq 18 (ASSISTANT, RECENT_INTERACTION, INPUT_TOKEN_BUDGET)。原始消息仍在 Domain 快照中。

压缩批次：
- 覆盖 `[1, 16]`；输入估算 6000 Token；来源序号 `1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16`；父摘要 `无`；结果 `SUCCEEDED`。
- 覆盖 `[1, 17]`；输入估算 595 Token；来源序号 `1, 5, 7, 9, 11, 14, 15, 16, 17`；父摘要 `context-summary-3eb92430-5e95-4559-b542-6bc62bbb639a`；结果 `SUCCEEDED`。

## WP3 最终 Fixture Model 输入内容核对

以下内容由实际传给确定性 Fixture Model 的持久化 `request_json` 复核。Message Token 为内容 Token；整条 prompt 的估算另含角色和消息开销。该输入没有经过真实 Provider。

| 最终输入部分 | 内容 Token | 来源/证据 |
|---|---:|---|
| 系统控制提示 | 2224 | 固定应用系统/安全控制 |
| 历史 Summary | 521 | 当前 Summary JSON；来源 ID 见 case trace |
| 近期合成用户消息 | 16 | Domain 消息序号 19、21、23、25、27 |
| 近期合成用户消息 | 16 | Domain 消息序号 19、21、23、25、27 |
| 近期合成用户消息 | 16 | Domain 消息序号 19、21、23、25、27 |
| 近期合成用户消息 | 15 | Domain 消息序号 19、21、23、25、27 |
| 近期合成用户消息 | 17 | Domain 消息序号 19、21、23、25、27 |
| 保留的长合成工具结果 | 4296 | 序号 28；完整合成结果中含 `Receiver=QUEUED` |
| 当前用户消息 | 53 | 包含未解决状态与最新 QUEUED 观察 |

WP3 的 30 条测试结束 Domain 消息快照约 35,095 Token；最终调用选中的原始消息约 4,450 Token。另有 5 条 RECENT_INTERACTION 来源（序号 18、20、22、24、26）因 `INPUT_TOKEN_BUDGET` 未发给模型，原始结果仍在快照中。序号 14、16 的旧材料落入摘要来源；序号 28 的完整长结果仍作为最近消息发送。

Fixture 的最后回答仅确认请求到达固定 Answer 分支。它不能证明模型从摘要记起早期 API 配置。自然语言语义忠实度、引用充分性和早期回忆仍为 `NEEDS_LIVE_SEMANTIC_EVAL`。

## WP3 摘要 JSON 信息保持核对

| Ground Truth | 当前 Summary JSON | 结构/来源判断 |
|---|---|---|
| 初始目标：只读核验回调处理，202 不等于完成 | 保留在 `initial_goal`，引用 seq 1 | 含义一致；Fixture 仅证结构字段和来源映射 |
| 禁止改凭证/业务写入 | 保留在 `constraints`，引用 seq 5 | 含义一致 |
| 初始 endpoint `/callback`、`max_attempts=3`、req-482、evt-731 | Summary 未保留 endpoint/max_attempts=3；req-482 仅在后续更正中作为错误值出现，evt-731 保留于更正 | 早期配置丢失；摘要不会自行恢复初始状态 |
| 正式更正 req-483；req-482 是录入错误；Event 仍 evt-731 | 保留在 `corrections`，引用 seq 7 | 内容和来源 ID 相符 |
| 排除 timeout 假设 | 保留在 `rejected_hypotheses`，引用 seq 9 | 内容和来源 ID 相符 |
| 协议 v1.2→v1.3；attempts 3→5；部署版本未知 | `timeline` 被 120 字条目上限截成 `...max_at` | attempts 变化和部署未知均丢失 |
| Synthetic tool result：202 ACCEPTED，Receiver=QUEUED，不证明完成 | `timeline` 保留两条重复材料且在 `HTTP 202` 结束 | 丢失 Receiver 与非完成语义；不能把摘要当事实回执 |
| Receiver completion unknown | `unresolved_items` 是空数组 | 未保留在 Summary；当前用户消息仍包含该未解决状态 |
| 最新观察：Receiver=QUEUED，时间 2026-11-14T12:00Z | 不在 Summary；在最终用户消息 seq 29 | 本轮实际 prompt 可见，不能证明跨轮摘要保持 |

Fixture JSON 中 `source_message_ids` 均可映射到同一 Domain 快照的源消息；这仅证明结构性来源存在，不证明自然语言陈述忠实。Summary 的 512 Token 上限、每条 120 字上限和每类最多 3 项均来自当前代码，以上截断/遗漏是该 Fixture 的实际输出，不是对真实模型质量的结论。

## 来源失效与原始数据

WP3 trace 导出了测试结束 Domain 中的原始消息 ID、序号、角色、文本和 digest；其中早期 endpoint、req-482、正式更正 req-483、v1.2→v1.3、原始 `Receiver=QUEUED` 长结果均可读取。测试 Domain 位于 `TemporaryDirectory`，trace 是离线审计快照。AR-04A 中 `test_ar04a_invalidated_summary_is_not_sent_to_the_model` 通过，证明失效 Summary 不进入最终 Fixture 输入；该断言属于 Fixture/Mock 回归，不是线上失效源验证。
