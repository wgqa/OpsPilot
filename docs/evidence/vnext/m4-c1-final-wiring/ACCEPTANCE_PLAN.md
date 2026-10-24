# C1 最终接线收口与事实可行性核验 — 冻结计划

**状态：** FROZEN / RED 开始前  
**仓库：** `wgqa/OpsPilot`  
**实施分支：** `codex/m4-autonomy-c1`  
**候选基线：** `3dc761b869112900f83180ee01d50be3f5e80493`  
**远端 main：** `77ea80e87e538f0f1fae8118ef231ec622601755`  
**候选远端：** `3dc761b869112900f83180ee01d50be3f5e80493`  
**候选与 origin/main 合并基线：** `77ea80e87e538f0f1fae8118ef231ec622601755`  
**冻结依据 Blob：** North Star `1f737712c7a36ceb34433ac09c3fbba3c3305542`；AGENTS `30319000ed0054007e9b7b6b46bf98b1493c8179`；C1 `FROZEN_PLAN.md` `7edcf669e88c8b2a34b77f8404438df973cfee78`；REV1 addendum `cdb62ab7dc798303ab73eca1171f6c7260312aa9`；HF-01 plan `a5625a484539fbf50886f1d0337c544bc0b67df2`；HF-01 supplement `0532bf6d904d9e9d2ff0e493ed4744bc3e9580e`。

## 开工核验与文件保护

目标候选 HEAD 和远端候选在开工时均为 `3dc761b869112900f83180ee01d50be3f5e80493`；远端 main 为 `77ea80e87e538f0f1fae8118ef231ec622601755`。主工作区本地 main 为 `add47ec83f31fa76b9b6a5782e013311732bc496`，相对 origin/main 落后 12 个提交，包含许多未跟踪测试目录和 `开发目录/` 资料；不在该工作区开发。本候选工作树有既存未提交 Trace、Knowledge/Skill 文件以及运行日志、临时数据库锁等未跟踪材料；本轮不修改、不删除、不暂存它们。只显式暂存本切片新增的验收、测试、报告和运行证据。

本轮从候选 HEAD 实际读取了 `PROJECT_NORTH_STAR.md`、`AGENTS.md`、C1 FROZEN/REV1 合同、HF-01 冻结计划与补充、C1 REV1-FIX-01 计划/报告、HF-02 授权与 SLA 报告、TTL-FIX-01 计划/主线集成补充。`.agents/skills/opspilot-slice-review/SKILL.md` 在候选和当前主工作区都不存在；未声称读取。既有授权撤销、TTL/Run Observation、TaskControl、只读补查不写 Diagnosis、预算与不可变回执门禁继续有效。

## A：验收目标与测试冻结

唯一实现缺口为 `S3Nodes.prompt()` 虽读取 `load_investigation_context()`，却没有把共享装配器产出的 `prior_readonly_followups` / exclusions 放入真实 S3 模型消息或该调用的来源 Provenance。本轮复用 `investigation_context.py` 的同 Tenant/Session/Task、早于当前 Message、有完整 Run/source digest、Knowledge 当前性、历史 Evidence 来源核验及已有 3 条/文本长度界限；不改装配器的权威语义。

| 用例 | 冻结判定 |
|---|---|
| C1-WIRE-01 有效历史 | 通过 `S3Nodes.model_call()` 实际捕获出站消息；有效先前结果、Run、摘要、Message、Knowledge 引用与 `CURRENT_APPLICABLE` 必须进入提示词和实际调用 Provenance。历史 Evidence 标为 `HISTORICAL_RUN_ONLY`，不得进入 `current_mcp_evidence`。业务 Diagnosis、Task 状态/控制版本及审批/动作/队列/回执/Outbox 快照不变。 |
| C1-WIRE-02 失效来源 | Knowledge 版本/Digest 变化后，先前答案可保留为明确的历史文字，但旧 Knowledge 不得进入当前 `selected_knowledge` 或作为当前事实；提示词和 Provenance 必须记录其历史当前性与排除原因。历史 Evidence 仍仅为历史引用。 |
| C1-WIRE-03 空历史正例 | 没有先前只读结果时，实际 S3 `model_call()` 正常完成，历史区块为空，不影响已有合法调查输入、预算与模型调用。 |
| C1-WIRE-04 出站前失效 | 首次组装后、Provider 调用前替换当前 Knowledge。现有重新校验须观察到历史来源状态变化；Provider `ainvoke` 调用次数为零，失败原因清楚，不能把旧内容发送出去。 |
| C1-WIRE-05 Token 边界 | 通过现有 `_investigator_context_budget()` 对包含历史结果的完整消息计算 Token；超过预算须 fail-closed，不能删掉预算检查或用历史文本绕过。正常大小正例可调用模型。 |

测试使用确定性 Provider 替身，只证明真实 S3 `model_call()` 传递的消息、预调用校验和持久 Provenance，不声称本轮有真实外部 Provider、自主性或浏览器新证明。执行顺序：冻结提交 → 新测试 RED 并保存原始日志/退出码 → 最小实现 → 新鲜 GREEN → C1/HF-01/S3/Context/TaskControl 与授权/回执安全回归 → 全量 pytest。保留所有历史 Gold、RED、E2E 失败与旧报告。

实现限制：只在 S3 已有 Prompt、`model_call()` Provenance 及必要的测试中接线；复用 `summary_refs` / `excluded_sources`，不加 Schema、Context 平台、Guard、Runtime、预算或新业务功能。历史结果仅为历史提示，只有当前 Knowledge 可被引用为协议依据；历史 Evidence 不跨 Run 成为当前 Observation。

## B：只读事实可行性核验

只读检查当前 S3 Schema、Fixture、HTTP 路径、MCP 工具与 Domain 事实，回答任务卡五问：是否有同 Event 可追加的多次 Transport Attempt；能否关联 Event ID、独立 Transport Request ID、逐次 HTTP response、重试序号、时间与来源；哪些是订单快照、哪些是历史；不足时最小新增事实存储职责；如何用现有绑定范围只读查询而不改变 Diagnosis/Handoff 权威。交付一个“同 Event 重试”、一个“不同 Event 易混淆”和一个“历史不足”的可验证样例。

本轮不新增 S3 工具、表、HTTP 行为、MCP Schema、模型预算或调查循环。结论仅作为下一里程碑的输入，不代表实施授权。

## 停止线与状态

所有新增测试和全量回归完成、原始日志与 B 事实分析写入独立目录、最小改动已提交并推送到现有候选分支后，状态只为 `ACCEPTANCE_CANDIDATE`。不合并、不签署主 Agent PASS、不启动 C2/C3。
