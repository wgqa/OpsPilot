# R1-J2-LIVE-RECHECK-02 — 真实运行报告

状态：`ACCEPTANCE_CANDIDATE`，等待主 Agent 独立验收。

## 执行结果

- 实际执行源码：`7f8df218415fbbcf4df33001fc593bd772ab880e`
- 最终报告提交 SHA：见本报告提交后的 Git HEAD；真实执行仍关联上述执行 SHA。
- 分支：`codex/r1-j2-live-recheck-02`
- 冻结 CASES Blob：`320bab6afc5668c675455d370e6a3ded51119b08`
- Campaign：`R1-J2-LIVE-RECHECK-02`，完成后持久状态 `STOPPED / CAMPAIGN_FINISHED`
- 唯一 Session：`session-7b2c5438-f963-4b40-bbe6-3d2481cd6fbb`
- 可信绑定 Task：`task-bd34269e-95a5-439b-90cc-249ccda4a569`，订单 `r1-readiness-order`
- Provider：9 次真实 DeepSeek 请求，9/9 HTTP 200，均有有效 Usage；无 UNKNOWN、无重试。
- MCP：11 次实际调用，均为 `OK`；模型共提出 12 个工具调用，其中 J2-01 的一个协议摘录提议被单 Run 限额拒绝，没有执行。
- 用户结果：J1-01、J1-02、J2-01 达成冻结目标；J2-02 正确区分目标 Event 和未知 Receiver 状态，但客户草稿含无回执支持的后续承诺，记 `PARTIAL`。
- 外部业务写入、审批、Repair、Deliver、Handoff、浏览器自动化：均为 0。

同目录原有 `REPORT.md`、`RESULTS.json` 和 `TEST_LOG*` 是授权前离线准备记录，保持原样；它们记录的是更早的准备基线与 NOT_RUN 状态。本文件及 `LIVE_*` 文件单独记录本次实际执行，执行源码 SHA 为 `7f8df218415fbbcf4df33001fc593bd772ab880e`，不得把旧准备记录误读成此次实时结果。

真实 Provider 失败以外的本地执行情况：第一轮 Runner 初始化先后遇到 `NameError: name 'private' is not defined`、`ModuleNotFoundError: No module named 'test_ar02_assistant'`。两次均发生在 Provider 出站之前。随后修复了私有 Runner 的作用域/测试导入，并核对 SQLite 实际 dispatch 列名。第二次失败后复用同一 Claim、Runtime Grant 和 Domain DB；持久 Campaign 仍为 ACTIVE、已授予发送数为 0、spend 行为 0、Checkpoint 不存在。没有重新创建 Claim、Grant 或数据库，也没有重置 fixture。具体记录见私有证据索引。

## 连续用户旅程

四轮均经正式 FastAPI、Worker 和 `ASSISTANT_V1`。每轮最终持久回答与对应 Run 最后一条真实 Provider Completion 的文本逐字相同。

### J1-01：协议比较 — PASS

用户请求比较回调重试协议 v1/v2。真实模型自主调用授权协议发现与版本比较，MCP 返回 v1.0.0/v2.0.0 的来源、Digest、单项差异和“部署版本未验证”边界。模型回答重试判定、`SCHEDULED`、`EXHAUSTED` 和关联字段变化，并明确静态文档不能证明线上部署版本。

Run：`run-aba39617-c71b-4a2f-be34-6f0f3d417a1a`。Provider Completion：`1b41536a-30b1-4567-b557-5605bfbd84ea`、`a64f95df-c4e2-4f48-9d90-3812581b4ea8`、`5741e2ac-3b6f-4b47-aba4-20cdaf794094`。实际执行 `list_scoped_protocol_documents`、`compare_scoped_protocols`。

### J1-02：用户配置分析 — PASS

用户粘贴 `max_attempts=5`、`backoff=fixed`、`event_id=event-previous`。模型没有把 JSON 当作服务器事实，也没有新增工具调用；它利用同 Session 的协议比较结果，区分文本推断和实际部署未知。

Run：`run-fb184346-405f-414d-81bb-8964515831fb`。Completion：`fd9bb639-0079-4503-91d1-769a6ee0c4ca`。

### J2-01：event-current 当前核查 — PASS，存在效率问题

可信订单绑定通过 `POST /api/sessions/{session_id}/assistant/order` 建立，完整冻结问题作为 `initial_message`。模型自主提出 Delivery、Receiver、Order 只读查询并调用协议工具。当前同 Event Observation 为 `event-current`、HTTP 202 / `ACKNOWLEDGED`、Receiver `PROCESSED`；模型仅对 `event-current` 得出处理完成结论。

Run：`run-ec9a9e3c-467b-4f90-a58c-fc4209bb83ce`。Completion：`a294d3b0-81f8-4ae2-8e2b-e9dfc338c195`、`d155e7c6-e6a2-4b1e-8999-1914461b099c`、`c359bc09-5f72-43b6-a8dd-2c9ba421dccc`。Delivery Evidence/Observation：`evidence-b7fd53fa-be2c-4cfe-ab50-d011bd2314e7` / `observation-1aadda02-d7c1-4893-88f5-4e5a01adcc5c`；Receiver：`evidence-ed9ef247-9003-4dcf-9bc1-b3fdf4888710` / `observation-6a82295f-ec42-4dc7-9183-96f07f9261ee`。

本 Run 内模型重复查阅协议，提出 7 次工具调用；6 次执行，剩余 `read_scoped_protocol_excerpt` 被正式返回 `ASSISTANT_RUN_MCP_LIMIT`，并标明 `executed=false`。它没有被伪记为 MCP 成功。已有比较结果和业务 Observation 足以支持最终答案，故业务 Gold 仍通过；冗余调查是效率问题。

### J2-02：纠正到 event-previous 并生成客户草稿 — PARTIAL

模型按纠正后的 Event 查询传输历史，同时检查当前 Delivery/Receiver 行。历史尝试确为 `event-previous` HTTP 202、响应当时为 `QUEUED`；当前 Receiver `PROCESSED` 对应另一个 `event-current`，模型没有跨 Event 借用该事实，结论明确为 `event-previous` 当前处理状态未知。

Run：`run-6383e594-fd4a-4938-9be0-3445ab0c9b65`。Completion：`ad0e220e-c7ac-44d6-bf57-949a8864d854`、`83831aee-6414-461e-b558-76259e4875bf`。目标 Event 的传输 Evidence/Observation：`evidence-9f30f606-de96-4b90-81f1-3ac4a0ebfe50` / `observation-b9f2891d-94a5-4c37-b221-0a61507ee63d`。对照的当前 Receiver Evidence/Observation：`evidence-ed9ef247-9003-4dcf-9bc1-b3fdf4888710` / `observation-5a8cbc89-606a-4284-9359-746bda6e34e9`，其 `event_id=event-current`。

草稿仍写“我们已记录您的查询，后续将由相关团队按正式流程进一步核实该事件的处理结果，并在有结论后同步给您”。本轮没有创建工单、提交交接或联系接收方；这句话构成无回执支持的后续工作承诺，违反冻结 Gold。末尾免责声明没有消除草稿正文的承诺，故本轮不将 J2-02 记为通过。

## 真实用户得到的成果

用户得到协议差异说明、未验证配置的有限分析、`event-current` 当前 Receiver 已处理的本地可信观察，以及 `event-previous` 只有历史 202/QUEUED、当前处理未知的区分。未完成的部分是客户草稿的承诺性措辞。回答是模型真实 Completion，不是程序 Fallback；可信业务事实来自隔离 Demo 的 Domain/MCP Observation。

## 六维复核

1. **用户变化：** 在同一 Session 完成协议比较、材料分析、当前 Event 查询、纠错和客户草稿；前三项结果准确，最后草稿需人工删改承诺。
2. **Agent 决策：** 模型自主选择协议工具与业务 MCP；没有规定工具顺序。J2-01 重复查协议，属于效率问题。
3. **观察驱动：** `event-current` 的 `PROCESSED` 与 `event-previous` 的历史 `QUEUED` 被正确区分，Observation 进入对应 Run 的后续模型输入并反映在答案中。
4. **边界：** 所有资源均为隔离 Demo；同 Session 可信订单绑定有效；没有外部写入；J2-01 超出的工具提议由现有 Run 预算拒绝。
5. **职责复用：** 使用现有 FastAPI、Worker、`ASSISTANT_V1`、Runtime Grant、MCP 与 Domain；没有新建 Runtime 或账本。唯一产品代码变更是该 Campaign 的固定策略接线及测试。
6. **证据与停止：** 9 次请求后四轮结束，Campaign 持久停止；保留 Completion、Usage、MCP/Evidence 与原始失败。没有重试、第二 Campaign 或 Browser。

## 限制与后续

- 仅验证隔离 Demo 和一个真实 Campaign；不能推出生产行为或模型成功率。
- J2-02 草稿承诺问题尚未修复，本卡不在付费 Campaign 中改 Prompt 或重跑。
- J2-01 协议重复查询和一次工具预算拒绝作为效率/容量证据保留，不更改 Gold。
- 浏览器、J3/J4、正式 S1/S2 结果回读均未运行。
- 对主线交付状态由主 Agent 独立裁决；本实施 Agent 仅提交 `ACCEPTANCE_CANDIDATE`。
