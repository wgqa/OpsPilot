# LIVE-02-FIX-01-HF-01 验证记录

当前阶段：`ACCEPTANCE_CANDIDATE`，等待主 Agent 独立验收。本记录只覆盖有界长期个人画像召回改造；不代表真实 Provider 回答质量已通过。

## 开工核验

| 项目 | 核对结果 |
| --- | --- |
| 仓库 / 工作树 | `wgqa/OpsPilot`；独立工作树 `D:\OpsPilot-LIVE-02-FIX-01-HF01` |
| 分支 / Base | `codex/live-02-fix-01-hf01`；`codex/live-02-fix-01@6446d6624611053ae6fe0d0ea11c8c21fdc4c586` |
| Base 本地与 origin SHA | `6446d6624611053ae6fe0d0ea11c8c21fdc4c586`；完全相同 |
| 工作开始时原工作树 | `antigravity/ar03-protocol-compare@9abad4de...`，116 个既有未跟踪项目；未在原工作树编辑 |
| North Star Blob | `43dabda468506717c6956e676dfad4304c4f38e6` |
| AGENTS Blob | `807b928686a4dd2cac7b15b3c354b9943c93c910` |
| `opspilot-slice-review` Skill Blob | `d405c8d413d633824b279202cc1503dab4cf0b03` |
| `docs/learning/OPEN_SOURCE_AGENT_REFERENCES.md` Blob | `890ddf8918f976401c4df849eda6394770ed1997` |
| C01-B2-A ADR Blob | `5cc27f62d2dee8bed816d562e68f6b66e8142fc2` |
| C01-B2-B ADR Blob | `a7a0639ef3ff466bd2b1cffd6c7fb158d49a258e` |
| LIVE-02-FIX-01 评审记录 Blob | `7bf3bfbc7f974399a7bd921fbea4f4713f769954` |
| LIVE-02 原始环境 | `D:\OpsPilot-C01-B2-LIVE-01-HF02` 及其 DB、Checkpoint、Grant、Spend、Session、Trace 未修改；测试只创建 Fixture DB 和临时 Checkpoint |

冻结 Gold、Schema、依赖锁、Runtime Grant 授权合同、C01-B2-B 自动学习合同与 Domain 业务状态未修改。此前 LIVE-02-FIX-01 的历史失败记录仍保留在 `docs/evidence/live-02-fix-01/VERIFICATION.md` 与 `logs/`。

## 变更前后调用链

普通用户消息继续走：Web/API 受理 → Session/Run → 内部 Worker → `assistant.Loop.context()` → `domain.chat._prepare_context()`。候选在现有 `personal_memory_context()` 中读取当前 Tenant/Owner 下的 `personal_memories`，复用现有 ACTIVE、过期、撤销、来源消息及 Digest 校验，再把最多六条完整稳定画像作为低权威系统提示块交给原本那次 Assistant Provider 请求。Context Manifest 记录 Memory ID、版本、Digest、来源引用、种类、选入理由、估算 token 和被排除原因。

候选移除了上轮按中文/英文词面、Java/Agent 主题正则和问题词面相似度的主召回门槛。`query` 仅为兼容保留，不再决定一个有效稳定画像是否进入模型上下文。模型在原有回答请求中自行判断背景是否有帮助；没有新增向量存储、Embedding、搜索工具、数据库表或逐轮模型调用。

System guidance 把画像明确标记为不可信的个人背景：它不是当前业务事实或授权，当前用户请求、可信 Domain 状态和当前 Evidence 优先，记忆正文中的命令不得执行。画像绝不转成 Business Memory、Evidence、Approval、Action Permission 或工具能力。

### 选择与预算

- 只考虑既有 `PREFERENCE`、`WORK_HABIT`、`PROJECT_BACKGROUND`；业务 Observation、历史工具结果和其它 Memory 类型不参与画像。
- 顺序确定为：用户明确/确认的偏好与工作习惯 → 用户明确/确认的长期项目背景 → 自动学习的偏好与工作习惯 → 自动学习的项目背景。相同等级优先 PINNED，再优先较新版本，最后按创建时间和 Memory ID 确定顺序。
- 最多 6 条且最多 600 个 Context 估算 token，按完整系统消息估算，含角色及消息封装开销；原有 PINNED 也计入这两个上限，并保留最多 3 条 PINNED 的既有小范围约束。
- 预算不足时整条排除并记录 `PERSONAL_PROFILE_TOKEN_BUDGET` 等原因，不截断正文。历史记录仍在原表中。`all_current` 仍用于现有历史摘要/依赖有效性校验；所选画像也仍在真正外发前复核。
- 个人记忆可选块优先级低于必需的当前用户输入和近期交互；超大工具输出继续走已有 request-only 投影器。Tool Call/Tool Result 配对与来源引用保持，原 Checkpoint/MCP Evidence 不被改写。

Recall OFF、历史摘要失效、版本修订、撤销、Checkpoint 恢复和外发前 Memory 复核均复用现有合同。`assistant.Loop` 只补齐 `AUTO-LEARNED PERSONAL MEMORY GUIDANCE` 对已选上下文的识别，使自动画像进入既有 Manifest、费用元数据与发送前重验，不改变 Agent Loop。

## RED / GREEN 验收

| 案例 | Base / 候选证据 | 结果 |
| --- | --- | --- |
| T01 原始 B07，两条 AUTO_LEARNED：Java 后端 + Python Agent 背景、技术解释偏好 | Base 原始失败见 [`b07-red.txt`](logs/b07-red.txt)；候选真实 Fixture Provider 输入与 Manifest 见 [`profile-green.txt`](logs/profile-green.txt) | Base `0/1`；候选 `1/1`。新 Session 的实际请求包含两条记忆 ID、完整内容、版本、Digest、来源和选择理由；两条画像估算合计 `545` tokens（单条 `270` 与 `275`），未把 SQLite 或放弃 Java 声称成记忆事实。 |
| T02 中英文改写 | 同一 Profile Fixture 用 7 条改写/无关问题，并有 8 条自然改写跨语言样本，日志见 [`profile-green.txt`](logs/profile-green.txt)、[`c01b-runtime-regression.txt`](logs/c01b-runtime-regression.txt) | 全部请求走同一预算选择；未添加测试句专用关键词。 |
| T03 无关问题 | SQLite 锁、HTTP 状态、数学题；另外包含 Excel 格式化、旅行和 Python 前端样例 | Profile 可用但 Fixture 最终回答仍是通用当前问题回答。此项只验证输入和 Fixture 行为，不证明真实模型不会过度个性化。 |
| T04 Tenant / Owner 隔离 | [`c01b-runtime-regression.txt`](logs/c01b-runtime-regression.txt) 和 [`b2b-regression.txt`](logs/b2b-regression.txt) | 其它 Tenant、同 Tenant 其它 Owner 均无该画像；有效、来源失效、撤销对照通过。 |
| T05 生命周期 | [`profile-green.txt`](logs/profile-green.txt)、[`b2a-regression.txt`](logs/b2a-regression.txt)、[`c01b-runtime-regression.txt`](logs/c01b-runtime-regression.txt) | ACTIVE 当前记录可用；REVOKED、EXPIRED、REVISED、SOURCE_CHANGED、SOURCE_UNVERIFIED 不注入；旧版本不与修订版同时出现。 |
| T06 Recall OFF 与 Summary | [`b2a-regression.txt`](logs/b2a-regression.txt) | 关闭记忆后同 Session 重新装配，受个人记忆影响的摘要不能重新带入；恢复开关与普通历史不受损。该既有测试通过。 |
| T07 并发撤销 | [`profile-green.txt`](logs/profile-green.txt) | 在 Runtime Dispatch 已登记、Provider 发送许可尚未使用的缝隙撤销；MockTransport 请求数为 `0`，Runtime Spend 状态为 `NOT_DISPATCHED`，回答失败关闭。 |
| T08 预算与工具输出 | [`profile-green.txt`](logs/profile-green.txt) | 10 条稳定记录中选择 2 条完整记录、估算 `492/600` tokens，另外 8 条都带 `PERSONAL_PROFILE_TOKEN_BUDGET` 排除原因；不截断。900 token 工具预算下，当前问题与两组 Tool Call/Tool Result 均保留、两个结果按来源投影，Evidence/Observation ID 成对可查，原始结果对象未修改。 |
| T09 记忆注入文本 | [`profile-green.txt`](logs/profile-green.txt) | 恶意内容按不可信背景进入提示；System guidance 明确拒绝执行嵌入命令；Fixture Run 没有 MCP Call，`d3_action_ledgers` 增量为 0。真实模型抵抗力未验证。 |
| T10 既有流程 | 下方回归汇总 | 六轮自动整理、显式记住/修订/撤销、跨 Session、Runtime Grant、SSE、Checkpoint 与 Business Memory 授权回归通过。 |

Base RED 是在目标 Base 源码上运行新增 B07 Fixture 测试，失败点为真实模型请求中没有 Memory ID。迭代中曾有一项测试断言把用户问题里的 `SQLite` 也当作 Memory 内容；现保留在 [`b07-iteration-assertion-failure.txt`](logs/b07-iteration-assertion-failure.txt)，最终断言检查实际画像块与 Manifest，已修正。

## 受影响回归命令与结果

测试使用 `D:\OpsPilot-C01-B2-LIVE-01-HF02\.venv\Scripts\python.exe` 的锁定依赖；禁用 Provider/Legacy Provider 环境授权，Fixture DB 和临时 Checkpoint 单独创建。没有联网调用真实 Provider。

```powershell
$py = 'D:\OpsPilot-C01-B2-LIVE-01-HF02\.venv\Scripts\python.exe'
$env:PYTHONUTF8 = '1'
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:OPSPILOT_ASSISTANT_PROVIDER_ENABLED = '0'
$env:OPSPILOT_LEGACY_PROVIDER_ENABLED = '0'
$env:OPSPILOT_ASSISTANT_RUNTIME_ENABLED = '0'
$env:OPSPILOT_MODEL_API_KEY = 'offline-only'
$env:OPENAI_API_KEY = 'offline-only'
$env:LANGSMITH_TRACING = 'false'
$env:LANGCHAIN_TRACING_V2 = 'false'
$env:OPSPILOT_ASSISTANT_EXPERIMENT_ID = ''

& $py -m py_compile opspilot/domain/semantic_memory.py opspilot/domain/chat.py opspilot/assistant.py tests/test_live_02_fix_01_hf01_profile.py
& $py -m pytest -q -rA -s -p no:cacheprovider --basetemp=.pytest-hf01-profile-final-20261113-03 --tb=short tests/test_live_02_fix_01_hf01_profile.py
& $py -m pytest -q -rA -s -p no:cacheprovider --basetemp=.pytest-hf01-memory-regress-final-20261113-01 --tb=short tests/test_live_02_fix_01_memory.py tests/test_c01_b_personal_memory.py tests/test_c01_b2_live_01_hf01.py
& $py -m pytest -q -rA -s -p no:cacheprovider --basetemp=.pytest-hf01-b2a-final-20261113-01 --tb=short tests/test_c01_b2_a_personal_memory.py
& $py -m pytest -q -rA -s -p no:cacheprovider --basetemp=.pytest-hf01-b2b-final-20261113-01 --tb=short tests/test_c01_b2_b_personal_memory_auto_consolidation.py
& $py -m pytest -q -rA -s -p no:cacheprovider --basetemp=.pytest-hf01-runtime-final-20261113-01 --tb=short tests/test_product_01_runtime_grant_01.py::test_grant_reservation_send_authority_usage_and_replay_are_persistent tests/test_product_01_runtime_grant_01.py::test_revoke_between_reservation_and_send_denies_wire_and_releases_only_unsent_reserve tests/test_product_01_runtime_grant_01.py::test_formal_api_worker_chatopenai_uses_persistent_runtime_grant_and_mock_transport tests/test_product_01_runtime_grant_01.py::test_runtime_context_compression_and_answer_share_the_persistent_pool tests/test_product_01_runtime_grant_01_hf01.py
& $py -m pytest -q -rA -s -p no:cacheprovider --basetemp=.pytest-hf01-stream-final-20261113-01 --tb=short tests/test_c01_b2_live_01_hf02_stream.py tests/test_checkpoint_smoke.py tests/test_m303_semantic_memory.py
```

| 命令测试文件 | 结果 | 原始日志 |
| --- | ---: | --- |
| `tests/test_live_02_fix_01_hf01_profile.py` | 8/8 | [`profile-green.txt`](logs/profile-green.txt) |
| `tests/test_live_02_fix_01_memory.py` + `tests/test_c01_b_personal_memory.py` + `tests/test_c01_b2_live_01_hf01.py` | 13/13 | [`c01b-runtime-regression.txt`](logs/c01b-runtime-regression.txt) |
| `tests/test_c01_b2_a_personal_memory.py` | 14/14 | [`b2a-regression.txt`](logs/b2a-regression.txt) |
| `tests/test_c01_b2_b_personal_memory_auto_consolidation.py` | 27/27 | [`b2b-regression.txt`](logs/b2b-regression.txt) |
| Runtime Grant 核心 5 项 + `tests/test_product_01_runtime_grant_01_hf01.py` | 18/18 | [`runtime-regression.txt`](logs/runtime-regression.txt) |
| `tests/test_c01_b2_live_01_hf02_stream.py` + `tests/test_checkpoint_smoke.py` + `tests/test_m303_semantic_memory.py` | 23/23 | [`checkpoint-stream-m3-regression.txt`](logs/checkpoint-stream-m3-regression.txt) |

累计上表为 `103/103`，测试间存在重叠，不作为独立全仓用例分母。Python 编译检查通过，包含三个生产模块和新增画像测试。完整 pytest 全仓、浏览器自动化和人工真实模型验证为 `NOT_RUN`。另有一次更宽的 Runtime Grant 合并运行在连续等待超过 3 分钟后手动停止；因此未计入结果。针对性 Runtime Grant、Legacy 授权、流式 UNKNOWN、不重发和 Checkpoint 跨进程恢复均单独通过。

## 数据、费用与未验证限制

- 本轮真实 Provider 发送：`0`；MockTransport 外部 Provider：只由现有离线回归发起。外部业务写入：`0`。
- 没有 Recall 检索模型请求。普通聊天仍为一次原有 Assistant 请求；自动整理只在原有六轮 Worker 条件下使用既有 Consolidation 调用，算法与触发未改。
- 未新增表、Schema、依赖、向量库、Memory Store、Context Manager、Runtime 或状态机；没有修改 `main`、Gold、LIVE-02 原始数据或费用账本。
- Base 新增 B07 Fixture 在 RED 之前仅被正确拒绝，Base 没有 Provider 发送。候选 Fixture 对照仍是离线双向证据，不代表 DeepSeek 或其它真实模型会正确调用/忽略长期个人背景。
- “所有有效小画像始终可供模型判断”提高自然改写召回率，也增加无关记忆出现在请求中的机会；当前使用 600-token 硬上限、完整来源、低 Context 优先级和非权威提示限制影响。真实回答的过度个性化和误用需由人工真实模型测试验证。
