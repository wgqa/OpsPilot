# M1-05 失败尝试与修复记录

所有尝试都保留在 `runs/<UTC-stamp>/`，包括原始浏览器/API 日志、事件与 Domain 安全快照、截图及该次机器结果。快照只包含字段白名单；没有提交 `.env`、授权凭据或原始 SQLite 文件。

| 时间 | 结果 | 发现与处理 | 原始证据 |
|---|---|---|---|
| `20261018T095512Z` | FAIL，UI selector | 调查与只读浏览器步骤通过；审批脚本等待 Support 页面专有的 `.rail-footer`，而独立审批页面使用 `.approval-center`。调整脚本为按角色页面定位，不改业务代码。 | [`RESULTS.json`](runs/20261018T095512Z/RESULTS.json)、`logs/edge-approval-response-loss.attempt-01.txt` |
| `20261018T095638Z` | FAIL，恢复重试耗尽 | 审批事务和两个 crash failpoint 都到达；REPAIR 已 COMMIT 为 v7→v8，但恢复 Run 最终 `WORKER_RETRY_EXHAUSTED`，快照只有一条 REPAIR、没有 VERIFY/REPORT/DELIVER。定位到 resume 标记同时由 LangGraph `Command.update` 与被中断节点返回，触发重复 state channel 写入。改为仅从原节点返回标记；原子 Domain 守卫和 ActionIntent 未改变。 | [`RESULTS.json`](runs/20261018T095638Z/RESULTS.json) 中间/终态快照，`logs/api-repair-crash.log`、`logs/api-recovery-process.log` |
| `20261018T095941Z` | 业务成功，smoke assertion FAIL | Edge、Provider、MCP、HTTP 验证、报告和工单均成功。APR-08 检查把等待前预算与业务完成后的预算比较，混入后续执行时间。改为比较只读追问前后、审批等待暂停后的同一预算值。 | [`RESULTS.json`](runs/20261018T095941Z/RESULTS.json)、对应四份 Edge 日志与截图 |
| `20261018T100221Z` | 主业务 PASS，旧 APR-08 assertion FAIL | 再次形成完整端到端业务事实；该次使用旧预算断言，保留为失败证据。之后更新断言并增加 SSE history/stream 与事件序列检查。 | [`RESULTS.json`](runs/20261018T100221Z/RESULTS.json)、`logs/`、`screenshots/` |
| `20261018T100615Z` | 浏览器/业务 PASS | 新鲜 Edge 实际双角色、两个进程响应丢失窗口及新进程恢复通过；全部浏览器布尔检查为真，截图、历史事件与流事件齐备。页面切换时 EventSource 有一次 `net::ERR_ABORTED`；同一浏览器后续 `/events/history` 和 `/events` 均为 200，持久 `event_seq` 单调且无重复。最终检查见本轮报告。 | [`RESULTS.json`](runs/20261018T100615Z/RESULTS.json)、`logs/`、`screenshots/` |
| 全量 pytest 首轮 | FAIL，环境权限 | pytest 默认扫描用户 Temp 命名目录时收到 Windows `PermissionError: [WinError 5]`，103 项在 fixture setup 失败，12 项完成；没有业务断言失败。将 `TEMP`/`TMP` 与 `--basetemp` 指向仓库 `.runtime` 后新鲜全量通过。 | [`pytest-full-attempt-01-temp-acl.txt`](pytest-full-attempt-01-temp-acl.txt)、最终 [`pytest-full.txt`](pytest-full.txt) |
| APR-05 新增用例首轮 | FAIL，测试会话夹具 | 同一 TestClient 先以 APPROVER 登录，再以之前捕获的 SUPPORT CSRF 头请求 abort；Cookie 已切到 APPROVER，服务端正确拒绝 403。测试改为 abort 前重新登录 SUPPORT，随后 APR-05 用例通过。 | [`pytest-approval-directed-attempt-01-session-fixture.txt`](pytest-approval-directed-attempt-01-session-fixture.txt)、最终 [`pytest-approval-directed.txt`](pytest-approval-directed.txt) |

旧系统 Python 未安装仓库所需 LangGraph；正式运行统一使用仓库 `.venv`。该环境识别阶段没有包含在本次正式 smoke 分母中。所有前端命令均实际执行；未执行的验收项为零。

pytest traceback 和命令回显日志按原样保留了工具输出的空白；未改写原日志。最终 `git diff --check` 对源码、测试、Markdown 与机器结果执行，排除 `.txt` 原始命令输出文件。
