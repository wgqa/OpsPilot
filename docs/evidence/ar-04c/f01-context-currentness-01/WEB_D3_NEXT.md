# Web 与业务闭环：同期只读梳理

**证据等级：源码静态检查；未运行浏览器，未执行业务写入。** 浏览器 STOP 仍有效。本清单与 F01 修复并行完成，不等待一次大型 Memory 评测。

| 用户环节 | 现有入口 | 当前断点/下一步 |
|---|---|---|
| 普通自然语言、材料与只读调查 | `App.vue::sendMessage/bindAssistantOrder`，`api.ts::bindAssistantOrder`，`web/app.py` 的 `/assistant/messages`、`/assistant/order` | 已有同 Session 专业助手入口；订单确认后创建 ASSISTANT_V1 Run，页面明确只读。继续复用。 |
| 当前资源与调查反馈 | 授权订单选择、对话投影、Run/SSE、来源展开；原 AR-03 Web 与 R1 证据 | 本轮未重做 DOM/刷新验收；下一次合法浏览器检查直接围绕现有界面开展。 |
| 发起既有受控调查 | `App.vue::createDemoTask`，可见“原有业务调查”按钮；`web/app.py` 的 Session task 创建接口 | AUTH_INCIDENT 仍走原 S1/S2 调查链，专业助手并未自动进入它。用户目前需要另一次明确确认。 |
| 可信 Plan 预览与审批 | `App.vue::selectPendingApproval/decideApproval`；`GET /api/approvals/pending`、Plan review 和 approval API | 独立 APPROVER、Plan hash 与确认界面已存在；不能拿自然语言答复代替不可变 Plan 或独立审批。 |
| CAS 修复与独立交付 | `task_control.py::submit_web_plan_approval` 创建 APPROVAL_RESUME；Worker 原 Investigator `d3_mode=True`；`d3.py::get_or_create_action_intent/execute_repair/execute_deliver` | 复用已存在的动作身份、CAS、Verifier、Ledger 和独立交付。此处不是缺少新的执行引擎。 |
| 用户看到真实结果 | `GET /api/tasks/{task_id}/outcome`；App 的 verification/repair/delivery 展示 | 已有回执展示组件；需要在同一对话里把问题、正式受控任务及最终回执关联起来。 |

## 最明确的产品断点

`Worker::_dispatch_run` 在选中 ASSISTANT_V1 时执行统一助手后直接返回；其工具集没有审批、Repair、Deliver。现有 D3 在另一条受控调查路径运行。因而“专业助手已经会调查和写草稿”不等于“专业助手用户入口已贯通修复”。

下一张产品任务应只锚定一个现有 S1 闭环：用户描述订单接口认证故障 → 在原 Session 明确确认授权资源和启动受控调查 → 沿用现有事实/Plan → 独立审批 → CAS → 同身份 HTTP 验证 → 独立交付 → 对话展示真实回执。先复用可见的原业务入口和既有 API，补最小目标/任务/结果关联；不在本次 F01 中实施，也不先迁移整套 S1/S2 工具和 Runtime。

验收必须同时包括拒绝/取消审批及重复恢复不会产生写入的反例。浏览器环境明确获准后，DOM、来源展开、刷新恢复可先检查；不需要等待新增 Memory 算法或大规模实验。当前源码梳理不冒称这些 UI 和写入验收已通过。
