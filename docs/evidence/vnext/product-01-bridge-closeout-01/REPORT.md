# PRODUCT-01-BRIDGE-CLOSEOUT-01

**状态：ACCEPTANCE_CANDIDATE**

## 执行摘要

| 项目 | 结果 |
|---|---|
| Base | `5b174aa59be072d38d716b7e908f523fa7df92f9` |
| 代码与 Trace 提交 | `83b886353c5252f1ec02d094259a2ca59fe699a5` |
| 最终分支 | `codex/product-01-bridge-closeout-01` |
| 本轮代码/证据 Diff | 12 个初始文件；本报告提交后新增本目录交付文件 |
| 聚焦 Python 回归 | 77/77，通过，126.00 秒 |
| 前端单测 | 29 通过、1 跳过、0 失败 |
| TypeScript / Build / ESLint | 均通过 |
| 全量 pytest | 757 收集；741 通过、16 失败；退出码 1；1013.15 秒 |
| 全量测试停滞 | 本轮未复现；进程正常退出 |
| 真实 Provider | 0 次 |
| 浏览器 | NOT_RUN，历史 Browser STOP 仍有效 |
| 外部业务写入 | 0 |
| 本地隔离 Demo 写入 | S1 闭环 Trace：1 次 REPAIR、1 条本地交付记录；S2：1 个本地 Queue、1 个 HandoffReceipt、1 个 Outbox；无 Scope/Policy 写入 |
| 权限、TaskControl、Domain 写入语义 | 未修改 |

远端复核：`main=60eee87bfe3cca522011316cb4cd2c0064ad291b`；原候选 `codex/product-01-final-bridge-01=5b174aa59be072d38d716b7e908f523fa7df92f9`。新隔离分支尚待推送确认。代码提交为 `83b8863`；未改写历史 Gold、RED、真实实验账本或原始 Trace。

## 本轮修改及用户变化

1. 会话结果列表仍最多返回 4 项，但 `omitted_count` 现在从同一授权范围查询的完整符合条件行数计算，不再把最多 5 行的读取上限误当作实际遗漏数。无权限、终止或来源不合格的 Task 不进入可见计数。
2. 刷新或重新进入 Session 后，前端会对最近最多 8 个符合条件的模型答复 Run 回读现有 Assistant Sources API，恢复仍有效且准确关联到原问题的受控调查建议。请求并发最多 3 个，切换会话会清空缓存并通过原有 Session fence 丢弃迟到响应；服务端重新验证来源。
3. S2 在只有 `HANDOFF_READY` 草稿时，Assistant 可读回“尚未提交”，不会把草稿说成已进入人工队列。实际提交后才显示 `SCOPE_ESCALATED / PENDING_REVIEW`。
4. S1 在 `WAITING_APPROVAL` 与完成本地 D3 闭环后，都可由普通 Assistant Run 读取持久 Outcome；时间语义标记为 `PERSISTED_OUTCOME_NOT_CURRENT_PROBE`，不会把历史 VerificationReceipt 表述为当前探测，也不会重复写入。
5. 正常 `opspilot reset` CLI 入口中一个局部导入遮蔽模块级函数，导致清洁初始化报 `UnboundLocalError`。移除该重复导入后，独立 Demo DB reset 和本地 Web Server 健康启动通过。

完整源码 Diff 由 Base 与分支提交核对；本轮不迁移 S1/S2 Graph，不增加状态权威或通用平台。

## 用户旅程证据

### Journey A：S2 403 交接

见 [TRACE-S2-OUTCOME-READBACK.json](TRACE-S2-OUTCOME-READBACK.json)。同一 Session 中，Assistant 替身先提出受控调查，用户确认后旧 S2 Investigator 通过正式本地 MCP/Domain 取得当前 403、同 Request Authn 成功与 Authz `DENY / SCOPE_INSUFFICIENT`，随后持久化 Diagnosis 和未提交草稿。

- 提交前 Assistant 读到 `HANDOFF_READY`，无 HandoffReceipt、无队列，答复明确说明未提交、未增加权限、未证明 403 恢复。
- 用户走已有确认入口提交后产生一个本地 Queue、一个不可变 HandoffReceipt 和一个 Outbox；状态为 `SCOPE_ESCALATED / PENDING_REVIEW`。
- Assistant 后续只读同 Session 专业结果，说明已进入本地受控队列等待人工处理；Scope 未增加、没有业务恢复结论。
- 轨迹中模型替身提出了多余的授权事实查询，后续工具提议被程序按当前 S2 Evidence 协议拒绝。它被保留为效率/决策证据，不能算成功 MCP Observation。

### Journey B：S1 401 受控调查与结果回读

见 [TRACE-S1-BASE.json](TRACE-S1-BASE.json)、[TRACE-S1-PROJECTION.json](TRACE-S1-PROJECTION.json) 与 [TRACE-S1-CLOSED-LOOP.json](TRACE-S1-CLOSED-LOOP.json)。

- 正式 S1 Investigator 在同一 TaskBinding 下经本地 MCP/HTTP 取得 401、配置与主体观察，形成 `READY / WAITING_APPROVAL` Plan。普通 Assistant 读取该持久结果后说明仍待审批，尚未修改配置或完成验证。
- 隔离 D3 Demo 的独立审批后，通过既有 Revalidation、CAS、同一 Service/Integration/Principal/Route 的 HTTP 200 验证、冻结报告及独立 DELIVER，最终 Outcome 为 `DELIVERED`。该轨迹显示一次本地 Repair、一条本地交付记录；没有外部业务写入。
- S1 过程由专业 Investigator/D3 执行；Assistant 只提出建议或读取同 Session 可信结果。

这些是隔离本地 Demo + 确定性模型证据，不是生产操作，也不是本轮真实 LLM 结果。

## 测试与运行证据

- 聚焦 Python：`tests/test_product_01_bridge_closeout_01.py`、PRODUCT-01 bridge、AR-05 S1/S2、D3、AR-02 Assistant/Worker/API 与 AR-02/AR-03 集成等共 9 个测试文件，77/77 通过。完整命令和私有日志 SHA 见 [EVIDENCE_INDEX.md](EVIDENCE_INDEX.md)。
- 聚焦前端：29 通过、1 跳过；TypeScript typecheck、生产 build、变更文件 ESLint 通过。
- 完整 pytest：757 项全部收集并执行至结束，741 通过、16 失败，1013.15 秒，退出 1。本轮没有出现 TestClient shutdown 无限等待。失败分类和限制见 [FAILURES.md](FAILURES.md)。
- 前端 npm 安装第一次因共享缓存权限失败；改用本任务私有 npm cache 后安装成功，lockfile 未改。未执行 `npm audit fix`。
- `pip check` 发现全局环境中 OpenTelemetry SDK/semantic-conventions 1.42.1 需要 API 1.42.1，但当前 API 为 1.45.1；锁定依赖未更改。相关测试仍成功。
- 本地后端清洁启动检查通过：独立 S1 Demo reset、正常 Web Server、`/api/health` 返回健康且 Worker ready；命令帮助通过。无真实 Provider 请求。
- 真实浏览器和新的真实 LLM Bridge 选择行为均未运行。

## 六维结论

**用户变化：** 刷新后可能丢失的有效调查建议可经现有 API 恢复；S1/S2 专业结果可在同一 Session 里由 Assistant 准确解释。展示层现在能区分“有草稿”和“已交接”，也能区分“待审批”和“历史修复已验证”。

**Agent 决策：** 生产 ASSISTANT_V1 仍可直接答复、使用现有资料/只读 MCP、提出专业调查建议或读取专业 Outcome。离线确定性测试验证了装配和接口，不能证明新 Bridge 下真实 LLM 会主动选择建议或 Outcome 工具。

**观察驱动：** S1 的当前 401/配置/主体 Evidence 决定 Plan；S2 的同 Request Authn 与 Authz DENY 支持缺少 `orders.read` 的结论。交接回执仅表示队列接收，不表示 Scope 授权或业务恢复；历史 VerificationReceipt 只描述其形成时的验证。

**新增约束：** 没有放宽授权、来源、TaskControl、幂等、Approval 或 Domain 写入语义。调查建议刷新不创建 Task，只有用户确认入口能创建受控 Task。

**简化结果：** 复用既有 Sources API、TaskControl、Investigator、D3、S2 HandoffReceipt 与 Outcome 读取。没有添加新 Runtime、Graph、状态机或状态存储。

**证据与停止线：** 本地确定性旅程、聚焦回归、前端构建和一次全量 pytest 均有实际退出状态。全量回归未全绿，16 项仍失败；没有因此修改历史合同。真实 Provider、真实浏览器、生产环境和 main 合并均未执行。

## 已知限制与建议

- 前端 Sources 的历史恢复有界为最近 8 个模型答复；更早的建议不会自动恢复。此上限仅约束恢复读取量，不改变后端权限。
- 真实 LLM 在新桥接链路中是否提出 S1/S2 建议、是否读取 Outcome，尚未验证。
- 浏览器 CTA、刷新、授权撤销后的可见行为仍需在 Browser STOP 正式解除后验收。
- 16 项全量失败中，若干属于冻结身份/历史合同限制；3 项 AR-03 历史 Runner MockTransport 测试没有发出预期模拟请求，原因尚未确认。详见 [FAILURES.md](FAILURES.md)。
- 新隔离分支为待审候选，未合并 main；最终远端 SHA 以推送后分支核验为准。\n