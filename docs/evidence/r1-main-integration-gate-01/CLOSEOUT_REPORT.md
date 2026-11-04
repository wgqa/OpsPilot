# R1 全量 pytest 停滞诊断补充

**状态：** ACCEPTANCE_CANDIDATE
**主线建议：** HOLD
**范围：** 测试生命周期诊断、现行 Follow-up 复核、历史 SQLite 安全复核；无业务源码修改。

## 基线

- Repo: wgqa/OpsPilot
- 诊断开始候选: codex/r1-main-integration-gate-01@aafa2149c87e3f6be3a80275ea44a0c2a2eaf895
- 远端 main: ec8c3582f6d145eec9979c43607302731411ead8，未变化
- Windows / Python 3.14.0 / pytest 9.1.1 / AnyIO 4.15.1 / LangSmith plugin 0.14.11
- Provider 请求、外部 MCP 请求、业务写入均为 0
- North Star、AGENTS、Skill 与冻结合同均从本轮候选实际重读；Blob 见原报告开工表。

## 停滞定位

受控全量命令：

    D:\学习gent新项目\.venv\Scripts\python.exe -m pytest -vv -s -o faulthandler_timeout=60 --tb=short --basetemp D:\学习gent新项目\.pytest-r1-closeout-full-20261104-01

收集 675 项，按原始顺序到约 31% 时停止输出。60 秒 faulthandler 捕获主线程路径：

    concurrent.futures.Future.result
    anyio.from_thread.call
    starlette.testclient.TestClient.wait_shutdown
    contextlib exit/close
    starlette.testclient.TestClient.__exit__
    tests/test_ar03_material_remainder_01.py:371
    test_remainder_repeated_same_tool_can_cross_old_ten_mcp_limit_in_formal_worker

可证实停在 TestClient 退出等待 ASGI lifespan shutdown。pytest 使用 -s，faulthandler 实际输出线程栈，因此不是仅由输出缓冲造成的假象。

临时 Domain SQLite 只读状态：task_run SUCCEEDED；chat_attempt SUCCEEDED；assistant_calls 23 条（12 MODEL、11 MCP）全 OK；d2_attempts 11 条，均为 get_callback_delivery 且 OK。当前线程栈没有 SQLite 查询/锁等待或 MCP 调用帧。AnyIO loop 在线程 selector 等待，worker/executor 线程在队列等待。没有捕获具体未完成 asyncio Task；没有停滞期间子进程快照，不能排除短暂子进程生命周期因素。

| 执行 | 结果 |
|---|---|
| 6 个前置 + 目标 + 下一个 QUEUED Worker 测试 | 8/8，13.31s，exit 0 |
| 目标独立运行 | 1/1，约 4.89s，exit 0 |
| 原顺序截至目标的 instrumented prefix | 213/213，198.84s，exit 0；task dump 插件改变调度，不代表全量 PASS |
| 现行合法 Follow-up + MCP | 1/1，4.87s，exit 0 |

全量复跑在栈捕获后人工停止，无 pytest summary；本地记录没有可核验的最终进程退出码。没有再启动第三次全量测试。 目标测试没有由 pytest 报 PASSED；停滞发生在 TestClient with-block 退出，with 之后的测试断言未执行。直接读取临时数据库仅作为旁证，不能替代这些断言。

**根因边界：** 已证实阻塞位置是 TestClient lifespan shutdown 等待；未证实具体 ASGI 子任务、Worker cancellation、线程工作项、MCP 清理或先前测试留下的全局状态。不能把单测通过当作整套无问题，也没有依据断言生产 Worker 一定有缺陷。本轮未做猜测性生产修复。

## C1 RED 与现行合同

历史 test_explicit_protocol_followup_is_accepted_as_same_task_readonly_run_before_ttl_fix 仍使用废弃 READONLY_FOLLOWUP。当前合同为 FOLLOW_UP + readonly_action=INVESTIGATE。保留历史 RED，不加兼容分支。

新鲜现行正例通过正式 API 建立同 Task 只读 Run、执行 search_callback_knowledge MCP、持久化 ANSWERED 与 Knowledge 来源；同 Operation 重放复用原 Run/结果，并核对 TaskControl、旧 Diagnosis、ActionIntent/Ledger/Handoff 不变。日志见 runs/pytest-current-followup-positive-20261104.log。

## SQLite / 公开数据

三个授权 SQLite 只读打开，quick_check 均为 ok；表仅为 authorizations/attempts，不含客户、订单或联系人表。数据库字段扫描 API-key-like、Bearer、私钥、邮箱均为 0。宽松数字模式命中项经逐列复核是模拟实验授权 ID 或 ISO 时间戳，无真实电话或客户数据。沿用已有 1,027 个 Git blob 扫描结论：未发现可确认真实凭据。哈希和结构见 runs/sqlite-public-assets-audit.json。

按当前任务的数据分类，这些是模拟/历史测试资产，不单独阻止发布或合并。未来新生成的运行态数据库不入库是维护建议。本轮未清理文件或改写历史。

## 建议

**HOLD。** 唯一未关闭门禁是修复候选的全量 pytest 未取得完整终态，且全量顺序下 TestClient shutdown 一次等待 60 秒。邻接组合、单测、213 项前缀及现行 Follow-up 已通过；这些证据缩小了调查范围，但不足以排除 Worker shutdown 生命周期问题，也不足以宣布全量回归通过。请主 Agent决定是否接受风险或另行授权最小 shutdown 诊断；本报告不等于 MERGE_READY。
