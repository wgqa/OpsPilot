# M3-HF-02 冻结范围与验收协议

基线 main@c2f71e9b4e3db9fdc3cd522115f304e6a53dfaae；开工时远端一致。仅按用户 M3-HF-02 任务卡 A→B→C 补证和学习交付。保留 M3-CLOSEOUT-01 PARTIAL、旧 Gold、旧失败和收益 NOT_PROVEN。完成后提交推送 main，停止等待独立验收；不做 M4/S3、新业务工具、Memory 类型或平台。

## 六段式最小卡

1. 用户旅程：新鲜隔离 Web 环境先完成无业务 Task 的观测标记 Chat；然后真实 S1 来源 Task A 获批修复、同身份200、冻结报告与交付，创建经独立 APPROVER 确认的 Episodic，供不同 Task B 的实际模型与 MCP 调查使用。撤销后 Chat、正式更正后的 Investigator 和同 Run 跨进程恢复均核对实际出站内容。随后用另一真实来源和目标完成独立的长对话摘要依赖实验。
2. 模型/工具：已有 ChatOpenAI、DeepSeek、MCP stdio。独立验收入口定位原 SDK 客户端，使用 httpx2 公共 request/response event_hooks 观测真实序列化请求体；不改变消息、工具、超时、重试、预算或传输内容。先校验观测器，再进行正式旅程。
3. 受信状态：所有业务动作仍由 Web/Domain、TaskControl、Approval、Intent/Ledger、Verification/Report/Delivery 决定；摘要/Memory 不提供事实权威或授权。观察与导出只读，业务库与 Checkpoint 为本轮新建副本，不改原用户库/服务。
4. 禁止：完整原始 Prompt、口令、Cookie、API Key、Authorization 入 Git；以模型文本或测试准备冒充业务成果；直接插入 Summary；放宽检索/审批/Gate；提高既有尝试数或恢复后重置预算；用新成功记录覆盖旧失败。生产代码原则上不改，明确直接阻塞 P0/P1 必须先独立冻结 RED 再最小修复。
5. Gold：A2 必须有真实 Provider 返回、实际请求体标记、Run/Attempt/Response 关联且内容未变；A3 核对实际 Memory 字段、版本、内容摘要、来源、非权威属性和当前 MCP；A4 用完整资产集合、结构化内容、历史消息/摘要 digest 与来源依赖核对撤销后的排除和 Manifest，一次真实 Checkpoint 同 Run 崩溃恢复预算不重置。B 单独判定是否形成 Memory→助手→真实 Summary→后续实际请求→撤销失效→重启不复活，未形成则如实报告，不修改旧 E2E Gold。C 无法证明旧 Worker 根因标 ROOT_CAUSE_NOT_PROVEN。
6. Trace：本轮独立目录、启动 SHA/源码 hash/PID、Task/Session/Run/Attempt/Memory/Message/Summary/Provider Response、Token、MCP/Evidence、HTTP/审批/账本、配置准备事件、完整失败及 UNKNOWN。仅脱敏必要片段与 digest，不保存全请求 Prompt。

## 固定环境与操作合同

- 所有临时文件位于本仓库 `.runtime/m3-hf-02/`；证据在本目录，学习资料在 `docs/learning/M3-REVIEW/`。
- 单一全新 S1_POS Domain 初始化一次；测试 API8003／前端5176。若端口被占用先记录并选未用端口，不停止用户服务。原8000／5173及已有5174页面不改。
- 使用合成 support-a / approver-a 正常登录。审批、Memory 确认/撤销走正常认证 Web API 与既有授权检查；真实浏览器完成用户 Chat 与检查器。每次记录实际渠道（Browser / authenticated Web HTTP API），不把 API 脚本称为人工点击。
- A：HYBRID 输入12000，输出预留512，window16384，安全余量1024；沿用 SDK max_retries=0、Investigator最多8 MODEL/6 MCP、Chat每Run最多3次（包括摘要）；既有 smoke helper deadline240000ms。不得因失败加次数。
- A2 标记固定 `M3HF02_PAYLOAD_PROBE_20261021_v1`。独立标记校验最多2个 Chat Run；第一次失败先定位观测器，不能先跑完整业务。真实响应与传输前 body 摘要必须关联。
- Task A 完成后仅可复用现有 `prepare_d5_auth_401_for_test` 显式准备下一合成事故 v8→v9；记录前后快照、版本单调及 Scope/回执/账本不变性。B当前401必须来自真实HTTP。准备动作不算Agent恢复。
- A4 在正式更正后同一目标Task的新Run已有MCP/Checkpoint时杀死本轮自有API树，重启同库；未知请求保留UNKNOWN。即使有界安全停止也不称业务恢复。若预算不足，不重置旧Task。
- A阶段技术门禁通过才进入B；若发现已撤销内容仍实际送到Provider，立刻判安全阻塞，先RED/修复，不进入B。

## B 实验固定协议（开始前补充准确 ID，不改变以下上限）

- 使用另一真实来源 Task C（同一 S1 v9→v10，经正常审批修复/验证/交付），创建新的 Episodic；旧已撤销版本不可复活。现有 fixture 显式准备 v10→v11，创建不同目标 Task D，真实 MCP 取当前证据。
- B 仅对独立验收进程将 Context 输入限额固定为 **3600 tokens**；HYBRID、输出预留512、window16384、安全余量1024不变。A→B环境切换记录；B开始前在 SUMMARY_PROTOCOL.md 冻结实际 Memory/Task/Session IDs、版本、digest及固定输入文件。
- ACTIVE期间最多8个连续只读Chat Run：第1轮生成真实依赖Memory的助手，第2–8轮是预先固定的有信息量的复盘、否定条件、当前任务约束和待办，要求简短回答。现有recent窗口12条消息，预计第7/8轮在超出3600时压缩早期目标助手。
- ACTIVE实验最多8轮、每Run沿用总3次Provider尝试；最多24次（包括摘要），没有应用层额外重试。若目标Summary未形成、预算安全停止或压缩失败，不增加轮数/限额，记录具体技术原因。
- Summary必须真实模型生成、持久化，并关联目标助手及其Episodic依赖，且至少一次被后续实际模型请求选用；压缩其他消息不算目标成功。
- 随后APPROVER Web撤销；第9轮新Chat核对传递失效和真实请求。再重启Worker同持久库，第10轮核对旧Summary不复活。第9/10轮同样每Run最多3次，没有额外重试。出现预算安全停止如实报告，不冒充回答成功。
- 不直接插入/修改消息、摘要、来源依赖、Memory状态或账本。所有实验输入是合成的非敏感测试说明，不伪造当前事实。

## C 有限审计与最终回归

只读旧日志/TaskRun/Lease/Outbox，最多两个明确的受控前置故障注入用于理解当前Worker分类。相似终态不能证明历史相同根因；不能复现则ROOT_CAUSE_NOT_PROVEN，不猜测修代码。源码审计按P0/P1/P2/P3列风险；仅本次明确直接阻塞P0/P1可先RED最小修复。

阅读材料必须区分参考Handbook思想、OpsPilot实现、自动化验证、真实E2E与未证明结论。至少15组面试追问。最终新鲜完整pytest（起点225）、Memory/Context定向、frontend typecheck/build/lint，保持既有S1/S2及M1-HF恢复边界。明确测试分子/分母、实际调用数、成本缺口与Git Diff。A充分时仅提交PASS_CANDIDATE，正式PASS由主Agent决定。

## 用户资产保护

AGENTS.md当前有用户未提交修改；PROJECT_NORTH_STAR.md、开发目录/、旧pytest临时目录及历史未跟踪资料均不覆盖、不暂存、不删除。只显式暂存本轮新建证据/学习目录和确有RED证明的必要修复文件。不开分支/PR。冻结提交早于新鲜模型执行和任何生产修改。
