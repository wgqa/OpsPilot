# M3-CLOSEOUT-01 新鲜验收补证报告

执行日期：2026-10-21，Asia/Shanghai。原始记录使用 UTC（2026-10-20 16:22–16:42）。执行结论：**PARTIAL，等待主 Agent 独立裁决**。本轮停止，不进入 M4。

本轮完成了真实浏览器 A→E 旅程及新鲜回归。Task A 确实受控修复并交付；Episodic v2 经独立身份确认，Task B 的持久 Context Provenance 记录选用；Web 撤销后，新 Chat 和跨进程恢复的 Provenance 排除该经验及相关旧回答。但是额外 Provider 请求体观测器挂错了 HTTP 库，没有捕获实际传输的请求体。因此，严格的“实际 Provider 请求包含／排除经验内容”补证仍不足，**不提交 PASS_CANDIDATE**。

## 版本、冻结与改动

| 项目 | 值 |
|---|---|
| 唯一代码基线 | `95b235f29af2df40b1608c23e3bf15acbaf25c26`，开工时本地及远端 main 相同 |
| 冻结范围提交 | `936c2c59f8ca13ea7187e6f25559f600d676405b` |
| Task B 准备补充提交 | `6f5249412f0420523c8476e300a523bd8a7e53b3`，准备第二事故前提交 |
| 生产代码／测试用例变更 | **0／0**；仅本目录新增报告、只读导出／索引脚本、观测辅助脚本和证据 |
| 最终证据提交 | 包含本报告的 main 提交；`git log -1 --format=%H -- docs/evidence/vnext/m3-closeout-01/REPORT.md` 可查完整 SHA，最终回复同时提供 |

没有依赖升级或 Schema 迁移。初次 API 成功启动于冻结范围提交，恢复启动于准备补充提交；两次加载的五个关键生产源码 SHA-256 完全一致，见 `runs/environment.json`、`provider-wire.jsonl` 的启动记录。导出时 checkout SHA 是导出元数据，不能冒充较早时刻的进程加载版本。

用户未提交的 `AGENTS.md`、`PROJECT_NORTH_STAR.md`、`开发目录/` 和旧临时资料没有被覆盖、暂存或删除。历史 M3 Gold、矩阵、报告及失败记录没有修改。本次不重刷 ON/OFF 收益指标。

## 环境和测试准备

独立测试 Domain 与 Checkpoint 位于项目内 `.runtime/m3-closeout-01/journey-01/`。全新库仅初始化一次 `reset_fixture(S1_POS)`，起始无 Task，integration-a 配置 v7。原用户 API8000／前端5173 的 PID 分别为32952／35684，本轮结束仍保持监听；未重置或写入用户原库。隔离 API8001／前端5174 只用于本轮，结束后已停止。

合成 `support-a`、`approver-a` 分别通过正常 Web 登录并使用既有身份／权限路径。口令随机生成并仅留在本地运行目录，不提交；独立角色身份不表示两个独立的人，也不表示生产级 IAM。浏览器原生确认弹窗无法通过当前自动化接口操作，四次由用户实际确认：A 的 Plan、Episodic 激活、Episodic 撤销、B 的正式关键更正。Web POST、Domain 行和对应事件均可查。

Task B 准备有一个必须公开的条件变化：原 SCOPE 首选复查 A 修复后的 HTTP200，但现有问题类型选择器正确地只对当前可信401／403选择相应 Episodic。只读预检后先独立提交 `CASE-B-SETUP.md`，再复用已有 `prepare_d5_auth_401_for_test` 显式准备第二个合成事故。配置 **v8→v9**，不回退版本、不重置库、不修改 A 的回执或账本，不改变 Principal／Policy／Scope。B 的401来自真实 HTTP Probe；准备动作不计入 Agent 的修复能力。前后数据和不变性在 `fixture-second-incident.json`。这一 fixture 选择是否充分满足验收代表性，由主 Agent 复核。

## A：真实401→获批修复→200→交付

| 引用 | ID／结果 |
|---|---|
| Session A | `session-ca36ed0f-1e55-4412-a552-ecb818455c4a` |
| Task A | `task-f0b9d95b-d158-4b07-8888-91d4d8030004` |
| 初始调查 Run | `run-1434f91b-5fcd-44c8-a544-c15b32cf4257` |
| Plan Hash | `2f3abcc08c9ec1672148db543c7818ee16ac9c9cfb7acdf144d9c5567eeb7ba6` |
| approver-a 的 Approval | `approval-9f8baf40-0e44-40ec-ba32-05707d07e254` |
| 原 Graph 审批恢复 Run | `run-c40635c1-fd46-42e8-ba02-06a69bf93caa`，SUCCEEDED |
| REPAIR Intent | `action-a0636774-d4cd-4db6-9dc7-e11afc6556bf` |
| REPAIR Ledger | `ledger-9fb50208-680a-44a8-a435-18ef55d88a3c`，COMMITTED，v7→v8 |
| Verification | `verification-109bf1e0-01e9-41ca-a569-00bfb22c9df5` |
| 冻结 Report v1 | `report-351640dd-9ffb-4e9d-a0bb-6864ed29d6d6` |
| DELIVER Intent | `action-9f1020d0-e159-4518-8e02-5c5e1b00fe10` |
| DELIVER Ledger | `ledger-5fdbaf3f-34ea-4cb6-a434-875a8382e40c`，COMMITTED |
| Delivery | `delivery-ac351112-bdc2-44b6-8b49-aed27e56d26d` |
| Ticket Entry | `ticket-entry-3aa09f96-7584-4710-b602-2da26f76266c` |

A 的5次实际 Provider 响应有 ID／Usage，4次 MCP 调用均有当前 Task Evidence。真实 Probe 先返回401（request `40c760a0ac63be91`），修复后相同 orders-demo／integration-a／principal-a／固定 `/api/orders/demo-order` 返回200（request `4cdbe11ce59f7027`）。实际订单字段为 `order_id=demo-order`、`status=CONFIRMED`，版本 config8／policy3／principal2；Verification 的同身份、同路由、订单及版本断言均为 true。

两个 ActionIntent 均早于相应 Ledger 提交，canonical request digest 与 Ledger 相同。唯一 Approval 明确授权 REPAIR 与独立 DELIVER。业务页面显示 DELIVERED；案例来源按可信修复与验证映射为 REPAIRED_VERIFIED。初始 INVESTIGATE Run 保留历史 WAITING_APPROVAL，实际完成由关联 APPROVAL_RESUME、回执和 Task COMPLETED 证明，不能只看旧 Run 标签。

原始引用：`TRACE-task-a.json`、`task-a-completion-snapshot.json`、`TRACE-final-domain.json` 的 d3 表及截图02–05。

## B：真实来源的 Episodic 生命周期

Memory ID：`episodic-248c7388-b3c1-4c37-a5b9-3028ecc73544`；类型 **EPISODIC**；schema `opspilot-case-memory-v1`；来源 Task A；来源 Outcome REPAIRED_VERIFIED；内容 digest：

`80f18b74aae542698b7e36108350ca8ba7cfce204bc69b55b10e1838f5da6795`

| 时刻（UTC） | 状态 | 操作者／事件 |
|---|---|---|
| 16:27:36.399 | CANDIDATE v1 | support-a；`memory-event-622eb17e-2b3e-4ac4-95d5-c7138bf067bd` |
| 16:28:53.191 | ACTIVE v2 | approver-a；`memory-event-e327f769-ed0f-4abd-9033-491e21da05d1` |
| 16:33:43.049 | REVOKED v3 | approver-a；`memory-event-1bd9f06c-9ad0-4f1f-944f-8e82e5bfd2ae` |

候选的真实内容、Experience、适用条件与来源 Evidence／REPAIR Ledger／Verification／冻结 Report 在 `episodic-candidate-state.json`，最终状态和事件在最终 Domain 导出。内容保留 A 的 v7→v8 和旧 HTTP200，明确历史方法不是当前事实或执行授权。没有以 Semantic Memory 代替，本测试库 Semantic 记录数为0。该来源未声称 S2 交接或自动授予 Scope。

## C：不同 Task B 调查与历史方法选用

Session B：`session-c9b368e0-a0ec-4fc7-896e-09adee031133`；Task B：`task-c84ae518-8a09-436c-a058-a059951c1d91`，与 A 不同；相同 tenant-a／service:orders-demo。调查 Run：`run-329a12de-0519-47c7-9d22-13f76be45c99`。

5次实际 Provider 响应、4次当前 Task MCP 调用。首次尚未证明401，Provenance 不选经验；当前 B 的 v9 HTTP401 得到可信 Probe 后，后续 **4/5** 次调用的持久 Provenance 记录选择同一 Memory v2、内容 digest、来源 Task／Outcome／refs 和 HISTORICAL_METHOD_HINT_ONLY。当前 B 的配置v9／主体v2／策略v3来自本次独立 MCP Evidence，不能把 A 的 v7／v8 当当前配置。

撤销前 Chat Run `run-9ff962f7-1487-411c-ada9-06d35600ef73` 的回答区分当前401、历史方法和未审批状态，生成依赖旧 Memory 的 AssistantMessage `message-fa6a2855-af5b-45d0-89c8-98267c9d4204`。该依赖在 `chat_message_sources` 可查，回答截图11可查。B 未获批准，未执行 REPAIR／DELIVER，Outcome 仍 WAITING_APPROVAL。

**证据边界：**这些是实际调用的 Domain Provenance、Prompt digest、Provider 返回和工具轨迹；观测器没有捕获实际发送的请求体，不能独立逐字核对进入 Provider 的经验文本。因此阶段 C 保留 PARTIAL，不把“选用记录”冒充“抓到请求体”。

## D：Web 撤销、新 Chat 与旧回答来源失效

真实 approver-a Web 撤销后，状态 REVOKED v3。随后同 Session 的 Chat Run：`run-d84bbca7-7299-46f4-9e3c-7b2b2b95b7d9`，真实 Provider response ID `f8851221c387dfcf85a08beb9378c1b7`，SUCCEEDED。

其 ContextManifest `chat-manifest-520ed173-1aa1-494f-b90d-00f1aa7ec8a7` 的 `memory_refs=[]`，排除旧助手 Message 的理由是 `MEMORY_REVOKED_EXPIRED_OR_CHANGED`。新回答没有声称已恢复或已获批准，明确本次仍是401／待审批。排除由既有结构化来源校验实现，没有按关键词删除历史文本；历史审计记录及原回答仍保留。

本轮只进行了两次 Chat，没有自然生成依赖摘要，真实 Summary DAG 撤销链标 **NOT_COVERED**。新鲜定向中的 `test_hybrid_context_compression_commits_versioned_source_linked_summary` 单独验证消息来源变化→摘要失效→依赖助手排除，Memory 撤销另有独立来源测试。这些是自动化证据，不能冒充真实 Episodic 撤销摘要旅程，也不声称验证了任意多层摘要 DAG。新 Provider 原始请求体仍属于 GAP-01，实际传输内容的独立证明保留 PARTIAL。

## E：同 Run 跨进程恢复

Web 正式关键更正 Message `message-8a8a7641-304c-424a-af98-327e21ebdddd` 进入同一个 Task B，控制版本受理1、应用2，旧 Plan 取消，创建调查 Run：

`run-4cde0f27-14a7-4044-bed8-291b01db9d7d`

Checkpoint thread：`opspilot-0338f70c-37a3-42b1-a02a-ead295b60d13::run-4cde0f27-14a7-4044-bed8-291b01db9d7d`。

在该 Run 已有1项当前 MCP Observation、5个持久 Checkpoint 时，受控终止本轮 API 进程树。旧 launcher30904／实际 API19320；新 launcher40016／实际 API38868。UTC16:35:41.846开始终止，16:35:41.992确认终止，16:35:42.712新服务就绪。同库、同 Checkpoint、同 Run 继续，最终同 thread 有10个 Checkpoint，Run 于16:35:49.258回到 WAITING_APPROVAL。不是重启后另造 Run。

Task B 累计 MODEL 预留6→8、MCP5→6，保持既有限额；新 Run 自身 MODEL3次预留（2次响应、1次结果未知），MCP2次。恢复后的 Context Provenance 仍无 selected memory，并记录该 Memory v3 的 `MEMORY_REVOKED`。Task B 未执行业务写入；全库仍只有 A 的一个 REPAIR 和一个 DELIVER，没有重复副作用。S1 Gate 可复用同 Task 的兼容事实，不能把2次新增 MCP 宣称为重新采集了全部4类事实。

崩溃窗口的 `attempt-52e3a93b-7e05-421e-a1e5-3f0e759e3ebc` 保留 RESERVED／PREPARED，无 Provider 返回。是否到达 Provider、Token 与费用均 **UNKNOWN**，不按零计。恢复成功只表示执行恢复到合法等待审批，不表示 B 的业务已经修复。实际恢复后 Provider 请求体未捕获，因此这项完整内容补证也保留 PARTIAL。

## 新鲜测试、调用计数和成本

| 类别 | 本次结果 | 原始日志／来源 |
|---|---|---|
| 完整 pytest | **225/225 PASS**，164.40s | `runs/regression-01/pytest-full.log` |
| Episodic／Semantic／Context 定向 | **24/24 PASS**，15.51s | `runs/regression-01/pytest-focused.log` |
| frontend typecheck／build／lint | **3/3 PASS**，各 exit0 | 对应 frontend 日志与 exit-code |
| Provider 响应含 Usage | **14**（Investigator12、Chat2） | d2_model_traces／chat_attempts |
| 模型尝试预留（含 Chat） | **15**；其中1次中断结果 UNKNOWN | d2_attempts／chat_attempts |
| MCP tools/call | **10次尝试、10次 OK Observation** | d2_attempts／d2_tool_observations |
| MCP tools/list | 未单独保存原始计数 | 已有真实 stdio 调查路径，不能虚报次数 |
| 真实业务 HTTP | **4**：A401、A验证200、B401、B更正Run401 | auth_events／Verification／Probe Evidence |
| Provider 原始请求体 | **0/14 捕获** | GAP-01；provider-wire 仅3条启动记录 |
| OS 崩溃／同 Run 恢复 | **1/1**，来源与预算检查通过 | crash-trigger／process-events／Checkpoint |
| Scope 写入／Task B 动作写入 | **0／0** | 初始、准备、最终快照及账本 |

24项定向用例是完整225项的子集，不能把两者相加成249项。没有新增、删除或修改测试。确定性回归中的 Mock 不计入上述真实模型、MCP 或浏览器旅程。

| Run 段 | 已知输入／输出／总 Token | MCP |
|---|---|---|
| A 调查 | 15912／1190／17102 | 4 |
| B 初次调查 | 19968／1628／21596 | 4 |
| 撤销前 Chat | 1462／545／2007 | 0 |
| 撤销后 Chat | 1084／1193／2277 | 0 |
| B 更正与恢复 | 5654／456／6110，另1次 UNKNOWN | 2 |
| 已知合计 | **44080／5012／49092**，另未知中断量 | 10 |

Provider 未返回货币费用，不根据未知的现价估算；中断尝试不能当作免费。内含 Provider 统计的 reasoning／cache 数据原样留存，不把估算 Token 当实测。本轮不提出 Memory 提高成功率或节省成本的结论。

## GAP-01、失败及已知限制

`runs/helpers/observed_server.py` 在额外测试入口包装了 httpx 的实际 send，意图原样转发并观测安全请求体。当前已安装 OpenAI SDK 的 `_base_client.py` 实际导入 httpx2，LangChain `_compat.py` 也选择 httpx2，因此该观测器没有截获模型请求。`provider-wire.jsonl` 名称保留原样，内容只有启动 PID／源码 hash，不得把文件名当成已抓包的证明。根因来自本地 SDK 源码核对，没有升级依赖、没有伪造或离线补造实际请求体。

本轮所有实际调用仍有 Provider 返回 ID／Token、MCP、Domain Provenance 和来源校验记录。缺口是独立核验实际传输的记忆内容／排除，而非声称模型未真实调用。按任务卡“缺少关键真实证据继续 PARTIAL”，本轮停止并保留这一裁决，未另建环境重复演示来覆盖原始记录。

其他尝试、操作工具超时、初始化错误、报告脚本误判及未保存为文件的早期检查输出，在 `FAILURES.md` 逐项说明。历史原库两次 `WORKER_RETRY_EXHAUSTED` 本次未复现，根因仍未定位，不能因本轮未出现而关闭。隔离 SQLite／loopback／合成身份仅证明本地 Demo 范围。

## 十条件裁决与证据入口

机器判定见 `RESULTS.json`：条件1、2、3、5、8、9、10具备本轮证据；条件4、6、7的 Domain／调用／恢复记录具备，但实际 Provider 请求体内容补证不足，保留 PARTIAL。真实 Summary 失效链 NOT_COVERED 属任务卡允许明确披露的子项，不伪装通过。

`TRACE.json` 按 UTC 关联全程；`runs/journey-01/TRACE-final-domain.json` 为47张白名单业务／来源表的脱敏只读导出，排除凭据值表和认证会话表。截图与 DOM01–16对应浏览器流程。`EXECUTION.md` 提供运行命令与阅读路径；`runs/environment.json` 提供依赖版本、锁文件摘要和加载源码 hash。

未发现需改生产代码的直接阻断缺陷，未更改冻结安全合同。本轮不自行接受整体 M3，也不进入 M4。等待主 Agent 与用户进行整体项目复盘。
