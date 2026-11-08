# R1-J2-PRODUCT-FIX-01

**状态：** ACCEPTANCE_CANDIDATE
**基线：** `codex/r1-live-journey-02@fa2777948c4e1749aca987d17d016696c47c7ff4`
**实施分支：** `codex/r1-j2-product-fix-01`
**main 基线：** `60eee87bfe3cca522011316cb4cd2c0064ad291b`

## 结果

离线复现支持两个产品缺陷的最小修正：

1. TaskBinding 约束租户、服务、集成和订单。用户在已绑定订单内明确指定 Event，是只读查询目标，不等于申请切换受信资源。Assistant 现在可自主选择当前 Delivery/Receiver 读取，或用带 Event 过滤的运输历史工具核实该 Event 是否属于订单。Domain 仍负责范围验证；越界 Event 被拒绝，历史 HTTP 202/QUEUED 也不会被提升为当前 Receiver 处理事实。
2. Assistant 上下文明确区分已完成、正在发生和建议后续动作。没有当前 Run 的实际动作结果或可信回执时，进一步核查、联系接收方等只能写成建议，不能写成已启动、正在进行、已指派或承诺反馈。

历史 J2-01 中模型没有发起 MCP，并要求重新确认同订单 Event；历史 J2-02 把建议中的后续核查表述成“正在进一步核实并会同步”。旧真实 Trace、Gold、Campaign 账本和 STOPPED 状态均未修改。本轮未发送真实 Provider 请求。

## 实施范围

- `opspilot/assistant.py`：收窄 Event 纠错语义，明确绑定订单内 Event 只读选择与动作状态表述。
- `opspilot/domain/s3_mcp.py`：说明当前 Delivery/Receiver 工具返回其实际 Event；运输历史的 `event_id` 是订单内查询选择，Domain 验证归属。
- `tests/test_r1_journey_readiness_01.py`：正式 API/Worker + MockTransport 对照覆盖当前 Event 事实、纠错 Event 历史和客户草稿语义。
- `tests/test_ar02_runtime.py`：覆盖越界 Event 拒绝后，同一绑定订单内 Event 查询和合法业务查询仍可继续。
- `PRIVATE_RUNNER_FIX.md`：私有 J1 Runner 的本地校正摘要与校验记录。

没有修改 TaskBinding、Domain Schema、S3 查询算法、审批/写入边界、Gold 或真实实验账本。

## 验证

新增测试先在旧上下文下触发 RED：形式化 API/Worker 测试因缺少明确的同订单 Event 查询语义，在 MockTransport 处失败；没有 Provider 外部请求。修正后定向集成与跨范围正反测试通过 2/2；Knowledge → 可信订单调查和无 Task 普通 Session 相关回归通过 2/2。实际命令及退出结果见 `TEST_LOG.txt`。

私有 Runner 在原始 J1-01 Trace 中看到 2 次 `status=OK` 的无 Task Knowledge 调用，但旧谓词要求 Evidence 与 Observation ID，故判定为 0 次。修正后只对无 Task 且属于 Knowledge/Skill 工具的成功结果免除业务 Evidence ID 要求；任务绑定的业务 MCP 仍必须具备 Evidence/Observation。旧 Campaign DB 未运行、未复活、未改额度或重发。

## 执行边界

- 真实 Provider HTTP：0；MockTransport 请求仅使用合成响应。
- 浏览器自动化：0。
- 外部业务写入：0。离线测试只在临时 SQLite 和本地 loopback HTTP fixture 中运行。
- 历史 STOPPED Campaign、私有 Domain DB、Checkpoint、Gold 和原始 Trace：未改写。
- 新真实模型复验：未授权、未执行；需要独立授权。

## 六维结论

- **用户变化：** 同一授权订单内可直接调查用户指定的 Event；客户草稿清楚呈现未知和建议。
- **Agent 决策：** 模型仍可选择直接回答、当前业务只读工具、Event 历史查询、澄清或停止；未加入固定顺序或样例 ID 规则。
- **观察驱动：** 同 Event 的 Delivery/Receiver 状态与另一 Event 的历史投递分别保留；现有正式 Observation 路径未改变。
- **新增约束：** 未新增授权门；补充既有 TaskBinding 和工具状态语义。越界查询继续由 Domain 拒绝。
- **简化结果：** 复用现有 Assistant Prompt、MCP 和 Domain；没有新增 Guard、状态机或业务模块。
- **证据与停止线：** 离线回归 4/4，另有 1 项预期 RED；私有 Runner 判定修正已做离线正反检查。真实模型复验仍是未验证项，须另行授权。

真实模型的实际选择与措辞效果尚未复验；本候选只证明当前系统为合法同订单 Event 调查提供正确工具/上下文，并保持范围拒绝与不虚构进度的离线行为。
