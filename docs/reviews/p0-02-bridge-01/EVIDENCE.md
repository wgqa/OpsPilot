# P0-02-BRIDGE-01 RED / GREEN

**ACCEPTANCE_CANDIDATE · Base 7786aa95331bba06af767a3f758eb320ab9e733a · 实测代码 698ddf434f9591c4d7aae799782e02922cb925f9。**

## 冻结深度与实际 SDK

在未改动历史脚本的 Base 上重新走 24 个用户回合和 6 代压缩，最后原始 SDK 请求缺 E7，覆盖 3/4。新审核接口先以实际 404 产生失败断言。GREEN 保留 24 条原话，不在前 24 轮预写任何结构化条件。第 24 轮普通请求在 7 代压缩后仍缺 E7。随后用户显式点按一次条件核对，才执行一次受账本控制的模型发现。持久候选找回 **4/4**，四条原文均指向同 Task 的原序号。勾选四项并正式应用后，下一轮实际 SDK 的 CURRENT TASK CONDITIONS 包含 **4/4**，合法公共背景保留，另一 Task 的专属内容未出现。[Base RED](runs/base-red/final-sdk.json) · [404 断言](red-api.log) · [完整 GREEN 结果与三份请求](runs/final/test_full_recovery_from_frozen0/results.json) · [全部 SDK JSONL](runs/final/test_full_recovery_from_frozen0/wire.jsonl.gz)

| 旅程 | 实测 |
|---|---|
| J1 重发续查 | 24 轮、7 代摘要。发现看到 24 条同 Task 用户来源，18 条只取片段。四条都是可核对的完整原话。候选明确标记部分历史未完整读取。 |
| J2 假设 | 全天假设为不可选项。GET 有效集合仍是原四项，此次提案未提交正式 Revision。 |
| J3 修订 | 只确认全天 REPLACE，其他三项的全文和来源结构不变。旧时段保留历史身份。 |
| J4 撤回 | Receiver 要求从当前集合移除。后续 SDK 的有效条件块只保留其余三项。 |
| J5 多 Task | 发现只收到 B 的来源。B 后续 SDK 保留公共背景，另一 Task 专属条件缺席。P0-01 的派生摘要、旧答复与恢复同次回归。 |
| J6 不完整 | 50 条历史触发分页标记，正文失效计数为 1。失效后的候选读面标记 STALE 且隐藏原文，确认被拒。撤销资源 Grant 后，审核读取和确认均为 404。默认 AUX 用满后没有新增出站尝试。 |
| J7 刷新 / 丢包 | 待确认提案可刷新，实际 Edge 测试在服务器已接受后丢弃响应，刷新恢复同一个 Run 及四项生效状态。重复提交同一集合严格返回同受理，改变选择用同键为 409，实际 Command 和 Run 均只有一条。 |
| J8 普通对话 | “HTTP 202 是什么意思？”通过原 Assistant 回答，发现模型调用数不变，浏览器没有出现确认面板。原正式更正按钮仍可见。 |

两个未确认冲突在测试中均不可提交，放弃审核后状态为 CANCELLED。旧确认 API 无法确认新提案。未获正式确认的候选最多用于人工讨论。Fixture 不衡量真实模型对引用、语义冲突、多语言或事实主张的理解。

## 浏览器证据

Headless Microsoft Edge 打开实际构建后的 Vue 工作台，经本机 HTTP 使用正式登录、Session、绑定、审核及确认入口。后台夹具仅让真实 TaskControl 应用正式输入，并用实际 ASSISTANT_V1 路径及 MockTransport 回答。未运行旧业务 Investigator 的真实模型结果。首跑截图断言错误地按用户回合计算消息序号。Session 序号也计入助手消息，已改为核对服务端返回的实际序号并保留原始失败。 [候选和来源](runs/browser/01-candidates.png) · [确认丢包后重载](runs/browser/02-applied-after-reload.png) · [正常提问](runs/browser/03-ordinary-chat.png) · [HTTP 验证记录](runs/browser/browser-results.json) · [首跑断言日志](browser-first.log)

## 成本和边界

- J1 只增加 **1 次**发现 SDK 请求。按实际 MockTransport 请求估算为 **1,593 输入 Token、81 输出 Token**，测试模型侧设置的输出上限为 640。一次本机 HTTP 审核耗时 **34.48 ms**，包括校验、SQLite、SDK 序列化和本地 mock。个别部署延迟与真实账单为 NOT_RUN。
- 第 24 轮普通 SDK 输入估算 8,717 Token，确认后续查估算 8,705 Token；分配的历史不同，这个差值不能单独代表新增条件块的成本。每个锚点最多一次持久预留，同一锚点重放读原尝试。应用状态继续来自 A-GREEN 的同一权威快照。
- 最终定向 pytest **99 通过、0 失败**。覆盖旧 TaskControl、S3、作用域撤回、检查点、P0-01/A-GREEN、旧提案与迁移。实际前端构建通过，1 条 Edge 旅程通过。早期 RED、时段重复误判、TS 兼容错误和浏览器断言错误保留在本目录各自日志。
- 付费 Provider 请求 0，外部业务写入 0。实际模型语义评估、真实业务结果和全量测试为 NOT_RUN。AR-04B 独立 HOLD / UNVERIFIED。

[最终 pytest](final-pytest.log) · [构建日志](build-verified.log) · [时段误判首跑原始日志](green-first.log.gz)

## 可复跑命令

在候选工作树使用已安装的仓库锁定依赖，输出目录使用新路径。浏览器启动器只监听回环。

```powershell
$py = 'D:/学习/agent新项目/.venv/Scripts/python.exe'
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:LANGSMITH_TRACING = 'false'
$env:LANGCHAIN_TRACING_V2 = 'false'
$env:OPSPILOT_MODEL_API_KEY = ''
$env:OPENAI_API_KEY = ''
$out = Join-Path $env:TEMP ('p002-bridge-' + [guid]::NewGuid().ToString('N'))
$env:OPSPILOT_BRIDGE_EVIDENCE = "$out/python"
& $py -u -X utf8 -m pytest -q -vv --tb=short -p no:cacheprovider -o faulthandler_timeout=55 --basetemp="$out/pytest" tests/test_p0_02_bridge.py tests/test_p0_02_task_conditions.py tests/test_p0_01_task_context.py tests/test_m4_01_dialogue_updates.py tests/test_m1_task_control.py tests/test_m1_dynamic_investigation.py tests/test_m2_01_facts.py tests/test_m2_03_handoff.py tests/test_m301_memory.py tests/test_m303_semantic_memory.py tests/test_m4_continuous_vs01.py tests/test_m4_03_hf_02.py::test_revoked_scope_blocks_s3_chat_context_chunks_and_redacts_bound_answer tests/test_ar04a_compression_cancel_hf_01.py::test_cancelled_compression_is_not_resent_on_recovery
npm --prefix frontend run build
# 终端 A，从工作树根目录启动
& $py -u -X utf8 docs/reviews/p0-02-bridge-01/browser_app.py --state "$out/state" --output "$out/browser" --port 8876
# 终端 B，从工作树根目录执行，输出应使用新目录
$env:OPSPILOT_BRIDGE_ORIGIN = 'http://127.0.0.1:8876'
$env:OPSPILOT_BRIDGE_BROWSER_OUTPUT = Join-Path $env:TEMP ('p002-edge-' + [guid]::NewGuid().ToString('N'))
node frontend/e2e/p0-02-bridge-browser.mjs
# 冻结原样 Base 对照从 Base 工作树执行
& $py -u -X utf8 docs/reviews/p0-02-red-design-01/repro.py journey --isolated-budget --output "$out/base"
```
