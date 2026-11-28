# R2-AR06-EVAL-01 Phase B 真实模型运行准备清单

## 本轮边界与结论

- 本次只做离线核对：真实 Provider 请求 `0`，Runtime Grant/Spend Pool 创建 `0`，浏览器自动化 `0`，外部业务写入 `0`。
- 本表没有读取 `.env`，也没有打开现有 `.runtime/user-demo` Domain/Checkpoint/账本；该目录的当前 Grant 状态因此为 **UNVERIFIED**。历史 `USER_TEST_GUIDE.md` 是过去时点的准备记录，不能替代当前账本查询。
- 建议第一批**计划**检查 E01-D、E03-D、E05-D、E07-D、E08-H、E09-D（6 个）；这不表示 6 个都能立即安全运行。当前可以直接复用的精确用户输入是 E01、E03、E05、E07、E08；E09 缺逐字多轮脚本与压缩材料。
- **真实 Live 运行目前 0/6 Ready。** 共同阻断是没有供评测使用的新隔离 Live Domain/Checkpoint 启动路径：`scripts/user-demo/Start-UserDemo.ps1` 固定 `.runtime/user-demo`，`scripts/user-demo/runtime_admin.py` 的 `DB_PATH` 也固定同一数据库。不能拿旧 Demo 账本/Session 当新评测库，也不能运行会创建该库 Grant 的 `runtime_admin.py configure`。
- 本轮没有授予 Provider 请求权限。即使数据已准备好，也必须等用户另行授权并建立独立运行数据目录后，才能配置 Grant 和发出真实请求。

## 案例与现有离线命令

每条命令只运行 Fixture/Mock；它不能作为真实模型结果。每次使用新 basetemp，不复用或清理旧目录。

| 案例 | 冻结输入位置 | 夹具/权限核对 | 现有离线命令 | Phase B 状态与缺口 |
|---|---|---|---|---|
| E01-D | `CASES.json` → `E01-D.user_turns[0]` | 新空 Session、无 Task、无 MCP；独立 Fixture 测试逐字从 Gold 读取输入。 | `python -m pytest tests/test_r2_ar06_eval_01_material_case.py::test_r2_ar06_e01_fresh_session_answers_http_202_without_mcp -q --basetemp="$caseTemp"` | 输入和离线断言就绪；Live 仍受隔离 Runtime/Grant 阻断。评分看持久回答、202 不等于处理完成、无当前订单主张。 |
| E03-D | `CASES.json` → `E03-D.user_turns[0]` | AR-03 Fixture 有授权项目下的 v1/v2、比较、摘录与 Skill Trace；User Demo 指南列出 `orders-callback` 项目与回调协议资料。需在未来 Live 环境确认 UI 项目授权与 Gold 的 `orders-async-demo` 来源映射。 | `python -m pytest tests/test_r2_ar03_integrated_journey_01.py::test_j1_material_protocol_comparison_and_checklist_without_binding -q --basetemp="$caseTemp"` | 输入可复制；现有测试是更长 J1 题面，不能算冻结输入精确执行。Live 评分看版本化文档来源/摘录/清单，不能推断生产部署版本。 |
| E05-D | `CASES.json` → `E05-D.user_turns[0]` | 无 Task/业务 Observation；JSON 与 503 日志直接在冻结输入中。 | `python -m pytest tests/test_r2_ar06_eval_01_material_case.py::test_r2_ar06_e05_material_analysis_uses_unbound_user_claims -q --basetemp="$caseTemp"` | 精确输入已冻结，但现有测试常量 `E05_INPUT` 措辞不同，故只证明映射 Fixture。Live 应直接复制 Gold 全文。评分区分材料明示、条件性解释、未知线上事实。 |
| E07-D | `CASES.json` → `E07-D.user_turns[0]` | 离线参数化测试显式固定目标 Event ID，观察 Delivery `ACKNOWLEDGED/202` 与 Receiver `QUEUED`。用户 Demo 初始化则随机生成 Event ID，不能满足冻结 Event。 | `python -m pytest tests/test_r2_ar03_integrated_journey_01.py::test_j2_same_session_binding_uses_current_same_event_observation -q --basetemp="$caseTemp"` | 需新隔离数据库并精确准备 Gold 的 trusted binding/Event。当前测试还包含前置 J1、后创建 TaskBinding，只是映射执行。评分看同 Event 当前 Run Evidence，202/ACK 不算完成。 |
| E08-H | `CASES.json` → `E08-H.user_turns[0]` | 需要同一目标绑定下的目标 Event=`PROCESSED`、另一 Event=`QUEUED`，并有历史 `QUEUED` 线索。现有 AR-03 参数化测试只翻转目标 Receiver 状态，没有 decoy Event。User Demo 只有两个独立订单示例，不能替代该 Event 组合。 | 同 E07 命令；只验证现有目标状态 Fixture，**不会**验证 Gold 所需 decoy。 | H 留出不能以现有测试宣称完成。先在新隔离库准备精确目标/decoy/历史身份，再逐字运行一次；禁止把另一个订单当作 Gold decoy。评分要求目标 Event 当前证据胜过历史/错误 Event。 |
| E09-D | `CASES.json` → `E09-D.user_turns[0]` | AR-04A 有合成长会话、压缩 Summary、后续 TaskBinding 和当前 Run MCP 事实，但具体消息由 `GOAL_MARKER`、`MATERIAL_JSON`、填充段及多轮脚本构造；Gold 没有冻结这些逐字材料/轮次。 | `python -m pytest tests/test_ar04a_context_journey_01.py::test_ar04a_long_session_keeps_goal_material_and_current_facts tests/test_ar04a_context_journey_01.py::test_ar04a_invalidated_summary_is_not_sent_to_the_model -q --basetemp="$caseTemp"` | **不要启动真实评测**，直到补充材料和每轮输入经过批准并冻结。现有测试命令只复测 Context 工程，不等于真实 E09。评分看真实出站 Context、Summary 来源有效性、目标/材料保留和当前 Observation 作用域。 |

PowerShell Fixture 临时目录示例（每个命令运行前重新生成；不删除已有目录）：

```powershell
Set-Location 'D:\OpsPilot-LIVE-02-FIX-01-HF02'
$caseTemp = Join-Path (Get-Location) ('.runtime\pytest-r2-ar06-hf01-' + [guid]::NewGuid().ToString('N'))
```

## 真实运行启动条件

1. 先提供一个不与 `.runtime/user-demo` 共用的运行目录，并让现有启动/Grant 管理入口明确使用同一新 Domain 与 Checkpoint 路径；这需要独立授权的最小运行适配。本次没有修改启动器，也没有复制旧数据库。
2. 在该目录中从新初始化流程创建测试身份和合成 Domain 数据。每个正式案例使用全新隔离 Domain/Checkpoint；不得把冻结 Gold expected labels 放进模型输入。
3. E07/E08 的 TaskBinding、Event 状态和事件身份由可信程序/隔离数据准备；不通过用户材料、模型输出或手工数据库写入冒充授权事实。E08 还需两个不同 Event 的目标与 decoy。
4. 只有用户另行授权后，才能在本地 `.env` 配置 Provider 凭据/官方计价版本，显式创建该隔离库的 Runtime Grant 和有限 Spend Pool。不要运行当前 `runtime_admin.py configure`：它指向 `.runtime/user-demo` 且会创建持久 Grant。
5. Preflight 后每个 Case 仅执行一次首次尝试；失败原样保留，不选择性重跑。每次记录候选 SHA、模型/配置/价格版本、Prompt 与 Tool Schema digest、真实 Provider 请求数/Token/费用、MCP 工具调用与同 Run Observation、业务 Outcome、耗时及原始失败。
6. 由冻结 Rubric 按证据进行显式 PASS/PARTIAL/FAIL/NOT_RUN/UNVERIFIED 评分；结构化证据断言与回答语义审阅分开记录。不能用 Fixture 评分、`Run=SUCCEEDED` 或跨 SHA 历史结果冒充真实 Agent 成功率。

## 既有失败和预算提醒

- AR-03 Real LLM 02：5 Provider 请求、11 MCP；取得 PROCESSED 观察，但因 MCP 预算耗尽没有交付最终回答。历史失败保持原报告，不计入本 6 案例的结果。
- AR-04C Live Exec 01：8 Provider 请求、14 MCP；Memory ON 时将历史 Observation 说成本轮重读，G7 仍 FAIL。不能与本次离线案例合并算准确率。
- E11 的 Fixture Assistant Run FAILED 仍是当前离线报告发现；不得以随后 S2 Task 成功遮盖。
- 目前没有新的真实模型请求、费用或 Grant。应用侧计价也不等同供应商账单；费用观察须来自本次隔离库的 Provider Usage/Spend 记录。
