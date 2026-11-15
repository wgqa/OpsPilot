# V2 Runner 设计与版本边界

## 目标

原 `run_recheck.py` 复用既有 ABC Runner，但固定的 `chat.py` Blob 属于早期版本。V2 不删除版本校验，也不自动接受新 Blob；它把新 Base 和当前两个生产入口显式冻结在本任务 Runner 中，再调用已有通用 Assistant/Grant/Domain 路径。

## 复用关系

```text
V2 freeze adapter
  ├─ pins Base SHA, chat.py / assistant.py Git blobs
  ├─ pins 29-row history, full questions, Gold/Rubric source file,
  │  previous real request trace/results, tool schema, prompt prefix, model/budgets
  ├─ adapts accepted ABC Runner's planned slots to Q02-A/Q02-B/Q06-B
  ├─ reuses Setup-HF01 isolated Domain seed and Runtime Grant binding
  └─ calls existing Assistant create_assistant_model + run_assistant
       ├─ HTTPX MockTransport only
       ├─ current production Context Builder and summary validation
       ├─ Domain summary persistence twice per case
       ├─ final answer request with tool_choice=none
       └─ Answer Manifest and per-case source capture
```

## 版本与输入冻结

- Base: `d8a526daa9c811814a5e2463b34eb37037ae1a8e`.
- `opspilot/domain/chat.py` Blob: `d10f495cadc4c2006504ecd87e5c02947f87e80b`.
- `opspilot/assistant.py` Blob: `4fa1aaa7059cf6478fce4c262b8c1876df9a7dcb`.
- Questions (包括完整问题、Gold、Rubric)、29 条 History、Phase A Results/Model Trace、前次真实 Trace/Results 与 preliminary scoring 都以 SHA-256 pin 固定；清单在 [`FROZEN_INPUTS.json`](FROZEN_INPUTS.json)。
- 每次出站前再次核对固定清单和生产 Blob。当前生产源码、旧实验目录与保护证据相对 Base 有任何 Git Diff 时拒绝发送。
- Answer 参数继续检查模型、thinking、temperature、输出上限、`tool_choice=none`、工具 Schema 与 Prompt 前缀；Gold/Rubric 由现有传输层检查不进入请求。
- 摘要工具为空；不创建或调用外部 MCP。测试请求只有 MockTransport，CLI 审计钩子拒绝外部网络。

## 冻结真实摘要的 Mock 用法

首轮摘要正文从上一轮真实 `LIVE_REQUESTS.jsonl.gz` 的 `Q02-A:SUMMARY:1` 原响应中按固定 response ID `c3435ff4-fc27-4ffb-b053-bbfcabc600e0` 读取。正文 SHA-256 为 `815ce6e46122561c83ab227c6fbe1bb3322e99663d144fd5ccac84b483393a83`。V2 只把这段冻结正文作为 MockTransport 回复，随后让当前生产 Assistant 调用 Domain 完整校验与持久化；本轮不会重放 HTTP 请求到 Provider，也不会伪称原错误码已验证。

Q02-B 与 Q06-B 首轮同样使用各自历史 Trace 中的冻结模型回复。第二轮摘要返回带明确 `SYNTHETIC_DETERMINISTIC_PARENT_PROJECTION` 标记的确定性父摘要投影；最终回答标记 `SYNTHETIC_MOCK_ANSWER`。所有 Mock 来源写入 `MOCK_REPLY_PROVENANCE.jsonl.gz`，Answer 语义评测记为 `NOT_RUN`。

## 预算和隔离

- 每例独立临时 Domain、Checkpoint、Session、Assistant Run 与隔离 Runtime Grant。
- 每例两个摘要请求和一个回答请求，三个 Case 共 6 + 3 个槽位，共用一个全局账本。模拟 usage/成本仅用于账本路径测试；本轮实际费用固定 USD 0。
- Grant 输入上限 12,000 Token，输出上限 512 Token。最终生成结果记录的有效 Context 预算为 Q02-A 8,185、Q02-B 8,188、Q06-B 8,184 Token。
- Provider request 只经 MockTransport；用例注入摘要预算超限、来源撤销、UNKNOWN 与 Domain 持久失败。
- V2 没有 `live` CLI 选项；`reject_live_dispatch()` 对任意参数均 fail closed。旧授权字串不构成授权。

## 相比旧 Runner

| 项目 | 旧 Runner | V2 |
|---|---|---|
| Base / `chat.py` pin | 旧 HF-02 Base 与旧 compactor Blob | 当前 Base `d8a526…` 与当前 `chat.py`、`assistant.py` Blob |
| 输入与工具检查 | 固定旧 matrix 的历史问题、Gold、Schema 与 Prompt | 保留同类一致性验证并用当前显式 pins；不删除或跳过 |
| Cases | 前次矩阵/旧 recheck 配置 | 新冻结三例 Q02-A、Q02-B、Q06-B |
| 完整 Runtime | 既有 Assistant + Grant + Domain | 复用原调用路径，不复制业务 Runtime |
| Provider 入口 | 旧脚本曾有受授权的 LIVE 分支 | V2 仅 MOCK/PREFLIGHT，无 LIVE dispatch 实现 |
| 旧证据 | 原文件和结果 | 未覆盖、未改写；新证据单独存放 |

## 解释限制

Mock 通过只证明当前源码可以把固定上下文经完整应用路径压缩、保存并交到最终 Prompt，及失败门禁能停发。它不证明真实模型仍会生成相同摘要、回答正确、保持事实的自然语言语义，或 API Key 可通过 Provider 认证。`PREFLIGHT.json` 的 `READY_FOR_AUTHORIZATION` 仅表示具备经审阅的技术准备条件，不是付费授权或 Live 评测通过。
