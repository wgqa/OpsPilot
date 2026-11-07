# R1-JOURNEY-READINESS-01 报告

**状态：** `ACCEPTANCE_CANDIDATE`
**判断范围：** 本轮隔离离线旅程与真实运行准备；不代表全仓 PASS、真实模型 PASS、浏览器 PASS 或主线合并放行。

## 基线与本轮改动

- Base: `d324c8d6b64936ba84d1b50d18ce54356dec2c40`
- 分支：`codex/r1-journey-readiness-01`
- 开始时 `origin/main`: `60eee87bfe3cca522011316cb4cd2c0064ad291b`
- North Star Blob: `43dabda468506717c6956e676dfad4304c4f38e6`
- AGENTS Blob: `807b928686a4dd2cac7b15b3c354b9943c93c910`
- Review Skill Blob: `d405c8d413d633824b279202cc1503dab4cf0b03`
- TASKS Blob: `1f08ee3a8e538d7ece4d2b2841c7c53e25737b7c`

生产代码未修改。变更仅为新增正式 Runtime Grant J1/J2 离线测试和证据；另对既有 S2 测试补了 test-scoped Legacy Provider opt-in（仅 deterministic Fixture 生效）。原始 RED、历史 Claim、Gold、账本与 `main` 均未改。

## 四条用户旅程结果

| 旅程 | 离线正式路径 | 本轮总体 | 用户可见结果与限制 |
|---|---|---|---|
| J1 协议/用户材料 | PASS | PARTIAL | 同 Session 发现并比较授权的 `callback-retry-contract` v1.0.0 与 v2.0.0；其版本只证明文档差异，不证明线上部署。JSON 被按用户材料处理，没有假装读取服务端配置。真实模型自主性未运行。 |
| J2 当前/历史 Event 纠错 | PASS | PARTIAL | 可信绑定后读取 event-current 的 HTTP 202/ACKNOWLEDGED 与同 Event Receiver PROCESSED。纠错到 event-previous 后只找到历史 202，没有当前 Receiver 观察，模型替身说无法确认处理完成并生成未提交草稿。未将当前 Event 状态借给历史 Event。 |
| J3 S2 403 结果回读 | PASS | PARTIAL | 本地正式链路从建议、显式 Task 确认、同请求 HTTP 403/Authz DENY、Draft 到用户显式提交；同 Session 读回 SCOPE_ESCALATED/PENDING_REVIEW 和 HandoffReceipt。Scope 未授予、403 未恢复。 |
| J4 S1 401 结果回读 | PASS | PARTIAL | 隔离 Demo 有 WAITING_APPROVAL 与完整 D3 本地路径：独立审批、Revalidation、CAS、同身份 HTTP 200、冻结报告及 DELIVERED；普通 Assistant 回读持久结果并标为历史验证，不是当前 Probe。Demo 预置过程有 1 次本地 CAS 和 1 个本地 ticket entry；回读本身无新业务动作。 |

J1/J2 新测试是实际 FastAPI → Worker → Runtime Grant → `create_assistant_model`/LangChain → MockTransport → MCP → Domain 路径；MockTransport 捕获 9 个合成 Provider dispatch 和 5 次实际 MCP 调用。协议发现/比较取得版本和来源/Digest；当前 delivery、receiver 与历史 transport 查询有对应 Run/Evidence/Observation。测试累计合成 Usage：40,608 input、432 output、41,040 total tokens。它们是 Fixture Usage，不是 DeepSeek 使用量或账单。

J3/J4 使用既有确定性模型和真实本地 MCP/HTTP/SQLite Demo；J4 的隔离 Demo 写入不是外部企业写入。全部真实 Provider HTTP、浏览器自动化、外部业务写入均为 0。细节与 ID 见 [`TRACE.jsonl`](TRACE.jsonl)；J1/J2 的原始 JSON 见 [`TRACE.json`](TRACE.json)。

## 工程与回归结果

- 最终相关回归：10/10 PASS；运行 44.19s，exit 0。包括新 Runtime Grant 旅程、J1/J2 既有路径、J3/J4、Grant 缺失/禁用拒绝、Grant 正常发送/结算、发送前撤权和价格版本过期拒绝。
- 来源与授权版本再验证：3/3 PASS。包括 Knowledge grant 撤销/恢复/版本变化、协议比较来源重新验证、撤权后禁止普通聊天借用历史观察。
- 既有 R1 Journey 基线单测：1/1 PASS。
- 全量 pytest 当前 SHA 未运行。此前 757 收集 / 741 PASS / 16 FAIL 属于历史 SHA，不是本候选结果；16 项分类和适用范围见 [`R1_GAP_MATRIX.md`](R1_GAP_MATRIX.md)。
- 本机直接 `pytest` 导入失败和默认 C 盘 temp 权限问题通过 `python -m pytest`、显式 `PYTHONPATH`、D 盘隔离 `--basetemp` 处理。没有改全局依赖或权限。
- 一次 S2 回归因测试没有表达独立 Legacy Provider opt-in 而被生产代码正确阻断。补了 test-only opt-in，模型仍由 deterministic fixture 替换，复测通过；不是生产授权放宽。失败与测试夹具 RED/GREEN 均留档于本目录。

所有测试命令与分子/分母见 [`TEST_LOG.txt`](TEST_LOG.txt)、[`TEST_LOG_FINAL.txt`](TEST_LOG_FINAL.txt)、[`SOURCE_REVALIDATION_LOG.txt`](SOURCE_REVALIDATION_LOG.txt)。

## 正常产品能力边界

| 用户能力 | 当前路径/权限来源 | 本轮能确认什么 | 尚未授权/不应宣称 |
|---|---|---|---|
| 普通协议/材料对话 | ASSISTANT_V1 + Session + Runtime Grant；授权资料工具按当前 Session grant/digest 校验 | 可在正式 API/Worker 内连续回答，必要时比较协议并区分用户材料 | 不证明真实模型自主选择，不证明部署事实 |
| Callback 只读查询 | 先用可信 API 创建 TaskBinding，再暴露订单/Delivery/Receiver 工具 | 查询受 Task/事件范围约束；历史 HTTP 202 不等于当前 Receiver 完成 | 无 Task 不得读取受保护订单；不调用任何写工具 |
| 读取既有 S1/S2 专业结果 | `read_session_professional_outcomes` 按当前调用者、Session/Task 关系和来源有效性读取 | 普通 Assistant 可解释同 Session 中已授权结果，且收到历史/当前性语义 | 不等于实时 Probe；不能跨 Session 用用户给出的 ID 取得授权 |
| 发起 S1/S2 专业调查 | Assistant 只能提议；用户经正式 Task API 确认；旧 Investigator 有独立 Legacy Provider 授权 | 离线正式路径和授权边界存在；Legacy 未授权时 Worker 真实阻断 | 本轮不启动真实 Legacy Provider，不重跑专业调查 |
| 审批、Repair、Handoff | 独立 Approver / 用户提交接口、TaskControl、D3/S2 Domain | 既有确定性 Demo 可证明状态回读 | 聊天不创建 Approval/Intent、不改 Scope、不自动提交 |

## WP4 真实运行准备

当前实现为 `deepseek-flash` / DeepSeek OpenAI-compatible Chat Completions；官方资料、参数、计费和有界预算建议见 [`PROVIDER_PREFLIGHT.md`](PROVIDER_PREFLIGHT.md)。按模型公开总 context/output 可行上界、peak 且无 cache 假设，单请求保守预留 USD 0.6456；建议下一轮最多 16 次、总应用 Grant 上限 USD 10.50，16 次满额预留 USD 10.3296。该方案只是待审建议，不是本轮已创建的授权/Grant。

发送前仍需按执行当天重查模型、价格、Grant/账本和最终序列化报文。未知、超时、缺失 Usage、越权或费用不一致即停止且不重试。12K Context 是应用估算边界，不能宣称是供应商账单绝对保证。

## R1 差距与停止线

当前工程能证明离线产品路径可执行，但四条旅程总体都只能记 PARTIAL：真实模型只存在于早先不同切片的历史证据，浏览器仍为 `NOT_RUN / BROWSER_STOP_ACTIVE`。Slice 02 曾有 4 轮真实 DeepSeek（8 Provider / 9 MCP）但总体 PARTIAL；不能把它转写成本轮 J1–J4 成功。完整矩阵、历史 16 项失败和最短后续路径见 [`R1_GAP_MATRIX.md`](R1_GAP_MATRIX.md)。

**下一步最短执行路径：** 主 Agent 审核本候选 → 用户对新实验单独批准 → 使用新 Runtime Grant/数据库/Session 与一次性运行身份执行有界真实模型旅程 → 浏览器只能在正式解除 STOP 后独立验收。未授权前不发 Provider 请求、不启动浏览器、不改 `main`。

## 六维自检

1. **用户成果：** 同 Session 可由协议/材料进入可信 Callback 核查并纠错；S1/S2 已有结果可在原 Session 被解释。
2. **Agent 决策空间：** 当前测试由 Fixture 提供工具选择；实际产品保留直接回答、查资料、只读查询、澄清、停止的选择，本轮不将 Fixture 决策冒充真实自主性。
3. **观察驱动：** event-current 的当前 PROCESSED 与 event-previous 的历史 202/无 Receiver 形成不同回答；S1/S2 回读取决于真实 Domain Receipt/状态。
4. **安全/授权边界：** Grant 禁用/缺失、撤权、过期价格、知识授权撤销均有负例；没有新业务写入或外部 Provider 请求。
5. **职责简化：** 复用现有 Assistant、Runtime Grant、MCP、TaskControl、D3/S2 及结果读取工具；没有新 Runtime/账本/平台。
6. **证据和停止：** 13 项定向回归结果和 RED/GREEN 原始日志可查；全量 pytest、真实模型和浏览器未运行，状态按范围标明 PARTIAL。

### Astra/主 Agent 可重点独立复核

- 新的 Runtime Grant + MockTransport 测试是否沿正式 Worker 出站边界执行，并在发送前完成持久预留。
- S2 测试显式 Legacy opt-in 是否严格局限于 Fixture；生产默认拒绝语义未变化。
- Provider 预检的 peak/max-capacity 费用公式是否适合下一轮授权。
- J1–J4 的 PARTIAL 表述是否准确区分 Fixture、历史真实模型、外部业务事实和未运行的 Web。
