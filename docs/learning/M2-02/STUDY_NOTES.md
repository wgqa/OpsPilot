# M2-02 源码学习笔记

## 业务调查是如何进入 S2

`opspilot/investigator.py` 仍是同一业务 Investigator Graph 的执行入口。M2-02 没有新建第二套业务状态机。新 Run 从可信 TaskBinding 和 TaskControl 上下文构造调查请求，先发起真实 Probe，再把当前 Run 的 Evidence 交给 Domain 侧 Gate。MCP Server 从绑定记录解析租户与资源，模型工具参数不能提供任意 URL、凭证或 Scope。

S2 的授权判断从实际服务端请求事件、主体、Grant、Route Scope Policy 和版本快照构造。关键关联是 Probe 产生的 request_id 与 Authz Decision 的 request_id 一致；仅看到 HTTP 403 不足以形成权限诊断。`opspilot/domain/s2_diagnosis.py` 负责验证证据当前性与关联、持久化诊断回执及冻结申请草稿。输出 `HANDOFF_READY` 不触发授权或业务配置写入。

## 连续对话、关键纠错与工具预算

Task/Message/Run/control revision 由 `task_control` 与 Domain 持久化。新线索以用户输入进入可信控制流程，但输入文本仍属于未信任事实。关键纠错由 TaskControl 绑定 revision 和消息序号，后续 Run 重新调用模型和工具，并以新的当前证据裁决；不会直接改写 Gate 或审批权限。

本轮补充修正了工具暴露窗口：`_s2_model_tools_for_evidence` 根据本 Run 已有可信证据缩小可调用工具；缺少 Probe 时只提供 Probe，最新 Probe 403 尚无对应 Authz 时只提供授权事实读取，且 `request_id` schema 限定为该 Probe 返回值。已拿到关联授权事实后不再向模型提供进一步 MCP 工具。这既减少无效循环，也让证据关联契约落实在模型可见的工具 schema 上。工具调用预算依然在 Domain 记录并执行。

## 申请草稿与冻结边界

草稿不是交接回执，也不推进权限变更。它引用当前诊断回执与证据摘要，表达人工/外部权限审批所需的信息。M2-02 不新增接收队列、审批系统、自动 Scope Grant 或恢复状态。S1 的 401 仍进入此前经授权的修复闭环；S2 403 则形成待申请草稿；资源不存在/证据不充分保持 INCONCLUSIVE/NO_ACTION。

## 可复现检查

```powershell
.venv\Scripts\python.exe -m pytest -q tests/test_m2_02_s2_diagnosis.py
.venv\Scripts\python.exe -m pytest -q --basetemp=.runtime/m2-02/pytest-final-05
.venv\Scripts\python.exe -m opspilot.smokes.m2_s2_mcp
Set-Location frontend; npm run build
```

最终全量结果 154 passed。模型与 MCP 的真实调用轨迹、Token 用量和脱敏说明见 `docs/evidence/vnext/m2-02/TRACE.json` 与 `traces/`。MCP smoke 会建立临时 Domain SQLite，使用真实 stdio Server 验证工具可见范围、Probe 403、当前关联 Authz DENY，以及跨 scope 请求被拒绝。

## 主要源码入口

- `opspilot/investigator.py`：Graph 调查流程、模型工具 schema、MCP client 调用和预算。
- `opspilot/domain/s2_diagnosis.py`：证据裁决、S2 Outcome、Receipt 与 Draft。
- `opspilot/domain/d2.py`：可信 TaskBinding 和调查工具域接口。
- `opspilot/domain/database.py`：Domain Schema、真实鉴权/授权事件与 fixture。
- `opspilot/domain/knowledge_assets.py`、`opspilot/skill_assets.py`：版本化知识/Skill 的装载与摘要。
- `opspilot/smokes/m2_02_provider_traces.py`：真实 Provider/MCP journeys 与 Domain trace snapshot。
- `tests/test_m2_02_s2_diagnosis.py`：S2 证据、负例和冻结边界回归。
