# OpsPilot vNext M1-03 实施与运行报告

**状态：** M1-03 功能与回归用例已完成，提交推送后交主 Agent 独立审查。该结果不表示完整 M1、Web 审批或 D1–D7 之外的目标已验收。

## Git 与范围

- 起点：`main@9d49e726f75e49cab23efc93ff472b36c560dcf0`；开工时已跟踪源码干净，`origin/main` 与该 SHA 相同。`开发目录/` 中已有用户任务资料处于未跟踪状态，本轮保持原样。
- 源码、测试和运行证据提交：`a87f902b8440fdaa5f72cd65c79ce6add0bf2336`。本报告随后作为交付审计材料提交；最终推送 SHA 由交付回报中的 `git rev-parse HEAD` 确认。
- 开发分支：`main`。仅实施 M1-03；未实现 M1-04/M1-05，也未变更冻结架构合同。
- 用户提供的 `开发目录/` 文件保持未跟踪，未暂存、修改或删除。`.env`、本地数据库、`.runtime`、venv 和 `node_modules` 未提交；证据目录的密钥格式扫描未发现 API key 或 Bearer token。

## 交付内容

- `frontend/`：Vue 3、TypeScript、Vite 三栏对话工作台，提供 Session 列表与恢复、流式聊天、Task Inspector、角色感知控件、错误提示及有限 SSE 重连。
- `opspilot/domain/chat.py`：只读聊天上下文、证据与来源重核、ContextManifest、持久模型 Attempt/Chunk、单一最终 Answer 回执和受作用域保护的读取。
- `opspilot/web/worker.py`：将持久 `CHAT_READONLY` Run 分派到独立真实模型路径；业务 `INVESTIGATE` 仍复用原 LangGraph/D2 流程。聊天不 resume 或改变业务 Graph。
- `opspilot/domain/database.py`：Domain SQLite v3 的聊天 Attempt、Context Manifest、来源、Chunk、Answer 回执和恢复字段；迁移回归通过。
- `opspilot/web/app.py`、`server.py` 与 `domain/events.py`：Session 消息/Run/Chunk/检查器 API、权限检查、SSE 投影与明确本地 UI Origin。
- `opspilot/smokes/m1_03.py`、Playwright 浏览器驱动、`tests/test_m1_chat.py` 与 HTTP/Worker 回归；学习材料见 `docs/learning/M1-03/` 和 `HANDBOOK_MAP.md`。

## 验收矩阵

`docs/evidence/vnext/m1-03/RESULTS.json` 提供机器可读的 CHAT/UI 矩阵、调用轨迹和计数；最新独立真实浏览器运行是 `20261018T071635Z`。

| 用例 | 结果 | 证据摘要 |
|---|---|---|
| CHAT-01 | PASS | Edge 中连续三轮无 Task 真实模型对话；第三轮正确复述 `BLUE-ORBIT`，并说明该标签来自用户消息。三轮聊天截图和每个模型 Attempt/response ID 均已留存。 |
| CHAT-02 | PASS | S1 Task 的只读回答引用实际 `cred-v1`、`principal-a ENABLED`、Policy 接受 `cred-v2` 和固定业务路由 HTTP 401；显示相应 Evidence ID。 |
| CHAT-03 | PASS | 浏览器发送“我已批准/立即替换凭证”后，真实模型说明聊天文本不是审批。操作前后 Plan hash、control revision、`WAITING_APPROVAL` Task 状态一致；审批、Intent、Permission、Ledger、验证、报告和交付写入均为 0。 |
| CHAT-04 | PASS | N1-10 回归验证显式 `CORRECT_TASK_INPUT` 使旧运行/Plan 失效；CHAT-04 定向测试验证依赖已撤销 Memory 的历史助手消息不会回注，排除原因进入 ContextManifest。普通只读回答另由 CHAT-03 的状态快照保护。 |
| CHAT-05 | PASS | HTTP 幂等与单 Run 单 Answer 回归通过；最终运行记录为 5 个成功聊天 Run、5 个最终助手答案，无失败或重复答案。 |
| CHAT-06 | PASS | Edge 在 Run 仍为 RUNNING 且有增量 Chunk 时刷新，随后恢复最终答案；API 进程重启后恢复同一 Session。最新记录含 541 个持久 Chunk、SSE event_seq 1–561。 |
| CHAT-07 | PASS | 跨租户 Session 读取返回 404；Approver 只读检查器返回 200；未列入的浏览器 Origin 写入返回 403。Cookie 身份、CSRF、租户和 SSE 作用域有定向 HTTP 测试。 |
| CHAT-08 | PASS | 新鲜全量 pytest 101/101 通过；包含 M1-01 N1-09/10/11、M1-02、D1–D7 回归。真实 S1 调查停在 `WAITING_APPROVAL`，聊天未写业务状态。 |
| UI-01 | PASS | Microsoft Edge 真浏览器完成登录、创建/恢复 Session、真实 Provider 增量回答、查看 Run/Evidence、流式中刷新和服务重启恢复。截图位于 `screenshots/`。 |
| UI-02 | PASS | 页面实际映射 401/403/409/超时错误；Approver 看不到 Support 专用建 Task 控件；跨 Origin 写请求被拒绝。 |

CHAT-04 中的显式纠错事务和撤销来源检查分别由既有 N1-10 业务回归与 M1-03 新增 Context 回归证明；本轮没有通过聊天 UI 提交业务关键更正，也没有在聊天中引入审批控件。

## 真实运行证据

最新 Edge smoke 由真实本机 API、Vite 页面和配置的模型供应商运行，没有用 TestClient 替代浏览器或用模板冒充回答。S1 调查调用真实 DeepSeek-compatible `deepseek-flash` 模型和真实 MCP Client/Server；MCP `get_integration_config`、`get_principal_status`、`get_auth_policy`、`probe_endpoint` 各有一次成功观察，Domain 保存四条同 Task Evidence。在线探针请求 `/api/orders/demo-order` 得到 401；只读聊天随后如实解释 `cred-v1` 与 `cred-v2` 不匹配，并保留 `WAITING_APPROVAL`。

本次聊天模型 Attempt 为 5/5 成功，0 次模型失败，输入/输出 Token 为 2,872/1,131（共 4,003）。每次调用均有 Provider correlation ID、状态、Token 和 Prompt digest，完整脱敏记录见 `RESULTS.json`。S1 Investigator 另有 5/5 次真实模型响应，输入/输出 Token 为 11,706/912（共 12,618），对应真实 MCP 调查轨迹。浏览器结果包含一组回答原文、真实 HTTP 响应、重启前后 PID、Run/Message 数和事件游标。

完整重跑入口（需要本机 `.env` 已配置模型参数、Python venv、Node/npm 与 Microsoft Edge；脚本会创建临时 DB 和本地演示登录凭据）：

```powershell
$env:TEMP = (Resolve-Path .runtime/pytest-tmp).Path
$env:TMP = $env:TEMP
$env:TMPDIR = $env:TEMP
.venv/Scripts/python.exe -X utf8 -u -m opspilot.smokes.m1_03 --evidence-dir docs/evidence/vnext/m1-03
```

前端单独检查，在 `frontend/` 下运行：

```powershell
npm ci
npm run typecheck
npm run lint
npm run build
```

前后端、锁定依赖、实际安装版本、运行命令输出分别保存在 `logs/environment.txt`、`logs/backend-dependencies.txt`、`logs/frontend-dependencies.txt`、`logs/pip-check.txt`、`logs/pytest-full.txt`、`logs/pytest-targeted.txt` 和 frontend 三项检查日志中。Python 为 3.14.0；FastAPI 0.137.1、Uvicorn 0.49.0、LangChain Core 1.6.12、LangChain OpenAI 1.7.2、LangGraph 1.2.16、SQLite Checkpointer 3.1.2、MCP 2.3.0、HTTPX 0.28.1、pytest 9.1.1；`pip check` 无依赖冲突。前端 Node 24.16.0、npm 11.13.0、Vue 3.5.44、Vite 8.3.4、TypeScript 5.9.3、Playwright 1.64.1，依赖以 `frontend/package-lock.json` 锁定。

## 新鲜验证与失败分母

| 检查 | 结果 | 实际命令 / 证据 |
|---|---|---|
| 全量回归 | PASS 101/101，55.95 秒 | `pytest -q -s --basetemp=.runtime/m103-full-20261018`；`logs/pytest-full.txt` |
| M1-03 定向回归 | PASS 36/36，12.78 秒 | `pytest -q -s tests/test_m1_chat.py tests/test_m1_task_control.py tests/test_m1_web_api.py tests/test_m1_web_events.py tests/test_m1_web_server.py tests/test_m1_worker_recovery.py --basetemp=.runtime/m103-targeted-20261018`；`logs/pytest-targeted.txt` |
| Vue 类型检查、lint、build | PASS | `frontend/` 中依次运行 `npm run typecheck`、`npm run lint`、`npm run build`；各自原始输出在 `logs/frontend-*.txt` |
| 依赖完整性 | PASS | `.venv/Scripts/python.exe -m pip check` 输出 `No broken requirements found.` |
| 真实模型/MCP/浏览器 | PASS（最新独立运行） | `RESULTS.json`、`screenshots/` 与编号运行日志；5 个聊天调用和 5 个 Investigator 调用均带 response ID。 |

实现过程中共有 8 次 smoke 检查失败，原因和后续修复逐项写在 `logs/FAILURE_HISTORY.md`，编号快照和可用的原始浏览器/API/Vite 日志保存在 `logs/runs/`。前两次浏览器运行共用 `browser-full.txt`，在 harness 加入编号轮转前被后续尝试覆盖；其错误详情来自当时捕获的命令输出，无法再恢复为原始 stdout。因此功能失败历史已如实计入，但“首次两次原始浏览器日志归档”这一证据要求未完全满足。其余检查失败记录未被从分母删除；最新一次独立运行才标为 PASS。早期 Provider 调用本身成功，但提取/保存 correlation ID 的检查失败；修复后最新运行中所有 5 个聊天调用和 5 个 S1 Investigator 调用均留有 Provider ID。

## 持久状态、安全边界与已知限制

- `CHAT_READONLY` 从 Domain 读取当前有权 Context，写入聊天 Run/Attempt/Chunk/Answer/来源回执；不调用 Investigator Graph resume，不改变业务 Task、TaskControl、Plan、审批、ActionIntent 或 D3 Ledger。真实浏览器对抗输入的前后快照相同。
- 用户身份由现有本地 HttpOnly Cookie 派生；消息 POST 检查 CSRF 与精确 Web Origin；API/Domain 在读取 Session、消息、Run、Chunk、Evidence 和 Context 来源时核验租户与权限。模型不能提交 actor、tenant、凭证或任意 URL。
- S1 是固定 `orders-demo / integration-a` 场景，首条自由文本尚未驱动业务调查图；这是任务卡明示限制，动态自然语言调查与工具选择属于 M1-04。页面显式展示固定场景提示。
- 审批、REPAIR 与 DELIVER 的 Web 写入口不在本阶段；Task 只读显示等待审批状态，不能将聊天回答宣传成恢复成功或业务完成。
- M1-02 schema 审计单独记录于 `logs/m1-02-schema-audit.md`：其 RESULTS 中 `schema_version: 1` 是结果 JSON 格式版本；SQLite 历史迁移 `PRAGMA user_version=2`，本轮迁移后为 3。历史 `RESULTS.json` 与日志未修改。
- 手册源码映射在 `docs/learning/HANDBOOK_MAP.md`；设计取舍和源码阅读见 `docs/learning/M1-03/STUDY_NOTES.md`，面试问答见 `INTERVIEW_QA.md`。

本轮交付后停止开发，等待主 Agent 独立审查；不自行进入 M1-04 或 M1-05。
