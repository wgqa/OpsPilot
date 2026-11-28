# R1-FINAL-INTEGRATION-01 — 集成候选报告

状态：ACCEPTANCE_CANDIDATE，等待主 Agent 独立裁决。本文不签署 PASS、MERGE_READY 或 main 合并许可。

## 基线与合流

- 代码 Base：codex/product-01-bridge-closeout-01，6b5bfb16c461afcf1cdafaad9ebe08dd6a004b27。
- 远端 main（开工与本轮复核）：60eee87bfe3cca522011316cb4cd2c0064ad291b，未修改。
- v1.2 文档来源：codex/product-roadmap-v1-2，339c2385ce0346dc97feaa63c9ca034545adbe77，父提交 5b174aa59be072d38d716b7e908f523fa7df92f9。
- 文档移植：在隔离分支 cherry-pick 文档提交，形成 aba552cebda5b0ec4c3da22aaca98ec944d9d8cb；仅改四份治理文件。
- 候选分支：codex/r1-final-integration-01。本报告随证据提交至该分支；最终完整 SHA 以远端分支核验值为准，并由本次交付消息报告。
- 原工作树、其他 worktree、私有账本、历史 Claim、Gold、RED、Trace 均未清理或覆盖。

合流只包含 6b5b 的既有产品代码及 v1.2 路线文档，不重新合并未验收开发分支。代码 Base 已包含 Product Bridge 与 Bridge Closeout。最终工作 Diff 不修改生产 Python、前端源代码、依赖锁或历史验收文件。

## 四份治理文档

本次只在以下四份现有文件上调整方向和状态：

- PROJECT_NORTH_STAR.md：说明 R1 冻结后 R2/R3 可在各自授权与验收下交错推进，R3 不必等待 R2 全部完成，也不代表 R2 已完成。
- AGENTS.md：同步上述 R2/R3 关系，保留用户成果优先、工程按需演进及各类独立授权。
- TASKS.md：更新 PRODUCT-01 与 R1 的当前状态、历史全量失败分类和浏览器/Provider 未运行项。
- README.md：说明现有证据级别与限制，并链接本集成评审输入。

集成前 Blob：

| 文件 | Blob |
|---|---|
| PROJECT_NORTH_STAR.md | 4850247350f71635d176699e304a5208d72adf0c |
| AGENTS.md | b606084799e463a6fb6ffeb6b18aa1f6b4afa64d |
| Review Skill | d405c8d413d633824b279202cc1503dab4cf0b03 |
| TASKS.md | 31be72ed36cdc5150768672766f5128fa1be5111 |
| README.md | 87a2ba465f00fabb512137129ca656ba6c992208 |

本次最终 Blob 与文档链接检查结果列于 EVIDENCE_INDEX.md。

## 用户成果与证据等级

已实现并有本地确定性业务证据的能力：

1. 用户在原 Assistant Session 发起问题，经明确确认后，旧 S1/S2 Investigator 继续调查；可信 Plan、Outcome 与 HandoffReceipt 可在同一 Session 读回。
2. 隔离 Demo 的 S1 路径已覆盖审批、Revalidation、CAS、同身份本地 HTTP 401→200、VerificationReceipt、冻结报告与独立 DELIVER。
3. 隔离 Demo 的 S2 路径以可信 HTTP/Authz Observation 形成草稿；显式提交后产生本地 Queue、Receipt、Outbox，状态为 SCOPE_ESCALATED / PENDING_REVIEW。结果说明未授予新 Scope、未证明 403 已恢复。
4. 普通 Assistant、S3 只读调查、Task/Session 来源与前端持久来源投影已有对应定向回归。

真实模型证据必须单独描述：

- PRODUCT-01 Slice 02 的 DeepSeek 四轮连续旅程为 PARTIAL：8 Provider 请求、9 MCP 调用。模型完成协议咨询、用户 JSON 材料分析、绑定后同 Event 调查及纠错说明；配置适用性推断超出证据，第四轮说明仍需校稿。
- AR-04C LIVE 的 Memory OFF/ON 实验为 PARTIAL：8 Provider、14 MCP。ON J4 在 MCP=0 时称本轮已重新读取，冻结 G7 ON 为 FAIL。
- F01 定向真实复验为 PARTIAL_STOPPED_PROVIDER_LIMIT：8 Provider、10 MCP。第三轮重新观察到 QUEUED；第四轮实际取得同 Event PROCESSED Observation，但第 9 次模型调用被上限阻止，用户看到程序限额通知，不能称模型已根据 PROCESSED 作答。
- PRODUCT-01 Final Bridge 的新桥接真实模型行为未运行。以上真实模型结果不能证明 S1/S2 新桥接路径由真实模型自主完成，也不能升级为整体 PASS。

## 三项 AR-03 Runner MockTransport 失败

当前候选的目标测试为 0/3；最近可确认的冻结通过基线 8df557dabb6f7440b371828c39974239363ee6d9 为 3/3。它们共同失败的确定原因是历史实验 Runner 的冻结工具 allowlist 与随后产品集成新增的两个正式 Assistant 只读工具 Schema 不一致。

当前真实 Assistant MCP Schema 除历史工具外还公开：

- propose_controlled_auth_investigation
- read_session_professional_outcomes

旧 Runner 位于 docs/evidence/ar-03/material-live-01/run_live.py，只有它冻结的 ALLOWED_TOOLS。Recording transport 的 handle_async_request 先调用 _CampaignState.begin；begin 在发现未知工具名时抛出 UNAPPROVED_TOOL_SCHEMA_EXPOSED，异常在进入内层 MockTransport handler 之前发生，因此测试记录器中的 request/observation 数为 0。

拦截条件是 Runner 对冻结 Schema 的精确拒绝，不是当前 Assistant 工厂绕过 MockTransport。正式测试工厂把显式 MockTransport 作为内层 AsyncTransport，并提供拒绝网络的同步 Transport；没有自动退回真实 Provider。三项测试都在临时 DB 中运行。数据库中 assistant dispatch 被记录为 UNKNOWN/Usage UNKNOWN、Run FAILED；这个 UNKNOWN 是该旧记录器在 request 已交给外层包装器后、内层模拟 handler 尚未收到时采用的保守软件状态，不表示已经向外部 DeepSeek 发出请求。本轮真实 Provider HTTP=0。

这是文档/产品集成造成的旧实验 Harness 兼容断裂：在已知通过的旧 Runner 版本中三项通过；加入 Product Bridge 工具 Schema 后，冻结 Runner 拒绝额外能力。它没有证明普通 Assistant 或 S1/S2 业务路径失败，也不构成放宽历史实验工具合同的依据。没有改旧 allowlist、Gold、Authorization、Claim 或 Runner，以免让已消费实验身份看似重新可执行。

主 Agent 在决定候选发布范围时仍应把这三项作为未关闭的实验复现债务，而不是当前 S1/S2 产品回归通过。具体日志、基线与影响见 FAILURES.md。

## 本轮验证

| 范围 | 结果 | 证据解释 |
|---|---:|---|
| PRODUCT-01、S1/S2、D3、AR-02/AR-03 适用的定向 Python 回归 | 77/77，通过，136.10 秒，退出码 0 | 当前候选源码 SHA 上实际执行；Provider=0，外部写入=0 |
| 三项 AR-03 旧 Runner 目标测试 | 0/3，通过；3 项失败，7.17 秒，退出码 1 | 已定位为冻结 allowlist 与新增工具 Schema 的冲突；不重写旧合同 |
| 前端 Assistant 入口单测 | 8/8，通过，退出码 0 | 使用 Node 内置测试运行器及 TypeScript transform |
| Vue TypeScript 检查 | 通过，退出码 0 | 当前依赖安装后执行 |
| Vite 生产构建 | 通过，退出码 0 | 当前依赖安装后执行 |
| 变更相关 ESLint | 通过，退出码 0 | 检查 App.vue、assistant-entry.ts 与测试文件 |
| Python compileall | 通过，退出码 0 | 编译 opspilot 包 |
| CLI reset | 通过，退出码 0 | 新建唯一临时 S1_POS Demo DB |
| 正式本地 API 健康启动 | GET /api/health 返回 HTTP 200，worker ready=true | 使用独立临时 DB/Checkpoint、127.0.0.1、Provider disabled、无凭据；本地服务日志达到 Application shutdown complete。Windows 控制信号退出码为 3，故本次只判定健康启动与 Worker ready，不把退出码记作正常终止 PASS |
| pip check | 环境检查退出码 1 | 全局 OpenTelemetry API 1.45.1 与 SDK/semantic-conventions 要求 1.42.1 不一致；未改锁文件或升级依赖 |
| 完整 pytest | 本轮未重跑 | 前次报告的 741/757、16 失败是上一个 SHA 的历史终态，不作为本候选新回归结果 |

前次完整结果中的 16 项：12 项与已消费的 AR-04C 授权/Claim/冻结身份相关，3 项为上述 AR-03 MockTransport Runner 失败，1 项仍要求废弃的 C1 READONLY_FOLLOWUP 合同。C1 当前合同 FOLLOW_UP + readonly_action=INVESTIGATE 在前次报告的独立正例已通过。原始失败与日志保持原样。

依赖处理：前次 npm audit 的 11 个 moderate 告警作为既有依赖债务保留；本轮未执行 npm audit fix、未改 package-lock。npm ci 使用任务私有 cache 成功，node_modules 未进入 Git。pip check 的 OpenTelemetry mismatch 也未处理。

## 正常本地运行

Windows / PowerShell 的可复现步骤与健康检查见 RUNBOOK.md。当前实际核验的是隔离 S1_POS reset 与单 Worker 本地 API health，不含浏览器页面验收，也不含真实 Provider Web 调用。

正常离线应用的启动不依赖实验 claim；但 Assistant 真实 Provider Factory 只有在显式开关、支持的实验 ID、匹配配置和对应授权条件成立时才可建造。仅设置 API Key 不构成付费授权。具体安全边界与命令见 RUNBOOK.md。

## 本轮未执行

- DeepSeek 或其他真实 Provider 请求：0。
- 浏览器 / Playwright / Computer Use：NOT_RUN，BROWSER_STOP_ACTIVE。
- 外部企业系统读写：0。
- main 合并或推送：未执行；只推送本隔离候选分支。
- 新 R3 业务开发：未启动。

## 六维自检

1. **用户结果：** 当前可复用的交付是同 Session 内从 Assistant 问题进入可信 S1/S2 调查，再读回真实 Domain Plan、Outcome 或 Receipt。真实模型完成新桥接的结果仍没有证据。
2. **模型决策：** 普通 Assistant 可回答、读资料/只读事实、提出受控调查建议或读取专业结果；只有用户通过现有可信入口确认后才建立专业 Task，S1/S2 Investigator 仍执行旧业务调查。
3. **观察驱动：** 本地 Demo 的 HTTP/Authz、S1 401→200 与 S2 403/等待审查结果来自真实本地 MCP/Domain；真实 PRODUCT Bridge 选择和回答尚未验证。
4. **约束：** 本轮没有放宽权限、Approval、来源、TaskControl、幂等、预算或业务写入边界。3 个旧 Runner 失败不以放宽 allowlist 消除。
5. **简化：** 复用现有 Assistant、MCP、Task API、旧 Investigator、D3/S2 Handoff、Domain 与 Web 投影；本轮仅移植路线文档并整理证据。
6. **证据与停止线：** 77 项定向 Python、8 项前端测试、typecheck/build/ESLint、compile、reset 与本地 health 均有本轮结果；3 项旧 Runner 测试和环境/历史失败明确列出。没有收费、浏览器或外部写入。

## 交付建议

实施方结论只为 ACCEPTANCE_CANDIDATE。建议主 Agent 复核是否接受为 R1-ENGINE 候选，并限制对真实 LLM/S1/S2 自主执行、浏览器体验和全量 pytest 的任何宣称。当前证据不足以建议无条件整体验收或 main 合并；最终裁决归主 Agent。
