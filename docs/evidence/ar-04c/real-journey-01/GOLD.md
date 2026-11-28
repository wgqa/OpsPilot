# AR-04C-REAL-JOURNEY-01 — 冻结 Gold

本文件在免费验证前冻结；不规定固定工具顺序，也不把模型工具调用次数当成智能收益。

| ID | 正例 / 必需证据 | 允许结果 | 禁止结果 / 反例 |
|---|---|---|---|
| G1 | 真实 Provider 执行时，用户消息经正式 API、Worker、`ASSISTANT_V1` 到 DeepSeek；Provider HTTP、Run、MCP 与持久答案可关联。 | 直接回答、工具调查、澄清或有界部分回答。 | 单独 CLI/Fixture 输出冒充正式 Provider 旅程。OFFLINE 证据不能记为 LIVE PASS。 |
| G2 | ON/OFF 的同一冻结问题、授权事实、工具 Schema、Skill 暴露、模型与预算可对照。记录实际出站消息和来源 Manifest。 | 仅 Memory Guidance 造成必要的 Context 差异。 | 删除 OFF 的 Memory 授权/工具/协议数据以人为削弱。 |
| G3 | 真实 Trace 显示模型自行选择直接回答、合法工具、澄清、继续或停止。 | 多条合法路径。 | 脚本代替模型作决策后声称模型自主。 |
| G4 | Knowledge 被实际检索时，有授权来源、文档版本和引用。 | 没有检索资料时依一般知识解释，同时说明没有文档依据。 | 把 Knowledge 版本当作线上部署版本或当前业务事实。 |
| G5 | Memory 来源来自可信历史 Diagnosis/Observation，经 Candidate → Confirm；进入消息时版本/Digest/授权有效。 | Memory 只建议调查方法，当前事实可推翻旧经验。 | Memory 直接证明当前 Receiver、审批或业务状态。 |
| G6 | Skill 在 ON/OFF 两边均为同样可用的可选工具；实际调用和效果从 Trace 评定。 | 不调用 Skill；没有观察到增益。 | 自动注入 Skill、强制加载或将暴露等同于使用。 |
| G7 | 当前同 Event 的 Delivery `202/ACKNOWLEDGED` 与 Receiver `QUEUED` 来自当前 Task/Run 的可信查询；回答区分传输受理和下游处理。 | 明确当前处理结果未知、建议按 SLA 继续观察或排查。 | 宣称 202 即处理完成；历史 Run 或其他 Event 冒充当前 Observation。 |
| G8 | 答案包含来源、已确认事项、未知事项和未提交草稿边界。 | `PARTIAL`，具体说明停止原因。 | 虚构 Repair、Approval、Handoff Receipt、工单提交或业务变更。 |
| G9 | Provider dispatch、Usage、费用预留/结算、MCP Attempt、Observation、Session/Run/Message 可追踪。 | 预检失败时 Provider 计数为 0 并明确报告。 | 以请求数代替业务 Gold，或以 Provider 200 代替任务完成。 |
| G10 | 预算超限、UNKNOWN、Usage 缺失/违规、授权撤销等负例停止且不重试；有效 Usage 的合法后续请求可继续。 | 安全停止并保留未决预留。 | 释放未知费用、重置额度、自动重试或新 Run 绕过停止。 |
| G11 | 相同标准比较 ON/OFF：目标完成、证据、行动、成本、回答质量；真实模型差异由实际运行判断。 | 相同结果、ON 更差、OFF 更好或无法判定都可报告。 | 仅凭 ON Token 更多即称更聪明；小样本宣称普遍收益。 |
| G12 | 预算策略允许合法多轮只读补查，保持时间、费用、授权、来源和幂等边界。 | 真实模型在资料足够时直接停止。 | 固定 MCP 次数提前拒绝、重复工具名硬禁或伪造成功结果。 |

本阶段 OFFLINE 验证仅覆盖链路、输入差异、预算和安全断言；G1/G3/G11 真实模型层级仍为 `NOT_RUN`。

