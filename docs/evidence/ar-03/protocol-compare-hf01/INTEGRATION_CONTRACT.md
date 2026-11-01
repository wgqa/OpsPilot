# AR-03 协议比较后续集成契约说明 (INTEGRATION_CONTRACT.md)

> **文档定位：** 本文件定义 AR-03 独立协议比较能力后续接入生产对话 Assistant、Investigation Graph 或 MCP 工具时的最小集成契约与安全前置条件。
>
> **当前状态：** 本阶段仅交付独立只读计算函数，**严禁现在修改** `opspilot/assistant.py`、`opspilot/assistant_mcp.py`、`opspilot/web/worker.py` 或 TaskControl。

---

## 1. Agent 自主调用边界（Autonomy vs Fixed Workflow）

1. **自主决定何时比对：** 协议比较是提供给 Agent 的一项受限只读调查能力。在排查 401、403、503、回调超时或用户明确提出“协议是否升级/变更”时，Agent 可以根据多轮对话中的观察、错误码及用户上下文，自主决定是否需要发起协议版本比对，以及比对哪两个版本。
2. **禁止固定调查模板：** 系统不通过代码写死硬编码规则（如“遇到 503 必须按顺序调用协议比对”、“在特定步骤强制执行版本对比”），不剥夺 Agent 基于实际观察调整调查路线的自主性。

---

## 2. 前置受信知识授权（Knowledge Scope Prerequisite）

1. **不可接收任意自由路径：** 协议比对函数 `compare_protocol_versions` 与 `compare_protocols_safe` 不接受未经校验的文件路径或任意 URL。
2. **必须依赖前置 DocumentRef 检索：** 外部调用方在调用协议比较前，必须先通过现有的 Session / Task 受信知识检索链路（如 `assistant_knowledge.py` 中的 `list_scopes`, `select_scope`, `search`）获取经过授权的受信任引用结构 `DocumentRef`：
   ```json
   {
     "document_id": "callback-retry-contract",
     "version": "1.0.0",
     "digest": "a5974f46bf50e2bfcd63ed1e6528d473560854204d12a50dfb3f82b9e61bc0c3",
     "source": "local:orders-async-demo/contract-v1"
   }
   ```
3. **租户与会话隔离：** 引用检索受到当前 `TaskBinding` / Session Scope 的租户身份校验；未授权或跨租户的协议文档在检索阶段即被拒，不能进入比较模块。

---

## 3. 独立性与最小权限暴露（No Raw Unscoped Exposure）

1. **纯无状态 Domain 模块：** `protocol_comparison.py` 是纯只读计算模块，自身不持有用户会话状态，不承担用户身份核验职责。
2. **禁止直接作为全目录 MCP 工具暴露：** 不能将比对函数无包装地直接暴露给模型（例如允许模型自由传入任意字符串当成文档 ID 或路径）。
3. **工具封装原则：** 将来作为 MCP 工具暴露时，输入必须限定为已检索到的合法 `source_refs` 中的文档标识，由服务端根据受信缓存或受控清单加载，防止模型利用未受限工具探测本地未授权文件。

---

## 4. 认知边界与线上环境区别（Epistemic Boundary）

1. **规范不等于线上部署状态：** 文档比较结果反映的是文档作者编写的规范差异，**绝对无法证明线上集群当前运行的具体版本**。比对结果中的 `deployment_version_verified` 恒为 `False`。
2. **在线验证必须使用探针工具：** 若 Agent 在排查中需要确认线上网关或服务到底运行的是 v1 还是 v2，必须继续调用受限的只读业务观察工具（如真实 HTTP 探针、Authz 决策回执、版本 Header 核验），绝不能仅因文档存在 v2 就断言线上已完成升级。
3. **不确定性显式保留：** 比较结果的 `unconfirmed_aspects` 必须透传给 Agent，明确指出线上部署版本与调用方迁移状态处于未确认状态。

---

## 5. 证据属性与不可替代业务副作用（Evidence Not Authorization）

1. **纯调查证据性质：** 协议比对结果仅作为 `Investigation Evidence / Knowledge Context`，供 Agent 形成诊断假设或在回答中向用户清晰解释新旧协议差异。
2. **非审批、非授权凭证：** 比较结果不具备 `Approval`、`PlanAuthorization`、`ActionPermission` 或 `ActionIntent` 的法律效力；不得将比对差异作为执行 REPAIR 或 DELIVER 的授权凭证。
3. **禁止借文档差异产生外部副作用：** 即使文档说明“旧版凭证已废弃，新版需更新配置”，Agent 也必须严格经过已冻结的 D3/TaskControl 人工审批与事务守卫流程，严禁直接自动修改配置或工单。
