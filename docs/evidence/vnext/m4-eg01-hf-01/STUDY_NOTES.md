# Context Engineering 源码学习笔记

## 原理

Agent 上下文不是“把所有历史数据塞进 Prompt”。应将业务裁决所需的最小事实集合，与用户解释可用的当前观察集合分开：两者用途不同，但都必须通过可信来源、适用范围和时效校验。

## 本次源码对应

- `opspilot/domain/chat.py::_current_evidence()`：从 Gate 子集偏差中恢复完整的同 Run MCP Observation 候选，并调用现有 `current_s3_evidence()` 做当前性校验。
- `opspilot/domain/s3.py::current_s3_evidence()`：负责 TaskBinding、授权、版本、Event 对应关系、Run Observation 与 TTL 的可信校验。
- `opspilot/domain/chat.py::prepare_chat_attempt()`：把已核验事实装入 Chat 出站消息与 Evidence refs/ContextManifest。
- `opspilot/domain/s3.py::_gate_from_evidence()`：仍负责正式诊断裁决，本轮没有把 Chat 可解释事实提升为 Gate 或写权限。

## 取舍

不能复用 `s3_diagnoses.body_json` 的复制数据作为当前事实；它是冻结诊断，不是新的可信观察。也不能只输出 `checked_fact_ids`，因为 Gate 为判断不完整所需的事实集并不一定等于回答用户可说明的事实集。Chat 因此以本次 Diagnosis Run 的成功 MCP Observation 为候选，并重走 Domain 当前性检查。投递 HTTP 202 的原始响应里可能包含受理时 Receiver 状态快照，Chat 投影移除该嵌套字段，防止它被误读成当前 Receiver 查询。

## 学习链

原理 → 用户想知道投递是否被受理 → 同 Run HTTP/MCP 证据 → Context refs/Manifest → RED 证明 Gate 子集丢失有效事实 → GREEN 证明只向 Chat 补入当前合法来源、不改变 Gate/业务状态。
