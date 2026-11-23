# P0-02-A-GREEN-01 实测证据

**ACCEPTANCE_CANDIDATE** · Base e37f4387e36aad9f23629bfa4f9c48bde2556638 · 最终复跑代码 ea4bd08461882abfe50dd47d60f76caf1f1deacc。证据提交只追加本目录文档和运行产物。

## SDK 请求对照

| 运行 | 用户轮 / 持久摘要代 | 四项原文覆盖 | 请求中的当前条件 |
|---|---:|---:|---|
| 冻结脚本，Base | 24 / 5 | 3/4 | 0 |
| 冻结脚本，候选 | 24 / 7 | 3/4 | 0。没有显式确认，未升级历史聊天。 |
| 同一配对脚本，Base | 24 / 6 | 3/4 | 0。显式确认载荷被 Base API 以 422 拒绝；最后读侧同一断言报“Expected one current conditions block, got 0”。 |
| 同一配对脚本，候选 | 24 / 6 | 4/4 | 4/4 均为 ACTIVE 版本 1，4/4 原始来源 ID 与 digest 相符。 |
| 配对中间复跑 | 24 / 7 | 4/4 | 四项均进入独立条件块，全部控制对照完成。 |

配对保留冻结旅程的 24 条原话及 HYBRID、12k 输入预算，在第 24 轮前另加一次显式确认。Base 也提交同一结构化请求并保留 422；两边最终 SDK 走同一断言。原始冻结脚本及上轮已有的 7 代 RED 未改动。真实持久代数随预算水位变化，新旧运行均保留。SDK 通过实际 HTTPX MockTransport 捕获，合成答复只确认接收。四项均来自同一 Task 的早期用户消息，公共协议说明保留，另一 Task 的 E9 排除。

[Base 最终请求](runs/verified-red/final-sdk.json) · [Base 断言失败](verified-red.log) · [候选最终请求](runs/verified/final-sdk.json) · [候选完整 SDK 回放](runs/verified/wire.jsonl.gz) · [候选七代对照](runs/paired-green-final/results.json) · [冻结原样候选请求](runs/verified-frozen/final-sdk.json) · [原始冻结 RED](../p0-02-red-design-01/runs/verified/final-sdk.json)

## 控制对照

| 对照 | 实测断言 |
|---|---|
| 替换时段 | 时段变为全天，版本 2；另三项的文本、版本、来源、确认引用均相同。旧时段可以在历史摘要的 historical_constraints 查到。 |
| 撤回报告格式 | 当前块只有 event、protocol、time；报告格式仍可作为明确的历史信息。 |
| 假设、未确认冲突 | 两个分支仍保持原始四项及来源，未升级未经确认的时间文本。 |
| 跨 Task 与公共信息 | 确认另一 Task 原始消息返回 404，普通 Assistant 路由带结构化字段返回 422。最终合法请求保留公共说明，不含 E9。已有 P0-01 覆盖派生摘要、旧答复、污染 checkpoint 与干净恢复。 |
| 来源失效、S3 撤权 | 更改活跃原始消息正文但不改原 digest、以及撤销现有资源 Grant，两个分支均 FAILED、0 SDK。 |
| Task 终止 | TASK_ABORTED，0 SDK；调用单次 Worker 入口的本地观察停在处理异常前，留下 RUNNING，不能把该行视为已完成的失败收尾。 |
| 整体预算 | 定向测试用四条较长条件和普通 “Continue”，证明计入条件后共同预算不足。SDK 分支用大请求复验失败收口：0 SDK，FAILED，持久用户提示要求缩小范围。 |
| Checkpoint | 干净 checkpoint 中断后继续，SDK 带四项；用同一恢复路径重放有伪造旧条件块的 checkpoint，FAILED，0 SDK。 |
| 默认 S3 配额 | 使用冻结脚本且不加隔离选项，第 9 个 Run 为 FAILED / TASK_AUX_PROVIDER_LIMIT，0 SDK。长旅程用已有的本机隔离配置，生产默认配额没有改动。 |

[逐项结果](runs/verified/results.json) · [默认配额停止](verified-default.log) · [已保留的首次失败](paired-green.log)

## 成本与范围

- 最终确认组 SDK messages 估算 8,677 Token，其中独立条件块 558 Token，另有 9 个工具 Schema。配对 Base 为 5,861 个消息 Token，历史选择和正式纠错锚点不同，因此两组总量差含历史变化。条件块的 558 单列。默认控制、必要工具和当前消息继续使用同一输入配额。
- 最终确认组前 24 轮共 24 次离线答复、6 次压缩，候选 33.80 秒，配对 Base 34.09 秒。两组在本地并行运行，耗时包含 SQLite、stdio 与 mock，不作生产延迟结论。
- 四项确认私有载荷净增 2,382 UTF-8 字节，由同一现有 Outbox 的受理和应用行承载，未含 SQLite 页、索引或常规纠错 Command、Message、Run 的开销。新增表、列与索引均为 0。快照定位经三个索引点查；活跃项各追加两次关联点查，最多 32 个槽位。完整配置下数据库时间、页放大与多租户压测为 NOT_RUN。
- 定向 pytest **37/37 通过，0 失败**，其中新增 Task 条件用例 3 个、既有用例 34 个。配对脚本 10 个控制分支全部通过各自断言。Base 保留 1 个真实失败断言，默认预算探针保留 1 个有意触发的失败断言。首轮 pytest 默认临时目录 ACL 报 30 个 setup errors，改为独立 basetemp 后复跑；首次候选来源失效时 MCP 退出包装成 ExceptionGroup，修正同一失败收口后重跑。全部日志保留。
- 执行与测试均针对本机临时 DB 和合成身份，无真实付费 Provider 或外部业务写入。踪迹确认审批、ActionIntent、Ledger、交接计数未增加。真实模型语义、用户任务结果、浏览器、全量测试为 NOT_RUN。AR-04B 独立 HOLD / UNVERIFIED。

[最终 pytest 日志](verified-regressions.log) · [初次 ACL 日志](regressions.log) · [存储查询计划](storage-proof.log)

## 复跑命令

在对应工作树根目录执行，使用仓库依赖环境。分别用不同输出目录，避免覆盖既有轨迹。Windows 的 pytest 使用当前任务专用 basetemp。

```powershell
$env:PYTHONDONTWRITEBYTECODE = '1'
$py = 'D:/学习/agent新项目/.venv/Scripts/python.exe'
$review = 'D:/学习/agent新项目/.worktrees/p0-02-a-green-01/docs/reviews/p0-02-a-green-01'
$replay = Join-Path $env:TEMP ('p002-green-' + [guid]::NewGuid().ToString('N'))
$frozen = 'docs/reviews/p0-02-red-design-01/repro.py'
# 在 Base 工作树
& $py -u -X utf8 "$review/prove_storage.py"
& $py -u -X utf8 "$review/run_pair.py" --baseline --output "$replay/red"
# 在候选代码工作树
& $py -u -X utf8 "$review/run_pair.py" --output "$replay/green"
& $py -u -X utf8 $frozen journey --isolated-budget --output "$replay/frozen"
& $py -u -X utf8 $frozen journey --output "$replay/default"
$env:LANGSMITH_TRACING = 'false'
$env:LANGCHAIN_TRACING_V2 = 'false'
$env:OPSPILOT_MODEL_API_KEY = ''
$env:OPENAI_API_KEY = ''
& $py -u -X utf8 -m pytest -q -vv --tb=short -p no:cacheprovider -o faulthandler_timeout=55 --basetemp="$replay/pytest" tests/test_p0_02_task_conditions.py tests/test_p0_01_task_context.py tests/test_m302_context.py tests/test_m1_dynamic_investigation.py tests/test_m1_chat.py tests/test_m4_03_hf_02.py::test_revoked_scope_blocks_s3_chat_context_chunks_and_redacts_bound_answer tests/test_ar04a_compression_cancel_hf_01.py::test_cancelled_compression_is_not_resent_on_recovery
```
