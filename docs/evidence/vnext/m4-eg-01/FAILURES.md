# M4-EG-01 RED 与失败记录

## 有效业务 RED

- `runs/red-sla-05/pytest.log`：冻结的定向用例执行结果为 **5 failed, 1 passed**，退出码 1。
- 四个独立 Chat Readonly 用例在真实 `prepare_chat_attempt()` 出站消息上均未找到同一事件的 PROCESSED、QUEUED/SLA、HTTP 202/UNKNOWN 规则。其 Gate 和当前观察状态已经正确，缺口位于 Chat 解释 Context。
- 版本化 Knowledge 检查发现 `receiver-ack-contract-v2` 仍为 `2.0.0`，内容没有明确规定“当前同事件 PROCESSED 即可证明完成，即使尚未到 SLA”。
- 同次 RED 中 Memory ON/OFF 的实际 Investigator `model_call()` 消息捕获通过：已批准 Memory 可进入目标 Run 的出站上下文，OFF 时不注入且记录 `EVALUATION_MEMORY_OFF`。

## 测试准备失败（保留，但不是业务证据）

- `runs/red-sla-01/pytest.log`：第一次 pytest 的 `--basetemp` 父目录未创建，4 项 setup error；另 1 项因待修复的 Knowledge 断言失败。不能作为业务 RED。
- `runs/red-sla-02/pytest.log`：临时目录问题修正后，测试 harness 错把 `prepare_chat_attempt()` 返回值当成带 `run_id` 的对象，并未先 claim Investigator Run；6 个失败不作为产品结论。
- `runs/red-sla-03/pytest.log`：改正 Run claim 后，S3 测试时钟早于实际 Observation 导致全部证据超前于假时钟；此日志是时钟准备失败，不作为产品 RED。
- `runs/red-sla-04/pytest.log`：统一时钟后，SLA Gate 和当前 Evidence 均通过；Memory 用例的工具名断言错误地要求工具名出现在消息正文，而工具 schema 是模型调用的独立 tool binding；不作为产品 RED。
- `runs/red-sla-05/pytest.log`：最终冻结定向 RED。4 个 SLA Chat Context 规则缺失，Knowledge 版本/内容不满足新合同；Memory 出站测试通过。
- `runs/green-deterministic-01/pytest.log`：首次修复后 4 个 SLA Chat Context 与 Memory 用例通过；1 个 Knowledge 断言遗漏文档中的 Markdown 反引号，属于测试匹配格式问题，修正断言后另目录复跑。
- `runs/green-deterministic-02/pytest.log`：同一格式问题的第二处，断言未包含 `QUEUED` 周围的 Markdown 反引号；属于测试匹配格式问题，继续修正后另目录复跑。
- `runs/provider-prep-failure-01/stdout.log`：首次真实实验 launcher 未设置仓库根 `PYTHONPATH`，在导入 `opspilot` 前退出；没有 Provider 请求。
- `runs/memory-paired-20261025T100214Z/FAILURE.txt`：第二次准备运行完成 Task A 的真实 loopback HTTP/MCP 读取并创建/确认 Memory 后，实验 harness 查询了不存在的 `content_json` 列，退出于第一个 Provider 调用之前；没有 Provider 请求。Schema 实际列为 `experience_json`，已修复 harness 并保留该失败目录。
- `runs/web-memory-20261025T102043Z/stdout.log`：Task A 的 R-policy Web E2E 准备器未加载本地 Provider 配置；`run_investigation()` 在启动 R 策略前要求配置变量存在并退出，未创建 Task 数据，也未发出 Provider 请求。修正为只向隔离进程加载模型配置后重新准备。
- `runs/web-memory-20261025T102107Z/WEB-exit-code.txt` 与 `browser-stale-source-01/WEB-JOURNEY-FAILURE.json`：SUPPORT 浏览器读取了 Task A，但其 Evidence 已超过 300 秒并在 UI 中显示 `S3_CURRENT_FACTS_INVALIDATED` / 0 当前 Evidence。候选未出现是既有失效来源保护的正确结果；这次不能证明初步推断的 S3 UI eligibility 产品缺陷。未创建候选或 Task B，Provider 请求为 0。后续 RED/GREEN 必须使用刚完成、当前性仍有效的来源。

## 本轮新增失败、修复与保留项

- `runs/web-memory-fresh-red-02/`：使用当前有效的 Task A 诊断后，浏览器仍没有显示创建 Memory 候选的合法入口。此时来源 `currentness=CURRENT`，因此才定位为 S3 UI eligibility 缺口。`frontend/src/App.vue` 最小修复后，Task A candidate API 实际返回 201，见 `runs/web-memory-green-02/WEB-JOURNEY-RECONCILIATION.json`。
- `runs/web-memory-green-02/browser.log`：候选创建、APPROVER 确认、Task B 受理与真实调查均已完成，但脚本最后要求 Task A Memory 必须出现在“最新一次模型调用”的 UI provenance，导致退出 1。Domain 的 7 条模型调用历史证明 Memory 在早期调用 `call-8b82f056-9566-409e-b31d-b765f889e7a6` 被选中；当前 Task B Evidence 与历史经验冲突后，后续调用正确排除它。该失败是浏览器断言选择错误，不是调查 Run 失败，仍原样保留。
- `runs/web-memory-green-02/browser-revisit.log` 与 `screenshots/WEB-REVISIT.json`：修正为只读持久结果重访后退出 0；无模型调用。重访发生在 Task B Event SLA 已到期之后，页面正确标为历史/当前性失效，不能当成 SLA 前即时 UI 截图证据。
- `runs/web-memory-green-02/reconcile.log`：证据关联器首次查询使用了不存在的 `created_by` 字段；修正 schema 查询后，第二次提示 `d2_tool_observations` 不含直接 `run_id`。随后按实际 schema 由 attempt 关联 Run；最终 `reconcile-green.log` 退出 0。首次 schema 错误是工具准备问题，没有更改业务数据库。
- `runs/full-pytest-01/pytest.log`：第一次全量为 368 passed / 3 failed。两个失败是本轮测试环境/路径缺陷：HF stale-Gate 子进程缺少仅供配置守卫的 deterministic 占位变量；VS-08 测试硬编码已退役的 Knowledge 文件名。各新增最小修复后，独立定向测试分别 1 passed，第二次全量中均不再失败。第三个失败是既有 C1 RED，保留未修。
- `runs/full-pytest-02/pytest.log`：新鲜全量回归为 370 passed / 1 failed。唯一失败 `tests/test_m4_autonomy_c1_red.py::test_explicit_protocol_followup_is_accepted_as_same_task_readonly_run_before_ttl_fix` 返回 502 `INVALID_MODEL_CLASSIFICATION`。这属于此前 C1 follow-up 行为 RED；本轮没有修复，整体测试状态不得报全绿。
- `runs/historical-trace-rerun-20261025/`：为核对旧 C1 JSONL 测试副作用，新鲜单项重跑了两个 deterministic RED 测试；结果 1 failed / 1 passed。该重跑实际生成的两行已归档至 `pytest-created-historical-traces.jsonl`，随后恢复了两个既有 C1 JSONL 到基线内容。run 01 的 pytest 临时附加行也已归档。run 02 的附加行在行结束符比较准备失败后被恢复，未能逐字保存；相同两个测试的隔离重跑 Trace 已保存，但不冒充 run 02 原行。历史文件恢复到 HEAD，原历史内容未改写。
- 最终脱敏扫描发现浏览器运行脚本内嵌了本地演示登录口令。已改为从 `OPSPILOT_EG01_SUPPORT_PASSWORD` 与 `OPSPILOT_EG01_APPROVER_PASSWORD` 进程环境读取，未把值复制进证据；`runs/harness-syntax-check/` 中两份 Node 脚本语法检查均退出 0。扫描后未发现证据目录含模型密钥、Bearer token 或硬编码口令。
- 一次本地验证命令误把 Python `build_trace_index.py` 交给 `node --check`，Node 因 `.py` 扩展报 `ERR_UNKNOWN_FILE_EXTENSION`。原始记录在 `runs/harness-syntax-check/incorrect-node-python-check.log`；这是验证器选错 parser 的准备错误，不是源码失败。随后以 Python AST 解析该脚本并分别 `node --check` 两个 `.mjs`，结果均为 0。
- 全量 pytest 在 `runs/*/basetemp/` 与 `pytest-temp/` 生成临时 SQLite fixture（约 783 MB / 747 MiB）。自动化审查拒绝了递归删除命令；这些目录保留在当前隔离工作树且不会提交，原始 pytest 日志、失败 trace 与结果摘要均单独保留。
- 原始 pytest `.log` 中有框架输出的尾随空格。日志按原样保留；源码、报告和非日志证据另行执行 whitespace 检查，不对原始运行日志做格式化。

所有失败目录与 raw logs 保留；不能把测试准备失败作为业务 RED，也不能把已识别的 C1 RED 从结果分母移除。

所有失败日志均原样保存；后续 GREEN 使用不同的运行目录，不覆盖以上文件。
