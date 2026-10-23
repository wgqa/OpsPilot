# M4-03 失败与修复记录

所有失败均保留在原运行目录；最终 PASS 结果没有覆盖先前失败。

| 尝试 | 失败 | 后续处理 / 最终状态 | 原始记录 |
|---|---|---|---|
| 冻结后 RED 01 | 新增 S3 测试首先证明订单目录、绑定和动态 Gate 尚未实现 | 确认为预期 RED，之后实现并由全量 pytest 复验 | `runs/red-01/pytest-red.log`、`pytest-red-exit.txt` |
| 冻结后 RED 02 | 7 项失败，缺失 `s3_handoff` 与 S3 订单/Gate/纠错链路 | 按冻结范围实现；最终 S3 和全量测试通过 | `runs/red-02/pytest-red.log`、`pytest-red-exit.txt` |
| 首轮 Memory smoke | DB 查询使用了不存在的 `status` 列 | 改为真实 schema 字段 `model_status`；修复后 Provider/MCP 运行通过 | `runs/memory-20261023T084116Z/`、`runs/memory-20261023T084339Z/` |
| Memory 无关中文样例 | 真实模型上下文曾错误选择“供应商发票”案例，因为单字匹配把泛化汉字当成强相关 | 保留 provider RED；中文改用字符双元组，并新增中文无关案例回归；单测通过，最终真实 provider 运行正确排除 | `runs/memory-20261023T092036Z/`、`runs/pytest-memory-chinese-relevance-final-20261023.log`、`runs/memory-20261023T092400Z/TASK-D-UNRELATED-CASE.json` |
| Web 自动化前几轮 | 初始集成发现缺少 handoff 资格字段、API 重启编排问题、event 引用列不符、重启后 502、TaskControl 结束版本取错 | 每次原始目录保留；最小修复后 Edge 真实旅程、回执回查和服务重启均通过 | `runs/web-20261023T074912Z/`、`075741Z/`、`080152Z/`、`080417Z/`、`080933Z/`、`081303Z/`、`082054Z/`、`082452Z/` |
| API 重启后页面刷新补跑 | 两轮在 Vite proxy 连接重置窗口内收到 502，单次页面加载未及时恢复；另一次浏览器旅程通过，但外层 PowerShell 使用 GBK 输出 Unicode 符号时退出码为 1 | 将验收轮询限制为最多两次页面刷新并等待持久回执；设置 `PYTHONIOENCODING=utf-8` 后最终 Edge smoke 退出码 0 且 PASS | `runs/web-20261023T095950Z/`、`runs/web-20261023T100658Z/`、`runs/web-20261023T101359Z/`、最终 `runs/web-20261023T101521Z/launcher.log` |
| Knowledge 显式检索 RED | 明确询问 bound contract v2 的 202 含义，模型先加载 Skill 并查 HTTP/MCP 当前事实，但 0 次 `search_callback_knowledge`；Gate 仍正确 | 冻结后记录；增加窄范围 prompt 要求并得到一条真实双文档检索，但当时 provenance 仍标为 v1 | `runs/knowledge-explicit-red-20261023T094100Z/`、`runs/knowledge-explicit-green-20261023T094300Z/` |
| Knowledge provenance v2 复验 | 修正 Prompt provenance 为 v2 后的新鲜真实 Provider Run 再次未调用 Knowledge（0 次），Gate 正确且零写入 | 保留失败，在线显式检索判 PARTIAL；按冻结停止条件不再追加调用追逐通过 | `runs/knowledge-explicit-green-v2-20261023T095000Z/` |
| Summary 实验准备 01 | 独立数据库缺少 S3 表，Provider 请求为 0 | 保留失败，正确备份旧 M3 fixture 后再执行 | `runs/summary-20261023T085329Z/` |
| Summary Provider 尝试 01 | 真实 Provider 请求超时；任务处于 `INTERRUPTED_RECOVERABLE` | 保留完整日志和恢复状态；第二个有界新鲜 attempt 成功，未覆盖首次失败 | `runs/summary-20261023T085347Z/` |
| 全量 pytest 初次执行 | 误用了系统 Python 3.14；收集 13 个测试模块时缺少 `mcp`、`langchain` | 识别仓库 `.venv` 后用项目锁定环境新鲜复跑；275 tests 全通过。系统解释器失败日志保留 | `runs/pytest-full-20261023T093000Z/pytest.log` 与 `pytest-venv.log` |

曾出现的行为偏差和失败运行均包含在 `RESULTS.json` 的 `retained_failures` 索引中，并可在上述目录复核。没有将失败从对照指标或证据目录中删除。
