# C1-REV1 失败与修复记录

所有记录按发生顺序保留；失败尝试不从结果中删除。历史 C1 Gold/RED 文件没有改写。

| 尝试 | 结果 | 影响与处置 | 原始材料 |
|---|---|---|---|
| TTL 合入后旧 RED 夹具 | 测试准备失败 | 旧夹具未建立 Run-scoped Observation，Gate 在到达 FOLLOW_UP 断言前失败；按 REV1 冻结只调整夹具，未改用户目标或安全断言。 | `runs/rev1/readonly-followup-red-baseline-01.log` |
| 真实 Web E2E-02 | 失败 | Provider 未检索出能回答 HTTP 202 的绑定协议 Knowledge；不能算成功补查。保留真实 Provider/MCP 轨迹。 | `runs/rev1/web-e2e-02/TRACE.jsonl`、`backend.stdout.log`、`backend.stderr.log` |
| 真实 Web E2E-03 | 失败 | Provider 选中订单生命周期协议而非接收确认协议，答案中承认来源缺少 202 语义，但结果曾标记 `ANSWERED`。调整检索指引和未标记回答的归类；后续 E2E-04 命中正确版本资产。 | `runs/rev1/web-e2e-03/TRACE-review.jsonl`、`backend.stdout.log`、`backend.stderr.log` |
| 浏览器刷新观察 | 首次失败，随后修复 | Inspector 水合完成前短暂显示旧 `CHAT_READONLY` 助手回答。增加历史加载门控后重新刷新，旧回答不再显示，持久追问卡和来源可见。 | `runs/rev1/BROWSER-REFRESH-INITIAL-01.json`、`runs/rev1/web-e2e-04/BROWSER-REFRESH.json` |
| 前端 typecheck/build 04 | 失败 | TypeScript 检出 Task ID 可能为 `undefined` 的传参错误；归一化后 typecheck/build 05 通过。 | `runs/rev1/frontend-typecheck-04.log`、`frontend-build-04.log`、对应退出码 |
| 全量 pytest 01 | 322 passed，2 failed | 一项是冻结的预实现 RED 预期 FOLLOW_UP 被拒，实施后自然不再适用；另一项子进程缺少 `OPSPILOT_MODEL_API_KEY` 和 `OPSPILOT_MODEL_NAME`。未掩盖该次失败。 | `runs/rev1/full-pytest-final-01.log` |
| 全量测试环境加载尝试 | setup failed | 隔离 venv 没有 `python-dotenv`，加载 wrapper 抛出 `ModuleNotFoundError`；改用 Python 标准库从本地 `.env` 读取必要设置，不输出值。 | `runs/rev1/full-pytest-final-02-setup-fail.log` |
| 最终全量 pytest 03 | 通过 | 设置正确后排除且仅排除历史预实现 RED 文件，其余 323 项全通过。 | `runs/rev1/full-pytest-final-03.log`、`full-pytest-final-03.log.exitcode.txt` |
| 实现后定向 RED 检查 | 测试成功（旧 RED 断言按设计不适用） | 历史 C1 RED 仍保留用于审计；当前 post-implementation suite 使用独立 REV1 验收测试。 | `tests/test_m4_autonomy_c1_red.py`（未修改）；`tests/test_m4_autonomy_c1_followup_red.py` |

安全结果：真实成功旅程没有提升 TaskControl revision、重建正式 S3 Diagnosis 或生成审批/Plan/Intent/Ledger/Queue/Receipt。最终 Gate 仍是 `NEED_MORE`。没有将聊天回答标记为业务恢复。

非阻断限制：真实 Provider 的直接解释路径尚未单独执行；Chat sidecar 隐藏后仍花费 3,709 tokens；浏览器截图只存在于 CUA 交互记录，仓库保存浏览器刷新状态与来源 Trace。
