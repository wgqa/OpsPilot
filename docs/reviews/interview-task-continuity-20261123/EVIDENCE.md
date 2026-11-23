# 审计证据与复现

## 版本和方法

报告中的相对源码链接均对应审计分支的父提交 `60eee87bfe3cca522011316cb4cd2c0064ad291b`。远端 Git 传输曾 connection reset，改用 GitHub commit 接口核实 main 与当前 AR‑03 分支的实时 SHA，再从相同 SHA 的本地 Git 对象读取。审计对原工作区的既存未跟踪文件不作版本判断。此次源码/用例/历史 Trace 由本轮独立审阅；历史报告中的 Provider 调用非本轮复跑。

| 层次 | 本次实际检查 | 证据效力 |
|---|---|---|
| 源码与合同 | main Web 两个消息入口、App.vue、SQLite DDL、分类/确认、两个 Context 消费方、记忆召回/失效、Assistant 与 Investigator、D3 与 Worker | 能证明程序能到哪一步；不能单独证明真实模型的选择。 |
| 已保存证据 | AR‑04A/B 的 Gold、RESULTS、TRACE、原始定向 pytest 输出和遗留缺口；另读 AR‑06 E09-D、E10-H、E11-D 与 AR‑04 修复的候选报告 | AR‑04A 历史 Fixture Trace 的绑定轮估算 11,179 / 12,000，数值不是付费账单。J6 正式纠错不在该长旅程覆盖范围。E11-D 只达离线 readiness；其“有诊断草稿但尚未交接”可复用为合法正例。 |
| 本人实跑 | 下列两个探针、23 个完成的 pytest 用例，另有一个未完成测试组。覆盖本地 TestClient/Worker、stdio MCP、临时 SQLite/Checkpoint、回环 HTTP 和 OS 子进程故障。 | 本机 Demo 范围；只读聊天与本地事务夹具可分别核查。没有真实付费 Provider、浏览器 E2E、外部业务写入、全量 pytest 或独立线上验收。 |

### 探针 A：两个合法 Task 的消息进入同一个待发 Context

在 main 工作树根目录用仓库虚拟环境运行以下 Python。使用临时 DB 与受信 Domain API，没有启动模型或业务系统。选择 B 时使用了正确的 B ID，故排除了“调用者传错 ID”这一解释。

```python
from pathlib import Path
from tempfile import TemporaryDirectory

from opspilot.domain.chat import prepare_chat_attempt
from opspilot.domain.database import reset_fixture
from opspilot.domain.task_control import (
    admit_task_message, claim_task_run, create_session, create_task_with_initial_run,
    register_worker_owner, trusted_identity,
)

with TemporaryDirectory() as directory:
    db = Path(directory) / "demo.sqlite"
    reset_fixture(db, "S1_POS")
    owner = trusted_identity(db, "support-a")
    session = create_session(db, owner)["session_id"]
    register_worker_owner(db, "audit-worker", 101)

    def create(key, text):
        return create_task_with_initial_run(
            db, owner, session_id=session, service_id="orders-demo",
            integration_id="integration-a", ticket_id="INC-A-001",
            initial_message=text, idempotency_key=key,
        )["task_id"]

    a = create("audit-task-a", "Audit A only: receiver condition ALPHA-ONLY")
    b = create("audit-task-b", "Audit B only: protocol BETA-ONLY")
    assert a != b
    accepted = admit_task_message(
        db, owner, session_id=session, task_id=b, input_kind="CHAT_READONLY",
        body="Continue B", idempotency_key="audit-follow-b",
    )
    claim_task_run(db, owner, accepted["run_id"])
    prepared = prepare_chat_attempt(db, accepted["run_id"], "audit-worker", "audit-fixture")
    print([m["content"] for m in prepared["messages"] if m["role"] == "user"])
```

实测消息中的三段原文依次为：

```text
Audit A only: receiver condition ALPHA-ONLY
ORIGINAL_TASK_INPUT (UNTRUSTED USER INPUT): Audit B only: protocol BETA-ONLY
Continue B
```

[chat.py 第 1131 行起](../../../opspilot/domain/chat.py)按 session、tenant、role、input_kind、sequence 取普通用户消息；后续独立添加 B 的任务锚点。此处验证了同一用户同会话的归属串入。任务 A 的可信 Evidence、其他租户的数据泄露、模型已遵从 A 均不在这个观察里。另一个独立风险是 [App.vue](../../../frontend/src/App.vue) 第 524/542/756 行的默认焦点沿用；它属于源码核验，未亲跑双任务浏览器用例。

### 探针 B：结构正确的四条条件在压缩时剩三条

```python
from opspilot.domain.chat import _compact_summary_document

items = [
    "Only event E7", "Use protocol v2",
    "Time window 10:00-11:00", "Report receiver status separately",
]
doc = {
    "initial_goal": {"text": "Investigate callback", "source_sequences": [1]},
    "constraints": [
        {"text": text, "source_sequences": [seq]} for seq, text in enumerate(items, 2)
    ],
}
result = _compact_summary_document(doc)
print([(item["source_sequences"], item["text"]) for item in result["constraints"]])
```

| 实际 checkout | 输入来源序号 | 实际保留 | 实际缺失 |
|---|---|---|---|
| main `60eee87` | 2、3、4、5 | 3、4、5 | 2，仅事件 E7 |
| AR‑04 候选 `b7c4445` | 同一组 | 2、4、5 | 3，使用协议 v2 |

两次都是本人调用当前 checkout 的函数，零网络调用。候选改变了保留项，对这四条同时有效条件仍只能留下三条。这个结果支持从已接受的任务输入重建有效条件，不能由此推断每次对话都会丢同一条；原消息、正式锚点等其他路径仍可能提供补偿。[main 压缩实现](../../../opspilot/domain/chat.py) · [候选实现](https://github.com/wgqa/OpsPilot/blob/b7c444586c0ee782109e3d5931034abb27a3d597/opspilot/domain/chat.py)

## 定向复跑与未完成项

Python 3.14.0，pytest 9.1.1，锁文件 Blob `de16e1113ac250511cee8d7b6a079b88b1ca4f99`。复用现有 venv，本次未重装也未做干净环境一致性签字。以下命令在基线工作树运行。每组使用独立的 TEMP basetemp，模型 key 在子进程中清空。重跑时为每次 pytest 另行生成全新 basetemp。

```powershell
$py = '../../.venv/Scripts/python.exe'
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:OPSPILOT_MODEL_API_KEY = ''
$env:OPENAI_API_KEY = ''
function Invoke-AuditGroup([string[]] $cases) {
    $tmp = Join-Path $env:TEMP ('opspilot-audit-' + [guid]::NewGuid().ToString('N'))
    & $py -u -X utf8 -m pytest -vv -s -p no:cacheprovider -o faulthandler_timeout=70 --basetemp=$tmp @cases
}
Invoke-AuditGroup @(
    'tests/test_ar04a_context_journey_01.py',
    'tests/test_m302_context.py::test_long_chat_keeps_original_task_and_latest_formal_correction_as_untrusted_input'
)
Invoke-AuditGroup @(
    'tests/test_m1_worker_recovery.py',
    'tests/test_m1_task_control.py::test_n1_10_correction_invalidates_old_run_and_new_run_binds_fresh_plan',
    'tests/test_d4_recovery.py::test_d4_terminal_checkpoint_without_domain_receipt_blocks_unknown_outcome',
    'tests/test_d4_recovery.py::test_d4_os_process_crash_and_lost_action_response'
)
Invoke-AuditGroup @('tests/test_m303_semantic_memory.py')
Invoke-AuditGroup @('tests/test_ar04b_memory_journey_01.py')
```

| 组 | 本次结果 | 可独立检查的观察 |
|---|---|---|
| 上下文 | **5/5**，40.17s | 压缩后长会话、Task-less 摘要隔离、无效摘要排除、超预算终止，以及原始任务/最近纠错锚点。[输出](context.txt) |
| Worker、TaskControl、D4 | **12/12**，9.26s | 含真实退出的子进程；终态 checkpoint 缺收据得到 ACTION_OUTCOME_UNKNOWN，Ledger 和工单均 0。DELIVER 已提交后丢响应，最终 delivery ledger、delivery 和 ticket entry 各 1。正式纠错后旧提交见 TASK_INPUT_PENDING 或 TASK_CONTROL_STALE，新的受批动作可成功。[含业务计数的输出](recovery.txt) |
| Semantic Memory | **6/6**，3.00s | 覆盖候选/确认授权、跨任务引用与撤销、修订版本、过期及迁移。[输出](semantic.txt) |
| AR‑04B 记忆旅程 | 收集 **9** 项，首项退出 TestClient 时未返回，**0 项取得 pytest 终态**。两次尝试均人工停止，未计入上述 23 项。 | 首次合跑先打印 4 个完成标记，未获得整组 summary；拆组后 faulthandler 在 70 秒时记录 `wait_shutdown → TestClient.__exit__ → test_ar04b_memory_journey_01.py:194`。不能判断退出后断言是否通过，也不能仅凭这段同步栈确定 Worker 根因。[未完成的定向输出](memory.txt) |

历史 AR‑04B 最终定向输出为 9/9；历史 AR‑04A 回归曾以 7/8 暴露对整个记录搜索 ID 的断言问题，后续仅核对实际 messages 得到 8/8。失效 ID 可在排除清单出现，有效性要查真正发送的正文与提交结果。本轮 AR‑04B 停滞另外记账。若拟将其作为后续基线，先复现并定位 shutdown，或取得完整的独立重跑结果，再签收这一组。历史 D6 E10 PARTIAL、AR‑04A J6 未覆盖、AR‑04B 大 Memory G9、候选 E09-D 第九轮失败均继续保留。[历史失败与后续记录](../../evidence/ar-04b/memory-journey-01/FAILURES.md)

**证据结论。** 已复现两项具体缺口并核实若干现有模块的业务接线；八个新案例的整套产品表现与改造收益尚未测量。本地测试的 SQLite 和回环 Demo 产生了预期的夹具写入。付费 Provider 与外部业务写入均为 0。
