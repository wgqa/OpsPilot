# AR-03-REAL-LLM-01 — 真实双场景执行报告

**实施状态：** `ACCEPTANCE_CANDIDATE`
**执行结果：** `PARTIAL`；A、B 的冻结业务目标均未完成。
**执行分支：** `codex/ar03-real-llm-01-live`
**执行代码提交：** `9131a8c27b75c60eb3231e0a2c2ffe4485c5de3b`
**授权基线：** `e416bd1398b5a4bca6cdf3360f3ae78037a2740b`
**冻结标准提交：** `6f9074e84c185553cfeab0f225e81640b8b525f0`

## 实际用户结果

两组都通过正式 API/Worker 的可信绑定接口绑定了 `tenant-a / support-a / ar03-order`，之后在独立 Session 中各提交一次冻结原文。正式目标 Run 因每场景 MCP 额度耗尽而 FAILED，系统持久化了 `PROGRAM_LIMIT` 说明；**没有生成协议变化分析或处理说明草稿**，不能把本轮计为完成。

绑定接口本身还接受一条 admission `initial_message`，并先运行了一个 `CHAT_READONLY`。这不是冻结 Gold 的用户目标答复，但它真实消耗了 Provider/MCP 额度，并取得了下列用户可见结果：

- **A / QUEUED：** 模型读取订单、同一 Event 的 Delivery、Receiver 和传输历史；回答区分了 `202/ACKNOWLEDGED` 与接收方处理完成，指出 Receiver 仍 `QUEUED`，建议 SLA 后复查。它还说明空的已记录尝试不能证明从未发送。
- **B / PROCESSED：** 模型读取同一 Event；回答指出 Delivery 仍为 `202/ACKNOWLEDGED`、Receiver 已为 `PROCESSED`，并限制结论到该 Event。它明确没有检索协议文档，也未核对线上部署版本。

这两条是绑定 admission Run 的真实模型答复，不是冻结问题的最终结果。冻结问题在 A、B 的最终消息分别收到程序生成的“本次解释未完成”通知；程序没有冒充模型回答，也没有把 admission Run 的事实说成冻结目标 Run 的新取证。

## 真实调用与业务轨迹

冻结用户原文在两组中各出现一次，未改写。两组使用同一 Event `event-00000000-0000-4000-8000-000000000001`、同一订单和 `HTTP 202 / ACKNOWLEDGED`，仅 Receiver 状态不同；Domain 与 Checkpoint 文件分别位于 `runtime/scenario-A/`、`runtime/scenario-B/`。

| 场景 | Session / Task | Admission Run | 冻结目标 Run | 真实业务观察 | 冻结目标结果 |
|---|---|---|---|---|---|
| A / QUEUED | `session-8a9d143c-20c7-403b-9459-bcb699936bc0` / `task-3ddeab59-7659-4af5-85b6-572a13cdedae` | `run-0dd0ca3f-4626-4413-9366-b67200137a63` | `run-d8181dc7-24bd-4aed-a694-8aa9efbf3290` | 同 Event Receiver `QUEUED`；Order `COMPLETED`；Delivery `ACKNOWLEDGED`/202 | `FAILED`, `ASSISTANT_RUN_MCP_LIMIT`; 持久 `PROGRAM_LIMIT` |
| B / PROCESSED | `session-81f47d1a-5a7b-4ac7-9459-bcb699936bc0` / `task-ecc70a09-8f1b-4133-a6e5-f9eb4d2645f4` | `run-2f11e7b4-f954-4cba-8d03-1c46f3b4158a` | `run-7bb4a870-886a-4c3c-b59b-fcebcca00e7c` | 同 Event Receiver `PROCESSED`（version 2）；Delivery `ACKNOWLEDGED`/202 | `FAILED`, `ASSISTANT_RUN_MCP_LIMIT`; 持久 `PROGRAM_LIMIT` |

真实模型行动（依据 Provider 响应和实际 MCP 记录，不推测模型内部思维）：

- 两组 admission Run 都选择 `get_order_status`、`get_callback_delivery`、`get_receiver_processing`、`get_callback_transport_history`，四项均实际经 MCP/Domain 执行并关联各自 Observation/Evidence。两组答复随 Receiver 的真实状态产生了不同且范围正确的结论。
- A 的冻结目标 Run 先调用范围内协议目录查询（0 条），再实际检索到 `callback-retry-contract-v2` v2.0.0；之后模型重复尝试查找 v1，并提出 Delivery/Receiver 查询。由于六次 MCP 额度已由 admission 的四次和目标 Run 的两次使用完，后续没有实际派发或新 Observation，也没有完成版本比较。
- B 的冻结目标 Run 的带主题目录查询返回 0 条，随后无主题目录查询返回 6 条。模型随后提出 Knowledge 和协议比较调用；额度已用完，未产生比较结果。两组没有实际执行 `compare_scoped_protocols`，也没有形成冻结任务要求的升级影响分析或草稿。

A、B 的目标 Run 没有把旧 Run 的观察冒充为本次目标 Run 的新 Observation。实际 MCP 以受信 TaskBinding 限定在订单/Event 范围内；没有跨租户或跨订单读取证据。

## Provider、MCP 与预算核对

- DeepSeek `deepseek-flash`：13 次真实 HTTP 请求，A 7 次、B 6 次；13 个响应均为 HTTP 200，均有 Completion ID 与完整 Usage；无超时、无未知结果、无重试、无在途请求。模型指纹均为 `bc19ba97cbe016479903222bb1578db6`。
- 13 个实际出站报文均核对为冻结的 URL、`max_tokens=2048`、`thinking.type=disabled`、`stream=false`、`parallel_tool_calls=false`；带工具请求使用 `tool_choice=auto`。原始请求/响应及 Completion ID 保存在 `PROVIDER_HTTP.jsonl`。
- Provider Usage：prompt 57,864 tokens，completion 2,406，total 60,270；其中 prompt cache-hit 39,808、cache-miss 18,056。最大单次 `prompt_tokens` 为 7,169，低于 12,000 上限。
- 应用账本：预留尝试 13 × USD 0.645600 = USD 8.392800；有效 Usage 后结算 USD 0.020252；未决预留 USD 0；应用预算 USD 10.50 未超限。USD 0.020252 是按峰值输入/输出单价、不使用缓存优惠并逐请求舍入的应用侧估算，不是供应商发票金额。价格和协议依据见 [DeepSeek 官方价格页](https://api-docs.deepseek.com/quick_start/pricing/) 与 [Chat Completions API](https://api-docs.deepseek.com/api/create-chat-completion/)；无缓存优惠假设。
- MCP 实际账本派发 12 次，A 6 次、B 6 次，均在各自隔离预算内。每场景达到上限后的模型工具提议没有形成 MCP 派发或 Observation；Trace 中的预算错误文本保留历史模块前缀 `AR02_LIVE_MCP_LIMIT`，而持久账本中的 `experiment_id` 是 `AR-03-REAL-LLM-01`。这是错误标识命名不一致，不应据此推断旧 AR-02 数据库被使用。
- 每场景受保护写表计数均为 0：Approval、Plan、ActionIntent、ActionLedger、Diagnosis、Handoff Queue/Receipt、Verification、Report、Delivery 等均未写入。`RESULTS.json` 记录 `business_action_writes=0`、`historical_experiments_modified=false`、`provider_inflight_at_stop=0`。

## 失败归因与限制

这是**产品/策略能力未达成**，不是 Provider 协议失败或安全失败。单场景 6 次 MCP 上限同时覆盖了绑定 admission Run 和冻结目标 Run；admission Run 自主查询四类订单事实后，只为正式目标留下两次 MCP 派发额度。随后 A、B 的模型均消耗剩余额度进行协议发现/检索，无法完成所需的版本比较、当前事实补查及最终说明。

限额按冻结合同执行，未提高预算、改题或重跑。此次实验说明模型能依据同 Event 的 QUEUED/PROCESSED 观察给出不同初步解释，也显示当前正式入口的 admission 取证开销会挤压主目标预算。未来如何重新分配合法预算或减少重复入口工作，需要主 Agent 另行裁决；本轮不修改实现、不补发请求。

## 证据与验证等级

- **真实 Provider：** 13/13 HTTP 200、Usage 已结算；见 `PROVIDER_HTTP.jsonl`、`BUDGET_LEDGER.json`。
- **真实 MCP/Domain：** 12 次实际受信只读派发；见 `TRACE.jsonl`、`runtime/scenario-*/result.json` 及本地隔离 SQLite/Checkpoint。
- **业务 Gold：** A、B 均未完成协议差异分析和处理说明草稿；目标 Run 状态 FAILED，最终等级 PARTIAL。
- **安全：** 本地执行证据显示 0 业务写入、无跨范围访问；未执行正式浏览器旅程。浏览器验收、全量 pytest、供应商最终发票金额均未在本次执行中验证。
- 本次关闭后未运行任何第二个 Runner、重试或额外模型请求。旧实验数据库、Gold、历史 Trace 未改；本次原始结果保持 Runner 输出，评分补充单独见 `ASSESSMENT.json`。

## 项目 Skill 收尾六问

1. **用户变化：** 用户通过正式接口获得了订单与同 Event 回调的可信初步状态；冻结的完整协议升级分析和草稿未完成。
2. **Agent 决策：** 模型实际选择并执行了只读状态工具、协议目录与 Knowledge 查询，并提出受预算拒绝的后续查询；未完成协议比较。
3. **观察驱动：** 同为 202/ACKNOWLEDGED，A 的 QUEUED 与 B 的 PROCESSED 导致 admission 回答不同；两组冻结目标都没有最终回答。
4. **新增约束：** 8 Provider/6 MCP 每场景分配保护总费用和请求上限；它没有误放越权调用，但本次合法旅程无法在该分配下完成。
5. **简化结果：** 复用了正式 Assistant、Worker、MCP 与 SQLite 账本；未增加新 Runtime 或业务状态机。仅实施前已提交的实验级预算分配与一次性 Runner。
6. **证据与停止线：** 真实运行原始证据齐全，13/16 Provider、12/12 MCP、USD 0.020252 估算、0 写入；两场景完成后立即停止。后续真实实验需新授权。

**实施方状态：** `ACCEPTANCE_CANDIDATE / PARTIAL`，交主 Agent 独立评审；不签署 PASS，不合并 `main`，不启动后续实验。
## Runtime database retention

Fresh Domain and Checkpoint databases are retained locally under `runtime/scenario-A/` and `runtime/scenario-B/`; their sizes and SHA-256 values are in `RUNTIME_ARTIFACTS.json`. The repository's existing `*.sqlite3` ignore rule is unchanged, so the databases were not force-added to Git. The sanitized `runtime/*/result.json`, Provider HTTP log, Domain Trace, budget ledger and assessment are included in the candidate evidence.
## Commands and pre-live verification

- Real run: the one-shot entrypoint `docs/evidence/ar-03/real-llm-01/run_live.py --execute-once` was invoked once in the authorized network-capable environment. The execution log and the captured HTTP/Domain traces are retained; no second invocation was made.
- Offline post-run audit: `python docs/evidence/ar-03/real-llm-01/verify_evidence.py`; result `PASS` is in `runs/postrun-evidence-check-green.log`.
- Before live execution, the retained targeted logs record 27 budget tests, 28 preflight tests, 4 transport-recorder tests, 76 safety-regression tests and 30 final free tests passed. The full pytest suite was not run for this live slice. Initial setup/command errors and the post-run audit script errors remain separately retained in `FAILURES.md` and `runs/`.