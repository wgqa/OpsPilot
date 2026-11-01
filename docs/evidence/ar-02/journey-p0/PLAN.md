# AR-02-JOURNEY-P0 冻结计划

## 开工核验

- Repo：`wgqa/OpsPilot`
- Branch / Base HEAD：`codex/ar02-live-01@09613b2d858313a0b11ff865ee2dfeb66dd52e09`
- 开工工作区：clean；本轮修改只进入当前隔离分支。
- 远端读取：`git ls-remote origin refs/heads/main refs/heads/codex/ar02-live-01` 因 GitHub 443 连接失败，远端 SHA `UNVERIFIED`。本地缓存的 `origin/main` 为 `ec8c3582f6d145eec9979c43607302731411ead8`，本地目标分支起始 HEAD 与上次已推送 SHA 一致。
- `PROJECT_NORTH_STAR.md` Blob：`1f737712c7a36ceb34433ac09c3fbba3c3305542`
- `AGENTS.md` Blob：`32c45506cceeaa8c76a5c56bf8360ff476b58856`
- `.agents/skills/opspilot-slice-review/SKILL.md` Blob：`d405c8d413d633824b279202cc1503dab4cf0b03`；本次实际读取 Skill A，并按任务卡准备测试/失败/收尾证据。
- `docs/evidence/ar-02/hf-01/SMOKE_INPUTS.md` Blob：`ee9b1623a2296905c425449709a2f9ae6563caca`
- `docs/evidence/ar-02/live-01/ACCEPTANCE_PLAN.md` Blob：`6ea52b2ee584a405d69d71861e48515b69b76d03`
- `docs/evidence/ar-02/conn-02/REPORT.md` Blob：`ab22885137e7a73f0520e4fa915d68488dc1a571`
- AR-02 专属 `DEFERRED_GATES.md` 未找到；适用的前序 P1 状态是 `NOT AUTHORIZED`，CONN-01 为 `FAIL / STOPPED_NO_RETRY`，P1 dispatch 为 `UNKNOWN`。这些历史状态、费用预留和数据库均只读，不恢复、不重置、不复用。
- 当前任务卡由用户在本对话完整提供。North Star §0/§2/§3/§8、AGENTS 顶部和历史条款已核对：本切片须让用户通过连续自然语言获得可追溯说明，同时不让模型获得绑定或业务写权限。

## 冻结范围

本轮只做免费实现与离线验证。唯一用户旅程是冻结的 S01 与同一 Session 中的 S02 五轮。S01/S02 原文和 Gold 不改写。

- S01：对 HTTP 202 是否代表回调已处理的提问，经正式 API、Worker、`ASSISTANT_V1`、确定性模型、必要时的授权 Knowledge/MCP，得到持久 Session 答案；无当前 Event/Receiver Observation 时不得称已处理。
- S02-1/2：分别提交冻结的示例线索和协议查询要求；示例线索是不可信用户输入，模型可零工具回答或请求有权限的 Knowledge。只有真实 Knowledge MCP 返回的 document/source reference 可被引用。
- S02-3：用户通过认证的正式订单绑定 API 确认 `ar02-order`。对话文本本身不得建立 TaskBinding 或授权订单访问。
- S02-4：在同 Task 内调查当前订单、Delivery、Receiver；同 Event HTTP 202 只能说明接收，QUEUED/UNKNOWN 不能解释为完成；不同 Receiver 观察必须导致不同、合理的答复。
- S02-5：生成带事实来源和明确未知事项的说明草稿；不得声称审批、修复、工单提交或外部写入。

## 冻结验收与 RED/GREEN 标识

| ID | 冻结断言 | 证据要求 |
|---|---|---|
| JP0-01 | Provider 默认关闭；仅有密钥不构造可发送的 Provider；服务器标准入口仍将正式 factory 注入 Worker | API/Worker/工厂测试；真实 Provider 请求 0 |
| JP0-02 | 正式 factory 用显式 HTTPX async/sync client；由 HTTPX2 的本地 MockTransport 捕获实际 LangChain SDK 序列化请求 | endpoint、model、thinking、max_tokens、tool_choice、parallel_tool_calls、tools、无 `max_completion_tokens` |
| JP0-03 | S01 正式 API→Worker→`ASSISTANT_V1`→MCP/Knowledge（或零工具）→持久答复完整 | Session Message、source Message/Run、Run 状态及出站模型输入关联 |
| JP0-04 | S02 五轮共用同一 Session；订单仅通过受信绑定 API 建立；每轮用户消息与持久答复可关联 | 五轮 Message/Run ID、绑定 ID、Answer、实际 MCP Observation |
| JP0-05 | 绑定后所有业务查询通过正式 MCP Client/Server；订单 GET 走受控 loopback HTTP，交付/接收事实来自 Domain | MCP tool/Observation、HTTP 轨迹及对应 Task/Order/Event/版本 |
| JP0-06 | Knowledge 命中、空结果、文档版本/来源语义不混淆 | 真正返回的 document ID、version、digest、source_ref；空列表不得宣称引用 |
| JP0-07 | 没有绑定时，用户消息或模型工具提议不能授权订单查询；绑定后合法同订单只读查询可成功 | 未绑定负例及受信绑定正例双向验证 |
| JP0-08 | QUEUED 与 UNKNOWN 的 Receiver Observation 不会被回答为已处理；改变观察会改变合理的结论/缺口 | 至少一组同目标不同状态的模型输入、Observation、答复对照 |
| JP0-09 | 所有 HTTP/MCP/SQLite 均限于测试本地；业务写入计数为零 | 禁止 Diagnosis/Approval/Intent/Ledger/Handoff/Receipt 写入；Provider 请求 0 |
| JP0-10 | 旧 CONN-01、P1 UNKNOWN 及冻结 Gold 字节保持不变，main 不变 | Base 对比、Git 状态和旧 SQLite/Trace 哈希检查 |

## 测试方法与停止线

- 先运行现有相关测试形成基线，再新增定向 RED，记录原始日志；实现后运行 GREEN 与相关 AR-02/MCP/Worker/安全回归。
- Provider 测试只能通过显式 HTTPX `MockTransport`，不创建可直连外网的测试模型；S01/S02 必须通过 TestClient 和正式单实例 Worker，业务工具经子进程 MCP stdio 与本地 HTTP/SQLite。
- 不调用真实 Provider、不做浏览器自动化、不执行任何业务写入、不重跑 P1/S01/S02 真实模型实验。
- 若发现现有合同不能在上述范围内满足，停止并报告；不更改冻结 Gold 或预算。
- 终态只交 `ACCEPTANCE_CANDIDATE`，主 Agent 独立审查后决定后续精确付费实验授权。

## 实现与证据状态

本文件先于源码变更冻结。RED、GREEN、最终分子/分母、运行版本与失败均追加到 `RESULTS.json`、`FAILURES.md` 和 `runs/`；真实 Provider 自主行为保持 `NOT_RUN`。