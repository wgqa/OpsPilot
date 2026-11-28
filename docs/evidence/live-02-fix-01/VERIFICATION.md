# LIVE-02-FIX-01 实施证据

`ACCEPTANCE_CANDIDATE`，供主 Agent 独立复核。代码工作树为 `D:\OpsPilot-LIVE-02-FIX-01`，RED 工作树为 `D:\OpsPilot-LIVE-02-FIX-01-BASE`。

## 开工核验

| 项目 | 实际版本 |
| --- | --- |
| 仓库和候选分支 | `wgqa/OpsPilot` · `codex/live-02-fix-01` |
| 基线分支及本地、远端 SHA | `codex/c01-b2-live-01-hf02` · `cce21bec283826910122047ba23138ede2ee17e5` |
| 开工核对的远端 `main` | `60eee87bfe3cca522011316cb4cd2c0064ad291b` |
| 实现提交 | `e0dad57f161e6ef4ceffe90edbb85f24e0c11b0b`、`aa7d57c2ebb53c0fdafd9e9a7057d388a10f138f`、`9f4cc7ea3837fa7c460a9fcc66ee7d2412076afc`、`10e8d030471cf904ca82a9da5d9b9998da3d16e5`、`6699b70a6748f01224e0b56ec70f6a7f5e4efc4b` |
| `PROJECT_NORTH_STAR.md` 实读 Blob | `43dabda468506717c6956e676dfad4304c4f38e6` |
| `AGENTS.md` 实读 Blob | `807b928686a4dd2cac7b15b3c354b9943c93c910` |
| `opspilot-slice-review` 实读 Blob | `d405c8d413d633824b279202cc1503dab4cf0b03` |
| 锁定依赖 Blob | Python `de16e1113ac250511cee8d7b6a079b88b1ca4f99`，Vue `b732ef421d59fcb6eaa1e64b311801fd8b2dc760` |

目标是让同一授权用户读回历史调查、用相关的长期背景继续聊天、识别当前 Event 的处理超时，并在同一回复看到运行进展。以本轮任务卡授权实施。保留 API/访问/事件与恢复合同、M4-03-HF-02 的 S3 权限与 SLA 冻结用例、B2-B Personal Memory ADR、Runtime Grant 授权和账本，以及 M2-01/M2-02 遗留门禁。实读 HF02 [验证记录](../c01-b2-live-01-hf02/VERIFICATION.md)与[开源实现对照](../../learning/OPEN_SOURCE_AGENT_REFERENCES.md)。LIVE-02 的真实浏览器验收证据由用户保管，本轮独立复查为 `NOT_RUN`。

## 切片证据

| 切片 | 前后可见差异和实际入口 | RED / GREEN 和双向验证 |
| --- | --- | --- |
| 1 历史可读性 | HF02 在 TTL 或版本变化后用固定提示替换原回答。候选对来源证明完整的 S3 答复保留原文，在会话内标记历史快照及过期原因。`web/app.py::get_messages` 复用 `domain/assistant.py` 与 `domain/s3.py` 的 Run、Observation、Evidence 和授权校验，`domain/chat.py` 复核其它依赖。前端通过现有消息分页与围栏，在重连、刷新或来源拒绝时重新检查已加载范围。 | Python Base 0/8，候选 8/8。验证 TTL、版本推进、重连游标、分页、跨租户、撤权、Grant 版本变化、无版本事实漂移、篡改来源、敏感字段和只读投影。新 Run 实际输入排除旧原文，当前 source 和旧 draft 端点无法把它带回。当前授权同一订单的新查询成功。前端缓存围栏 Base 0/2，候选 2/2。另有 S3 授权与冻结回归合计 32/32。[RED](logs/01-history-red.txt) · [授权回归](logs/01-history-permission-green.txt) · [前端 RED](logs/01-cache-red.txt) · [前端 GREEN](logs/01-cache-green.txt) |
| 2 记忆召回 | 原始词面覆盖率在中文改写、`SpringBoot` 与 `LangGraph` 等别名上漏选。`domain/semantic_memory.py::personal_memory_context` 对 `PROJECT_BACKGROUND` 增加有限技术主题匹配，继续由现有排序和预算选择。 | Base 0/1，候选 1/1。用 Consolidator Fixture 从本人消息持久化一条 `AUTO_LEARNED`，核对五个相关和三个不相关的实际 Fixture Model 输入。另验同租户另一 Owner、跨租户、来源失效、零选择额度及撤销。B/B2-A/B2-B/HF02 受影响组 54/54（含本用例）。[RED](logs/02-memory-red.txt) · [GREEN](logs/02-memory-green.txt) |
| 3 SLA | HF02 模型拿到原始接收时间和 SLA，需自己做时间计算。候选在 `assistant.py::Loop.context` 与 `domain/assistant.py::source_context_for_model` 传入 `domain/s3.py::receiver_sla_at_observation` 的结果，包含准确的 Observation 时间、Event 和版本。模型仍决定合法查询和回答。 | Base 0/8，候选 8/8。用实际本机 MCP/HTTP 对照未超时、次日仍排队、已处理、传输失败重试耗尽，并按用户样本复算精确截止点和非法观测时间。保持原 Evidence 内容和正式 Gate 计算。SLA/AR02 共 23/23，S1/S2/S3 共 44/44。[RED](logs/03-sla-red.txt) · [GREEN](logs/03-sla-ar02-green.txt) · [业务回归](logs/03-business-regression.txt) |
| 4 流式 UX | HF02 活动折叠区在会话底部且首个 Delta 前分开显示运行状态。候选在 `App.vue`、`conversation.ts` 和 `AssistantRunActivity.vue` 把真实活动放入当前回复，批量追上新 Chunk、按序去重。保留失败草稿标识，最终答案接管展示。代码块可键盘聚焦和横向滚动，离开底部可继续阅读历史。Inspector 把 Task 摘要放在前面，窄屏容器在工作区内定位。 | Base 0/4，候选 4/4。验证等待、同 Run 活动、真实片段去重、最终答案去草稿、隐藏结果不显示活动、Markdown 逃逸及单表单布局。源码确认 HF02 与候选各只有一个个人记忆表单。历史长截图的重复触发路径待手工确认。MockTransport 流式/SSE/Session 共 36/36，Vue 构建通过。[RED](logs/04-ux-red.txt) · [GREEN](logs/04-ux-green.txt) · [组件 SSR 原始输出](logs/04-activity-ssr.txt) · [后端回归](logs/04-streaming-regression.txt) · [构建](logs/04-build.txt) |

来源复核对无法证明可见的依赖采取保守处理。若同一答复还依赖已失效的其它 Run、正式 Evidence、摘要、TaskState 或 Memory，历史投影仍会隐藏正文。撤权与授权变化在下一次投影读取时复核，SSE 重连先遮蔽缓存再查。识别的敏感内容包括已配置的本地秘密、Bearer、常见凭据字段和私钥标记。历史快照从 Web 投影返回，其来源状态无法进入当前 Context、Gate 或 Action。

## 运行命令和失败记录

Windows PowerShell、Python 3.14.0、Node 24.16.0。复用已安装的锁定解释器。每组数据库均由测试在本组 `.runtime` 临时目录创建。Base 只复制本轮测试文件，生产源码固定在指定提交。`pytest` 运行命令与组选项如下，原始输出见各链接。

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
$pytest = @('-m', 'pytest', '-q', '-rA', '-s', '-p', 'no:cacheprovider', '--tb=short')

& $py @pytest --basetemp=.runtime/fixture-new tests/test_live_02_fix_01_history.py tests/test_live_02_fix_01_memory.py tests/test_live_02_fix_01_sla.py
& $py @pytest --basetemp=.runtime/fixture-history tests/test_live_02_fix_01_history.py tests/test_m4_03_hf_02.py
& $py @pytest --basetemp=.runtime/fixture-memory tests/test_live_02_fix_01_memory.py tests/test_c01_b_personal_memory.py tests/test_c01_b2_a_personal_memory.py tests/test_c01_b2_b_personal_memory_auto_consolidation.py tests/test_c01_b2_live_01_hf02_memory.py
& $py @pytest --basetemp=.runtime/fixture-sla tests/test_live_02_fix_01_sla.py tests/test_ar02_runtime.py
& $py @pytest --basetemp=.runtime/fixture-business tests/test_s1_business.py tests/test_m2_02_s2_diagnosis.py tests/test_m4_02_s3.py tests/test_m4_03_s3.py
& $py @pytest --basetemp=.runtime/fixture-stream tests/test_c01_b2_live_01_hf01.py tests/test_c01_b2_live_01_hf02_stream.py tests/test_r1_user_demo_hf02_sse.py tests/test_m1_web_events.py tests/test_c01_a_session_context.py
& $py @pytest --basetemp=.runtime/fixture-runtime tests/test_product_01_runtime_grant_01_hf01.py tests/test_m3_hf02_lineage.py

node --experimental-strip-types --test frontend/test/live-02-history.test.ts frontend/test/live-02-ux.test.ts
$frontendTests = @(Get-ChildItem -LiteralPath frontend/test -File -Filter '*.test.ts' | ForEach-Object FullName)
node --experimental-transform-types --test @frontendTests
npm --prefix frontend run build
npm --prefix frontend run lint
```

- 新 Python 用例合并对照 Base 0/17、候选 17/17。Runtime Grant 与 M3 来源回归 15/15。[Base 原始输出](logs/baseline-red.txt) · [候选原始输出](logs/candidate-green.txt) · [Runtime 与来源](logs/runtime-lineage.txt)
- `test_pre_send_failure_is_not_sent_and_releases_only_unsent_reserve` 在两边都得到 `ASSISTANT_STOP:RuntimeError:offline pre-send validation failure` 的既有程序文案。`test_ops_02_expired_total_deadline_blocks_run_without_model_call` 在两边均由 Legacy 守卫先返回 `LEGACY_PROVIDER_AUTHORIZATION_REQUIRED`。两个节点均以完整名在同环境单独复跑。[Base](logs/legacy-python-base.txt) · [候选](logs/legacy-python-candidate.txt)
- 前端全组候选 34 通过、2 失败、1 跳过。相同的两项历史断言在 Base 期待 `message:a2` 和 `message:limit-answer`，实际分别为既有 `turn:chat-r2:q2`、`turn:limit-run:limit-question`。AR05 的一项真实 Trace 依赖用例跳过。全组用 `--experimental-transform-types`，以支持既有 `ApiError` 参数属性。[Base](logs/frontend-base.txt) · [候选](logs/frontend-candidate.txt)
- `npm run lint` 在 Base 和候选均有 30 errors、25 warnings。Vue 构建含 `vue-tsc` 已通过。[Base lint](logs/lint-base.txt) · [候选 lint](logs/lint-candidate.txt)
- 本轮实际真实 Provider 发送 0，外部业务写入 0。原 LIVE-02 的数据库、Checkpoint、Grant、账本、历史验收记录均在其它工作树。真实浏览器自动化、手工长截图复查、真实模型回答质量及全仓 pytest 为 `NOT_RUN`。冻结 Gold 与锁文件保留原 Blob。
