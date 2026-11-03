# AR-03-B-RELIABILITY-01 — 冻结验收标准

**状态：** 离线定向修复；真实 Provider 与浏览器均不运行。  
**Base：** `332f93cca4daad308a8d57730f141e8cc5ed96b3`  
**实现分支：** `codex/ar03-b-reliability-01`  
**基线证据：** CASES `c29b5cf7630fa838a365634d0df5f9f0f2bfa834`；GOLD `88d5e6f40f027ce2622b957d8ab32b8d2b827381`；North Star `1f737712c7a36ceb34433ac09c3fbba3c3305542`；AGENTS `32c45506cceeaa8c76a5c56bf8360ff476b58856`；Skill `d405c8d413d633824b279202cc1503dab4cf0b03`。

## 用户结果与问题

真实 AR-03-REAL-LLM-02 的 A 完成；B 获取到同 Event 的 `HTTP 202/ACKNOWLEDGED` 与当前 `PROCESSED`，但因一次授权的只读 MCP 工具提议超过 Run 六次上限而终止，没有交付最终结论。真实轨迹中，初始主题检索为空；模型随后进行了更宽的协议发现和 Knowledge 查询。B 的 MCP 额度 6/6 用完后，下一工具没有执行，Run 以 `FAILED / ASSISTANT_RUN_MCP_LIMIT` 收尾。

本修复保持 Agent 自主选择和 6 次安全边界：改善受信文档候选召回/排序；预算拒绝须作为明确“未执行、不是事实”的 ToolMessage 返回给 Agent，使其仍可基于当前 Run 已持久观察回答或交付未知，不伪造工具成功、不发送第七次 MCP、不强迫固定工具顺序。只有经当前来源校验的本 Run 工具结果才可支持回答。

## 冻结验收

### P — 协议发现

1. `callback retry`、`callback retry protocol`、`callback retry behavior`、`回调重试协议`、`回调 重试` 应召回授权范围中的 `callback-retry-contract` v1.0.0 与 `callback-retry-contract-v2` v2.0.0。
2. 检索须先取得可信 Session 的已授权文档 ID 集，再对该集合召回、排序；未授权 API-scope 文件不得因关键词匹配进入结果。
3. 查询须按词项规范化与相关性排序；查询 `callback retry` 时 retry 家族应排在仅命中 callback 的 ACK 文档之前。不得因无关短语（例如 `invoice color`）召回回调文档。
4. 返回的 ID、版本、来源、Digest、有效期与 `scoped_discovery_is_current()` 现有重验继续有效。Grant/Session/Document 失效的拒绝行为不得放宽。
5. 空 topic 继续作为授权集合浏览；仅含通用检索词时可按授权集合返回，不扩大 scope。

### B — MCP 上限与交付

1. Run MCP 硬上限仍为 6；Task、Provider、Context、模型/Token、授权和历史实验账本不改。
2. 6 次实际合法 MCP 后，第 7 次模型提议必须在真实 MCP 调度前拒绝。拒绝结果标记 `executed=false`、`TOOL_REFUSAL_NOT_FACT`，不记成功 `assistant_calls`、不预留 D2/MCP Attempt、不调用 handler、不生成 Observation 或 Evidence。
3. Agent 收到拒绝后仍可在剩余模型预算内回答或说明未知。确定性正式 API/Worker/MCP 测试要求 Run 能使用既有当前观察产生非空回答；不得固定模型必须选择哪一工具顺序。该结果只算 Fixture 验证。
4. 如果后续模型/运行上限仍耗尽，保留现有程序生成的失败通知；不得把未执行工具当成事实、伪造模型最终回答或提升 Run 成功。没有已校验当前来源时必须 fail closed。
5. QUEUED 与 PROCESSED 的既有业务事实、同 Event 关联、来源撤权、零写入与历史 A/B Gold/Trace 语义不变。

### 固定限额决定

默认 MCP 单 Run 上限继续为 **6**。理由：真实 B 原始轨迹显示额外 broad list/Knowledge 查询来自首轮空召回；离线回放预期由检索修复消除重复尝试。任务不授权真实 LLM 重跑，且确定性顺序不能证明真实模型将少调用。因此目前证据不足以调整 6/12 历史上限。实现将处理预算拒绝的产品交付语义，不借调高预算掩盖漏召回。

## 证据区分与停止

- 历史真实模型 B：仅作为原始决策轨迹证据重放/分析，不重新执行 Provider。
- 新定向测试：确定性离线测试，可证明协议查询、正式 MCP 路由、额度未越界与程序运行语义；不能证明真实模型自主性或新真实 B 完成。
- 真实 DeepSeek、浏览器、业务写操作：`NOT_RUN`。
- 若来源当前性、授权或回执合同需扩大修改，或要求提高历史付费预算，停止并报告。
- 不改 CASES、GOLD、历史 Trace、历史失败或 main。
