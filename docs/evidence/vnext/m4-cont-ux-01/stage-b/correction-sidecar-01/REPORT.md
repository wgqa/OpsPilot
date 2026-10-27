# Stage B Correction Sidecar 补差报告

**状态：`INTERMEDIATE_IMPLEMENTATION`**

**Stage B 整体验收：`HOLD`，本补差不签署阶段 PASS。**

## 开工核验

- Repo：`wgqa/OpsPilot`。
- 批准基线：`main@54329a6f11f909167ca6b64de6a905d5fe9e36fc`。
- 冻结标准提交：`1743bedd670012887788ab8a1ddfe1dc39c7c742`。
- RED 测试提交：`04ee2aca19b524b4474653f88b03166e3e843413`。
- 实现提交：`a515a0e580e76d3358a679446987ee5f27afd825`。
- 远端核验：最初两次 fetch 因 GitHub HTTPS 连接中断失败；第三次 fetch 成功，确认 `origin/main` 仍为批准基线 `54329a6f11f909167ca6b64de6a905d5fe9e36fc`。最终推送结果以本次交接回报中的实际 post-push SHA 为准。
- 主工作区存在用户修改的 `AGENTS.md` 和未跟踪资料，本轮未触碰。实现使用已存在的隔离工作树。
- 总纲、AGENTS、项目 Skill、Stage B 验收计划、Gold 和前轮收口报告均从批准基线实际读取；Blob 见 `BASELINE.json`。结束时重读了 Skill 并按其 C 节整理停止报告。

## 已确认的问题和最小修复

保存的真实 FastAPI Inspector JSON `../closeout-01/runs/green-api-05/responses/correction-answered.json` 中，存在一条 `CHAT_READONLY / BLOCKED / CORRECTION_CONFIRMED` Run。它来源于原用户问题；同一已确认纠错拥有 `APPLIED_TO_RUN` 更正消息与新 Investigator Run。旧投影把这个 sidecar 单独呈现为“本次工作未完成”，和新调查结果同时出现。

修复仅在现有 `projectConversation()` 中生效：只有当纠错为 `CRITICAL_CORRECTION / CONFIRMED`，更正消息确已应用到同一 Task 的新 Investigator Run，且 sidecar 的 Task、原问题来源、kind、status、reason 全部精确匹配时，才不把该 Chat Run 单独投影成状态卡。原 Run 对象仍留在 Inspector 数据中，并挂入纠错卡的可展开关联记录。其他 blocked 原因保持原行为；真正的 `FAILED / MCP_TIMEOUT` 调查失败继续作为主对话结果展示。

没有修改 Domain Run、API、TaskControl、S3 Gate、权限、预算或业务状态，也没有删除失败历史。

## RED / GREEN 与回归

- RED：针对真实保存的 API JSON 和确定性负例执行 2 项，`0 passed / 2 failed`。两项都证实 `CORRECTION_CONFIRMED` sidecar 被错误显示为独立未完成工作。日志：`runs/red-01/node-test.log`。
- GREEN：同两项 `2 passed`，保留 sidecar 展开详情，同时确认真实调查结果和真实失败仍可见。日志：`runs/green-01/node-test.log`。
- 前端既有投影 + closeout 回归 + 新用例：`17 passed`。日志：`runs/frontend-projection-01/node-test.log`。
- 本地 API/S3 回归：`20 passed`，覆盖 Stage B closeout、Supplement API、Stage B API 与 M4 S3。日志：`runs/api-regression-01/pytest.log`。
- `npm run typecheck`、`npm run build`、改动文件 ESLint：均退出码 `0`。
- 本次没有重跑全量 pytest；上一轮历史 `402` 结果不作为本次证据。

## 未执行与停止线

- 真实浏览器/DOM/截图/刷新/SSE：`NOT_RUN / BLOCKED_BY_TOOL_ENVIRONMENT`。此前 Computer Use 停止限制没有解除；本轮没有使用替代浏览器自动化。
- 真实 Provider、MCP 及付费调用：均未运行。
- 远端已复核为批准基线，修复与证据准备按单人工作流直接推送到 `main`；推送结果和 SHA 在交接回报中给出。用户主工作区及其未提交资料保持原样。
- Stage B 仍缺真实浏览器用户旅程和刷新验收；本补差只关闭已复现的对话投影问题，交主 Agent复核后停止。

## Skill 六问摘要

1. **用户变化：** 确认正式纠错接管后，不再看到 Chat sidecar 误报“工作未完成”；真实调查失败仍可见。
2. **Agent 决策：** 本修复不增加 Agent 自主性或模型决策。
3. **观察驱动：** 已确认且实际应用到新调查 Run 的纠错才使精确来源的 `CORRECTION_CONFIRMED` sidecar 被收纳到详情；其他观察保持原行为。
4. **新增约束：** 不新建硬 Gate；通过真实 API 快照及正反投影用例证明只抑制已被业务调查接管的 Chat 状态，不误隐藏真实失败。
5. **简化结果：** 复用既有纠错来源映射和用户问题投影，只将 sidecar 放入已有可展开纠错详情；没有新增业务状态。
6. **证据与停止线：** RED/GREEN、17 项前端、20 项 API/S3 回归和前端构建检查有原始日志。浏览器与全量 pytest 未运行，远端推送未执行。停止于 `INTERMEDIATE_IMPLEMENTATION`。
