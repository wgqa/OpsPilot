# AR-02-HF-01 冻结验收标准

**状态：** `AUTHORIZED_FREE_FIX_ONLY`

**仓库/分支：** `wgqa/OpsPilot` / `codex/ar02-hf-01`

**基线：** `0beb5b16d98e0036011ac87c1ada055063ea0bc1`

**产品 main：** `ec8c3582f6d145eec9979c43607302731411ead8`
**冻结时实际远端：** `main=ec8c3582f6d145eec9979c43607302731411ead8`，`codex/ar02-p0-01=0beb5b16d98e0036011ac87c1ada055063ea0bc1`。

开工时实际读取了当前提交的 North Star、AGENTS、`opspilot-slice-review` Skill、原 P0-01 任务卡、实现与报告、M2-01/M2-02 延期门禁。North Star/AGENTS/Skill Blob 分别为 `1f737712c7a36ceb34433ac09c3fbba3c3305542`、`32c45506cceeaa8c76a5c56bf8360ff476b58856`、`d405c8d413d633824b279202cc1503dab4cf0b03`。开工时本分支在指定 Base；原主工作区不在当前 worktree。前一切片遗留 `.tmp/` 与历史 Trace 的 EOL/stat 提示保留，未暂存。

## 产品目标和边界

用户询问当前获准范围内的回调协议时，助手应能把实际检索到的版本化资料作为来源；零命中时仍可用一般知识解释，但要如实说明没有检索到资料。资料项目配置及 TaskBinding 版本只用于检索/选择适用合同，不能冒充线上部署版本验证。此修复沿用现有有限词法/BM25 检索、资料 grant、当前来源复核、MCP 与 Chat Context；不增建 RAG、IAM、部署探测或强制 Knowledge Gate。

## 冻结正反用例

| ID | 输入/条件 | 必须发生 | 禁止结果 |
| --- | --- | --- | --- |
| HF01-K1 | 无 Task；“callback receiver protocol HTTP 202 processing” | 实际本地 MCP 搜索至少一份授权、有效且版本匹配文档；实际 `document_id`、文档版本、digest、source 与 `source_refs` 一一对应；免费替身最终依据实际结果回答 | 使用预设资料 ID 伪造命中或将一般知识冒称文档引用 |
| HF01-K2 | 无 Task；保留历史查询 `HTTP 202 acceptance processing`，它没有有限检索所需的回调/Receiver 锚点 | 允许一般 HTTP 概念解释；模型输入中的结果必须为 `documents=[]`、`source_refs=[]` | 声称“根据检索协议”或存在工具引用 |
| HF01-V1 | 无 Task；用户显式要求检索 v1 | `user_requested=1`；可信项目配置/latest 为 v2；retrieved 文档只来自 v1；部署验证恒为 false | 把 requested 或 configured 当成 deployment fact |
| HF01-V2 | TaskBinding 合同 v2，不指定检索偏好 | trusted binding/config/retrieved/applicable 可分别核对；查询只选 v2；部署验证恒为 false | 仅因 TaskBinding 有版本就设置 deployment verified=true |
| HF01-V3 | TaskBinding 合同 v2，用户查询偏好 v1 | 真实检索 v1 文档并保留请求与可信绑定的版本差异、冲突标志；applicable 仍表达可信绑定/项目配置，不把历史查询写成线上部署版本 | 静默把 v1 检索说成当前部署 v1 |
| HF01-A1 | 撤权、跨项目/跨租户、无 Task 读订单 | 拒绝/空范围；允许同一已授权项目合法资料查询 | 资料内容泄露或因修复误拒合法命中 |

正向和负向都使用实际 MCP stdio 工具链及确定性模型；本地测试 HTTP/S3 业务链仅在需要 TaskBinding 的对照中使用。模型调用和真实费用均为 0。模型回答字段只用于核验替身遵循工具事实，不能计作真实模型自主行为。

## 冻结 Smoke

`SMOKE_INPUTS.md` 独立冻结 S01/S02 原始输入、事实初态、允许工具、禁止结论及结果标准。允许不同的合理只读工具顺序，不要求零工具或调用 Knowledge。

## RED 顺序和停止线

先提交本冻结文件与 Smoke 输入，再保存有效 RED：既有空结果 `FixtureModel` 仍输出来源声明；TaskBinding MCP 把 `deployment_version_verified` 误设为 true。之后只作最小修复，再运行新定向测试、原 P0 相关免费回归和适用全量 pytest。保留所有失败日志，不改 P0 Gold、历史 RED、S1/S2 业务和费用策略。

付费 Adapter/预算上限和真实模型请求继续 `HOLD / NOT_RUN`；浏览器继续 `NOT_RUN`（B-11 STOP）。旧约 USD 0.20 建议下单次约 USD 0.317031 的预留，任何一项都不因本任务自动生效或获授权。完成后只交 `ACCEPTANCE_CANDIDATE`，交主 Agent 独立核验。
