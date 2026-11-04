# AR-04A 已知失败、未覆盖项与限制

**状态：** 随候选提交，不修饰、不回填历史。
**基线：** `48234e5dabb6ed28ea816b8ebc438288409353b8`

## 1. 本轮确认并修复的真实缺口

| 编号 | 现象 | 证据 | 处理 |
|---|---|---|---|
| F-1 | 长会话第 6 轮 Run `FAILED`，用户可见 `INVESTIGATOR_CONTEXT_EXCEEDS_BUDGET (13541 > 12000 tokens)`；历史选择预算未计入 SYSTEM / WORK_CONTEXT / 工具 schema | 离线复现日志（本目录 `runs/red-baseline-journey.log`） | 把工具 schema、固定 system 与 WORK_CONTEXT 作为预留计入选择预算 |
| F-2 | 调查链路不执行既有压缩：`prepare_chat_attempt` 返回 `CHAT_CONTEXT_COMPRESSION_REQUIRED` 后直接结束 | 源码 `assistant.py:803-805`（修改前） | 在 ASSISTANT_V1 首次 Provider 调用前复用既有压缩 Domain 原语 |
| F-3 | 压缩产物 `HISTORICAL SESSION SUMMARY` 从未进入 ASSISTANT_V1 模型输入（system 角色被丢弃） | 源码 `assistant.py:831-835`（修改前） | 保留该 system 摘要块作为初始上下文，并在 provenance 中标记来源 |

## 2. 未覆盖 / NOT_RUN

| 项目 | 状态 | 原因 |
|---|---|---|
| J6 正式纠错（`CORRECT_TASK_INPUT` + 确认）在本旅程内端到端复验 | `NOT_COVERED` | 确认纠错会创建 legacy Investigator Run，需要额外的 provider seam；本轮时间与范围未包含。既有 M1/M4 纠错测试仍通过，但未在本旅程内重跑 |
| 真实收费 Provider 对照 | `NOT_RUN` | 未获用户预算授权；不得宣称真实模型增益 |
| 浏览器体验 | `NOT_RUN` | R1 `BROWSER_STOP_ACTIVE` 继续有效 |
| Task 作用域摘要复用（把绑定前摘要带入 Task Run） | `NOT_IMPLEMENTED` | 既有按 `task_id` 精确匹配的安全设计；跨任务复用需要新的作用域校验与负例，超出本切片 |
| 绑定前材料早于最近 12 条消息时的保留 | `LIMITATION` | 压缩只覆盖最近窗口之外的历史；若材料更早且无 Task 摘要，可能被预算淘汰 |
| 工具观察导致的二次预算增长 | `PARTIAL` | 预留 1024 token 覆盖一次有界只读观察；更大观察仍按设计 fail-closed |
| 全量 675 项回归 | 见 `RESULTS.json` | 本轮已跑；历史 C1 RED 仍保留 |

## 3. 历史失败（不修改）

- `tests/test_m4_autonomy_c1_red.py::test_explicit_protocol_followup_is_accepted_as_same_task_readonly_run_before_ttl_fix`：使用已废弃 `READONLY_FOLLOWUP`；冻结 RED，保留原样。
