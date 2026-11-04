# AR-03-MATERIAL-REMAINDER-LIVE-01 — 真实执行结果

**交付状态：`ACCEPTANCE_CANDIDATE`，等待主 Agent 独立验收。** 本报告不是最终 PASS。

## 基线与范围

- 仓库：`wgqa/OpsPilot`
- 实验分支：`codex/ar03-material-remainder-01-live`
- 授权 Base：`abd25e20b308df3c95f81c4039295908f399ef71`
- 真实执行源码 HEAD：`91cf810bb6106a1faad3c965ade121b363229ef9`
- 预检时 `main`：`ec8c3582f6d145eec9979c43607302731411ead8`，本轮未修改
- 冻结 MAT Cases Blob：`faf16fbb857278e98f8afbe179fe327855132967`
- 当前目标提交实际读取项目 Skill；North Star、AGENTS、Skill 与冻结 CASES 的 Blob 记录见该源码提交的预检材料，分别为 `1f737712c7a36ceb34433ac09c3fbba3c3305542`、`32c45506cceeaa8c76a5c56bf8360ff476b58856`、`d405c8d413d633824b279202cc1503dab4cf0b03`、`faf16fbb857278e98f8afbe179fe327855132967`。
- 本次仅运行 MAT-05、MAT-06 OFF、MAT-06 ON；不包含 MAT-01～04，不启动浏览器，不执行业务写入。

运行器通过全新隔离 Domain DB、三份独立 Checkpoint 和一个新 one-shot claim 执行。原 RESUME-01/02 的 claim、UNKNOWN dispatch、预留、数据库和 Trace 不作为本次运行目录，也未由本运行器打开写入。

## 用户实际得到的结果

### MAT-05：绑定订单的当前 Receiver=PROCESSED

正式 `/api/sessions/{session_id}/assistant/order` 请求以冻结 MAT-04 问题作为 `initial_message`，并由可信 API 绑定 `ar03-order`。最终 `ASSISTANT_V1` Run 为 `SUCCEEDED`，持久答复为模型生成、未提交的支持说明草稿。

模型自主选择并实际调用了 `get_callback_delivery`、`get_receiver_processing`、`get_order_status` 和 `list_scoped_protocol_documents`，随后读取 `receiver-ack-contract-v2` v2.1.0 与 `callback-retry-contract-v2` v2.0.0 的原文摘录并结束。当前 Delivery 是 `HTTP 202 / ACKNOWLEDGED`；同一 Event、同一 delivery version 的当前 Receiver 观察是 `PROCESSED`，`receiver_version=2`。Delivery 与 Receiver 的 Event 标识摘要一致。答复把完成结论建立在当前 Receiver 观察上，明确 202 单独只证明受理，也保留线上部署版本未知；草稿注明未提交、未创建工单或回执。

此处 `PROCESSED` 是在隔离数据库中、Run 启动前由受信测试夹具设置的事实；模型随后通过正式只读 MCP/Domain 路径取得它。夹具准备不是模型行动，也不是生产事实。

### MAT-06 OFF：Skill loader 不可用

OFF/ON 使用相同的冻结 84 字符用户输入，SHA-256 均为 `80e34814cfe65f9f361af4cdd0c4af06c36e15d987b8ebbddb7396e02b67ea98`，分别创建 Session 与 Checkpoint；OFF 的模型工具 Schema 不含 Skill loader。OFF 模型没有调用 Skill，而是发现协议、查询 Knowledge（实际为空）、调用版本比较并读取原文摘录。模型给出协议材料分析，同时说明没有 TaskBinding，不能判断具体订单的当前状态。

### MAT-06 ON：Skill loader 可用

ON 的工具 Schema 暴露了现有 Skill loader。模型自主调用 `load_protocol_upgrade_skill`，取得 `protocol-upgrade-impact-analysis` v1.0.0、Digest `aea84ee9efe7cea60fe0262681251bdbba51866de58dcd67c575a8c8b581fd40` 及正文；下一次真实 Provider 请求中确实包含该 Skill 内容。答复正确说明 Skill 只提供方法提示，不授予权限或当前事实；因未绑定订单，业务状态仍为未知。

ON 没有继续调用 `compare_scoped_protocols` 或原文摘录工具。它提供了机制层的 OFF/ON 说明，但没有在该次运行中重新验证协议差异。OFF 的比较比 ON 更深入；这是实际行动差异，不能据单次成对样本推断 Skill 导致了准确率提升。Skill 的来源有效性/篡改拒绝另由下述离线单测验证。

## 真实执行与费用

- 正式链路：FastAPI → Worker → `ASSISTANT_V1` → DeepSeek Chat Completions → MCP/Domain → 持久 Session 答复。
- Provider：8 个请求、8 个 HTTP 200、8 个唯一 Completion ID、8 份有效 Usage；无 UNKNOWN、无自动或人工重试。
- MCP：12 次 `tools/call`，全部为允许工具且结果为 `OK`；Campaign 的 MCP 计数没有硬上限。本次没有因 MCP 次数被截断。
- 请求实际参数：`deepseek-flash`、thinking disabled、`max_tokens=2048`、有 tools 时 `tool_choice=auto`、`parallel_tool_calls=false`、`stream=false`。均使用 `/v1/chat/completions`。估算上下文最大 6,090 tokens，Provider 报告的最大 prompt 为 6,940 tokens；最高单次 completion 为 1,445 tokens，均低于冻结的 12,000 / 2,048 限制。
- 合计 Usage：prompt 27,742、completion 4,421、total 32,163 tokens，其中缓存命中输入 13,184 tokens。
- 应用账本按冻结费率结算估算 USD 0.013631；最终预留 USD 0，预算余额 USD 10.486369。该数字是应用侧 Usage 估算，不是供应商账单。
- Campaign 账本状态仍为 `OPEN`，但本次 one-shot claim 已消费，重试数为 0；剩余额度不构成再次请求许可。

官方价格及接口依据在执行前复核：[DeepSeek pricing](https://api-docs.deepseek.com/quick_start/pricing/)、[Chat Completions API](https://api-docs.deepseek.com/api/create-chat-completion/)、[Thinking Mode](https://api-docs.deepseek.com/guides/thinking_mode/)。

## 安全与证据等级

- 绑定订单只用于 MAT-05；MAT-06 两个 Session 均无 TaskBinding。未绑定场景没有读取订单业务事实。
- MAT-05 所有助手来源复核为 current；Delivery 与 Receiver 属于相同 Event。模型未调用写工具。
- 隔离 Domain DB 的 14 个受保护业务写表经独立只读 SQLite 查询均为 0：Diagnosis、Plan、Approval、ActionPermission、ActionIntent、ActionLedger、VerificationReceipt、ReportArtifact、DeliveryRecord 及 S2/S3 Handoff Queue/Receipt。
- 没有 Provider UNKNOWN、费用异常或停止原因；运行器报告三项条件均执行结束。`COMPLETE_CASE_SET_RUN` 表示三次授权 Run 均完成并取得有效 Usage，不等同于所有实质 Gold 均获最终验收。
- 原始 Provider HTTP、完整模型答复、Domain DB、Checkpoints、claim 和私有日志保留在本地私有运行存储，没有提交。公开的 `PROVIDER_HTTP_SUMMARY.jsonl`、`TRACE.jsonl` 与 `PRIVATE_EVIDENCE_SHA256.json` 只含脱敏摘要及原始文件哈希。

## 验证记录

实际执行命令（来源 HEAD `91cf810...`）：

```powershell
python docs/evidence/ar-03/material-remainder-live-01/run_live.py --preflight-only
python docs/evidence/ar-03/material-remainder-live-01/run_live.py
```

第一次命令最终预检退出码 0，含显式 MockTransport 的正式 Worker 请求校验；第二次命令是本任务唯一一次收费 Campaign，退出码 0。正式 Campaign 结束后未再运行任何 Provider 请求。

付费前定向回归：44 passed；Campaign 后仅补跑来源完整性单测：

```powershell
python -m pytest -q tests/test_ar03_material_01.py::test_protocol_upgrade_skill_is_integrity_checked_and_only_loaded_on_demand --basetemp <private-unique-directory>
```

结果：1 passed。该测试验证已签名 Skill 可加载、当前 Digest 通过、篡改正文会被 `skill_asset_is_current` 拒绝；是本地单测，未触发 Provider。完整 pytest、真实浏览器和 Skill 效果因果实验均未运行。

## 当前候选评估与遗留限制

- MAT-05 的可观察目标得到真实模型与当前同 Event Observation 支持：`PROCESSED` 与 202 区分正确，且答复仅限该 Event。
- MAT-06 OFF/ON 均实际运行；OFF 不可用 Skill，ON 实际加载 Skill 正文。ON 没有完成协议版本比较，故该运行不能证明 Skill 提升了实质分析效果。
- Skill 效果只有一个固定顺序的 OFF→ON 样本对，模型随机性和执行顺序是混杂因素；因果结论为 `NOT_ESTABLISHED`。
- 来源篡改拒绝由独立离线单测覆盖，未在真实付费 Run 中人为篡改 Skill 文件。
- `RESULTS.json`、`TRACE.jsonl`、`PROVIDER_HTTP_SUMMARY.jsonl` 和预算 Ledger 为从私有原始记录导出的审阅摘要。原始 SHA-256 清单可供私有材料持有人逐项核对。

## 六问自检

1. **用户变化：** 用户现在能收到以当前同 Event PROCESSED Observation 支持的未提交说明草稿；无 TaskBinding 的 Skill 对照保持业务状态未知。
2. **Agent 决策：** 模型自主选择了订单读取、协议发现/摘录、版本比较与 Skill 加载；未被固定工具顺序驱动。
3. **观察驱动：** MAT-05 的当前 Receiver=PROCESSED 支持该 Event 完成；HTTP 202 只说明传输受理。与历史 QUEUED 是跨运行对照，不是同轮 A/B。
4. **新增约束：** 只有预先授权的三项条件可执行，预算、来源、TaskBinding 和零写入边界保持有效；12 次合法只读 MCP 均未被次数门限误拒。
5. **简化结果：** 复用了正式 Assistant、MCP/Domain、现有持久 Campaign Ledger 和 Skill loader；没有增加 Runtime、预算平台或业务写权限。
6. **证据与停止线：** 一次 Campaign 完成 3/3，8 Provider / 12 MCP，未重试；原始数据私有，公开摘要可由哈希核对。没有执行全量 pytest 或浏览器验收，且 Skill 效果尚未证明。

**实施状态：`ACCEPTANCE_CANDIDATE`。** 仅提交主 Agent 独立验收；不代表主 Agent PASS，也不允许再次调用 Provider。
