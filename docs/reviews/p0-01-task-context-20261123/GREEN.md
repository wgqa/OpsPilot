# OpsPilot P0-01 实施候选

2026-11-23 · **ACCEPTANCE_CANDIDATE** · 待主 Agent 独立验收

首个真实受理场景是同一 Session 里 A 和 B 绑定同一演示订单，用户明确跟进 B。SDK 序列化后，B 保留其原文、当前追问和服务端可证实归属的公共会话信息。其他 Task 的原始条件、污染答复与摘要被排除。对比使用正式 API、Worker、ChatOpenAI/OpenAI SDK 和本地 MockTransport。[修复前输入](red-replay/mock-sdk-wire.json) · [修复后输入](verified-focused/mock-sdk-wire.json)

## 基线和交付边界

| 核验项 | 本轮记录 |
|---|---|
| Repo / Branch | `wgqa/OpsPilot` · `codex/p0-01-task-context-green` |
| Base | GitHub 实时核实 `main@60eee87bfe3cca522011316cb4cd2c0064ad291b` |
| 设计 / 原 RED | GitHub 实时核实 `codex/p0-01-task-context-plan@a5e15d0dcb7d03287eda3c38123a44af703ba910`，是候选实现的直接父提交。原始失败未覆盖。 |
| 已测试的源码 HEAD | `4a91e2a92b3a15b37d08848447e5046b250a443d`。此后的交付提交仅含候选报告和离线证据；精确交付 HEAD 由远程分支核验。 |
| Diff / 合并 | `60eee87..HEAD` 含上轮审计、设计、隔离实现与本轮证据；`a5e15d0..4a91e2a` 是实现和新测试差异，无 merge commit。 |
| 实读治理 | [PROJECT_NORTH_STAR](../../../PROJECT_NORTH_STAR.md) Blob `e36f2f75509738551ac6d4a2de5b4f9cf44a7991`、[AGENTS](../../../AGENTS.md) `f174a6ab7f23f9e6d8b3ef98d455b99a75193143`、[opspilot-slice-review](../../../.agents/skills/opspilot-slice-review/SKILL.md) `d405c8d413d633824b279202cc1503dab4cf0b03`。本轮用户裁决 `AUTHORIZED_FOR_ISOLATED_IMPLEMENTATION`。 |
| 合同 | AR‑04A/B Gold 分别为 `6c8ba3867e2dad983abe6f1b85bd559fc28e36ac` / `f5056cbb3344208e2e34671ea08a50963d3aea3d`，连同既有 API、恢复、来源链和 M2‑01/M2‑02 遗留门禁按设计报告核对。历史验收语境为 AR‑04A ACCEPT_WITH_LIMITS，AR‑04B 独立验收缺口继续保留。 [已核对的合同与适用范围](README.md) |
| 环境 | Windows，Python 3.14.0，pytest 9.1.1，复用已有虚拟环境。依赖锁 Blob `de16e1113ac250511cee8d7b6a079b88b1ca4f99`。 |

## 实现与观察

| 路径 | 实现及实测 |
|---|---|
| 原始消息 | 原始历史按当前 Run 的 tenant/session/task 与受理 Command、来源 Run 精确关联，在排序和限制之前过滤。当前来源还核对 command、sequence 和正文 digest。仅有 `task_id=NULL` 而无接受记录和对应 Run 的历史材料排除。原始任务和最新正式纠错沿现有锚点机制进入上下文。 [Context Builder](../../../opspilot/domain/chat.py) |
| 旧回答、摘要 | 回答和它的持久 Run 归属一致，普通 MESSAGE 依赖也重新核对受理来源。Task B 摘要可引用已经证实为公共的原始用户消息；任务级摘要及助手回答的归属保持精确匹配。旧 B 摘要即使自身归属 B、正文 digest 正确，只要依赖 A，便不能当作当前摘要。 [派生来源验证](../../../opspilot/domain/chat.py) |
| 会话公共答复 | `WORK_CONTEXT` 保留经来源复核的公共答复摘录。旧 B 答复所引用的公共摘录失效时，依赖它的回答不继续作为合法来源。实际 SDK 输入证明 B 最新纠错、合法 B 历史及公共原话仍存在，来源失效后仅保留仍有效的公共原话。 [Assistant 装配](../../../opspilot/assistant.py) · [来源复核](../../../opspilot/domain/assistant.py) · [两次 SDK 输入](verified-focused/sdk-correction-and-lineage.json) |
| checkpoint | 采用历史 checkpoint 前，核对其中的历史消息前缀与重新验证的上下文；后续本 Run 的模型和工具消息可以保留。实际 SQLite checkpoint 正反例中，干净恢复派发 1 次并 SUCCEEDED，污染恢复以 `ASSISTANT_CHAT_HISTORY_CHANGED` 结束且派发 0 次，有明确的程序提示。 [合法恢复](verified-focused/checkpoint-clean.json) · [污染恢复](verified-focused/checkpoint-polluted.json) |
| 权限与副作用 | 未调整 Task 选择或绑定、审批、Intent、Ledger、MCP 工具策略和压缩算法。RED 与 GREEN SDK 探针的 Approval、Intent、Ledger、S2/S3 回执计数均为 0→0。夹具使用本机回环及临时 SQLite，真实付费 Provider 和外部业务写入为零。 |

## 可重跑命令

从候选工作树执行。每组使用独立临时数据库和输出路径。历史原件位于设计提交；本轮复跑使用新文件夹保存失败。

```powershell
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:LANGSMITH_TRACING = 'false'
$env:LANGCHAIN_TRACING_V2 = 'false'
$env:OPSPILOT_MODEL_API_KEY = ''
$env:OPENAI_API_KEY = ''
$env:OPSPILOT_CONTEXT_STRATEGY = 'HYBRID'
function Invoke-P001([string[]] $Cases) {
    $env:P0_01_OUTPUT = Join-Path $env:TEMP ('p001-artifacts-' + [guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Path $env:P0_01_OUTPUT | Out-Null
    $baseTemp = Join-Path $env:TEMP ('p001-pytest-' + [guid]::NewGuid().ToString('N'))
    & '../../.venv/Scripts/python.exe' -u -X utf8 -m pytest -q -vv --tb=short -p no:cacheprovider -o faulthandler_timeout=70 --basetemp="$baseTemp" @Cases
}
# RED 在设计提交 a5e15d0 单独运行，期望 exit 1。
# Invoke-P001 @('docs/reviews/p0-01-task-context-20261123/repro_p0_01.py')
Invoke-P001 @('docs/reviews/p0-01-task-context-20261123/repro_p0_01.py', 'tests/test_p0_01_task_context.py')
Invoke-P001 @('tests/test_m1_chat.py', 'tests/test_m1_task_control.py', 'tests/test_ar02_assistant.py',
    'tests/test_m302_context.py', 'tests/test_m303_semantic_memory.py',
    'tests/test_m4_03_hf_02.py::test_revoked_scope_blocks_s3_chat_context_chunks_and_redacts_bound_answer')
Invoke-P001 @('tests/test_ar04a_context_journey_01.py', 'tests/test_ar02_context_continuity_01.py',
    'tests/test_ar04a_compression_cancel_hf_01.py::test_cancelled_compression_is_not_resent_on_recovery', '-x')
```

| 同一源码 HEAD 上的验证组 | 结果 |
|---|---:|
| P0‑01 原探针及新增历史、纠错、摘要、恢复用例 | 7/7，17.83 秒。[原始输出](verified-focused/pytest.txt) |
| M1、AR‑02、M3 与 S3 撤权后历史正文隐藏 | 41/41，28.96 秒。[原始输出](verified-safety/pytest.txt) |
| AR‑04A 长会话、AR‑02 连续旅程、压缩中断不盲重发 | 7/7，65.34 秒。[原始输出](verified-journeys/pytest.txt) |
| **合计** | **55/55**。原设计分支 RED 2/2 预期失败另计。 |

## 非通过记录和停止线

- RED 在原 Builder 和 SDK 隔离断言各失败一次。修复前的 SDK 请求包含 A 的原文，B Run 仍 SUCCEEDED。 [本轮 RED 复跑](red-replay/pytest.txt)
- 首版恢复测试通过在 LangGraph 节点内抛出 CancelledError 模拟中断，框架将其转换为 NodeCancelledError 并收口，导致测试的两项中断断言失败。最终用外层任务取消模拟中断，读取真实 SQLite checkpoint，成对验证后续派发。 [首版失败](focused-initial/pytest.txt)
- 中间一次长会话回归首项失败，下一项在 TestClient 退出时停滞。另一次诊断记录显示 MCP 退出期间伴随 SQLite heartbeat 提交锁错误。两次运行的线程栈已保存，验证计数使用最终源码的完整定向复跑。 [中间停滞](regression-a/pytest.txt) · [诊断输出](regression-a/diagnostic.txt)
- 首次补丁因工作树路径拼接错误短暂落在 AR‑03 工作树的两个文件中。已用原补丁逆转，并复核 AR‑03 工作树无跟踪文件差异。所有提交与验证产物位于 P0‑01 候选工作树。
- **AR‑04B 独立 HOLD / UNVERIFIED**。上一轮首例退出 TestClient 停滞的线程栈继续保留，本轮不复签，也不计入通过。真实付费模型、浏览器、全量 pytest 为 NOT_RUN。 [原始停滞记录](../interview-task-continuity-20261123/memory.txt)
- 来源关系随记录的现行归属校验。数据库内缺失原受理关联的旧内容没有公共资格。checkpoint 的合法历史若已变动并无法与当前重建一致，当前只读 Run 会停止，允许用户按原 Task 发起新问题。该恢复条件有合法原样续跑的正例。用户主动粘贴到 B 或明确提交为公共会话内容的文本仍按其新提交的来源处理。

## 实施方六问

1. 用户可在同一 Session 专注于 B，带上 B 的条件、纠错与有效公共信息。
2. 模型仍可选择合法查询、解释、澄清或结束。此切片的结果来自上下文范围修正。
3. 在同一个演示订单上，用不同已受理的 Task ID 可以得到各自的候选历史。已授权的当前 Receiver 观察仍由模型用于选择后续调查。
4. 普通历史、派生答复、摘要与恢复均有归属约束，分别用合法保留和污染拒绝验证。
5. 复用 Command、Run、来源引用和 checkpoint，无需迁表。仅为出站历史增加来源检查。
6. 可交付证据限于离线正式调用链与 MockTransport 输入。候选提交后停止，交主 Agent 独立验收。
