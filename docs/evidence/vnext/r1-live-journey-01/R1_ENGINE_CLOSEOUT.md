# R1-ENGINE 收口候选与最短演示路径

**实施方结论：** 本轮不具备新的真实模型证据，不自签 R1-ENGINE PASS。现有隔离工程能力可供主 Agent按 R1-ENGINE 原合同独立评审；本轮 J1–J4 真实模型 Campaign 因发送前预算界阻断。

## 能力分级

| 能力 | 已理解/复现 | 已接入用户旅程 | 已证明效果 | 当前限制 |
|---|---|---|---|---|
| 协议发现、版本比较、来源/摘要校验 | 是；正式 MockTransport 与 Domain 测试 | 是；同 Session J1 离线路径 | 离线接线成立；新真实模型自主选择未验证 | 本次 J1 BLOCKED_BEFORE_PROVIDER_SEND |
| 用户 JSON 材料分析与纠错 | 是；用户材料与配置事实区分回归 | 是；同 Session J1/J2 离线路径 | event-current 与 event-previous 事实隔离离线成立 | 本次 J2 BLOCKED_BEFORE_PROVIDER_SEND |
| Callback 当前只读查询 | 是；真实本地 MCP/Domain Observation | 是；可信订单绑定后查询 | 离线当前 Event 观察能改变结果，跨 Event 不借事实 | 新的真实 LLM 行为未验证 |
| S2 403 结果回读/显式交接 | 是；隔离本地 API/Worker/Domain | 是；同 Session 草稿→确认→Receipt | 证明 SCOPE_ESCALATED/PENDING_REVIEW，不证明已恢复 | 新 Assistant 真实模型回读与 Browser 未验证 |
| S1 401 受控闭环/结果回读 | 是；隔离 Demo D3 因果链 | 是；持久结果回读 | 证明本地 Demo 401→审批→CAS→同身份 200→DELIVER | 本地 Demo 写入，不是生产；新 Assistant 真实模型回读未验证 |
| Runtime Grant | 是；发送前持久预留、唯一 Send Granted、UNKNOWN/Usage 处理已有定向测试 | 已接入 ASSISTANT_V1 | 离线授权/预留路径通过；本次发现 Public capacity reserve 与 campaign-wide count 缺口 | 本次不 provision、不发送；不可宣称 Campaign 费用门禁就绪 |
| Web/Browser | 有现存工作台代码与历史 API 证据 | 部分 | 未以本次浏览器验收证明 | Browser STOP 仍有效 |

## 可用于校招沟通的谨慎表述

可讨论的工程贡献：把统一 Assistant 接到受 TaskBinding 限制的只读协议/业务工具，并保留 `message → Run → tool call → MCP Observation → Answer` 的来源链；将 S1/S2 专业处理继续委托现有 Investigator/D3，同时把可信持久结果回流到同一 Session；对模型付费调用采用显式 Runtime Grant、发送前预留、唯一 send authority 和 UNKNOWN 停止。

不可宣称：本次 R1-LIVE Campaign 的真实模型能力通过；四条 R1 旅程已被同一真实模型完成；浏览器体验通过；该 Demo 是生产级 IAM；S2 handoff 修复了权限；本次运行产生真实业务恢复。

建议的面试讲解顺序：用户如何在同一 Session 从材料咨询推进到可信只读调查；模型只选择行动，TaskBinding/MCP/Domain 决定可读事实；HTTP 202 与 Receiver 状态如何区分；S1 Approval/ActionIntent/CAS/Verification/Delivery 与 S2 Diagnosis/Draft/HandoffReceipt 的终点为何不同；费用 UNKNOWN 为何不重试。

## 最短演示路线（只复用已保存证据）

1. **协议/材料/纠错**：阅读本目录 `CASES.json` 的 J1/J2 与 Base 的 [`TRACE.json`](../r1-journey-readiness-01/TRACE.json)。若需离线重现，使用 Base `TEST_LOG_FINAL.txt` 中的目标 pytest 命令；它走正式 API/Worker/MCP/Domain，但 Provider 为 MockTransport，不是实时模型。
2. **S2**：查看 Base R1 Readiness 的 J3 Trace/结果与 `tests/test_product_01_final_bridge_01.py::test_assistant_proposes_s2_then_reads_same_session_handoff_without_writing`；结果是受控本地 `SCOPE_ESCALATED / PENDING_REVIEW`。
3. **S1**：用 README 的 D3 Demo 步骤创建全新命名的本地 Demo 数据库，核查同身份 401→审批→CAS→本地 200→报告/DELIVER；这是隔离 Demo 流程，不是统一 Assistant 的真实 Provider 或 Browser 旅程。
4. **浏览器**：本轮不启动。必须等 Browser STOP 有效解除后才可把真实 Web UI 计为验收。

## 最短恢复真实旅程路径

新的执行授权仍需遵守已授权模型、无重试和不复用 Claim。以当前价格重新核算后，至少选择其一并形成明确新预算：

- 保留 16 次上限：全公开容量上界为 USD 11.06688，原 USD 11 不能覆盖；该最低数学额没有价格浮动余量。
- 保留 USD 11 上限：若要维持相同公开最大容量预留，最多 15 次（USD 10.37520）。这属于修改次数边界，必须在新执行合同中明确。

两种方案都需先复用 Runtime Grant 实现补齐真实发送前公开容量预留和持久 Campaign 累计发送限制；不是开新平台。执行当天重核价格/模型版本及序列化 Body；配置/授权通过后立即运行，不重复建设 Readiness。
