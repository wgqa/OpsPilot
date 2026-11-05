# AR-04B-REGRESSION-HF-01 — AR-04A 断言范围定向复核

状态：`ACCEPTANCE_CANDIDATE`（实施方）；不代表主 Agent PASS。

## 基线与读取

- Repo：`wgqa/OpsPilot`
- 候选分支：`codex/ar04b-memory-journey-01`
- 本轮基准候选：`6dc71e91b83203b07647fd12caf777239c2b153b`
- 远端 `main`：`134df49f792dfdf8d4b9a3b846d218af5c34ec6d`
- 被比较测试在 main 与候选上的 Blob 相同：`8ac8f90c5bad30aa94d47f0787e028b1cdedb6ac`
- `PROJECT_NORTH_STAR.md` Blob：`e36f2f75509738551ac6d4a2de5b4f9cf44a7991`
- `AGENTS.md` Blob：`f174a6ab7f23f9e6d8b3ef98d455b99a75193143`
- 项目 Skill Blob：`d405c8d413d633824b279202cc1503dab4cf0b03`
- AR-04B GOLD Blob：`f5056cbb3344208e2e34671ea08a50963d3aea3d`
- AR-04A GOLD / REPORT Blob：`6c8ba3867e2dad983abe6f1b85bd559fc28e36ac` / `ab409090311132166ff1a79f2cb5c031f55ab8e5`
- 适用 M2-01 / M2-02 延期门禁 Blob：`2e65870acb26a7c1383fdd96b5b8619748dda6b9` / `2536030b5b942bf9e3765e0916607549fa919934`

实际复读了目标提交的 North Star、AGENTS、Skill、AR-04B Gold/报告/失败记录、AR-04A Gold/报告及上述延期门禁。远端 main 未变；比较没有合并历史。工作限于 AR-04A 测试断言和本证据目录。

## 根因判断

结论：**本失败是测试断言检查范围过宽，不是失效摘要进入模型消息的安全回归。** 本轮没有修改产品源码、Gold、摘要失效逻辑或来源检查。

原测试把 `_model_wires()` 的整个持久 `request_json` 序列化，然后断言摘要 ID 在整个 JSON 中不存在。候选请求的 `excluded_sources` 会保留被拒摘要 ID 和原因，供内部审计使用；因此该断言在候选上失败，即使模型输入没有摘要。

## 数据库与模型消息实证

检查的是正式 API/Worker/Assistant 路径下 Fixture Model 实际调用前持久化的 `assistant_calls.request_json`。这是真实本地模型处理器输入记录，不是外部 Provider HTTP。

| 核查项 | 候选重现结果 |
|---|---|
| 摘要状态 / 失效原因 | `INVALID` / `SUMMARY_MESSAGE_SOURCE_INVALID` |
| 摘要 ID、Digest、完整 `summary_json`、`HISTORICAL SESSION SUMMARY` 是否出现在 `messages` | 均未出现 |
| `source_refs.summary_refs` | 空列表 |
| `HISTORICAL_SUMMARY` Context block | `NOT_APPLICABLE`，估算 Token `0` |
| 摘要 ID 出现位置 | 仅在 `$.excluded_sources[1].source_id` 与 `$.source_refs.excluded_sources[1].source_id`；两处均为内部排除审计元数据 |
| 排除原因 | `SUMMARY_SCOPE_OR_DIGEST_INVALID`；摘要行自身保留 `SUMMARY_MESSAGE_SOURCE_INVALID` |
| 原始用户来源文本 | 仍作为普通 `human` 历史消息存在；不是派生摘要块，也不是可信 Evidence。测试触发的是摘要依赖摘要不匹配，未删除用户消息 |
| 后续 Run 与回答 | `SUCCEEDED`；有持久 `chat_run_answers` 关联及 238 字符的非空 Assistant Message；消息读取 API 也返回非空答复 |

候选 RED 数据库对应 Run `run-98fc879f-de53-4b30-b83d-f046314cd585`。修正断言后的 GREEN Run 为 `run-96285a07-e565-4e1c-b058-60557f844870`。两个独立测试库的摘要 ID、来源 Message 和 Answer ID 不同；均为本地合成数据。SQLite 只读检查显示本定向 GREEN 库的 ActionIntent、ActionLedger、Approval、HandoffReceipt 均为 `0`。

原始用户话语继续以普通会话历史输入模型是既有历史上下文行为；本测试不把它误称为摘要重新注入。AR-04A G6 禁止的是失效的派生摘要回流。若后续合同要求来源 Message 自身因 Digest 不匹配而从普通历史中剔除，应另行冻结其语义；本次没有擅自改变该行为。

## 最小 Diff

只修改 `tests/test_ar04a_context_journey_01.py::test_ar04a_invalidated_summary_is_not_sent_to_the_model`：

- 检查 `request_json["messages"]`，而非整个审计包装对象。
- 断言摘要 ID、Digest、完整摘要正文、摘要标记均不在模型消息；摘要引用为空、Token 选择为零。
- 同时断言 `excluded_sources` 保留摘要 ID 与失效原因。
- 保留摘要 `INVALID`/原因、Run 成功断言，并增加非空持久答案与 API 可见答复断言。
- 区分原始 `human` 历史消息与派生摘要，不因正文内容重合将其视为摘要块。

没有生产源码 Diff，未放宽来源或安全校验。

## 执行结果

| 执行 | 结果 | 原始日志 |
|---|---:|---|
| 未修改 `origin/main@134df49` 同一测试 | 1/1 PASS | `runs/regression-ar04a-main-baseline-hf01.log` |
| 候选原断言、未修改测试 | 1/1 FAIL：ID 出现在全量审计 JSON 的排除元数据 | `runs/regression-ar04a-candidate-before-fix-hf01.log` |
| 候选最终定向测试 | 1/1 PASS | `runs/regression-ar04a-candidate-green-02-hf01.log` |
| AR-04A Context + compression/cancel | 8/8 PASS | `runs/regression-ar04a-context-cancel-hf01-final.log` |
| AR-04B | 9/9 PASS | `runs/regression-ar04b-hf01-final.log` |
| Memory/D5 | 28/28 PASS | `runs/regression-memory-d5-hf01-final.log` |
| Assistant/TaskControl | 14/14 PASS | `runs/regression-assistant-taskcontrol-hf01-final.log` |

另有一份中间诊断日志 `runs/regression-ar04a-candidate-source-history-diagnostic-hf01.log`：先试验了“源用户文本也必须不存在于消息”的更强断言，该断言失败；SQLite 与 LangChain 消息结构核实后确认该文本是普通 `human` 历史消息，而非摘要正文注入，因此没有把它误作为产品 RED。该原始失败保留，不计入以上冻结回归分母。

此前 7/8 的历史候选回归日志和原始结果均保留，没有覆盖。此次没有运行全量 pytest；没有真实 Provider、浏览器或外部业务写入。全部测试使用隔离 SQLite、确定性 Fixture Model 和本地应用路径。G9 的专门大 Memory 超预算用例仍未覆盖。

Python `3.14.0`、pytest `9.1.1`。原始命令记录在各 `.log` 中。最终候选 SHA 由远端分支 HEAD 和交付消息核对，避免在报告中写入自指提交哈希。

## 六维收尾

**用户变化：** 用户可继续获得非空答复；本补差修正的是测试对“模型输入”和“内部审计”的混淆，不新增产品能力。
**Agent 决策：** 本轮不修改模型调查决策或自主工具选择。
**观察驱动：** 失效摘要不注入；原话作为普通历史用户消息保留；有效回答继续持久化。
**新增约束：** 没有新增运行时约束，只增加摘要正文/引用与审计字段分离的断言，并保留合法历史消息。
**简化结果：** 不改生产校验、不删 `excluded_sources`，只把原断言收敛到实际模型 `messages`。
**证据与停止线：** main/候选对照与必要相关回归已执行；Provider、浏览器、全量 pytest、G9 专项未运行。停止于 `ACCEPTANCE_CANDIDATE`，由主 Agent 定向复核。
