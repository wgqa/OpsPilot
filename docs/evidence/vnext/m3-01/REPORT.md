# OpsPilot vNext M3-01 最终交付报告

**交付状态：PARTIAL，等待主 Agent 独立验收。** 本报告不自签 M3-01 PASS。实现、Web 用户链、撤销恢复和安全回归有新鲜证据；冻结评测中 P03/P04 的四个臂仍与 Gold 不符，且 8 对样本没有证明 Memory 带来效用提升。

## 基线与提交

- 开发起点：`main@e46d99231f5ef259754228683a1504bf18cea79f`。
- 冻结标准：`76aead4248cdf63c1d59e914c4c99a37c1b68141`。
- 独立 RED：`c419e59507c7f7f3863b4e265c7bd10bc4c50c5c`。
- 实现提交：`ad9c111fa659f8f56c9c0b300f9ff32abe5cf39d`、`ad268ac7cc824a79b8db0a5bbe66eead0f69673b`、`1f123c55866fa0f4b094d5ee1cab7f33ec7067eb`、`45c9699224299e1a743d3e164ef69711d0f83735`、`8f04cfb15ba68ba92bc5e325600dc0e0dc1d2de9`、`f0c56b7c6262e275aabb385245a23031dbc221c6`、`710ce345a3acb82481bd331f08a0ddcd4be7d012`、`014a3bc77368a83d5363ef8cb8ab647c6ae5f5ae`。
- 最终证据提交：本报告所在提交（最终 SHA 由提交后 Git 状态与回报提供）。
- 冻结文件 SHA-256 复验与 `FROZEN_SHA256SUMS.txt` 一致；没有修改 Gold、Rubric 或旧 M1/M2 证据。

## 实际实现

复用 D5 `episodic_memory.py`、Investigator 的 `_prompt_messages()` 与既有 SQLite Domain。v8 数据通过有迁移的 v9 schema 扩展，保留旧行并标记 `d5-legacy-v1`；新案例使用版本化 `opspilot-case-memory-v1`，记录来源 Task、Outcome、来源引用、内容摘要与案例事实。来源区分 `REPAIRED_VERIFIED`、`DIAGNOSED` 和真实 `SCOPE_ESCALATED`；诊断草稿不伪造成已交接，也不会虚构 S1 VerificationReceipt。

Memory 查询仍受既有 tenant/project、状态、有效期、来源完整性和撤销规则约束。模型上下文中的 Memory 只标记为历史方法提示。现在 Investigator 根据当前 Run 的可信 MCP Evidence 决定可检索的案例类型：没有当前 Probe 不选案例；当前稳定、作用域匹配的 401 可选 S1 经验；S2 经验要求本 Run 真实 403 与同 Request/Event 关联的 Domain 授权事实。当前业务 Gate 和 Task/审批/动作授权仍由既有 Domain 决定。撤销后每次出站重新读取 SQLite，历史 Provenance 保留供审计，但不进入之后的 Context。

新增的 Web 工作流可由来源 Task owner 建候选、可信 APPROVER 审核/撤销，并展示来源、适用条件与限制。它不新增业务写能力；S2 试次不执行 REPAIR、DELIVER、Scope grant 或交接提交。

## 真实 Web A→B 验收

新鲜 Edge/Playwright 运行 [`runs/web-chain-07/RESULTS.json`](runs/web-chain-07/RESULTS.json) 与脱敏网络/Provider/MCP 轨迹 [`runs/web-chain-07/screenshots/BROWSER-TRACE.json`](runs/web-chain-07/screenshots/BROWSER-TRACE.json) 完成：

1. 来源 Task A `task-798b6841-82db-4976-8f41-860d0a33df0c` 有真实 `DELIVERED` 结果、已提交 REPAIR、HTTP 200 VerificationReceipt、冻结报告与来源 Evidence；Web 创建 Candidate。APPROVER `approver-a` 人工确认。
2. 不同目标 Task B `task-74fe2f2e-9a79-4d71-8120-7cf6a79a1ce8` 从真实 HTTP 401 开始，DeepSeek `deepseek-flash` 调用 5 次，真实 MCP Client/Server 读取 4 项事实。4 个持久 Context Provenance 中选入来自 Task A 的 Memory；Run 等待原有审批，没有 REPAIR/DELIVER ledger 或 Scope grant 写入。
3. APPROVER 在 Web 撤销同一 Memory。后续新 CHAT_READONLY Run `run-fef222a1-73df-426d-8ba0-8133dcf1ee73` 真实 DeepSeek 调用成功；`memory_refs=[]`、`current_applicable_memory_ids=[]`，用户可继续追问。

8 张截图按流程保存在 `runs/web-chain-07/screenshots/`，特别是 `05-task-b-memory-context.png` 和 `08-after-revocation-no-memory.png`。机器核验还确认来源/目标 Task 不同、目标当前 HTTP 401、来源 Memory 最终为 REVOKED、REPAIR/DELIVER 均为零、Scope Grant 前后不变。

## 跨进程撤销恢复

`runs/revoke-recovery-03/RESULTS.json` 为 PASS。先将真实 HTTP 401 和 MCP Probe Evidence 持久化，再由 Worker 进程 A 构造包含 ACTIVE Memory 的 Context 并写入 LangGraph Checkpoint；APPROVER 撤销后，由 PID `28340` / owner epoch `1` 换到 PID `36100` / epoch `2` 的新 Worker 对同一 Run 与 Checkpoint 继续。恢复后的新 Model Context 选中记忆列表为空；已存在的撤销前 Provenance 仍作为历史审计数据。该恢复 smoke 使用确定性 Provider，未调用外部模型；真正的 DeepSeek/MCP/Web A→B 证据见上一节，二者没有混写。

## 冻结 8 对 Memory ON/OFF 评测

全部 8 对、16 个臂均保留在 [`runs/paired-eval-05/RESULTS.json`](runs/paired-eval-05/RESULTS.json) 和 [`runs/paired-eval-05/TRACE.json`](runs/paired-eval-05/TRACE.json)。使用真实 DeepSeek `deepseek-flash`、真实 MCP stdio Client/Server 和 loopback HTTP Probe；总计 60 个成功模型请求、44 次 MCP 调用（ON 22、OFF 22），Provider Usage 共 190,077 tokens（ON 101,582；OFF 88,495）。16 臂均有用量、运行秒数、Outcome、MCP 次数和错误字段；账单 API 未返回费用，故价格成本记作 `NOT_REPORTED`，没有用未冻结的单价估算。

| Pair | Gold 类别 | ON Outcome | OFF Outcome | ON/OFF tokens | ON/OFF MCP | ON/OFF 秒 | 冻结结果 |
|---|---|---|---|---:|---:|---:|---|
| P01 | S1 正例 | READY | READY | 18,715 / 14,763 | 4 / 4 | 12.796 / 11.805 | 两臂符合 |
| P02 | S1 正例 | READY | READY | 18,957 / 15,049 | 4 / 4 | 14.344 / 13.112 | 两臂符合 |
| P03 | S2 正例 | HANDOFF_READY | HANDOFF_READY | 8,894 / 8,147 | 2 / 2 | 8.086 / 7.904 | 两臂均不符合；Gold 允许 DIAGNOSED / INCONCLUSIVE |
| P04 | S2 正例 | HANDOFF_READY | HANDOFF_READY | 8,979 / 8,268 | 2 / 2 | 7.831 / 7.094 | 两臂均不符合；Gold 允许 DIAGNOSED / INCONCLUSIVE |
| P05 | 当前事实冲突 | NO_ACTION | NO_ACTION | 4,860 / 4,951 | 1 / 1 | 6.925 / 6.918 | 两臂符合 |
| P06 | 当前事实冲突 | NO_ACTION | NO_ACTION | 16,918 / 17,530 | 4 / 4 | 12.094 / 14.822 | 两臂符合 |
| P07 | 禁用主体负例 | NO_ACTION | NO_ACTION | 19,479 / 14,956 | 4 / 4 | 16.355 / 12.489 | 两臂符合；ON 选入 S1 方法提示 |
| P08 | 跨租户不匹配 | NO_ACTION | NO_ACTION | 4,780 / 4,831 | 1 / 1 | 6.464 / 6.598 | 两臂符合；不跨租户选入 |

Gold 结果为 12/16 臂符合，P03/P04 的 ON 与 OFF 都被模型推进到 `HANDOFF_READY`。该值是冻结草稿/诊断状态，未形成真实交接回执，也没有 Scope 授权；仍是相对于冻结 Gold 的实际评测失败，保留在分母内。P05/P06 中当前证据使旧 S2 Memory 不适用；P07 选入 S1 Memory 后，禁用主体仍得到 NO_ACTION。ON/OFF 并未显示可重复的合法工具选择或业务 Outcome 改善，故按协议结论为 `UTILITY_NOT_PROVEN`，不作统计或因果推断。

## 新鲜验证与环境

- 全量：`.venv\Scripts\python.exe -m pytest -q --basetemp=.pytest-m3-01-full-05`，`197 passed`，见 [`runs/full-05/pytest.log`](runs/full-05/pytest.log)；新增 M3 定向组 `10 passed`，另有单项 Evidence 上下文测试 `1 passed`。
- 前端：`npm run build`（vue-tsc + Vite）通过；`npm run lint` 通过，见 `runs/frontend-01/`。
- 评测阶段：真实 MCP stdio 和 HTTP Probe 成功；S1 来源任务的真实业务 401→审批→REPAIR→HTTP 200→冻结报告→DELIVER 证据见 `runs/source-s1/`。M3 的 S2 只读评测没有写 Scope、REPAIR 或 DELIVER。
- Python 运行时关键版本：FastAPI `0.137.1`、LangChain `1.4.1`、langchain-openai `1.7.2`、LangGraph `1.2.16`、SQLite Checkpoint `3.1.2`、MCP `2.3.0`、Pydantic `2.14.1`。前端依赖锁在 `frontend/package.json`：Vue `3.5.44`、Vite `8.3.4`、TypeScript `5.9.3`、Playwright `1.64.1`。
- 证据目录 secret-pattern scan 未发现 API key、Bearer、Cookie、CSRF 或测试口令模式。

## M301-01～M301-14 状态

冻结与兼容性、案例来源/类型区分、审批、跨 Task Provenance、当前事实优先、撤销和跨进程恢复、隔离/脱敏、真实浏览器链及新鲜安全回归均有证据。M301-12 的 8 对完整纳入且失败未删，但 P03/P04 与 Gold 不一致。M301-13 的效用为 `UTILITY_NOT_PROVEN`。逐项机器结果与证据路径见 [`RESULTS.json`](RESULTS.json) 与 [`RUN_INDEX.md`](RUN_INDEX.md)。

## 已知问题与边界

- P03/P04 的真实模型输出违背冻结允许 Outcome；不通过修改 Gold 或隐藏试次来“修绿”。它们没有产生 Scope 写入或交接回执，但仍然是 Gold 失败。
- ON/OFF 样本中 Memory 的效用未证明；token 使用量和 Provider 返回的 usage 可查，账单成本未返回且未估算。
- 浏览器 Trace 在无选中 Task 的过渡时刻记录到空 Task 路径的 handoff/outcome GET 404；随后绑定正确 Task 的请求均返回 200，演示链成功。保留原始记录供主 Agent检查。
- 本地 SQLite Demo、固定绑定订单服务、有限案例数和一名本地 APPROVER 不等同生产 IAM、企业记忆平台或通用案例库。
- 初次 RED、Web 尝试、评测运行器/恢复 smoke 和全量测试的所有失败均保留，索引见 `FAILURES.md`。这轮到此结束；等待主 Agent 独立验收，不进入 M3-02。
