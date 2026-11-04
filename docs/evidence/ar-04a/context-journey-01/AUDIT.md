# AR-04A 现有 Context / Memory 能力审计（实施前）

**基线：** `48234e5dabb6ed28ea816b8ebc438288409353b8`
**方法：** 源码阅读（三路只读子审计 + 主实施方抽样复核）。行号对应本候选基线；未运行真实 Provider。
**状态标注：** ① 已在普通聊天生效；② 已进入正式调查链路（Web 默认 `ASSISTANT_V1`）；③ 只有模块/测试、未接入真实模型输入；④ 已接入但未证明用户收益。

## 1. 能力矩阵

| 能力 | 实现位置 | 状态 | 说明 |
|---|---|---|---|
| Token 估算（tiktoken cl100k_base） | `domain/context_engineering.py:41-61` | ① ② | 聊天与调查共用 |
| 模型预算 profile + 环境变量 | `context_engineering.py:17-111` | ① ② | 默认 16384/12000；可用 `OPSPILOT_CONTEXT_INPUT_BUDGET_TOKENS` 等覆盖 |
| 块优先级分配 `allocate_context_blocks` | `context_engineering.py:114-172` | ① | 调查链路不调用 |
| 近期窗口 / 滚动摘要 / 混合策略 | `domain/chat.py:1336-1362`、常量 `chat.py:25-32` | ① | `OPSPILOT_CONTEXT_STRATEGY`，默认 HYBRID；仅经典聊天 Worker 执行压缩 |
| 压缩尝试持久化 + 来源再校验 | `chat.py:1703-1819`、`1822-1940` | ① | `context_compression_attempts` 先 RESERVED 再外发 |
| 摘要 DAG、版本、SUPERSEDED/INVALID | `chat.py:635-806`、`1876-1900` | ① | 依赖消息/答案/证据/记忆/Task 状态/Knowledge |
| 摘要 currentness 传播 | `chat.py:653-763` | ① | 摘要失效后不再被选中，引用它的答复也失效 |
| 任务输入锚点（原始输入 + 最近正式纠错） | `chat.py:1139-1160`、`1540-1551` | ① | required 块，逐字、不被摘要改写 |
| 聊天 manifest / 上下文回查 API | `chat.py:2037-2051`、`2391-2473`；`GET /api/runs/{id}/context` | ① | manifest 不含 prompt 正文；经典聊天原文不可回放 |
| 调查链路上下文度量 `investigator_context_budget` | `context_engineering.py:200-312` | ② | 只度量 + 超限抛异常；策略写死 `FAIL_CLOSED_NO_HISTORY_COMPRESSION`，汇总块 `NOT_APPLICABLE` |
| 调查链路真实输入持久化 | `assistant_calls.request_json`（`domain/assistant.py:18-24`、`assistant.py:593-596`）；S3 `s3_model_contexts` | ② | ASSISTANT_V1 的 authinc wire 可逐字回查 |
| 历史线索投影（prior answers / pre-binding 摘录） | `assistant.py:550-583`、`domain/assistant.py:411-420` | ② | 220 字符摘录、最多 6 条；只作线索 |
| 记忆检索/来源 currentness（Episodic/Semantic） | `domain/episodic_memory.py`、`semantic_memory.py` | ②（Investigator 图）/①（聊天） | 未证明收益（M3 证据 `UTILITY_NOT_PROVEN`） |
| `bounded_recent_window` | `context_engineering.py:175-197` | ③ | 无调用方 |
| `MAX_CHAT_MESSAGES`、`SUMMARY_PROMPT_VERSION` | `chat.py:26,32` | ③ | 定义未使用 |
| Knowledge/Skill 摘要依赖校验 | `chat.py:747-762` | ③ | 摘要依赖构造从不产生这两类依赖 |
| 真实模型长会话收益 | m3-02-03 实验 | ④ 未证明 | 只有 Recent Window 成功；Rolling/Hybrid `CHAT_ATTEMPTS_EXHAUSTED`（`docs/evidence/vnext/m3-02-03/REPORT.md:89`） |

## 2. 正式调查链路的真实缺口（源码 + 复现）

1. **调查输入预算与真实出站请求不一致。** 聊天侧 `_prepare_context` 按 12000 预算选历史，但 `ASSISTANT_V1` 的 wire 还包含固定 `SYSTEM`、`WORK_CONTEXT` payload 与工具 schema；`investigator_context_budget` 把这部分一起计入后直接抛 `INVESTIGATOR_CONTEXT_EXCEEDS_BUDGET`（`context_engineering.py:213-218`），Run 在首次模型调用前失败。**离线复现：** 7 轮协议咨询（含约 5000 token 粘贴材料）第 6 轮即失败，用户可见提示 `INVESTIGATOR_CONTEXT_EXCEEDS_BUDGET (13541 > 12000 tokens)`，Run 状态 `FAILED`。
2. **调查链路没有压缩。** 压缩循环只在 `web/worker.py:347-411` 的经典聊天路径；`ASSISTANT_V1` 一旦 `prepare_chat_attempt` 返回 `CHAT_CONTEXT_COMPRESSION_REQUIRED` 就直接结束（`assistant.py:803-805` 修改前），既不落答复也不自动重试。
3. **摘要被静默丢弃。** `_run_assistant` 只把 `prepared["messages"]` 中 user/assistant 转成初始消息，`HISTORICAL SESSION SUMMARY`（system 角色）被丢弃（修改前 `assistant.py:831-835`）。
4. **Task 作用域限制（既有安全设计）。** `context_summaries.task_id` 精确匹配；Task-less 摘要不得进入 Task Run（`chat.py:784-788`）。因此“绑定前的会话摘要”不会自动进入绑定后的调查轮——本轮保留该隔离，并在 Gold 中固定为断言。

## 3. 结论

现有 Context 能力在**普通聊天**上完整，在**正式调查链路**上只复用了来源选择与预算度量，没有复用到压缩、摘要与锚点预算。AR-04A 的最小切片因此是：把既有压缩/摘要机制接入 `ASSISTANT_V1`，并让选择预算与真实出站预算一致；不新建 Context 框架，不改变 Task/授权/写入边界。
