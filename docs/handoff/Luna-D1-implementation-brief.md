# Luna D1 实施任务书（可直接转发）

**放行状态**：R5 DESIGN APPROVED；**唯一规范**：`docs/baseline/v1.0-implementation-baseline.md`。**任务**：只实施 D1，别抢做 D2–D7。首个交付应是能运行的最小 Domain 因果链与三个技术 smoke，不是大量空目录。

## 一、你要实现的产品事实（请先准确理解）

任务场景 S1：`integration-a` 使用工具侧安全解析的旧凭证引用 `cred-v1`，服务端当前接受 `cred-v2`，`principal-a` 为 ENABLED；通过**同一个 caller/integration/principal** 访问登记的订单业务端点 `GET /api/orders/demo-order` 必须返回 401。测试驱动把调用方引用更换为新凭证（只允许 fixture 专属变更能力，不能以无审批 Agent 工具暴露），再次通过**同一个调用方身份和同一个业务路由**访问得到 200 且返回 `order_id=demo-order` 和 `status=CONFIRMED`。

迷惑负例：Principal 为 DISABLED，即便使用新引用仍返回 401；不能通过换凭证或者擅自启用主体来“修复”。模型只允许看到凭证引用、版本和非敏感事件，不能看到原始凭证/离线 Gold。

## 二、D1 工作包（按顺序）

### WP-01 环境/依赖锁定（目标 30–60 min，实际以执行为准）

- 建 Python 3.11+ 最小工程，包含 `pyproject.toml`、锁定后的依赖版本、`.env.example`（只有变量名）、`.gitignore`（不能提交密钥或实际数据库/实验日志）。
- 确认模型服务实际可访问、其 Function Calling 兼容，记录 model ID、版本/提供商、模型端点类别（不得泄漏 key）。
- 先使 `pytest` 和项目启动脚本可用，再增加模块；失败时保留错误记录与版本，而非无脑升级所有依赖。

**验收**：从干净环境依 README 可安装、执行一次 smoke；记录 `python --version`、已锁定包版本和关键兼容性说明。

### WP-02 真实模型 Function Calling smoke（目标 30–60 min）

- 仅一个类型化**只读**测试工具，例如 `get_demo_service_info(service_id)`；真实 LLM 返回合法 Tool Call，实际工具执行并返回结构化 Observation。
- 必须记录 `tool_call_id`、工具名、参数 Schema、结构化结果和错误路径；脚本应能在调用未成功时以非零状态退出。
- 不许通过 `if 'tool' in text` 模拟模型工具调用，不许以截图代替 Trace/日志。

**验收**：一份真实模型工具调用日志（敏感值脱敏）+ 可重跑命令；至少一次成功/一次参数错误测试。

### WP-03 真 MCP stdio smoke（目标 45–75 min）

- 用官方 MCP SDK 创建本地只读 Server + Client（使用当前锁定版本的真实 SDK API）。
- 客户端真实执行 `tools/list`，再 `tools/call` 查询同一 Domain 数据；确保结果是从 Domain 实体查询得来而不是硬编码 `success`。
- 固定可信运行 scope，工具输入不接受模型自选 tenant/Authorization/URL；记录结构化返回与 `isError` 的实际适配行为，并区分连接异常和工具失败。

**验收**：真实 Server/Client 进程间通信日志、工具列表、工具调用结果、权限负例至少 1 条；提供最小启动命令。

### WP-04 LangGraph checkpoint + interrupt 跨进程 smoke（目标 45–75 min）

- 编写最小 LangGraph 工作流，checkpoint 使用实际持久化实现（不可只用内存 checkpointer）。
- 启动进程 A，以合法 thread ID 进入 interrupt；保存 checkpoint。**彻底结束 Agent 进程 A**（不是仅关闭业务 HTTP 服务），启动进程 B，以原任务身份恢复、读取原状态继续到下一节点。
- 不把业务写副作用放在可能从 interrupt 节点重新执行的位置；非法 thread 所有权请求不得绕过绑定校验。

**验收**：两次不同 PID 的运行记录、同一合法 thread_id、恢复前后 State 值一致的断言、结束码与失败路径；不是进程内重复 invoke。

### WP-05 无模型 S1 真实业务因果链（目标 90–150 min）

- 用最小 Python Domain API + SQLite（优先稳定易测）实现 client integration、principal、server accepted ref、测试凭证解析模块、鉴权事件与业务订单响应；两个 fixture 可重置。
- 测试驱动 `reset(S1_POS)` → `probe()` 得 401 → `fixture_only_switch_ref(cred-v2)` → **原 caller `probe()`** 得 200 和订单业务断言。业务服务使用密钥值验证，而不只是比较两个可被模型随意指定的引用字符串。
- `reset(S1_DISABLED)` → `probe()` 401 → 测试中切换引用后 `probe()` 仍 401；确保主体不被自动启用。
- 测试 fixture 更改功能与未来 `execute_REPAIR` 是不同入口；前者仅在测试环境存在，不在 MCP 只读工具或 Agent 生产侧暴露。
- 隔离 tenant-a/b 数据；记录当前主体、凭证与配置版本、事件观测时间，真实测试值不能出现在 LLM Context/Trace。

**验收**：一份自动集成测试证明 401→200 的真实服务调用链、DISABLED 负例仍 401、同一 principal/integration/route 与响应业务字段；对比日志可重现。

### WP-06 提交与报告（建议 30 min）

- 更新 README，填入实际命令，不写假命令。提交测试脚本、脱敏运行输出、锁文件、已知风险、未实现清单。
- 若没有可用模型 API、MCP 适配困难或持久 checkpoint 版本不兼容，先保留精确错误和最小复现，不以 Mock 代替真实 smoke；写明阻断并停在 D1。

## 三、D1 严格非目标

- **不要**提前铺建复杂的 LangGraph Agent Loop、Memory Store、Skill 系统、Plan/Approval/ActionLedger 的完整实现或生产式 UI。它们属于 D2–D5。
- 不得使用真实生产客户环境、真实密钥或开放任意 URL 探测。
- 不得把 fixture 更改工具暴露给模型作为无审批写能力。
- 不得为了缩短开发时间删掉 S1 真实业务验证或 DISABLED 负例。

## 四、交付清单 / 机器可验收要求

```text
[ ] 运行环境、依赖及模型版本锁定
[ ] tool_call_smoke: actual model Tool Call -> typed tool -> real observation
[ ] mcp_smoke: real stdio tools/list + tools/call from Domain + negative case
[ ] checkpoint_smoke: process A interrupt -> terminate -> process B resume
[ ] S1_POS: caller business request 401 -> fixture-only config change -> same caller/route 200 + exact order fields
[ ] S1_DISABLED: changes cannot bypass DISABLED 401
[ ] tests: actual commands + PASS/FAIL counts + redacted logs
[ ] source code committed and a diff/changed-files summary
[ ] README actual quickstart and known limitations
```

如果全部通过，由主 Agent审查并签收 D1；否则只报告完成的部分，继续修 D1。**R5 设计放行不代表 D1 通过。**

## 五、给主 Agent 的回报模板

```text
[D1][branch][commit SHA]
Python / LangChain / LangGraph / MCP SDK / Model versions:
项目启动/测试命令:
WP-01 环境验证证据:
WP-02 Function Calling smoke: PASS/FAIL + tool_call_id + redacted trace
WP-03 MCP smoke: PASS/FAIL + tools/list/tools/call raw structured output + error case
WP-04 Checkpoint smoke: PASS/FAIL + PID A/B + thread_id + persisted state
WP-05 S1 POS/DISABLED: actual request/response/status + config versions + API business assertions
单测/集成测试: passed/failed/skipped
修改文件清单 / 新的接口 / 与 v1.0 的偏差:
已知问题/阻断/下一阶段建议:
```

如果需调整 v1.0 外部语义或 P0 范围，先提出简短 ADR，不擅自更改合同。实现细节（文件名/内部函数拆分）可自主决定。
