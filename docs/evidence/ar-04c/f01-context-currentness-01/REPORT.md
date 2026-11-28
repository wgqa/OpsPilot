# F01 Context 当前性修复候选

**状态：`ACCEPTANCE_CANDIDATE`。** 用户已接受原 LIVE 为 `ACCEPT_WITH_LIMITS / PARTIAL / G7 ON FAIL`。本轮完成限定的离线表达修复与回归，真实模型效果仍待一轮新的小额复验。

## 用户行为与实现

同 Task 的后续回答现在能收到明确的本轮执行记录：成功调用了哪些工具、哪些 Observation 确实由当前 Run 取得。没有新的业务观察时，Context 直接说明“本轮尚未重新查询”，同时保留合法的历史快照用于解释。

- `Loop.context()` 从现有成功 MCP 记录提取当前 Run 工具和 Observation 引用；它在原有 `sources_current()` 校验之后读取，不新增事实、权限或存储。
- `domain.assistant.source_context_for_model()` 将历史有效性表达为“历史快照可引用”，保留来源 Run、ID、Digest、时间、版本和摘要；排除历史的原因仍可见，失效正文仍不进入。
- 只有这个展示投影进入实际 `WORK_CONTEXT`，初始化 Context 预留也使用同一投影。原始来源审计结构，包括内部 `current_source_valid`，保留在 `assistant_calls.request_json.source_refs` 中。
- 没有增加最终答案验证器、关键词过滤、强制每轮查工具、Memory 排序/压缩算法或新的 Runtime。模型仍可直接解释、继续查询、澄清或停止。

生产 Diff 仅两个 Python 文件，60 行新增、3 行替换；预算、工具、Domain Gate、TaskControl 和业务写入逻辑未改。

## 证据

| 验证 | 实际结果 |
|---|---|
| 冻结真实 F01 的结构性 RED | 4/4 失败，原始日志保留 |
| 零工具合理解释 | 成功交付“历史快照、本轮未重查、当前未知”；后续 Run MCP=0 |
| 同 Event 合法重查 | QUEUED 与 PROCESSED 均取得新 Run 的 Delivery/Receiver Observation，回答与真实工具结果对应 |
| 过期/版本失效 | 旧快照正文被排除，排除原因保留；新的合法查询仍成功 |
| 最终限定回归 | 11/11，43.41s，exit 0；含 Context 连续性、12K 超额、失效摘要、Memory 撤销与同 Task 重查 |
| F01 原输入静态投影 | Context 估算 8,620→8,483 tokens；系统文本 16,319→15,887 字符；原生历史消息和 Memory Guidance 保留 |
| 实际收费 Provider / 外部业务写入 | 0 / 0 |

新增测试使用既有可信 Task/Session 与正式 ASSISTANT_V1、真实本地 MCP 和 SQLite。相关既有回归还覆盖正式 API/Worker 路径。替身决定工具仅用于接线验证，不计为模型自主性或真实效果。

测试源码、原始 RED/初次失败/最终 GREEN、实际持久的出站消息和工具 Observation 均保存。`F01_PROJECTED_MESSAGES.json` 是冻结真实输入的静态变换，明确标识没有 Provider 调用；`OFFLINE_TRACE.jsonl` 才是本轮定向测试真正经过 Assistant 的持久请求与结果。

原始 `.log` 留在本地；公开 `.txt` 只规范化编码与换行，原始摘要和对应关系见 `LOG_INDEX.json`。最终限定回归的实际命令如下（在本工作树执行）：

```powershell
& 'D:/学习/agent新项目/.venv/Scripts/python.exe' -m pytest -vv -s -o faulthandler_timeout=60 --tb=short --basetemp=.pytest-tmp-f01-regression `
  tests/test_ar04c_f01_context_currentness.py `
  tests/test_ar02_context_continuity_01.py `
  tests/test_ar04a_context_journey_01.py::test_ar04a_invalidated_summary_is_not_sent_to_the_model `
  tests/test_ar04a_context_journey_01.py::test_ar04a_over_budget_still_fails_closed_without_provider_call `
  tests/test_ar04b_memory_journey_01.py::test_ar04b_confirmed_cross_task_memory_is_present_on_formal_assistant_wire `
  tests/test_ar04b_memory_journey_01.py::test_ar04b_same_task_followup_keeps_memory_non_authoritative_and_rechecks_current_fact `
  tests/test_ar04b_memory_journey_01.py::test_ar04b_revocation_before_provider_boundary_blocks_stale_memory_and_keeps_valid_path
```

学习映射：Context Engineering 要分别表达“来源仍有引用资格”和“事实何时取得”。这次在 `Loop.context()` 装配当前执行记录，在 `source_context_for_model()` 呈现历史语义；冻结 F01 是原始失败证据，离线接线已证明，真实回答改进未证明。面试可表述为：“有效的历史来源不等于刚查询的当前事实；审计保留完整来源，模型输入明确时间语义，再以实际出站消息和新 Observation 验证。”

## 基线与范围

Base 为 `f34295a245149492e9c5ce711caa64a4738cf57d`，分支 `codex/ar04c-f01-context-currentness-01`，远端 main 开工为 `60eee87bfe3cca522011316cb4cd2c0064ad291b`。工作树在 D 盘，原工作树与未提交资料未清理。总纲、AGENTS、Skill Blob、原 F01 Blob 与用户裁决见 `PLAN.md`。

本报告是实施方亲自执行的离线证据，不代表主 Agent 独立复跑。全量 pytest、浏览器和新的付费实验均 NOT_RUN。旧原始报告、Gold、Claim、UNKNOWN 和费用账本未修改。

## Web 与停止线

`WEB_D3_NEXT.md` 已同期完成源码梳理：原审批、CAS、验证及回执 UI/API 已存在；明确断点是专业助手只读路径尚未与既有受控调查入口形成同一用户旅程。无需先新增 Memory 算法或执行框架。

本轮到定向回归即止。`REAL_RECHECK_PROPOSAL.md` 建议只在 Memory ON 下做一条短旅程，Provider 最多 8 次、应用上限 $5.25，待单独授权；不重复完整 OFF/ON Campaign。之后主要精力回到现有 Web 与业务闭环，不继续追补丁或扩建治理。

## 六维摘要

**用户变化：** 后续 Context 明确分开旧快照和本轮查询，正常解释与重查均可完成；真实回答质量尚未验证。

**Agent 决策：** 工具、调查顺序、直接解释、澄清与停止仍由模型决定。

**观察驱动：** 确定性同 Event QUEUED/PROCESSED 与新 Observation 对应；真实行为待小额复验。

**新增约束：** 无新增业务硬限制或答案 Guard；原授权、TTL、预算继续生效。

**简化结果：** 审计保留完整来源，模型只看清晰的时间语义投影；共用现有 Context 预算。

**证据与停止线：** 11/11 离线通过；提交候选后停。旧 G7 FAIL 不改写，不自行签 PASS、合并 main 或发收费请求。

实施方仅提交 **`ACCEPTANCE_CANDIDATE`**，等待主 Agent 独立核验；不授权合并或自动进入下一轮。
