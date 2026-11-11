# C01-B2-LIVE-01-HF02 候选验证记录

实施状态为 `ACCEPTANCE_CANDIDATE`，待主 Agent 独立验收。仓库 `wgqa/OpsPilot`，候选分支 `codex/c01-b2-live-01-hf02`，Base `f5eb94810a0254633ea20fc2959d50eb1a38c3eb`。开工时远端 HF01 与 Base 一致，远端 `main` 为 `60eee87bfe3cca522011316cb4cd2c0064ad291b`。

## 开工核验

| 已实际读取的文件 | Base Blob |
| --- | --- |
| `PROJECT_NORTH_STAR.md`，含第 8 节 | `43dabda468506717c6956e676dfad4304c4f38e6` |
| `AGENTS.md` | `807b928686a4dd2cac7b15b3c354b9943c93c910` |
| `.agents/skills/opspilot-slice-review/SKILL.md` | `d405c8d413d633824b279202cc1503dab4cf0b03` |
| `docs/learning/OPEN_SOURCE_AGENT_REFERENCES.md` | `890ddf8918f976401c4df849eda6394770ed1997` |
| `docs/evidence/c01-b2-b/ADR-001-personal-memory-auto-consolidation.md` | `a7a0639ef3ff466bd2b1cffd6c7fb158d49a258e` |
| `docs/baseline/v1.0-implementation-baseline.md` | `30e18d7ddbade7cdf7712d035d6fd8488bcb9676` |
| `docs/baseline/MEMORY_LINEAGE.md` / `EVENT_RECOVERY.md` | `f66683083ce81b1d1eb7ae7d89b4af9e78123a2e` / `9ae6c3f35b93c8c139d598c4dfde42447cf5d0cc` |
| `docs/evidence/vnext/m2-01/DEFERRED_GATES.md` / `m2-02/DEFERRED_GATES.md` | `2e65870acb26a7c1383fdd96b5b8619748dda6b9` / `2536030b5b942bf9e3765e0916607549fa919934` |
| Runtime Grant `REPORT.md` / Runtime Grant HF01 `REPORT.md` | `dcd228603d9f1e603346021feb1c760e500f2ce7` / `794b88cc071467d068f200607eb6e21ec44e819d` |

本轮以用户完整 HF02 任务卡为范围，继承 B2-B 的 Owner/来源/写入合同、Runtime Grant 发送与结算合同和既有业务门禁。仓库未找到 LIVE HF01 独立裁决原件，该原件标记 `UNVERIFIED`。`requirements.lock.txt` Blob `de16e1113ac250511cee8d7b6a079b88b1ca4f99`，`frontend/package-lock.json` Blob `b732ef421d59fcb6eaa1e64b311801fd8b2dc760`。

## 修复与结果

1. **受理时间边界。** `advance_disabled_personal_memory_watermarks()` 在开关写事务读取同 Owner 各 Session 已受理的最大 USER sequence。两个 Fixture Session 的旧消息都是 sequence 1，开启时 Run 为 `RUNNING`，之后成功。各自完成 5 条新消息后没有批次，完成第 6 条后各产生一个 `[2, 7]` 批次。关闭再开、换 Worker、重复调度也只读取这 6 条。`SKIPPED_DISABLED` 水位记录的来源列表为空。
2. **记忆有效性。** `semantic_memory.py` 的 `_personal_memory_exclusion()` 由前台召回、Context 当前性校验和 Consolidator 共用。实际 Fixture 模型输入含合法 ACTIVE 项，重复提案产生一次去重。过期、来源正文与 Digest 不符、撤销和另一身份的记录都未进入提取 Prompt。发送许可前撤销时 MockTransport 发送 0 次，预留释放。响应过程中撤销时提案提交失败。Worker 在预留后重启且 Prompt 变化时，未外发预留释放，旧请求结束。
3. **流式结束。** `assistant.py` 只让 `stop` 或完整 `tool_calls` 通过。框架仍组装增量参数，执行前校验组装后的原始 JSON 完整性。已保存的异常 SSE 回放、旧 HF01 Checkpoint 中尚未提交的截断回答均在恢复时失败，两项各只有 1 次 Mock 发送。旧 Checkpoint 的既有结算记录可回查。
4. **取消清理。** 阻塞型 MockStream 在首段持久化后进入下一次读取。取消 Run 的外层 Task 后，测试在同一事件循环内确认读取 Task 已终止、流已关闭。Run 和 Chat Attempt 为 `FAILED`，Assistant Call 与 Spend 为 `UNKNOWN`，保留 1 个草稿 Chunk，成功回答数为 0。换 Worker 后无重新领取，发送次数仍为 1。会话投影保留草稿和失败说明。
5. **单 Session 导出。** `export_live_evidence.py` 只导出本 Session 来源记录，及成功模型调用或有 HTTP 响应记录的请求实际选入的 Personal Memory。空 Session 导出 0 条记忆及事件。Session B 实际使用 Session A 的一条记忆时，只导出该条记录、事件、来源 Session/Message ID 和 Digest。无关记录、排除项及自动整理比较上下文已过滤。跨 Session 比较输出可能复述其他记忆，含已过滤比较项的输出在证据中以省略标记表示。文件范围守卫和 API Key、Bearer Token、Cookie 脱敏通过。

### Fixture 流式状态与费用

| Provider 结束条件 | Assistant 结果 | Runtime Spend |
| --- | --- | --- |
| `stop` | `SUCCEEDED`，一个最终回答 | `DELIVERED`，40 input / 9 output，49 micro-USD |
| 合法 `tool_calls` 后 `stop` | 继续现有工具循环，完成一个最终回答 | 两笔 `DELIVERED`，合计 111 micro-USD（HF01 MCP Fixture） |
| `length` | `FAILED`，`ASSISTANT_PROVIDER_STREAM_OUTPUT_TRUNCATED` | `RESPONSE_STORED`，49 micro-USD |
| `content_filter` | `FAILED`，`ASSISTANT_PROVIDER_STREAM_CONTENT_FILTERED` | `RESPONSE_STORED`，49 micro-USD |
| `insufficient_system_resource` | `FAILED`，`ASSISTANT_PROVIDER_STREAM_INSUFFICIENT_RESOURCES` | `RESPONSE_STORED`，49 micro-USD |
| `aborted` | `FAILED`，`ASSISTANT_PROVIDER_STREAM_ABORTED` | `RESPONSE_STORED`，49 micro-USD |
| 不支持的结束原因或不完整工具参数 | `FAILED`，明确错误码，0 次 MCP 调用 | `RESPONSE_STORED`，49 micro-USD |
| 缺 `[DONE]`、缺 Usage、断流，或发送许可发放后取消 | 无最终回答，Assistant Call `UNKNOWN` | `UNKNOWN`，保留 14,048 micro-USD Fixture 预留 |

结束原因和工具增量格式按 [DeepSeek Chat Completions 文档](https://api-docs.deepseek.com/api/create-chat-completion/) 核对。上表所有金额是隔离账本里的 Mock 数据。

### 单 Worker 等待

原有 30 秒 HTTPX 网络阶段超时限制两次读取之间的等待，整次整理缺少总截止。候选对现有 `ainvoke` 加 30 秒总截止。注入 250 ms 截止后，Mock 响应流阻塞并被关闭，Job 为 `UNKNOWN / PROVIDER_TIMEOUT_RESULT_UNKNOWN`，账本保留未知请求预留。队列里随后受理的聊天成功完成，Mock 发送顺序为一次整理、一次聊天。浏览器 Fixture 验证现有设置 API 轮询能显示排队、运行、超时结果未知。单 Worker 仍可能在正在执行的整理结束或截止前推迟下一条聊天。

## 回归与复跑

环境为 Windows、Python 3.14、Node 24。数据库与日志在候选目录 `.runtime/hf02-evidence/`。Base RED 用同一份新测试复制到独立 `D:\OpsPilot-C01-B2-LIVE-01-HF02-BASE`，该工作树的生产源码为指定 Base。使用同一个解释器、锁定依赖和假密钥。下表每组 Python 文件均使用 `-p no:cacheprovider --tb=short -q` 及独立 `--basetemp`。

| 测试文件或命令 | 结果 | 本地日志 |
| --- | --- | --- |
| `test_c01_b2_live_01_hf02_memory.py` + `test_c01_b2_live_01_hf02_stream.py` | Base 6/26，候选 26/26 | `red-final-corrected.log`、`green-final.log` |
| `test_c01_b2_a_personal_memory.py` + `test_c01_b_personal_memory.py` | 16/16 | `regression-b2a.log` |
| `test_c01_b2_b_personal_memory_auto_consolidation.py` | 27/27 | `regression-b2b-final.log` |
| `test_c01_b2_live_01_hf01.py` | 10/10 | `regression-hf01-final.log` |
| `test_product_01_runtime_grant_01.py` | 21/21，拆为 20 + 1 | `regression-runtime-split.log`、`regression-runtime-api.log` |
| `test_product_01_runtime_grant_01_hf01.py` | 13/13 | `regression-runtime-hf.log` |
| `test_c01_a_session_context.py` + `test_m3_hf02_lineage.py` | 7/7 | `regression-context.log` |
| `test_m1_chat.py`、`test_m1_web_events.py`、`test_r1_user_demo_hf02_sse.py`、`test_checkpoint_smoke.py`、`test_m1_worker_recovery.py`、`test_mcp_smoke.py` | 21/22 | `regression-session.log` |
| `test_r1_live_failure_closeout.py` | 8/9 | `regression-closeout.log` |
| `test_s1_business.py`、`test_m2_02_s2_diagnosis.py`、`test_m4_02_s3.py`、`test_m4_03_s3.py` | 44/44 | `regression-business.log` |
| `node --experimental-strip-types --test test/conversation.test.ts` | 候选与 Base 均 10/12，增强的失败草稿用例 RED 0/1、GREEN 1/1 | `projection.log`、`baseline-projection.log`、`red-frontend-draft.log` |
| `npm run build`、`npm run test:e2e:c01-a`、`npm run test:e2e:c01-b` | 构建通过，浏览器用例 2/2 | `build.log`、`e2e-c01-a.log`、`e2e-c01-b.log` |

```powershell
Set-Location 'D:\OpsPilot-C01-B2-LIVE-01-HF02'
$py = 'D:\OpsPilot-C01-B2-LIVE-01-PREP\.venv\Scripts\python.exe'
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:OPSPILOT_ASSISTANT_PROVIDER_ENABLED = '0'
$env:OPSPILOT_LEGACY_PROVIDER_ENABLED = '0'
$env:OPSPILOT_MODEL_API_KEY = 'offline-only'
$env:OPENAI_API_KEY = 'offline-only'
$env:LANGSMITH_TRACING = 'false'
$env:LANGCHAIN_TRACING_V2 = 'false'
& $py -m pytest -p no:cacheprovider --tb=short -q --basetemp='.runtime\hf02-evidence\rerun-db' tests/test_c01_b2_live_01_hf02_memory.py tests/test_c01_b2_live_01_hf02_stream.py
Set-Location frontend
npm run build
npm run test:e2e:c01-a
npm run test:e2e:c01-b
```

## 历史失败与验证边界

- `test_pre_send_failure_is_not_sent_and_releases_only_unsent_reserve` 期待特定说明文案，基线与候选均得到 `ASSISTANT_STOP:RuntimeError:offline pre-send validation failure` 的程序说明。`test_ops_02_expired_total_deadline_blocks_run_without_model_call` 期待 `INVESTIGATION_DEADLINE_EXCEEDED`，两边均在 Legacy 授权守卫返回 `LEGACY_PROVIDER_AUTHORIZATION_REQUIRED`。同环境单独复跑 Base 为 0/2。
- 两项前端历史断言期待 `message:a2`、`message:limit-answer`，Base 与候选均返回现有 `turn:chat-r2:q2`、`turn:limit-run:limit-question`。保留原断言。
- Runtime Grant 文件整组运行有一次 Windows `TestClient.wait_shutdown` 挂起。已中止该次测试并拆分复跑，20 项和单独的正式 API 用例均通过。未改对应测试或关闭逻辑。
- 现有开启期的旧 Watermark 历史无法据消息完成时间回推原开关边界。本次按后续开关事务记录准确边界，保留历史消息、Memory、账本和已完成回答。
- 真实 DeepSeek、全仓测试及真实用户测评 `NOT_RUN`。真实 Provider 发送 0，外部业务写入 0。测试只使用隔离数据库，PREP 真实数据及历史 Gold 保留原样。
