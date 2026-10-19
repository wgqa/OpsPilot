# M2-02 失败、部分结果与修复记录

冻结观察与后续补充严格分开。原始日志在 `raw-logs/`，原始和补充 Trace 的脱敏副本在 `traces/`。

| 阶段/记录 | 结果 | 处理与当前状态 |
|---|---|---|
| RED 基线 | `opspilot.domain.s2_diagnosis` 尚不存在，定向测试按预期失败 | 保留在 `raw-logs/20261019-red-01/pytest-red-01.txt`；随后实现冻结范围内 Domain。 |
| Provider trace 首次 G4 harness | D3 校验返回 `TICKET_OUTSIDE_TASK_TENANT`，原因为测试 harness 的 ticket fixture 与 Task 租户不匹配 | 保留在 `raw-logs/20261019-provider-traces-01/provider-traces-01.txt`；修正 harness 绑定后重跑，未把该失败误记为 S2 Domain 通过。 |
| 初始 R/H scorer | 汇总错误地把 `_status()` 的错误字段读成 4 PASS / 12 FAIL | 原结果留在 `traces/rha/RESULTS-RH-initial-scorer-failure.json`；修复 scorer 后只从原始 Trace 重算，未重跑试次；16 R、16 H 均 PASS。 |
| G4 API trace snapshot 首次运行 | Harness SQL 引用了不存在的 `o.arguments_json` | 保留 `raw-logs/20261019-g4-api-02/g4-api-run-01.txt`；改为当前表字段后 `g4-api-03` 运行成功。 |
| Provider G7-H2 原始冻结 A 观察 | 测试意图为 404，但固定 fixture 返回真实 403，随后生成 `HANDOFF_READY` | 冻结标记 PARTIAL；没有替换 Gold/观察。修正 fixture 的独立补充运行得到 404/INCONCLUSIVE，仅作为补充。 |
| Browser G4 修正旅程 | 浏览器提交纠错 HTTP 202、revision 1；Run 随后查询旧 Request ID/多余主体事实并耗尽 8 model / 6 MCP 预算 | 原结果 INCONCLUSIVE 且旧诊断失效；留存浏览器证据。随后按固定合同收窄每 Run 工具 schema，并以真实 Provider/MCP G4 supplemental 验证，不冒充 UI 重跑。 |
| G6-H1 冻结 A | 越界请求仍得到 `HANDOFF_READY`，违反预期 `NO_ACTION` | 冻结 FAIL。没有发生成功跨租户读取或写入；修复后的独立 supplement 返回 `NO_ACTION`、0 attempts、0 回执/草稿。补充结果不覆盖原 FAIL。 |
| Browser screenshot | 自动化工具无法可靠确认活动 Edge URL | 按自动化约束停止该截图尝试；未伪造截图。浏览器验收因此记 PARTIAL。 |
| Browser midstate inspection | 一条调试查询缺少 SQL 参数，报 ProgrammingError | 仅调试检查失败，不代表业务链失败；原输出保留在 `runs/20261019-browser-01/g4-midstate-03.json`，不纳入代码 PASS。 |
| System Python import | 使用系统 Python 导入项目依赖失败：`ModuleNotFoundError` | 非项目虚拟环境。已用 `.venv` 完成全量测试；原命令与输出保留在 `raw-logs/20261019-final-05/system-python-import.txt`。 |

目前真实阻断性遗留为冻结 A-G6-H1 FAIL，以及 UI 截图/原始数据不足导致的 PARTIAL。实现层全量 pytest 为 154/154；是否满足 M2-02 阶段验收由主 Agent 决定。
