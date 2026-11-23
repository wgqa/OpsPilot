# P0-01 修复前证据

源码基线 `60eee87bfe3cca522011316cb4cd2c0064ad291b`，运行树父提交 `e8f897bf1b293c2249fe8f2617bbac7acf3aa052`。Python 3.14.0，pytest 9.1.1。复用仓库现有虚拟环境，锁文件 Blob `de16e1113ac250511cee8d7b6a079b88b1ca4f99`。所有输入与凭据均为测试标记，证据只保存 JSON 正文、合成 ID 和计数。

## RED 断言

| 检查 | Builder 探针 | 正式 Assistant SDK 探针 |
|---|---|---|
| 调用路径 | Domain 受理、claim、`prepare_chat_attempt` | HTTP 登录、Session、`/assistant/order`、`/assistant/messages`、Worker 的 `_dispatch_run`、ChatOpenAI/OpenAI SDK、HTTPX MockTransport |
| 目标 | B | 发送、Run、来源消息均为 B，同 Session 中 A 与 B 绑定同一个测试订单 |
| A 原文 | **存在**。选入行的 `task_id` 为 A | **存在**。SDK JSON 有普通 `user` 消息 `Audit A only: receiver condition ALPHA-ONLY` |
| 正对照 | 有标注的 B 原始任务和 `Continue B` | 另保留未绑定的 `Session protocol reference: HTTP 202 acknowledges receipt.` |
| 终态和副作用 | 断言预期失败 | 隔离断言预期失败。B Run 为 SUCCEEDED，1 次 MockTransport 派发，无真实 Provider 请求。Approval、ActionIntent、Ledger 和 S2/S3 handoff receipt 计数均为 0→0。S3 初态造数走本机回环。 |

[RED pytest 输出](red-pytest.txt) · [Builder 消息及所选来源](builder-context.json) · [MockTransport JSON 与账本](mock-sdk-wire.json)

`local_mock_requests[0].messages` 是 SDK 序列化后接到的请求正文。`ledger[0].request` 是程序在 SDK 调用前记录的内容，格式不同，双方可在消息正文和 ID 上交叉核对。此次仅证明文本到达 MockTransport 和正式 Run 能收口；Mock 回答是固定字符串。浏览器与真实模型推断均未运行。

## 重跑命令

从设计工作树根目录运行。命令将输出置于临时目录，以保留已保存的 RED。两项 pytest 预期以 exit 1 结束，且应在具体隔离断言处失败。

```powershell
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:LANGSMITH_TRACING = 'false'
$env:LANGCHAIN_TRACING_V2 = 'false'
$env:OPSPILOT_CONTEXT_STRATEGY = 'HYBRID'
$env:P0_01_OUTPUT = Join-Path $env:TEMP ('opspilot-p0-01-output-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $env:P0_01_OUTPUT | Out-Null
$p0Temp = Join-Path $env:TEMP ('opspilot-p0-01-' + [guid]::NewGuid().ToString('N'))
& '../../.venv/Scripts/python.exe' -u -X utf8 -m pytest -q -vv --tb=short -p no:cacheprovider -o faulthandler_timeout=60 --basetemp="$p0Temp" 'docs/reviews/p0-01-task-context-20261123/repro_p0_01.py' 2>&1 |
    Tee-Object -FilePath "$env:P0_01_OUTPUT/red-pytest.txt"
$LASTEXITCODE
```

同一脚本中显式注入两份 MockTransport，异步返回固定 JSON，同步发送被拒。应用通过 TestClient 真实受理，Worker 在测试中只派发目标 B Run，不启动常驻轮询与 TestClient 后台 Worker。第一次探针不启动模型。

## 主线正例基线

另跑 AR‑04A 四项旅程回归、M1 原子/幂等受理和 AR‑02 无任务受理，得到 **6/6，38.94 秒**。这是修复前基线，包含初始材料保留和无 Task 摘要不跨域的参照。测试在独立 TEMP basetemp 下运行，Provider key 置空。 [基线回归日志](baseline-regression.txt)

```powershell
$env:OPSPILOT_MODEL_API_KEY = ''
$env:OPENAI_API_KEY = ''
$p0Temp = Join-Path $env:TEMP ('opspilot-p0-01-baseline-' + [guid]::NewGuid().ToString('N'))
& '../../.venv/Scripts/python.exe' -u -X utf8 -m pytest -q -vv -p no:cacheprovider -o faulthandler_timeout=70 --basetemp="$p0Temp" tests/test_ar04a_context_journey_01.py tests/test_m1_task_control.py::test_n1_01_02_admission_is_atomic_and_idempotent tests/test_ar02_assistant.py::test_no_task_professional_message_is_idempotent_without_fake_binding
```

## AR‑04B 独立记录

上一轮审计在同一源码版本独立尝试 AR‑04B。pytest 收集 9 项，首项退出 TestClient 时等待 shutdown，70 秒线程栈进入 `starlette.testclient.wait_shutdown`；终止时没有任何一项取得 pytest 终态。当前 P0‑01 的单次 Worker 探针是不同用例，不提供 AR‑04B 通过证明。本轮未重新执行 AR‑04B，状态保留 **HOLD / UNVERIFIED**。仓库实施方历史 9/9 仍以原报告为准，并与该次独立停滞分别呈现。 [上一轮采集的线程栈](../interview-task-continuity-20261123/memory.txt) · [AR‑04B 历史输出](../../evidence/ar-04b/memory-journey-01/runs/green-ar04b-final-03.log)
