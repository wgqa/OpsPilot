# OpsPilot vNext M2-03 交付与验收报告

**状态：** 实施与本地验收证据完成，提交主 Agent 独立复核；本报告不代替主 Agent 验收。M3 未启动。

**基线：** `main@0cdc3160a2c2a6c74a89bce0a1360f2939c1ed8b`

**冻结标准提交：** `35af8d763176705adc844859cd65dc96b087a54c`

**RED 原始证据提交：** `d0e9627f6961c62af432b9abf40cd5fcc22fae4c`

**实现提交：** `c4335c186dd93b505d15f15c5ffa322ae245cd4a`
**最终证据提交：** 本报告随最终证据提交进入 main；该提交 SHA 在交付回报中给出。

## 交付结果

M2-03 在 Domain 内新增了本地 S2 受控交接。只有当前可信 SUPPORT Task owner 在 Web 明确确认并通过 Domain 的最终核验后，冻结申请草稿才会进入本地接收队列。首提交、幂等身份、Queue Entry、不可变 HandoffReceipt、Task 投影和 Domain Outbox 在同一个 SQLite `BEGIN IMMEDIATE` 事务内提交。业务唯一键为 `(tenant_id, task_id, handoff_kind)`，可抵御不同 operation ID 和不同进程竞争。

最终真实浏览器 run 为 `runs/browser-07/`，在实现提交 `c4335c186dd93b505d15f15c5ffa322ae245cd4a` 上执行。Microsoft Edge 使用真实 DeepSeek `deepseek-flash` 和 MCP Investigator，经历初始自然语言调查、正式关键纠错、新 Run/Request、当前 DiagnosisReceipt 与冻结 Draft、用户确认提交、接收回执展示及只读结果追问。两个页面并发提交同一 operation ID；首请求在 Domain 已提交后丢弃 HTTP 响应，另一请求得到幂等回放。页面刷新后仍保留 operation ID，并从 Domain 回查相同 Receipt。

这次运行的结果为：首次提交 HTTP **202**，幂等回放 HTTP **200**；Queue Entry、HandoffReceipt 和 `S2_HANDOFF_ACCEPTED` Outbox 各 **1**。真实 HTTP/Authz 证据仍为 403；`scope_authorized=false`、`recovered=false`。追问说明请求等待人工审查，尚未授权、业务没有恢复。Scope/Policy 表数量与提交前相同，运行期授权写入为零。

最终真实轨迹的主要关联 ID：

- Task `task-edf6da86-2351-460a-a15b-4f5476b6e98a`，Session `session-90ed4970-c677-4067-b62b-c2a94fb1d561`。
- Request 链：初次 `fb493d84a78ba39f` → 独立真实 403 纠错线索 `c8ef68dd858fe571` → 更正后 Investigator 请求 `e35db77ac675378c`。
- 更正 Run `run-40b0bcf5-fcc8-4c03-a5c6-ed38d0bda034`，冻结 Draft `s2-draft-1e7e97cc-28c5-4f4d-b785-2df3362c6edc`。
- operation ID `8174263f-e0a7-459e-bafd-2ba0b346145e`，Queue Entry `s2-queue-2accff7c-c83e-4091-a9a9-54e9ce1d4983`，Receipt `s2-handoff-1ea789e5-c7ab-4a87-8dea-fe6ffc7ce36f`。

浏览器画面： [用户可见的 Receipt 与回查状态](runs/browser-04/screenshots/03-accepted-receipt.png)、[刷新后的最终 Domain 状态](runs/browser-07/screenshots/03-accepted-receipt.png)、[只读结果追问](runs/browser-07/screenshots/04-readonly-result-followup.png)。Browser-04 的 Receipt 画面来自同一实现与相同 UI 提交路径；Browser-07 在最终实现提交上补验了 reload 持久性。

## 冻结验收矩阵

| 门禁 | 结果 | 新鲜证据 |
|---|---|---|
| M203-01 冻结标准先于 RED/实现；冻结摘要有效 | PASS | [ACCEPTANCE_PLAN.md](ACCEPTANCE_PLAN.md)、[FROZEN_SHA256SUMS.txt](FROZEN_SHA256SUMS.txt)、`runs/freeze-check-01/CHECKS.json` 与 `commit-order.txt`，7 个摘要均复核通过；冻结提交早于 RED 和实现。历史 M2-02 资料未修改或暂存。 |
| M203-02 Draft 未提交时无队列副作用 | PASS | `runs/browser-07/RESULTS.json` 的提交前 Domain snapshot；`tests/test_m2_03_handoff.py`。 |
| M203-03 可信 owner 显式提交并原子入队 | PASS | `runs/browser-07/RESULTS.json` 与 Domain trace；Queue/Receipt/Outbox 各 1，Scope 未变化。 |
| M203-04 响应丢失与幂等回查 | PASS | Domain replay 测试；真实浏览器丢弃已提交响应，回查同一 Receipt。 |
| M203-05 同 key 异 payload 拒绝 | PASS | `test_m203_05_same_operation_with_changed_payload_is_rejected_without_side_effects`。 |
| M203-06 两标签页、不同 operation ID、跨进程争用 | PASS | 独立 OS 进程屏障测试；不同业务请求测试；Browser-07 两页共享同一 operation ID。 |
| M203-07 Policy/Grant/Principal/Probe 过期后旧 Draft 失效 | PASS | `test_m203_07_*` 定向测试。 |
| M203-08 关键更正/Abort 与提交竞争 | PASS | `test_m203_08_*` 覆盖更正或 Abort 先提交、交接先提交的两种裁决。 |
| M203-09 非 owner、APPROVER、跨租户及伪造输入拒绝 | PASS | 真实 FastAPI 路由权限负例和严格 Schema 测试。 |
| M203-10 Origin/CSRF/可信身份与稳定 Web operation | PASS | Web API 测试；Edge 刷新后 localStorage operation ID 和 Receipt 均稳定；聊天追问不执行交接。 |
| M203-11 事务中途故障和提交后响应丢失 | PASS | 三个提交前 failpoint 全回滚；提交后丢响应重放返回原 Receipt。 |
| M203-12 真实浏览器完整旅程 | PASS | `runs/browser-07/`：Edge、Provider、MCP、HTTP、正式更正、当前 Draft、双页提交、Receipt 和结果追问。 |
| M203-13 72 小时超期只读投影 | PASS | 虚拟时间测试确认 OVERDUE 不改 Receipt、不触发 Worker/自动授权。 |
| M203-14 回归与独立 smoke | PASS | 完整 pytest 186/186；真实 MCP stdio、M2-01 HTTP/MCP、S1 401→200、前端构建和 lint 通过。 |

## 验证命令与依赖

- 全量回归：`.venv\Scripts\python.exe -X utf8 -m pytest -q --tb=short --basetemp=.runtime/m2-03-full-02` → **186 passed**，150.85 秒。日志见 `runs/full-02/pytest.log`。
- 定向交接与 S2 回归：`.venv\Scripts\python.exe -m pytest tests/test_m2_03_handoff.py tests/test_m2_01_facts.py tests/test_m2_02_s2_diagnosis.py -q --tb=short --basetemp=.runtime/m2-03-impl-06` → **29 passed**。原始日志见 `runs/green/impl-06/pytest.log`。
- 真实 MCP stdio：`.venv\Scripts\python.exe -X utf8 -m opspilot.smokes.m2_s2_mcp` → PASS。默认 tools/list 4 个工具，S2 opt-in tools/list 5 个工具；真实 HTTP 403，可信 Authz Decision=`SCOPE_INSUFFICIENT`，越界 request_id 被拒。
- M2-01 HTTP/MCP 回归：`.venv\Scripts\python.exe -X utf8 -m opspilot.smokes.m2_01_facts --output docs/evidence/vnext/m2-03/runs/m2-01-facts-01/TRACE.json` → PASS；HTTP 401/403/200，运行期 Scope 写入 0。
- S1 业务 smoke：`.venv\Scripts\python.exe -X utf8 -m opspilot.smokes.s1` → PASS；同一绑定业务调用由 401 转为 200，响应 `order_id=demo-order`、`status=CONFIRMED`；DISABLED 负例仍为 401。
- 前端：`npm --prefix frontend run build` → PASS（vue-tsc、Vite 8.3.4）；`npm --prefix frontend run lint` → PASS。
- 最终 Edge run 的 6 次 Investigator Provider 调用共回报 **17,531 tokens**；1 次 CHAT_READONLY 共 **3,467 tokens**。模型、调用级 usage、MCP observation、Gate、Evidence、Receipt、Outbox、请求状态和 SSE 事件见 [TRACE.json](TRACE.json) 与 `runs/browser-07/RESULTS.json`。

本次锁定/运行环境：Python 3.14.0、pytest 9.1.1、LangGraph 1.2.16、langchain-openai 1.7.2、MCP 2.3.0、FastAPI 0.137.1、Pydantic 2.14.1；Node v24.16.0、npm 11.13.0、Vue 3.5.44、Vite 8.3.4、TypeScript 5.9.3、Playwright 1.64.1。锁定文件仍为仓库既有依赖文件，本阶段没有新增运行依赖。

## 失败记录、已知限制与安全边界

首次全量 pytest 的 184 passed/2 failed 来自两处历史 schema 版本断言仍期待 v7；更新为 v8 后完整 186 项新鲜通过。新增真实浏览器旅程中曾出现两次自然语言否定措辞词表过窄和一次跨行字段标签误报，全部原样保存在 `runs/browser-02/03/05/` 并详见 [FAILURES.md](FAILURES.md)；最终按句/行和否定上下文判定后，Browser-07 通过。早期系统 Python 缺少 `mcp`、新增测试 oracle/harness 失败和 ESLint 浏览器全局错误也均保留原始日志及修复说明，没有隐藏失败。

本地 Queue 仅是 SQLite 演示接收队列，没有真实人工审核工作台、远端 ITSM 或企业权限集成。M2-03 不做人工审批处理、Scope 自动授予、业务恢复或 S2 自动完成；本地事务幂等不能宣传为跨系统 exactly-once。S1 的真实 401→200 smoke 是独立业务闭环，不代表 S2 的 403 已修复。演示身份不构成生产 IAM。证据文件已扫描 Provider API key，未发现密钥；Cookie、CSRF 和本地随机口令未写入 Trace。

源码阅读笔记见 [SOURCE_STUDY.md](SOURCE_STUDY.md)，面试问答见 [INTERVIEW_QA.md](INTERVIEW_QA.md)。本报告只提交主 Agent 复核，不启动 M3。
