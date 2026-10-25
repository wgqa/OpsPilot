# CONT-UX 阶段 A · 实施前冻结

状态：`FROZEN_BEFORE_RED`；仅预算、恢复和确定性接口旅程获授权，阶段 B / 付费 Provider `NOT_AUTHORIZED`。

Base：`37df7236ae3ce6fe7125cda671d1a28a3409f830`，fetch 后 HEAD 与 origin/main 相同。复用既有 detached 集成工作树，最终正常推送 `HEAD:main`，不切换或清理用户主目录。tracked/index 起始干净，7 类旧 basetemp/cache 保留。

已实际读取原压缩包 `opspilot-slice-review/SKILL.md`，执行 A 节开工核验；目标提交没有该项目入口，不声称自动发现已安装。总纲与 AGENTS 实际重读，Blob 分别 `1f737712c7a36ceb34433ac09c3fbba3c3305542`、`30319000ed0054007e9b7b6b46bf98b1493c8179`。阶段 0 Gold Blob `1290ef276690f00b6e9683f0251302f376a70098`；逐文件实测见 `READ_RECORD.json`。

唯一新授权是用户本轮阶段 A 任务卡及补充：新 S3 `CONTUX_S3_V1`，Task 24 MODEL / 18 MCP；初始或正式纠错 Run 8/6；只读 Follow-up 4/3；分类、Chat、Compression Task 合计 8。所有 RESERVED/失败/未知尝试占额度；时间仍 300,000ms。新请求是新 source Message/Operation/Run；恢复仍是原 Run，不重置计数。旧 Task 迁移保留 legacy policy，S1/S2 不改变。旧受信隔离实验配置入口的兼容性须单列，不把它暴露成 Web/MCP 能力。

## 新测试与原 Gold 对照

| 用例 | Gold | 冻结判据 |
|---|---|---|
| A01 新请求及 Run 分配 | 01/03/16 | 初始用满 8 后，可信新 Follow-up 可预留；同 Operation/重复 Assessment 返回原 Run；同文不同 Operation 不合并。 |
| A02 Run/Task 硬上限 | 01/04 | 每轮及总额在同一 SQLite 写事务裁决，传任意较大 limit 不扩权；两个独立连接接近边界时只能一个成功。 |
| A03 旧任务/迁移 | 02/14/15 | v16 历史行迁移不升级额度；新 S3 默认新策略，S1/S2 仍旧策略；跨 Task/Run、畸形策略拒绝。 |
| A04 辅助计数 | 04/18 | 分类、Chat、Compression 三表全部计数，包含失败与 RESERVED；第 9 次无外发。两连接跨类别竞争仍不能超额。 |
| A05 可读耗尽结果 | 04/18/20 | Run/Task/辅助耗尽给出准确层级、具体非空正文/原因；无新观察不声称新事实，不能留下永久 Pending 或空成功。 |
| A06 OS 恢复 | 02/03/07 | 首 checkpoint 前及成功真实 MCP Observation 后 checkpoint 前，真实子进程终止、另一 PID 恢复同 Run；原 Attempt、控制高水位、Task 累计时间与剩余额度不重置。 |
| A07 组合补查/复用 | 05/19 | 选择合法 Knowledge/业务事实，逐观察继续，允许直接解释或提前结束；不冻结工具顺序；有效终答复不用额外 report 调用。 |
| A08 四次接口请求旅程 | 01/05/14/15/20 | 原 API 受理初次调查→协议补查→代词解释→当前状态核实；确定性模型替身、真实本地 HTTP/MCP、可信 Task/Run；逐轮有实际答复、来源与累计活跃时间。 |

新增测试先在 Base 运行并保留完整 stdout/stderr/exit code，然后提交 RED，再改实现。原 C1 obsolete `READONLY_FOLLOWUP` Intent RED 不改、不兼容、不重定级为现行产品缺陷。不会改阶段 0 Gold、原始 Trace/日志、历史 Receipt。

## 最小职责与回归

复用 `task_execution_budgets` 做兼容列迁移、原 Attempt 表计数和 `BEGIN IMMEDIATE`；Run 类型来自可信持久记录，非模型/调用方 cap。`execution_budget.py` 负责共同计数，D2/辅助 reservation 负责各自写入，S3 使用两级剩余及已有事实降级。若需要触及审批/写事务语义，停下请求裁决。迁移版本断言仅随真实 Schema 升级更新，不修改业务 Gold 或旧 RED。

执行顺序：冻结提交 → 新测试 RED → 最小修复 → 新定向 GREEN → HTTP/MCP/SQLite/OS 集成 → C1/VS01/S3/M1-HF/S1/S2 安全回归 → 未筛选完整 pytest及单列 obsolete RED 的活动回归。使用本切片独立 basetemp；每次失败原样保存。测试若写旧证据文件，将本次追加行保存本目录后还原历史 Blob，不丢弃本次失败。

## 六问与双向限制

1. 用户变化：同一 Task 新追问不再因为初始轮花完 8 次而失去所有调查机会；本轮以四次真实接口请求的确定性替身旅程验证，不冒充真实模型体验。
2. Agent 决策：保留解释、调查、澄清、合法工具与结束选择；本轮不宣称模型质量提高，程序只守住额度和恢复权威。
3. 观察驱动：协议依据充分时直接解释；问当前状态时新 Run 取证；同 Event QUEUED 与 PROCESSED 支持不同结论，不依靠旧 Run 或 202 猜当前状态。
4. 新限制：Run 小窗口保护后续请求，Task/辅助总额防无限消息消耗。必须同时证明新请求可继续、原 Run 不刷新、正常同 Task 可读与撤权 fail-closed。
5. 简化：统一在既有预算职责读取策略/计数，替换 S3 只看 Task 的分散判断；不增预算平台、Planner、Guard、Runtime 或前端业务状态。
6. 证据与停止：RED/GREEN、Attempt/Run/观察链、双连接及 OS 恢复、完整回归、源码学习和失败均交候选；所有付费 Provider/J1–J4正式旅程与阶段 B 未运行。推送 `ACCEPTANCE_CANDIDATE` 后停止，主 Agent 独立裁决。
