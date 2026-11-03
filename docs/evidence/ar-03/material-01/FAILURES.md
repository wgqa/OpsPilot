# AR-03-MATERIAL-01 — 失败与修复记录

## RED-01 — 首次整合测试（测试准备缺陷 + 产品 RED）

- 命令：`python -m pytest tests/test_ar03_material_01.py -q --basetemp docs/evidence/ar-03/material-01/runs/red-01-tmp`
- 结果：5 failed，退出码 1；原始日志 `runs/red-01.log`、`runs/red-01.exitcode`。
- 两项有效产品 RED：`read_scoped_protocol_excerpt` 不存在；正式 Assistant 的 `load_protocol_upgrade_skill` 提议未执行并记录为 `ASSISTANT_TOOL_NOT_EXPOSED`。
- 测试准备问题：把包含换行的 `HumanMessage` 与 Python 对象 `repr` 字符串比较，断言方式错误。已改成直接比对 `HumanMessage.content`。原始日志保持不变。
- 同次绑定场景中 Skill 工具未暴露，故状态断言失败；这与 Skill 入口缺失一致。

## RED-02 — 修正断言后的整合运行未退出

- 原始尝试使用同一 pytest 命令；进程开始时间 2026-11-03 10:45:19（执行环境本地时间）。因工具会话未返回退出码且无完整日志文件，结果标记 `INCOMPLETE / NOT_COUNTED`。
- 独立 SQLite 临时数据表明该尝试已运行首轮正式 Assistant 路径：无绑定请求实际执行文档发现、原文提议被拒绝；绑定请求执行发现、比较、当前 Delivery/Receiver，但 Skill 提议被拒绝。临时数据库保留在 `runs/red-02-tmp/`。
- 本轮只终止自己启动的两个 Python 测试进程（PID 12516、32896）；没有清除临时库。此 Windows Worker/TestClient 回收问题不等同业务断言通过，后续将用窄化的独立进程测试复核。

## RED-03 — 独立 Domain/来源投影冻结复现（有效）

- 命令：`python -m pytest tests/test_ar03_material_01.py -q -k 'authorized_protocol_excerpt or fails_closed_after_grant or skill_is_integrity_checked or history_projection' --basetemp docs/evidence/ar-03/material-01/runs/red-03-tmp`
- 结果：4 failed、3 deselected，退出码 1；原始日志 `runs/red-03.log`、`runs/red-03.exitcode`。
- 原文读取与授权/摘要重验证两项因 `read_scoped_protocol_excerpt` 尚不存在而失败。
- Skill 正反完整性用例因 `PROTOCOL_UPGRADE_PROBLEM_TYPE` 和对应完整性入口尚不存在而失败。
- 历史原文来源没有专用有界投影，当前退化为 `HISTORICAL_TOOL_RESULT_REFERENCE_ONLY`，不能支撑下一轮对刚才引用条款的指代续接。
- 以上 RED 在生产源码修改前执行；冻结 CASES/Gold 未修改。

## 后续修复记录

实现与 GREEN 结果追加于本文件后续章节。失败日志不覆盖、不重命名、不改写。

## RED-01 / GREEN 测试夹具修正与实现记录

- `green-01-focused` 使用 `D:\python\python.exe`，在收集阶段因全局解释器未安装 `langchain_core` 退出 2。未进入业务测试；后续明确使用项目工作区 `D:\学习\agent新项目\.venv\Scripts\python.exe`。该日志保留，不作为实现失败或通过。
- `green-02-focused` 为 2 failed，退出 1。其一，Skill 正文正确表达“未验证”，但冻结测试检查英文词 `untrusted`；正文补上明确的 untrusted 表述。其二，历史投影测试将 `authority` 同时要求精确等于 `HISTORICAL_PROTOCOL_SOURCE_TEXT_ONLY` 并包含 `NOT_CURRENT`，两项断言彼此冲突；实现改为分开字段 `authority` 与 `currentness=NOT_CURRENT_BUSINESS_EVIDENCE`，测试保留原意并断言显式 currentness。
- `green-04-material-full` 为 3 failed，退出 1。发现 follow-up 测试把 `Response` 当字典取值，以及绑定任务真实出站输入按既有合同带有 `ORIGINAL_TASK_INPUT (UNTRUSTED USER INPUT):` 前缀。修复测试读取 `response.json()` 并验证完整原文包含在不可信包装中；未改变产品原文或成功标准。
- `debug-bound-01` 因测试编辑时缩进错误在收集阶段退出 2；`debug-bound-02` 的 2 个失败将运行时不可信包装误判为用户正文不一致。保留两份失败日志，修正测试代码。
- `green-05-material-full` 为 2 failed，退出 1。测试误要求静态协议摘录产生 D2 `evidence_id/observation_id`；协议资产工具不代表业务 Observation。修正为要求 MCP 调用持久状态、原文与 `source_refs`，并验证 `sources_current()` 重新校验；订单 Delivery/Receiver 仍必须有真实的 Evidence 与 Observation ID。
- `green-06-material-full` 在收集阶段因测试编辑时缩进错误退出 2，原始日志保留并修正。
- `green-07-material-full` 与最后一次 `green-08-material-final` 均为 7 passed，退出 0。最终新鲜执行命令见 `RESULTS.json`。相关协议/Assistant 回归 71 passed。

## 冻结 CASES 对齐补充

- `green-09-material-final` 使用冻结 CASES 原文扩充纯协议引用与缺失字段测试，结果 8 passed、1 failed，退出 1。原因是测试夹具误要求 `MAT-05-BOUND-PROCESSED` 提供独立 `input` 字段；冻结卡定义它复用 MAT-04 问题，只更换可信 Receiver 状态。未修改 CASES；测试改为对两个状态使用同一 MAT-04 原问题。
- `green-10-material-final` 按上述冻结语义新鲜重跑，9 passed，退出 0。原 `green-09` 日志和临时库保留。
- `green-11-material-final` 为新增长行续读测试，9 passed、1 failed，退出 1。测试准备以 Windows `write_text` 生成 CRLF 内容，却用 LF 字节计算 manifest Digest，触发了既有 `resolve_document()` 正确的完整性拒绝。产品代码未绕过 Digest 校验；测试改用 UTF-8 原始字节写入后重跑。

## 全量回归遗留失败

- 命令：`D:\学习\agent新项目\.venv\Scripts\python.exe -m pytest -q --basetemp=docs/evidence/ar-03/material-01/runs/regression-02-tmp`
- 结果：602 passed、4 failed，退出 1，完整日志 `runs/regression-02-full-pytest.log`，退出码 `runs/regression-02-full-pytest.exitcode`。
- 失败为 `tests/test_m1_event_process_recovery.py::test_n2_01_committed_repair_event_replays_after_commit_process_death`、`tests/test_m1_web_server.py::test_server_uses_configured_vue_origin_for_exact_origin_guard`、`tests/test_m1_web_server.py::test_server_defaults_origin_to_same_loopback_api_origin`，以及历史冻结 `tests/test_m4_autonomy_c1_red.py::test_explicit_protocol_followup_is_accepted_as_same_task_readonly_run_before_ttl_fix`（旧 Intent 被拒绝）。本切片未修改这些合同/测试；旧 C1 RED 继续保留。
- 本切片的 7 项专项、71 项相关回归均通过。全量结果不可表述为全绿；三个既有回归与旧 C1 RED 由主 Agent独立判读。
