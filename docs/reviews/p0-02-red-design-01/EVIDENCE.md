# P0‑02 证据

**Base `93d5ac831447c5d23c677bd477958f9817ad8c2a`，状态 ACCEPTANCE_CANDIDATE。** 真实生产调用为零，外部业务写入为零。测试依赖锁 Blob `de16e1113ac250511cee8d7b6a079b88b1ca4f99`，Python 3.14.0、pytest 9.1.1。

## A. 纯函数

| 版本 | 条件输入 | 生产返回 | Token 估算（输入 / 输出 / 四项回填同结构 / 上限）|
|---|---|---|---:|
| main `60eee87` | 序号 2、3、4、5 | 序号 3、4、5，原文均未裁剪 | 79 / 90 / 102 / 512 |
| P0‑01 `93d5ac8` | 同上 | 同上 | 79 / 90 / 102 / 512 |

唯一丢项是序号 2 的 `Only event E7`。完整 JSON 和截断后逐项文本见 [main](runs/pure-60eee87b.json) · [P0‑01](runs/pure-93d5ac83.json)。回填操作只做本地估算，未修改被测函数。在同一输出 JSON 结构下四项仍低于 512，因此这个反例的直接原因是每分类三项。先前 AR‑04 候选 `b7c4445` 丢的是序号 3，本轮未重跑该分支。[原审计](../interview-task-continuity-20261123/EVIDENCE.md)

## B. 到实际 SDK 序列化的观察

正式 API 完成登录、Session、订单绑定和消息受理。S3 夹具只在本机回环初始化，Task 和异 Task 绑定同一演示订单。已有 Worker 单次派发入口负责 claim、LangGraph、stdio MCP 工具发现及实际 ChatOpenAI/OpenAI SDK 请求构造。异步 HTTPX MockTransport 捕获完整 JSON 并返回确定性回复，同步 Transport 拒绝发送。压缩替身只读取本次的 `previous_summary` 与 `new_messages`，不会向未见到的早期消息发明来源。它在能看见四项时返回四项，刻意给保留能力一个宽松输入，虽然现行压缩提示要求每类最多三条。程序实际接受四项 JSON，随后自身的持久化规则删项。固定 ACK 用于观测模型输入，实际业务调查与结果满足率为 NOT_RUN。

### 原始默认预算与隔离实验

- 正常 S3 策略 `CONTUX_S3_V1` 第 9 个 Task Run 返回 `TASK_AUX_PROVIDER_LIMIT`，前 8 轮 SDK 有输入，第 9 轮没有任何 SDK 派发。24 条消息虽均已用正式接口受理，但默认预算下只完成 8 个模型轮，未到多代压缩。 [原始失败](runs/journey.log) · [逐轮记录](runs/hybrid/turns.json)
- 长旅程在临时 DB 中调用仓库已有的 `configure_s3_experiment_budget(db, task_id, 16, 10)`，仅在首次调用前生效，使用可核对的 LEGACY_V1 实验配置和无累计 AUX 上限。每 Run 的限制及全部输入预算判断保留；应用保持普通 HYBRID 策略，配置 12,000 Token。原默认结果保留。 [隔离配置](runs/verified/task-budget-policy.json)
- 第一轮隔离实验已生成完整输入与结果，但 Windows 临时 SQLite 备份连接未关闭，清理以 WinError 32 退出。只修复审计脚本的连接关闭，原日志及轨迹保留。干净复跑 exit 0。两次实测均最终丢 E7，代际分别为 6 和 7；条件进入摘要的轮次受预算水位和实际序列化大小影响。 [首跑含清理失败](runs/isolated-hybrid.log) · [干净复跑](runs/verified.log)

### 干净复跑的证据链

长旅程 24 个绑定用户轮全部得到离线 ACK。摘要保存 7 代，前两代各有 E7、协议 v2、时段。第 20 轮压缩替身返回四条带序号条件，估算正文 152 Token。第 3 代摘要覆盖至消息 10，其中的 `constraints` 已少 E7。第 7 代覆盖至 14，仍缺 E7。四条原始消息均在 SQLite，真实序号为 4、6、8、10。最后一轮原始 Task 锚点只含 `Investigate callback`，没有正式纠错锚点。近期普通用户历史与其他块未补回 E7。最后三个条件均只由第 7 代摘要带入。

| 条件 | 消息序号 | 第 24 轮 SDK 实际位置 | 对照 |
|---|---:|---|---|
| `Only event E7` | 4 | 缺失 | 原消息和早期摘要还有完整源码引用 |
| `Use protocol v2` | 6 | system，第一个历史摘要 | 准确引用同 Task 用户原文 |
| `Time window 10:00-11:00` | 8 | 同上 | 同上 |
| `Report receiver status separately` | 10 | 同上 | 同上 |
| 绑定前公共协议说明 | 1 | 同上 | NULL Task 原始用户消息经受理验证 |
| 同 Session 的另一 Task E9 | 2 | 无 | 全部采集的长旅程请求均排除 |

原始 SDK `messages[].content` 与 `assistant_calls.request_json` 对齐。以四项文案为分母，Provider 输入覆盖 3/4（75%）。送达的三条条件均引用到正确原文，条件来源准确率 3/3，按全量要求计 3/4。当前版本没有逐项有效状态，所以结构化状态和旧条件错误激活数不能从出站历史摘要直接读出。

| 资源 | 观测 |
|---|---:|
| 长旅程保留的 SDK 请求 / 压缩调用 / 回答调用 | 31 / 7 / 24 |
| 最终 SDK messages 估算 / 工具 Schema 数 | 8,740 Token / 9 |
| 最终 Builder 输入估算 / 有效配额 / 配置配额 | 8,019 / 8,595 / 12,000 Token |
| 31 次 SDK messages 估算合计 | 142,476 Token，未含工具 Schema 开销，替身 usage 也由估算提供 |
| 24 个 Worker 派发累计 | 30.55 秒，本机含 SQLite、stdio 与 mock，无法代表生产延迟 |
| 长旅程持久摘要 JSON / 依赖 | 5,035 UTF‑8 字节 / 26 行，未含索引、SQLite 页与其它账本 |
| 新增 Schema / 生产运行时存储 | 0 / 0，本轮只有审计材料；方案成本待实测 |

[最终 SDK 请求](runs/verified/final-sdk.json) · [完整出站与模拟响应 JSONL.gz](runs/verified/wire.jsonl.gz) · [SQLite 消息、各代摘要、依赖和账本](runs/verified/long-state.json) · [逐代来源和 Token 复核](runs/verified/measurements.json)

## C. 修订、撤回和失效对照

每个分支从实际 24 轮后的临时 SQLite 快照开始。正式条件变更复用 Domain `CORRECT_TASK_INPUT` 受理、claim、应用与任务修订，纠错应用后将该调查 Run 置为等待输入；之后用正式 Assistant 再发最后一问。未模拟前端提案分类器的准确性。

| 对照 | 本轮实际观察 | 结论边界 |
|---|---|---|
| 原时段正式替换为全天 | `task_run_inputs` 出现应用记录，原文到达 `LATEST_FORMAL_CORRECTION`。旧 10:00–11:00 仍在历史摘要的 constraints。E7 仍缺。 | 修订后的当前状态缺少可单独读取的有效条件集合。模型是否遵守新时段为 NOT_RUN。 |
| 正式撤销分别报告 Receiver | 已应用撤回、纠错锚点送达，旧要求仍在历史摘要。 | 检测到历史冲突文字，不能把出现次数当作实际错误采用次数。 |
| 仅假设改全天 | 假设作为普通用户消息进入请求，无新应用记录，无正式锚点。 | 受理层未升级。固定 ACK 无法证明模型会主动澄清。 |
| 未确认的两段冲突时段 | 两段文字均为普通上下文，无新应用记录。 | 未观察到对任务权威状态的升级。模型自然语言宣称与工具选择 NOT_RUN。 |
| Task 被终止 | 受信 abort 后早期检查返回 `TASK_ABORTED`，SDK 派发 0 次。脚本调用到单次 dispatch 返回异常，未执行常驻 Worker 的失败收尾，所以轨迹 DB 的 Run 仍为 RUNNING。 | 证明出站前阻断。另以现有安全回归验证 S3 资源撤权后不能读旧答复、旧摘要依赖失效与恢复。 |

[各分支状态和覆盖](runs/verified/results.json) · [全部 P0‑01 隔离、M3、撤权与恢复回归](runs/regressions.log)

## 命令与计数

从相应 worktree 根目录执行。脚本绝对路径指向本交付目录。`--output` 使用新目录，历史 RED 不覆盖。测试不读取凭据，SDK 使用本地 MockTransport 与合成 key。

```powershell
$env:PYTHONDONTWRITEBYTECODE = '1'
$py = 'D:/学习/agent新项目/.venv/Scripts/python.exe'
$probe = 'D:/学习/agent新项目/.worktrees/p0-02-red-design-01/docs/reviews/p0-02-red-design-01/repro.py'
$output = Join-Path $env:TEMP ('p002-replay-' + [guid]::NewGuid().ToString('N'))
# 分别在 main 的 detached worktree 和 P0-01 Base 对应 worktree 执行
& $py -u -X utf8 $probe pure --output $output
# 两条 journey 在 P0-01 Base 的工作树执行。默认预算的预期结果是第 9 轮失败。
& $py -u -X utf8 $probe journey --output "$output/default"
& $py -u -X utf8 $probe journey --isolated-budget --output "$output/isolated"
& $py -u -X utf8 $probe measure --output "$output/isolated"
$env:LANGSMITH_TRACING = 'false'
$env:LANGCHAIN_TRACING_V2 = 'false'
$env:OPSPILOT_MODEL_API_KEY = ''
$env:OPENAI_API_KEY = ''
$env:OPSPILOT_CONTEXT_STRATEGY = 'HYBRID'
& $py -u -X utf8 -m pytest -q -vv --tb=short -p no:cacheprovider -o faulthandler_timeout=70 --basetemp="$output/pytest" tests/test_p0_01_task_context.py tests/test_m302_context.py tests/test_m4_03_hf_02.py::test_revoked_scope_blocks_s3_chat_context_chunks_and_redacts_bound_answer tests/test_ar04a_compression_cancel_hf_01.py::test_cancelled_compression_is_not_resent_on_recovery
```

既有定向 pytest **18/18 通过，0 失败**。审计另记 **2 个纯函数保真 RED、1 个最终 SDK 覆盖 RED**，以及 **1 个任务级默认预算阻断**。4 个非终止对照获得 ACK，1 个终止对照零派发，均不作为任务结果正确率。AR‑04B 未纳入运行或通过数，保留独立 HOLD / UNVERIFIED。真实模型的 5 个语义旅程（四条件、替换、撤回、假设、冲突）均 NOT_RUN；浏览器、付费 Provider、全量 pytest 未运行。
