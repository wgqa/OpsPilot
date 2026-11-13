# R2-AR06-EVAL-01 执行一致性审计

本表只核对 Phase A 的 12 个冻结案例、其实际测试/Trace、初态和证据；不改写 `CASES.json`、`RUBRIC.json`、`EVAL_PROTOCOL.md`、原始 Trace 或原有状态。

## 口径

- `EXACT_FROZEN_INPUT`：实际提交给 Assistant 的用户输入逐字取自冻结 `CASES.json`，并有独立新测试证据。
- `MAPPED_EXISTING_TEST`：输入或多轮脚本不是冻结题面的逐字执行；测试可能是新加的，但只证明相近 Fixture 工程路径，不能计入精确题面覆盖。
- `NEW_INDEPENDENT_TEST`：为本评测新增的独立测试/Session，不复用 AR-03/04/05 Run。它不自动表示输入精确或真实模型运行。
- `REUSED_EXISTING_TRACE`：把既有 AR-03/04/05 测试 Trace 映射到冻结案例。
- `trusted initial state` 和 `required evidence` 分开判定。`PARTIAL` 不改变原 PASS/PARTIAL 状态，也不进入“完整匹配”统计。
- H 的“独立留出执行”按冻结输入逐字匹配、独立新测试和可信初态匹配判断；运行未取得全部必需证据仍算已执行，失败证据另行保留。只有同时满足必需证据才计入“完整匹配”覆盖。
- 这里的模型输出均来自 Fixture。`PROGRAM_ASSERTIONS` 检查程序断言，`FIXTURE_SEMANTICS` 表示输出由脚本化模型决定；Trace 检查不等于独立语义评分。没有真实 Provider 评测，也没有独立语义人工评分。

## 12 个案例

| Gold | 原状态 | 输入匹配 | 执行来源 | 可信初态 | 必需证据 | H 独立执行 | 评定方法与差异 |
|---|---|---|---|---|---|---|---|
| E01-D | PASS | `EXACT_FROZEN_INPUT` | `NEW_INDEPENDENT_TEST` | MATCH | SATISFIED | 不适用 | 程序断言 + Fixture；新 Session，测试直接从 `CASES.json` 读取第一条冻结输入，无 Task、无 MCP。 |
| E02-H | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | `HOLDOUT_NOT_INDEPENDENTLY_EXECUTED` | 没有执行冻结的信息不足问题。 |
| E03-D | PASS | `MAPPED_EXISTING_TEST` | `REUSED_EXISTING_TRACE` | MATCH | SATISFIED | 不适用 | 程序断言 + Fixture + Trace 检查；复用 AR-03 J1 的长材料问题，不是 E03 冻结短题面。新 Session、无 Task、协议来源/比较/摘录/清单路径覆盖。 |
| E04-H | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | `HOLDOUT_NOT_INDEPENDENTLY_EXECUTED` | 没有隔离的冲突文档 Fixture，未修改共享 Knowledge 来造样本。 |
| E05-D | PASS | `MAPPED_EXISTING_TEST` | `NEW_INDEPENDENT_TEST` | MATCH | SATISFIED | 不适用 | 程序断言 + Fixture；新独立测试，但 `E05_INPUT` 与 Gold 题面措辞不同。JSON/503 值及无 Task 限制相同，不能算逐字题面执行。 |
| E06-H | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | `HOLDOUT_NOT_INDEPENDENTLY_EXECUTED` | 没有执行冻结的互相矛盾主张/日志组合。 |
| E07-D | PASS | `MAPPED_EXISTING_TEST` | `REUSED_EXISTING_TRACE` | PARTIAL | SATISFIED | 不适用 | 程序断言 + Fixture + Trace 检查；复用 AR-03 J2 QUEUED。Session 先有 J1 材料，TaskBinding 后创建；绑定 Run 有同 Event 当前 Delivery/Receiver Observation，但初态不是 Gold 的“新 Session 已绑定”。 |
| E08-H | PARTIAL | `MAPPED_EXISTING_TEST` | `REUSED_EXISTING_TRACE` | PARTIAL | PARTIAL | `HOLDOUT_NOT_INDEPENDENTLY_EXECUTED` | 程序断言 + Fixture + Trace 检查；复用 AR-03 J2 PROCESSED，目标 Event 有当前 PROCESSED；没有另一个 QUEUED decoy Event，冻结的历史/错误 Event 排除条件未验证。 |
| E09-D | PASS | `MAPPED_EXISTING_TEST` | `REUSED_EXISTING_TRACE` | MATCH | SATISFIED | 不适用 | 程序断言 + Fixture + 实际模型输入摘要检查；复用 AR-04A 的 `GOAL_MARKER`、`MATERIAL_JSON`、填充多轮、后续可信绑定和 Run-scoped MCP 路径。Gold 只给情境描述，未冻结同一份逐字多轮脚本/材料。 |
| E10-H | PARTIAL | `MAPPED_EXISTING_TEST` | `REUSED_EXISTING_TRACE` | PARTIAL | PARTIAL | `HOLDOUT_NOT_INDEPENDENTLY_EXECUTED` | 程序断言 + Fixture + wire/Domain Trace 检查；复用 AR-04B，验证有效 Memory、Tenant 隔离、撤销和恢复边界；没有 Gold 要求的“有效 Memory 与冲突的撤销/失源 Memory”成对样本。 |
| E11-D | PARTIAL | `MAPPED_EXISTING_TEST` | `REUSED_EXISTING_TRACE` | MATCH | PARTIAL | 不适用 | 程序断言 + Fixture + 只读 DB/Trace 检查；复用 AR-05 S2，输入措辞不同。调查/交接 Domain 路径有证据，但 Assistant 聊天 Run 实际 FAILED、无回答；原测试没有断言该 Run 状态。 |
| E12-H | PASS | `MAPPED_EXISTING_TEST` | `REUSED_EXISTING_TRACE` | MATCH | SATISFIED | `HOLDOUT_NOT_INDEPENDENTLY_EXECUTED` | 程序断言 + Fixture + Domain Trace 检查；复用 AR-05 S1 本地审批/修复/验证/交付 Fixture，用户措辞不同。原 PASS 保留，但它不是独立 H 执行，也不代表真实 Provider 或生产恢复。 |

## Run 复用审计

- 12 个冻结案例没有两个案例共享同一个 `run_id`。51 个案例 Run 引用均为 Fixture/Mock 或隔离本地测试 Run；Phase A 真实 Provider 请求为 0。引用可在 `runs/RUNS.jsonl` 按案例复查；一个案例可以包含其多轮链路的多个不同 Run。
- 安全负例是独立的**评定记录**，但不是独立执行：N01 复用 E10 Run；N02 复用 E09/E10 Run；N03 复用 E11/E12 Run；N04 没有 Run。它们不能被计作新 H/D 运行。
- E03/E05/E07/E08 共用 AR-03 Trace 文件，E09/E10/E11/E12 复用不同工作包 Trace。共享文件不等于共享 Run；同一条安全负例与主案例引用同一 Run 时则明确按复用处理。

## 覆盖统计

- 保持原始首次尝试状态：6 PASS、3 PARTIAL、3 NOT_RUN、0 FAIL。
- `Phase A 离线工程覆盖评定` 为 **6/12 PASS**；这是 Fixture 工程路径覆盖评定，不是当前模型真实任务成功率。
- 冻结输入完全匹配且新独立执行：**1/12（仅 E01-D）**。同时满足初态匹配和必需证据的也是 **1/12**。
- `MAPPED_EXISTING_TEST`：8/12；未运行：3/12。
- H 集共 6 例，**0/6 独立留出执行**；E08/E10/E12 的已有 Fixture 证据是映射复用，E02/E04/E06 未运行。
- 四条安全负例仍为 3 PASS、1 UNVERIFIED；其结果不加入 12 例分母，且上述 Run 复用不算独立负例运行。
