# R1 主线集成门禁报告

**交付状态：** `ACCEPTANCE_CANDIDATE`
**主线建议：** `HOLD`（不合并、不推送 main）
**范围：** 离线集成审查；未运行浏览器、未调用真实 Provider、未执行业务写入。

## 基线与实际读取

| 项目 | 实际值 |
|---|---|
| 仓库 | `wgqa/OpsPilot` |
| main | `ec8c3582f6d145eec9979c43607302731411ead8` |
| 原 R1 候选 | `codex/r1-integration-web-journey-01@91a067aa083c2d4446d88a09d84164ea4c3bb956` |
| 本次评审分支 | `codex/r1-main-integration-gate-01`，基于原候选 |
| North Star Blob | `1f737712c7a36ceb34433ac09c3fbba3c3305542` |
| AGENTS Blob | `32c45506cceeaa8c76a5c56bf8360ff476b58856` |
| Skill Blob | `d405c8d413d633824b279202cc1503dab4cf0b03` |
| TASKS Blob（开工） | `7b17c634692f7ca3ee4d70649674b53ff8cb772c` |

以上规则和 Skill 均从候选 SHA 实际读取；North Star 第 8 节是正式评审准则。读取了 R1 `ACCEPTANCE_PLAN.md`、`REPORT.md`、`RESULTS.json`、`FAILURES.md`、`TRACE.jsonl`、M2-02 Deferred Gates，以及 AR-02/AR-03 适用冻结材料。原 R1 证据将 Engine 标为 PARTIAL，Interactive 标为 `HOLD / NOT_RUN / BLOCKED_BY_TOOL_ENVIRONMENT`；本轮没有提升这些历史证据等级。

## Git 与集成差异

- 开工远端核验：候选分支 HEAD 与冻结 `91a067aa...` 相同；远端 main 与冻结 `ec8c3582...` 相同。两者无分叉，候选领先 121 个提交，提交区间无 merge commit。
- `main..候选` 累计差异为 1,048 个文件：974 个 `docs/evidence` 文件、42 个测试文件、18 个 `opspilot` 模块、6 个前端文件、2 个项目 Skill 文件，以及 6 个实验/Knowledge/配置等文件。候选包含既有 AR-02/AR-03/R1 能力，不需要从 Antigravity 分支重复 cherry-pick。
- 核查了 Assistant/Worker、MCP/Knowledge/Skill、TaskBinding/TaskControl、来源当前性、前端 API/对话投影、迁移测试和实验预算隔离。全量测试中已执行的授权、恢复、幂等、撤权、MCP、数据库迁移与业务写边界用例均见测试日志；本轮没有生产业务源码修改。
- 首轮全量 `git diff --check` 有 476 条既有证据文本空白告警（主要是历史 `.log`）；对 Python/JS/TS/Vue 源码、测试及本次 `TASKS.md` 路径的检查无输出。没有改写历史日志来消除告警。

## 回归结果

第一次完整 pytest 收集 675 项，`670 passed, 5 failed`，退出码 1。四项不是业务运行错误：两个付费 one-shot 测试直接读取评审 checkout 分支名，与授权固定的实验分支不一致；两个 Web Server 测试没有断言 R1 候选新增的 `assistant_model_factory` 注入。只修改了这两处测试夹具/期望，没有放宽生产 one-shot 分支校验或改动 Server 运行逻辑；修复后的 7 项定向测试 `7 passed`。重复同一 MCP 只读工具超过旧 10 次限额的独立 Worker 测试 `1 passed`。

唯一完整 pytest 失败是历史 `test_explicit_protocol_followup_is_accepted_as_same_task_readonly_run_before_ttl_fix`：它仍发送已废弃的 `READONLY_FOLLOWUP` 分类意图，当前合法合同是 `FOLLOW_UP + readonly_action=INVESTIGATE`。项目既有 C1 失败材料记录了旧意图/旧分类的历史 RED；本轮保留该用例，不添加生产兼容分支。

在上述测试夹具修正后再次启动了全量 pytest。它在 31% 处长时间停留于 11 次重复 MCP 读取的 Worker 用例；只读检查临时 DB 显示 Run 已 `SUCCEEDED`、11 个 MCP Attempt 为 `OK`，但 pytest/Worker 进程未退出。为避免无限等待，保存日志后中断该次运行，未得到全量摘要，不能计为通过。相同测试单独新鲜运行通过 1/1（4.89 秒）。

前端实际检查：`npm ci`、`npm run typecheck`、`npm run build` 均退出 0；三组前端对话投影测试 17/17 通过；变更前端文件 ESLint 通过。全量 `npm run lint` 退出 1，仅报告未改动且与 main Blob 相同的 `frontend/e2e/m4-03-s3-journey.mjs`：第 1 行 `access` 未使用、第 56 行 `setTimeout` 未定义。该历史 lint 问题不涉及本候选新增文件。

日志及退出码见本目录 `runs/`。前端依赖安装使用 D 盘本地 npm cache。全量后端的首轮失败、复跑中断和定向 GREEN 均分别保存，不互相覆盖。

## 公开材料与安全审查

对候选 1,027 个 Git blob 做了凭据模式扫描（常见 Provider/GitHub/AWS 密钥、私钥、Bearer/凭据赋值及邮箱模式），没有发现可确认的真实 API Key、Token 或私钥；合成测试值与代码变量名不作为泄露结论。Web 截图有遮盖带，目视没有可见凭据或业务标识。

**发现公开发布阻断：候选提交历史包含 3 个私有授权 SQLite 数据库，不能纳入公开发布或主线合并：**

| 路径 | Blob 大小 | 只读检查 |
|---|---:|---|
| `docs/evidence/ar-02/conn-02/runs/authorization.sqlite3` | 28,672 bytes | `quick_check=ok`；保存一次性授权/attempt 与成功连通性记录 |
| `docs/evidence/ar-02/live-connection-diag-02/runs/authorization.sqlite3` | 28,672 bytes | `quick_check=ok`；保存 UNKNOWN attempt/预留 |
| `docs/evidence/ar-02/live-connection-diag-03/runs/authorization.sqlite3` | 28,672 bytes | `quick_check=ok`；保存 UNKNOWN attempt/预留 |

数据库中未发现 Provider API Key，但内容属于私有执行授权和账本状态，任务卡明确禁止公开 SQLite。它们不仅存在于候选当前树，也存在于已提交历史；仅新提交删除文件并不能去除历史 blob。本轮没有擅自重写历史、清理或覆盖原证据。需要主 Agent 决定采用受控私有归档/公开安全快照还是经授权的历史处理方案。

因此本分支不推送：新的公开评审分支仍会继承这些私有 blob。该项单独足以阻止 `MERGE_READY`。

## 状态与范围

- **R1-ENGINE：** 有可复核的离线代码候选；本轮结果为 `ACCEPTANCE_CANDIDATE / HOLD`，尚未达到发布放行。完整 pytest 复跑未结束，且公开候选历史含私有数据库。
- **R1-INTERACTIVE：** `HOLD / NOT_RUN / BROWSER_STOP_ACTIVE`。未使用 Computer Use、Playwright 或其他浏览器自动化替代。
- **AR-02/AR-03：** 只核验已集成范围与历史证据；没有真实 Provider 请求、浏览器操作、业务写入或旧账本变更。既有 PARTIAL、UNKNOWN 与 HOLD 结论保留。
- `main` 保持原 SHA；没有合并、推送 main、启动付费实验或 AR-04。

## 六问与六维交付

1. **用户变化：** 尚无新增用户能力；本轮把既有 R1/AR-02/AR-03 组合候选整理成可审查的发布决策材料。
2. **Agent 决策：** 原有 Assistant 的合法工具选择和补查空间未改；本轮离线检查不能证明真实模型自主性增益。
3. **观察驱动：** QUEUED/PROCESSED、同 Event、授权撤销和预算相关确定性测试继续作为差异证据；不把历史真实 Trace 冒充本轮新运行。
4. **新增约束与合法任务影响：** 没有新增产品硬限制；one-shot 授权仍要求固定分支/授权身份，测试通过模拟被授权 checkout 保留负例。正常多次 MCP Worker 用例单独通过；真实浏览器合法路径未测。
5. **简化结果：** 未建新平台、未 cherry-pick 重复 AR-03 能力；只改两处测试夹具，生产代码不变。
6. **证据与停止线：** 测试与 lint 的失败/中断均保留；公开 SQLite 历史与未完成全量复跑未关闭前停止，不合并、不推送、不进入 AR-04。

**裁决建议：`HOLD`。** 范围是代码发布与主线合并门禁；尚未验证：浏览器交互、真实 Provider、全量 pytest 在夹具修正后的完整退出结果。由于历史私有 SQLite 暴露和复跑不完整，不建议当前候选进入 main。由主 Agent 决定后续安全发布/历史治理，不由实施方自签 PASS。
