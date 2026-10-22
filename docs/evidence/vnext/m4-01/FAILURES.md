# M4-01 失败与修复记录

保留所有原始失败日志、浏览器脚本 stderr 和中间尝试。早期失败用于界定实现问题与验收假设；它们未从证据目录删除，也没有被改写为通过。

| 尝试 | 结果 | 原因与处理 | 原始记录 |
|---|---|---|---|
| 冻结先行 RED-01 | pytest 在收集前失败 | basetemp 父路径不可用；重新指定本仓库隔离目录后进入测试。 | `runs/red-01/` |
| 冻结先行 RED-02 | 8 failed | 冻结的 API 断言在实现前得到 404，证明验收测试先于实现。 | `runs/red-02/pytest.log` |
| GREEN-01 | 8 failed | 初版 Session 关联查询误从 TaskBinding 读取 `session_id`，该列不存在，导致 500。改为由 Domain 的 `session_task_links` 解析 owner Session。 | `runs/green-01/pytest.log` |
| GREEN-02 | 8 passed | 修复 Session/Task 关联后，冻结验收集转绿。 | `runs/green-02/pytest.log` |
| SAFETY-01 | 11 passed, 1 failed | 安全快照测试假设 `task_bindings.route` 存在；实际 route 由受信 Service 绑定。测试改为联查 Services。 | `runs/safety-01/pytest.log` |
| SAFETY-02 | 11 passed, 1 failed | 测试只接受跨租户 404；实际 Web 明确返回 403。两种状态均符合拒绝访问，随后断言状态码与错误码都为安全拒绝。 | `runs/safety-02/pytest.log` |
| SAFETY-03 | 12 passed | 修正安全快照后，定向安全测试通过。 | `runs/safety-03/pytest.log` |
| 初版全量系统 Python | 13 collection errors | 默认系统 Python 未安装仓库 LangChain/MCP 依赖。改用锁定仓库虚拟环境运行；这是环境选择错误，不作代码通过记录。 | `runs/full-01/pytest.log` |
| 初版全量 `.venv` | 239 passed | 实现阶段快照通过；随后新增一个 S1 Gate 投影回归并修复真实浏览器发现的问题，因此以最终 `full-02` 为最终全量结果。 | `runs/full-01/pytest-venv.log` |
| 首轮真实 Edge，S1 | failed closed | 较含蓄的“可能是 403”用语被 DeepSeek 判为 `HYPOTHESIS`，没有改变 Task，也未创建 Run。该结果符合不确定即不正式纠错的冻结规则。浏览器实验改用用户真实能表达的明确纠错，独立记录在后续尝试。 | `runs/web-20261022T165321Z/s1_401/`，包括 `TRACE.json`、`journey-browser.attempt-01.log` 与截图 |
| 首轮真实 Edge，S2 | 断言失败 | 脚本把确认受理和后续关键输入应用当成同一次 revision 递增；已验收 TaskControl 对两步分别记 revision（受理 +1、应用 +1）。脚本改为分别验证这两个版本。业务动作未重复。 | `runs/web-20261022T165321Z/s2_403/` |
| 第二轮真实 Edge，S1 | 断言失败 | Domain 已保存实际 401、新 Run 和 S1 证据；Inspector 把 S2 的 `NOT_APPLICABLE` 状态覆盖到当前 Gate。最小修复为仅在 S2 Gate 适用时覆盖 S1 Gate，并新增回归测试。 | `runs/web-20261022T165916Z/s1_401/` |
| 第二轮真实 Edge，S2 | 断言失败 | 底层同请求 Probe/授权 Evidence、Gate、DiagnosisReceipt 已一致；公开的 S1 Evidence 列表不包含 S2 Scope Evidence，故浏览器断言读错投影字段。脚本改用 Gate+Receipt ID 关联，Runner 直接校验 SQLite Evidence 与持久 Authz Decision 的 Request ID、Decision ID、拒绝根因和同一 Run。 | `runs/web-20261022T165916Z/s2_403/` |
| targeted pytest 默认 Temp | 13 setup errors | Windows 用户级 pytest Temp 根目录拒绝遍历。所有定向与最终全量 pytest 均显式使用 `docs/evidence/vnext/m4-01/runs/...` 独立 basetemp；可用 basetemp 运行通过。 | 初始完整错误保存在本轮执行记录；重现日志写入 `runs/temp-root-01/pytest.log` |
| 构建日志采集路径 | 采集失败 | 首次在 frontend cwd 创建了错误的空目录，Tee 输出目标不存在，未把这次结果当成通过。已移除本次误建的空目录；从仓库根目录以 `npm --prefix frontend run build` 重跑，正式日志 exit0。 | `runs/frontend-build-03/CAPTURE_FAILURE.md` 是工具错误输出转录；正式原始日志为同目录 `build.log` |
| 真实 Provider Gold，提示 v1 | 8/10 | M401-09 与 M401-10 明确修订先前调查前提，但没有给出新的确定值，旧提示把它们漏判为 FOLLOW_UP。Gold 未修改；提示 v2 补充“明确修订前提并要求重新调查也可提出纠错”，仍不自动提交。 | `runs/intents-20261022T171607Z-c0fa8d67/RESULTS.json`、`intent-matrix-01.log` |
| 真实 Provider Gold，提示 v2 | 10/10 | 同一冻结 Gold 新鲜重跑，全部匹配；每条重放复用评估 ID，没有创建关键输入、额外调查 Run 或动作 Intent。只证明这十条冻结样本，不作为未见表达的泛化准确率。 | `runs/intents-20261022T171819Z-ce631d9c/RESULTS.json`、`intent-matrix-02.log` |

提示 v1 的两组真实浏览器通过记录是 `runs/web-20261022T170532Z/RESULTS.json`，完整回归为 `runs/full-02/pytest.log`。提示 v2 的最终运行入口由顶层 `REPORT.md` 与 `RESULTS.json` 指定。主 Agent 应分别审阅失败记录和最终通过记录；本文件不宣告阶段独立验收结论。

补充记录：`web-20261022T171819Z` 两组底层旅程通过，但 403 截图早于前端轮询完成提示；未把该截图当作最终提示证明。脚本加入显式等待页面“重新调查已结束”和实际 Probe 状态，`web-20261022T172814Z` 两组重新通过。全量 `full-03` 为 240/240；补齐终止 Task 和真实完成 S1 Task 的两项提议拒绝负例后，最终 `targeted-03` 为 15/15，`full-04` 为 242/242。

证据整理的首次聚合脚本遇到旧 `PREPARATION.json` 未记录 `runtime_directory`，在任何结果写入前抛出 `KeyError: 'runtime_directory'`；之后显式绑定两份已知原隔离数据库路径，只读补齐 `DOMAIN_SNAPSHOT.json`。该错误不涉及功能运行，未改旧浏览器失败文件或业务数据库。
