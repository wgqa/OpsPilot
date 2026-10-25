# M4-EG-01 — 经验驱动的连续自主调查

**状态：`ACCEPTANCE_CANDIDATE`，等待主 Agent 独立验收。** 本报告不声明 PASS。

## 用户现在实际能够完成的事情

一次真实浏览器旅程中，SUPPORT 为 Task A 建立了当前有效的 S3 调查结果，创建历史经验候选；APPROVER 独立启用该候选；随后 SUPPORT 为另一个 Task B 创建调查。Task B 的真实 DeepSeek 调查在一次模型调用中把 Task A 的 Memory 与来源 Task ID 放入实际出站消息，之后执行了自己的订单、回调、接收端、传输历史和协议查询。当前 Task B 的 Evidence 与 Task A 的旧失败案例冲突后，后续调用排除了该 Memory。业务结论仍来自 Task B 自己的 Event：`RECEIVER_PROCESSING_UNCONFIRMED`、`WAIT_FOR_RECEIVER_PROCESSING`，没有宣称恢复或提交交接。

浏览器 API 记录：候选 `201`、APPROVER 确认 `200`、Task B 受理 `202`；Task B Run `run-56c10a98-61d8-4ba6-bb89-569f4b462f70` 为 `SUCCEEDED`。该 Task 没有 Queue、Receipt、ActionIntent、Ledger 或 DeliveryRecord 写入。Task B 的 Event SLA 在后续只读浏览器重访前到期；重访页面正确显示结果已失效为历史信息，当前 Evidence 因过期被 Gate 排除，且重访没有调用模型。

浏览器证据：

- [Task A 当前来源](runs/web-memory-green-02/screenshots/01-task-a-source-ready.png)
- [Memory 候选已创建](runs/web-memory-green-02/screenshots/02-task-a-candidate-created.png)
- [APPROVER 审核](runs/web-memory-green-02/screenshots/03-approver-candidate-review.png)
- [Memory 已启用](runs/web-memory-green-02/screenshots/04-approver-memory-active.png)
- [Task B 持久结果重访](runs/web-memory-green-02/screenshots/06-task-b-persisted-result.png)

**浏览器限制如实记录：** 原旅程脚本在 Task B Run 已成功后，因为过严地要求 Memory 必须仍出现在“最后一次”模型调用 provenance 而退出 1。真实持久记录证明 Memory 在较早的 Task B 调用中被选择，后续在当前证据冲突时正确排除。修正后的只读重访成功，但发生在 SLA 到期后；所以这轮证据证明了真实浏览器 A→候选→审批→B 调查→持久回访和正确失效显示，没有把脚本整体标成全绿，也没有伪称浏览器即时截图证明了 SLA 到期前结论。

## 变更范围

- `opspilot/domain/chat.py`：补充 S3 只读解释的可信规则：同 Event 当前 `PROCESSED` 可在 SLA 前证明处理完成；SLA 只约束仍为 `QUEUED` 的事件；`202` 单独只证明接收；无匹配 Receiver 状态时保持 UNKNOWN；不借用其他 Event 状态。
- `knowledge/async-callback/receiver-ack-contract-v2-1.md` 与 `manifest.json`：保留 v2.0 原文件，新增并激活版本 2.1.0，明确同 Event 事实与 SLA 语义。
- `frontend/src/App.vue`：S3 Memory 候选只在可信 outcome 为 `CURRENT` 且属于白名单 S3 结果时启用；过期/失效结果不能创建候选。
- `tests/test_m4_eg_01.py`：测试真实 Chat 准备路径和真实 S3 `model_call()` 的出站内容。
- `tests/test_m2_02_hf_01.py`：跨进程 deterministic `NoToolModel` 子进程提供仅供测试配置守卫使用的占位变量，不发出 Provider 调用。
- `tests/test_m4_continuous_vs01.py`：来源变更测试跟随当前活动 Knowledge manifest 文件，避免硬编码旧版本文件名。
- `docs/evidence/vnext/m4-eg-01/`：保存冻结计划、原始运行、失败、真实 Web/Provider/MCP/HTTP 证据、结果索引及学习材料。

浏览器复现脚本从进程环境读取 SUPPORT/APPROVER 演示口令；提交目录不含这些值。修改后对两份 `.mjs` 执行 `node --check` 均退出 0，日志在 `runs/harness-syntax-check/`。

未修改 Gold、sealed holdout、历史 RED、旧 Knowledge v2.0 内容、M1/M2 业务状态与写权限语义。Memory 仍只是线索，不是当前 Evidence 或 Gate 输入。

## 验收证据

| 验证 | 结果 | 证据 |
|---|---:|---|
| 冻结 SLA/出站 Context RED | 5 failed / 1 passed（预期 RED） | `runs/red-sla-05/pytest.log` |
| 本轮确定性 GREEN | 6 passed | `runs/green-deterministic-05/pytest.log` |
| HF stale-Gate regression | 1 passed | `runs/regression-fix-m2-hf-01/pytest.log` |
| VS-08 Knowledge source invalidation | 1 passed | `runs/regression-fix-vs08/pytest.log` |
| Frontend production build | PASS，Vite 8.3.4 | `runs/web-memory-20261025T102107Z/frontend-build.log` |
| 全量 pytest 第一次 | 368 passed / 3 failed | `runs/full-pytest-01/pytest.log` |
| 全量 pytest 修正后第二次 | 370 passed / 1 failed | `runs/full-pytest-02/pytest.log` |
| 浏览器原始自动化 | Run/HTTP 旅程完成，最终 locator 断言失败；不标 PASS | `runs/web-memory-green-02/browser.log`、`WEB-JOURNEY-RECONCILIATION.json` |
| 刷新后只读重访 | PASS，无模型调用，SLA 后正确显示证据过期 | `runs/web-memory-green-02/browser-revisit.log`、`screenshots/WEB-REVISIT.json` |

第二次全量 pytest 的唯一失败是既有 C1 RED 测试 `test_explicit_protocol_followup_is_accepted_as_same_task_readonly_run_before_ttl_fix`：分类端返回 `502 INVALID_MODEL_CLASSIFICATION`，该测试以 RED 语义要求 follow-up Run 接线。本轮未修复此 C1 范围问题。全量 pytest 因此 **不是 PASS**。第一次全量中另两项被定位为 deterministic 子进程测试配置和 VS-08 过期文件名问题；各自定向复跑均通过，并在第二次全量中不再失败。

所有 pytest 与浏览器流程的失败/准备错误均保留在 [FAILURES.md](FAILURES.md) 及 `runs/`。run 01 与隔离重跑生成的旧 C1 JSONL Trace 行已保存；run 02 的临时附加行未能逐字保存（行结束符校验失败后已恢复原文件），相同测试的隔离重跑行单独保存，未冒充为 run 02 原记录。旧 C1 跟踪文件恢复到 HEAD。

pytest 的 `basetemp/` / `pytest-temp/` 含约 783 MB（747 MiB）临时 SQLite fixtures；递归清理请求被自动化安全审查拒绝，因此保留在当前隔离工作树并排除出提交。原始 pytest 日志、失败 trace 与结果摘要已经独立保存。

## 真实 Provider / MCP / HTTP 结果

- Provider 总计 **37 次**：DeepSeek Flash SLA Chat 4 次、Memory ON/OFF/冲突/无关/撤销实验 26 次、真实 Web Task B 7 次；在计划最大 40、硬上限 80 内，之后没有继续调用。合计 155,671 input / 33,682 output / 189,353 total tokens。原 Memory `RESULTS.json` 顶层聚合字段错误地写了 `total_tokens=0`，本报告从 26 条实际 Provider Trace 的 usage 字段复算；原始结果未改写。
- SLA Chat 使用本地隔离 Domain 状态和已持久化的测试 Observation 作为事实准备，再由真实 DeepSeek `CHAT_READONLY` Worker 生成回答；这四次不是四条真实 MCP 调用。每个 Case 实际 HTTP 读取和 Evidence/Gate 摘要在 `runs/sla-provider-20261025T101512Z/RESULTS.json`。四个答案均按冻结合同人工核对方向；结果文件保留 `manual_review_required=true`，机器结果本身不宣称自动语义通过。
- Memory E1 ON/OFF 使用相同目标状态但不同 Task。两者都是 `RECEIVER_PROCESSING_UNCONFIRMED`，工具序列均为 order → delivery → receiver → transport history → knowledge；ON 33,249 tokens，OFF 30,895 tokens，ON 高 2,354（7.6%），未证明结果或行动优势。
- Task B 的实际 Web Investigator 调用了 6 次当前 MCP 查询，生成 6 条 Observation；7 次 Provider 调用中，Memory `episodic-892bfc7d-6d89-459c-9dea-c3164fd72242` 在 `call-8b82f056-9566-409e-b31d-b765f889e7a6` 进入实际 prompt，包含来源 Task A ID。之后以 `CURRENT_EVIDENCE_CONFLICTS_WITH_MEMORY` 排除。当前 Gate 的结果为 `RECEIVER_PROCESSING_UNCONFIRMED`，`WAIT_FOR_RECEIVER_PROCESSING`。
- 真实 Web Task A 准备流包含 loopback HTTP `200` 与两条实际 MCP Observation。它是固定本地测试业务准备，不计为 Agent 自主决策。Memory 创建、人工 APPROVER 确认和 Task B 创建均由浏览器/API 实际完成。
- 在 2026-10-25 的 37 次调用上，按 DeepSeek 公布的高峰缓存未命中价作上界估算为约 **USD 0.08712**（非账户账单、非实际扣费核算）；来源：[DeepSeek Models & Pricing](https://api-docs.deepseek.com/quick_start/pricing/)。冻结预算上限为 USD 1.00。

## 实施边界与已知问题

- 没有引入 Memory 类型、Agent/Runtime、MCP 工具、Gate 或业务写能力；未扩大默认 8 model / 6 MCP 的任务预算。
- Memory ON 在本组对照中没有改善结论或工具路径，且增加 token；它证明了真实跨任务进入上下文及与当前事实冲突时被舍弃，但不能据此宣传它提升了诊断表现。
- Task B 调查结束时为 `CURRENT`；浏览器回访时 Evidence TTL 和 SLA 边界已越过，显示 `INVALIDATED_BY_CURRENT_FACTS`。这是正确的失效保护，也意味着回访截图不是有效期内的新鲜诊断证明。
- E3 无关经验场景没有使用 MCP，得到明确不足状态；它验证经验过滤，但不证明所有自然语言目标均可在无工具条件下回答。
- 本轮没有重新运行密封 P2/P3 留出实例，保持未解封；没有进行真实浏览器撤销 Memory 的二次旅程，仅使用现有真实 Domain/provider E4 撤销后出站排除证据。
- C1 `READONLY_FOLLOWUP` RED 仍在全量测试中失败，需主 Agent 决定是否单独纳入后续修复。

## 六问回顾

1. **用户多完成什么：** 可以把经 APPROVER 核验的 Task A 经验带到不同 Task B，并在浏览器中完成 Memory 创建/确认、调查与结果重访。
2. **Agent 真正决定什么：** 真实模型选择了 Task B 的查询；早期选入经验，当前观察冲突后不再依赖它。ON/OFF 对照没有观察到业务行动优势。
3. **什么观察改变行动：** 同一 Event 的当前回调/接收状态与历史失败 Memory 不同，后续模型上下文明确将 Memory 作为冲突来源排除；SLA 后时间当前性又将历史诊断降为不可用于当前结论。
4. **硬限制保护什么、影响什么：** 同租户 Task A Memory 仅是方法线索，Task B 当前 Event 仍需自己取证；授权和当前性有效时可正常跨 Task 参考。测试中没有触发任何业务写入。
5. **简化了什么：** 复用现有 Memory 查询、当前性规则与 S3 Knowledge；只补充 S3 Chat 规则、Knowledge 新版本和 UI 候选适用条件，没有新增通用治理层。
6. **证据与停止线：** 6 个新确定性测试通过，37 次 Provider 与真实 Web/MCP/HTTP Trace 已保存；全量 pytest 仍有一个既有 C1 RED，因此本提交只作为候选。到此停止，不再扩展。

## 提交信息

验收计划 / Gold 冻结提交：`18e9b0e0b7b5112befd767a3f9bef53ec43d1ac9`（冻结文件与该提交内容一致）。实现起点及独立 RED 证据提交：`0c142e91f04ec1278b0cf547aeeeb480466466c8`。本报告随最终交付提交一并入库；其提交 SHA 在最终交接中给出，避免文件自引用。只推送 main 的 fast-forward 更新，不合并其他候选分支。

开工时从目标提交实际读取：`PROJECT_NORTH_STAR.md`（blob `1f737712c7a36ceb34433ac09c3fbba3c3305542`，2026-10-24 方向/评审修订）与 `AGENTS.md`（blob `30319000ed0054007e9b7b6b46bf98b1493c8179`）；实施前的目标提交为 `0c142e91f04ec1278b0cf547aeeeb480466466c8`。冻结验收计划 blob 为 `949938a3c269cf8069f0fb526930a9947e80e786`，Gold blob 为 `9ef662173c3bcbdae05a20d24fe3673cd2dd8cbf`。
