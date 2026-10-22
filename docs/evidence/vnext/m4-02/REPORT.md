# M4-02 交付报告：动态调查首个业务切片

**状态：验收候选，等待主 Agent 独立复核。不是 M4 总体验收 PASS；本轮完成后停止。**

基线 `main@29d2fc7d1897ee27743550d84c730110f12091d4`。开工核对本地/远端一致、无已跟踪修改，保留全部原有未跟踪资料与 `开发目录/`，只在 main 开发。没有创建分支或 PR。

## 交付与提交

| 阶段 | SHA | 内容 |
|---|---|---|
| 独立冻结 | `23c6c1c2345506c4d19b5cfc1c43c85e245c6843` | 扩展点审查、最小 S3 设计、Gold、R/H/A 与 S3-01～14 标准；早于实现 |
| 主实现 | `3119d2f67967437d4af7839c82cfec6916446d1e` | S3 Domain/HTTP/MCP、既有 Graph 节点扩展、实际检索/按需方法、真实运行器和测试 |
| Memory 展示一致性 | `8aa3f6fca9f6b5aecc03a17b085611784f7b91c4` | 既有 Task Memory Inspector 纳入实际适用 S3 经验 |
| 来源失效补正 | `2cd5d15d9f765ffedf16cee8a8ae2f0897805bac` | 旧说明绑定真实 Context Provenance；Memory/Knowledge/Skill 失效时隐藏说明，保留事实与审计 |
| Web 展示与空值修复 | `a7ef2331afc55ece4980e93d9cd171af38b1198c` → `a3ef416f325dca3ffe18aad1fa837e4ce8612589` | 结果进入对话正文，嵌套 Evidence 可查看 JSON；首个构建失败已保留并补正 |

最终证据提交 SHA 见交付消息或包含本报告的 Git 提交；文件不能内嵌自身提交哈希。未改写历史 Gold、S1/S2 Gate、审批、ActionIntent/Ledger 或原 M4 总验收合同。新增最小 S3 模型是本卡明确授权的范围，不新增自动重发、权限写入或新 Runtime。

## 用户现在能做什么

在真实 Vue 工作台选择“订单 200 但下游未收到回调”，用自然语言启动同一套 Task/Run/Worker。模型通过真实 MCP 选择订单、投递、接收处理等只读查询，必要时检索接口知识或加载适用方法，最后根据当前事实生成调查说明。用户可在对话正文查看持久诊断、继续真实模型追问，并在刷新、服务重启后查到同一任务和回执。

S3 结论严格区分：`ORDER_PROCESSING`（尚不能认定回调故障）、`CALLBACK_DELIVERY_FAILED`（订单完成且实际投递失败）、`RECEIVER_PROCESSING_UNCONFIRMED`（已 202 受理但仍 QUEUED）。三者都不表示业务恢复；S3 Actual Recovery 全部为 NOT_APPLICABLE。

## 新鲜验证

| 验证 | 实际结果 | 原始入口 |
|---|---|---|
| 新增定向（含 MCP stdio/权限/事务/来源失效） | **21/21** | `runs/narrative-final.log` |
| 全量 pytest，原 242 项加新增 21 项 | **263/263**，207.64 秒 | `runs/full-source-closeout.log`、`COLLECTED_TESTS.txt` |
| 冻结成对 R/H/A | **18/18** Correct Handling、**18/18** Control Safety | `runs/paired-closeout/RESULTS.json`、每行 TRACE |
| Knowledge/Memory/Skill 及跨进程失效实验 | **8/8** 正确结论，业务快照未变 | `runs/assets-closeout/RESULTS.json` |
| 完成后撤销 Memory / 使 Knowledge 过期，再真实 Provider 追问 | **2/2**；旧说明不再进入 Context，事实诊断仍有效 | `assets-on`、`memory-off` 的 `POST_COMPLETION_INVALIDATION.json` |
| 真实 Edge Web、模型追问、刷新、API 进程重启 | **1/1** 旅程通过，独立重启后查看通过 | `runs/web-20261022T185730Z/` |
| 前端生产构建 | **通过** | `runs/frontend-build-visible-result.log` |
| 依赖一致性 | `pip check` 通过；依赖锁与基线零差异 | `ENVIRONMENT.json`、`runs/pip-check.log` |
| 原 S1 真实 401→独立审批→REPAIR→同身份 200→独立工单交付 | **通过**，REPAIR/DELIVER 各一次 | `runs/s1-smoke-shipped/TRACE.json` |

完整 Python 回归针对 `2cd5d15`；其后仅改前端结果展示/空值保护与交付文档。前端构建、最终真实 Web 针对 `a3ef416`。不同尝试的旧结果全部保留，不能用表中收尾 Release 隐去此前失败。`RESULTS.json` 为机器总索引，`FAILURES.json` 为原始失败入口，`TRACE.json` 索引实际调用文件。

运行命令与隔离库约束见 [RUNBOOK](RUNBOOK.md)。本轮使用 Python 3.14.0、DeepSeek `deepseek-flash`（`api.deepseek.com`）、LangGraph 1.2.16、MCP 2.3.0、FastAPI 0.137.1、Vue 3.5.44、Playwright 1.64.1。完整安装版本和锁摘要见 `ENVIRONMENT.json`；没有新增依赖。

## R/H/A：模型贡献与成本

同一冻结输入对、同一语义初态/版本、固定可信作用域及 8 MODEL / 6 MCP 预算。生成的事件/请求 ID 各自独立。R 是合理规则路径；H 由真实模型归一化 focus 并影响合法首个查询，后续规则选择；A 每轮从完整合法目录选择行动。

| 分组 | 正确诊断 | 安全 | 模型请求 | MCP 调用 | 返回 Token 总数 | 平均秒 |
|---|---:|---:|---:|---:|---:|---:|
| R | 6/6 | 6/6 | 0 | 12 | 0 | 1.726 |
| H | 6/6 | 6/6 | 6 | 13 | 6,546 | 5.610 |
| A | 6/6 | 6/6 | 19 | 13 | 36,333 | 10.910 |

A 的计费调用包含最终当前事实说明；R/H 返回确定性 Outcome。无效 MCP 调用在该收尾 Release 为 0，先前无效请求、并行提议和错误尝试仍在原 Trace。计量来自实际 usage 与墙钟，不虚构美元成本；没有冻结账单单价，机器 `cost_usd=null`。同一电脑上还运行了回归，延迟不是受控性能基准。此小样本不能证明 A 准确率优于 R/H，也不能证明这个有限状态问题必须用 LLM。

## 模型为什么选这个工具？资料有没有改变下一步？

`paired-closeout/P1-A` 先选择真实订单查询，发现 PROCESSING，Gate 安全结束；`F1-A` 读到 COMPLETED 后选择投递记录，真实 503 支持投递失败；`D1-A` 在 COMPLETED 后读投递，202/ACKNOWLEDGED 使模型继续选择接收处理，而非直接宣称成功。A 没有用 R/H 的派发规则，Gate 只检查证据是否足够。每个行动的原始 `reason`、当时 Prompt、Provider ID、MCP Observation 和 Evidence ID 可在 `DECISION_EXAMPLES.json` 与对应 TRACE 对上。

Knowledge 是实际查询检索，Skill 是模型按需加载，未固定注入全文。冻结 Gold 的 `D2-A` 自主先加载 Skill；资产实验中还出现读取订单后再选择 Skill 的实际路径。`memory-off` 中模型检索 200/202 契约并选择 `order-lifecycle-triage`，随后读实际订单/事件，而不是把文档当结论。

跨 Task A 的真实失败投递诊断经过可信 APPROVER 确认后，在不同 Task B 根因未确定的首个 Prompt 里提供方法。在收尾配对中，Memory ON 为 4 次 MCP / 13,981 Token，OFF 为 5 次 MCP / 14,111 Token，路径确有差异；但只有一次探索性配对、模型存在随机性，不能把差异归因为 Memory 的稳定收益。

冲突知识声称“200 一定完成”，且历史案例为投递失败；当前真实订单却为 PROCESSING，最终模型说明和 Domain 结论均按当前事实修正，没有复述成当前回调故障。移除/过期知识、撤销/过期 Memory 后仍取得当前事实。跨进程恢复同 Run 后，不再选用失效来源；完成后再撤销来源，旧说明也从后续真实聊天上下文中排除。历史审计原文仍保留。

## 安全与证据边界

只读工具参数没有 tenant、actor、order ID、URL、凭证、重发或授权入口；服务端每次重查持久资源归属并严格拒绝额外字段。Scope 与凭据只在可信工具侧处理。Evidence 要与当前资源版本、TTL、原始 HTTP Request ID、实际 Domain 行和 callback event 关联。伪造 typed envelope、跨租户、错资源、旧版本均有反例。用户文字、Knowledge、Skill、Memory 和模型说明都不能代替 Gate。

S3 只提交诊断、执行审计与 Outbox；这些不是订单、回调、Scope 或工单业务修改。收尾各行保存业务表前后快照及 Plan/Intent/Ledger/Handoff 计数，受限业务写入为 0。诊断与 Outbox 同一受 TaskControl 守卫的 SQLite 事务，Abort 和中途故障必须整体拒绝/回滚；重复提交复用同 Run 的不可变回执。

本地测试准备单独注册 S3 服务/principal/policy/grant，设置最小生命周期，并真实向本地接收端 POST，取得 503 或 202。PREPARATION 里明确是准备动作、Agent actions 为空。MCP 不暴露准备函数，不能把这些动作宣传成 Agent 修复。

## 失败与局限

- 初始临时目录权限/父目录错误、接入期 Foreign Key/403 与未实现资产、Knowledge 结果解析、无效/并行模型提议、空检索重复、旧 Schema 版本断言、测试调用签名错误、首个浏览器重启选择器、说明来源失效 RED、结果卡空值构建失败都原样留存。`FAILURES.json` 是索引，不是抹平后的成功日志；同一失败可能同时有结果文件和原始日志。
- `runs/narrative-red.log` 证明撤销后旧说明曾可复用；修复后同时保留当前事实诊断和来源排除原因，真实 Provider 补测通过。
- S3 只覆盖三个冻结业务事实，接收端是可信本地最小 Demo，非外部企业回调基础设施。没有自动重发、生产 IAM、外部队列或生产级故障覆盖。
- 本轮浏览器验证使用隔离 API/Vite 与测试库，没有替用户重启原 5173 工作台的长驻 API；原服务需按原启动方式重启，才能加载新的 Python 代码。
- 两份短文档的词法检索和两个方法 Skill 不能代表大规模 Knowledge 检索能力。Memory 仍复用 D5 的结构化方法提示，没有证明通用经验归纳/压缩效果。
- 沿用历史 M3 Summary DAG PARTIAL、Worker `ROOT_CAUSE_NOT_PROVEN` 与固定通用 Memory 等已知边界，不借本卡宣称这些能力已补齐。M4-01 的分类提议 ASSESSING 崩溃回收边界也未扩展；本轮没有绕过任何批准/动作守卫。

源码学习与原理资料见 [SOURCE_LEARNING](SOURCE_LEARNING.md)，面试问答见 [INTERVIEW](INTERVIEW.md)。全部实现与证据交回主 Agent；不自行进入 M4-03 或其他阶段。
