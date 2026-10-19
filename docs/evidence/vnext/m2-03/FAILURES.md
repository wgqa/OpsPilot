# M2-03 失败与修复记录

所有记录按发生顺序追加；原始 RED 日志不可改写。最终评估时逐项标注修复提交与新鲜 GREEN 命令。

## RED-01 — 冻结基线缺少交接能力

- **冻结标准提交：** `35af8d763176705adc844859cd65dc96b087a54c`
- **执行代码 SHA：** `35af8d763176705adc844859cd65dc96b087a54c`
- **命令：** `python -m pytest tests/test_m2_03_handoff.py -q --tb=short --basetemp=.runtime/m2-03-red-01`
- **结果：** 5 failed，1 warning；退出码 1。
- **观察：** 三条 Domain 路径因不存在 `opspilot.domain.s2_handoff` 失败；旧 Draft 当前性用例同样显示缺少 Domain 错误码/拒绝边界；Web `GET /api/tasks/{task_id}/handoff` 返回 404。
- **归因：** M2-02 基线只有诊断 Receipt 和冻结 Draft，没有 Queue、持久 HandoffReceipt 或受控 Web 提交 API。此 RED 符合预期，不是环境失败。
- **原始记录：** `runs/red/red-01/META.txt`、`runs/red/red-01/pytest.log`。
- **处理：** 尚未修复；测试与日志先提交保留，再开始实现。

## REG-ENV-01 — 初次回归使用了系统 Python

- **命令：** `python -m pytest tests/test_m2_01_facts.py tests/test_m2_02_s2_diagnosis.py -q --tb=short --basetemp=.runtime/m2-03-impl-01`
- **结果：** collection error；系统 Python 3.14 环境未安装项目锁定的 `mcp`（`ModuleNotFoundError`）。
- **归因：** 测试解释器选错，属于环境错误，不是产品代码失败。
- **原始记录：** `runs/green/impl-01/META.txt`、`runs/green/impl-01/pytest.log`。
- **处理：** 改用仓库 `.venv` 的锁定依赖解释器重跑；保留首次失败，不把它算作产品 GREEN。

## REG-DB-01 — 新 Schema 版本使旧回归硬编码版本号失效

- **命令：** `.venv\\Scripts\\python.exe -m pytest tests/test_m2_01_facts.py tests/test_m2_02_s2_diagnosis.py -q --tb=short --basetemp=.runtime/m2-03-impl-02`
- **结果：** 1 failed、13 passed；仅 `test_m2_01_s2fact09_migration_is_idempotent_and_scope_write_count_is_zero` 仍断言 schema version 为 7，实际新迁移版本为 8。
- **归因：** 任务卡要求在 v7 上新增显式增量迁移；该回归断言已过时。没有业务行为回归。
- **原始记录：** `runs/green/impl-02/META.txt`、`runs/green/impl-02/pytest.log`。
- **处理：** 只将该 migration assertion 更新为 v8，并添加 M203 v7→v8 双次初始化用例；后续重新运行确认。

## GREEN-ASSERT-01 — M203-03 测试期望值写错

- **命令：** `.venv\\Scripts\\python.exe -m pytest tests/test_m2_03_handoff.py tests/test_m2_01_facts.py tests/test_m2_02_s2_diagnosis.py -q --tb=short --basetemp=.runtime/m2-03-impl-04`
- **结果：** 1 failed、19 passed。
- **观察：** Domain 已产生唯一 Queue/Receipt/Outbox；授权写审计触发器读数为 0。失败断言却错误期待 `scope_writes=1`。
- **归因：** 新增测试 oracle 笔误；实际观察符合冻结的零写 Gold。
- **原始记录：** `runs/green/impl-04/META.txt`、`runs/green/impl-04/pytest.log`。
- **处理：** 将该断言修正为 0，下一次新鲜运行确认；保留本次失败输出。

## GREEN-HARNESS-02 — 同一测试内重复准备 Fixture 时审计表重复创建

- **命令：** `.venv\\Scripts\\python.exe -m pytest tests/test_m2_03_handoff.py tests/test_m2_01_facts.py tests/test_m2_02_s2_diagnosis.py -q --tb=short --basetemp=.runtime/m2-03-impl-05`
- **结果：** 2 failed、27 passed。
- **观察：** Abort/Handoff 顺序与三段事务故障、跨进程争用、授权负例等已通过；两个测试在同一临时数据库内第二次准备 S2 Fixture 时重复创建 `m203_scope_write_audit` 表导致失败。
- **归因：** 新测试辅助函数未对重复调用幂等；不是 Domain 或产品事务失败。
- **原始记录：** `runs/green/impl-05/META.txt`、`runs/green/impl-05/pytest.log`。
- **处理：** 审计表改用 `IF NOT EXISTS`，每次准备时清空计数；触发器也改为幂等创建，随后复跑。

## REG-FULL-01 — 两条既有迁移测试仍固定断言 schema v7

- **命令：** `.venv\Scripts\python.exe -X utf8 -m pytest -q --tb=short --basetemp=.runtime/m2-03-full-01`
- **结果：** 184 passed、2 failed；完整套件执行 146.50 秒。
- **观察：** `test_schema_v3_database_adds_context_input_provenance_columns` 与 `test_schema_migration_is_idempotent_and_preserves_frozen_plan_hash` 都验证 M1 迁移，却将最终 `PRAGMA user_version` 固定断言为 7；当前实现新增 M2-03 v8 增量迁移后实际为 8。其余 M1/M2/D1-D7 回归均通过。
- **处理：** 只将两处最终 schema 版本预期更新为 8，并注明 M2-03 增量迁移；不改迁移语义、测试数据或业务断言。随后用全新 basetemp 重跑完整 pytest。
- **原始记录：** `runs/full-01/META.txt`、`runs/full-01/pytest.log`。

## LINT-01 — 新增浏览器存储访问未显式限定 window

- **命令：** `npm --prefix frontend run lint`
- **结果：** 4 个 `no-undef` 错误，涉及 `localStorage` 与 `sessionStorage`。
- **归因：** ESLint 的浏览器全局配置要求显式使用 `window`；生产构建和真实浏览器旅程不受影响。
- **处理：** 将这些浏览器存储调用改为 `window.localStorage` / `window.sessionStorage`，随后重新执行 lint 和 build。
- **原始记录：** `runs/frontend-lint-01/META.txt`、`runs/frontend-lint-01/lint.log`。

## BROWSER-02 — 真实回答中的否定句触发错误的正向恢复断言

- **命令：** `.venv\Scripts\python.exe -X utf8 -m opspilot.smokes.m2_03_browser --evidence-dir docs/evidence/vnext/m2-03/runs/browser-02`
- **结果：** 真实 Edge、Provider、MCP、双标签幂等提交和响应丢失回查均完成；运行最终被答案断言器标为 FAIL。
- **观察：** 模型回答明确说明“没有证据显示订单 API 已恢复”“权限未变更”；一个未检查否定词的子串正则将 `API 已恢复` 错判为正向声明。Queue/Receipt/Outbox 均正确提交，两个标签页回查同一回执。
- **处理：** 将断言收紧为否定上下文感知的授权/恢复声明识别，并仍要求答案明确说明本地队列接收与未授权/未恢复。保留该次原始失败，不改写结果。
- **原始记录：** `runs/browser-02/RESULTS.json`、`runs/browser-02/logs/browser-run.txt`、`runs/browser-02/screenshots/01-03-*` 与 `.runtime/m2-03-browser/20261019T120404Z/domain.sqlite3`。

## BROWSER-03 — 真实回答使用等价自然表达，否定结果词表过窄

- **命令：** `.venv\Scripts\python.exe -X utf8 -m opspilot.smokes.m2_03_browser --evidence-dir docs/evidence/vnext/m2-03/runs/browser-03`
- **结果：** Provider、MCP、双标签并发提交、丢失响应恢复和回执显示均完成；最终追问答案正确说明“还没有获得授权”“不能宣称业务已恢复”，但严格答案词表未识别该措辞，运行判 FAIL。
- **归因：** 测试 oracle 对同义自然语言表达过于狭窄，不是业务闭环或安全边界失败。
- **处理：** 对授权与恢复使用范围受限的否定语义正则，并保留对无否定前缀正向声明的独立拒绝判断；保留原始失败。
- **原始记录：** `runs/browser-03/RESULTS.json`、`runs/browser-03/logs/browser-run.txt`、`runs/browser-03/screenshots/01-03-*` 与该 run 的 `.runtime` SQLite。

## BROWSER-05 — 字段标签跨行造成授权正向断言误报

- **命令：** `.venv\Scripts\python.exe -X utf8 -m opspilot.smokes.m2_03_browser --evidence-dir docs/evidence/vnext/m2-03/runs/browser-05`
- **结果：** 双标签并发、首响应丢失、同回执恢复、刷新后 operation_id/receipt 稳定性都已通过；最终判定器把相邻两行的“缺失范围”与“已授予范围：空”拼接，错误识别为正向授权声明。
- **处理：** 正向授权/恢复语句按中文句号、逗号和换行切分后单独检查，避免跨字段边界拼接；保留本次真实运行失败。
- **原始记录：** `runs/browser-05/RESULTS.json`、`runs/browser-05/logs/browser-run.txt`、`runs/browser-05/screenshots/01-03-*` 与该 run 的 `.runtime` SQLite。

### 浏览器最终复验

- `runs/browser-04`：真实 Edge 旅程 PASS，双页 202/200 幂等重放、丢响应回查和结果追问通过。
- `runs/browser-06`：最终旅程 PASS，并额外刷新页面确认 localStorage 中 operation_id 与重载后查回的 Receipt 均不变。
- 所有中间浏览器失败仍保留在各自 `runs/browser-02/03/05`，没有从通过分母中删除。
- `runs/browser-07`：在实现提交 `c4335c186dd93b505d15f15c5ffa322ae245cd4a` 上重新执行并 PASS；刷新后操作 ID/Receipt 均稳定，Provider/MCP/HTTP/Domain 轨迹和最终截图已保存。

### LINT-01 补充运行

- **命令：** `npm --prefix frontend run lint`
- **结果：** 2 个 `no-undef` 错误；`.mjs` 测试脚本的 ESLint 环境也没有声明 `window`。
- **处理：** 浏览器回调使用 ECMAScript 标准 `globalThis.sessionStorage`，Vue 页面保留 `window.localStorage`；之后再次运行 lint。
- **原始记录：** `runs/frontend-lint-02/META.txt`、`runs/frontend-lint-02/lint.log`。

### 全量与静态检查复验

- `.venv\Scripts\python.exe -X utf8 -m pytest -q --tb=short --basetemp=.runtime/m2-03-full-02`：**186 passed**，150.85 秒。原始日志 `runs/full-02/pytest.log`。
- `npm --prefix frontend run lint`：通过。原始日志 `runs/frontend-lint-03/lint.log`。
- `npm --prefix frontend run build`：通过，Vite 8.3.4。原始日志 `runs/frontend-build-03/build.log`。
- 以上新鲜结果确认迁移断言修正和显式 browser global 修正已通过。
