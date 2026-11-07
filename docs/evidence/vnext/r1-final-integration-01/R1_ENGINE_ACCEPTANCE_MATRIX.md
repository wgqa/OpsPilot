# R1-ENGINE 能力矩阵

状态：实施方证据整理，供主 Agent 复核；矩阵不签署 PASS。

| 用户能力 | 代码存在 | 离线业务证明 | 真实 LLM 证明 | Web 证明 |
|---|---|---|---|---|
| 协议查询与版本比较 | 有受限发现、比较、原文读取与来源校验 | 有 Assistant/MCP/Domain 确定性回归 | PRODUCT-01 第 1 轮真实模型主动发现、比较 v1/v2、读原文；真实结果范围仅此历史任务 | 正式页面旅程未验收 |
| 用户材料分析与纠错 | 有同 Session Context、用户材料与 Event 归属能力 | 有真实 API/Worker/MCP 接线回归 | Slice 02 四轮真实旅程 PARTIAL；配置推断超证据，纠错 Event 的处理完成状态明确保留未知 | 页面端到端未验收 |
| S3 回调与历史 Event 调查 | 有可信 TaskBinding 下的订单、Delivery、Receiver、传输历史只读工具 | 有 QUEUED/PROCESSED、跨 Event 与权限正反回归 | Slice 02 对当前 Event PROCESSED 与历史 Event 未确认处理进行真实查询；F01 后续运行另有新观察，但部分结果受 Provider 限额阻止最终作答 | 页面结果呈现未验收 |
| S1 受控调查和修复 | 旧 Investigator/D3、独立审批、Revalidation、CAS、验证与 DELIVER 存在 | 隔离本地 Demo 有 401→Plan/审批→CAS→同身份 HTTP 200→Receipt/DELIVER 因果链 | 未证明真实模型在 PRODUCT Bridge 中自主完成 S1；新 Bridge Provider NOT_RUN | Browser STOP 有效，未验收 |
| S2 诊断与交接 | 旧 Investigator、Authn/Authz Evidence、Draft、Queue/Receipt/Outbox 存在 | 隔离本地 Demo 有 403/Authz DENY→Draft→显式提交→SCOPE_ESCALATED/PENDING_REVIEW；Scope 未授予，业务未恢复 | 未证明真实模型在 PRODUCT Bridge 中自主完成 S2；新 Bridge Provider NOT_RUN | Browser STOP 有效，未验收 |
| Assistant 调查提议及结果回读 | 有同 Session proposal/source 与可信结果只读工具 | 确定性模型正式 API/Worker/MCP 路径及跨 Session/撤权反例回归通过 | 真实模型是否会提出调查建议或读回专业结果尚无证据 | CTA、刷新与来源展开未验收 |
| Context / Memory / Skill | Context 投影、Memory 来源验证与可选 Skill loader 存在 | 有 Context/Memory/Skill 选择、撤销和预算离线回归 | AR-04C OFF/ON 有真实调用，但 ON J4 当前性表述 G7 FAIL；F01 定向复验为 PARTIAL_STOPPED_PROVIDER_LIMIT；两边未调用 Skill，不能宣称 Skill 有效或 Memory 提升 | 不推定 Web 成效 |

## 总体可用声明

目前有证据支持“隔离环境中的 Assistant + 可信 S1/S2 专业能力 + 同 Session 结果回读”作为工程候选。它不等于真实模型已完整自主完成 S1/S2，也不等于生产可用、Browser 通过或所有历史回归全绿。

来源报告：

- [PRODUCT-01 Slice 02 真实旅程](../product-01-slice-02-live/REPORT.md)
- [Final Bridge](../product-01-final-bridge-01/REPORT.md)
- [Bridge Closeout](../product-01-bridge-closeout-01/REPORT.md)
- [AR-04C 真实 Memory 对照](../../ar-04c/live-exec-01/REPORT.md)
- [F01 真实模型定向复验](../../ar-04c/f01-recheck-01/REPORT.md)
