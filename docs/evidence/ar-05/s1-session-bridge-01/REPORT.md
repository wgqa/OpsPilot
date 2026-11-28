# AR-05-S1-SESSION-BRIDGE-01：实施候选

状态：`ACCEPTANCE_CANDIDATE`；浏览器 `NOT_RUN / HISTORICAL_STOP`。

## 用户旅程与证据

用户在同一会话问：“我们轮换了 API 凭据以后订单接口一直返回 401。你帮我调查一下，如果需要修复，告诉我后续怎么操作。” 本地确定性助手答复：401 表示认证未通过，凭据轮换只是线索；尚未查询或确认原因，需要确认资源后进入受控调查。用户确认原文和服务器列出的 Demo 资源后，既有 API 创建新 Task 和初始专业调查 Run。页面代码按服务端返回的来源关联显示已确认描述、运行、可信来源和方案；方案存在且仍 ACTIVE 时才显示等待独立审批。没有在线验证时明确尚未确认恢复。

本次本人实际运行的 [TRACE-verified.json](TRACE-verified.json) 使用确定性模型替身与正式 FastAPI、Worker、S1 Investigator、真实本地 MCP/HTTP 和隔离 SQLite。它不是收费模型智能表现或浏览器证据：

- Session `session-ad5ad703-ca1f-4294-89d2-2068c16c7c21`；原问题 `message-0a4b31a7-2ede-4197-a3b9-b3fa15a7ae84`。
- 确认消息 `message-966df13a-cfe9-49b8-bea8-940b4224762d` → Task `task-28dc1988-3f04-49a2-88c4-fbaa348f4525` → Run `run-8461f6b1-fdd0-4319-94dc-a52e8465dfde`。Run 核心 `PROFESSIONAL_INVESTIGATOR`；原对话仍为 `ASSISTANT_V1`。
- 四次只读取证获得同一绑定的 HTTP 401、集成配置、启用的主体和认证策略；Gate 为 `READY`。Plan `90360be484467d573c18da7600a719d59df4064ef02febdcc98db7a36039228c`、版本 1、`ACTIVE`，Task/Run 为 `WAITING_APPROVAL`。
- 当时 Outcome 中 Approval、Repair、Verification、Delivery 均为空；业务配置版本和凭据引用未变化，审批、ActionIntent、Ledger 和工单条目计数为零。测试末尾在隔离库内故意破坏 Plan 哈希以验证只读预览拒绝失真，不是业务操作。
- `TRACE-initial-fixture.json` 保留第一次使用旧通用替身时给出不相干 HTTP 202 答复的事实；最终证据使用明确标注的 401 确定性替身，不将其宣称为真实模型表现。

## 基线与变更

Repo `wgqa/OpsPilot`；Branch `codex/ar05-s1-session-bridge-01`；Base `9b28cd057f3f98174e366d4d0b2e3d49868dae4a`；复核远端 main `60eee87bfe3cca522011316cb4cd2c0064ad291b`。候选 HEAD 以包含本报告的最终提交为准，不伪造自引用 SHA。已实际读取目标提交的 North Star（Blob `e36f2f75509738551ac6d4a2de5b4f9cf44a7991`）、AGENTS（`f174a6ab7f23f9e6d8b3ef98d455b99a75193143`）、项目评审 Skill（`d405c8d413d633824b279202cc1503dab4cf0b03`）、M2-02 Deferred Gates（`2536030b5b942bf9e3765e0916607549fa919934`）及 S1/D3 合同。用户本轮任务卡优先于历史阶段限制。

- 前端复用原 Task API，在问题下提供显式确认并显示服务端限定的 Demo 服务、集成和主体。稳定 operation ID 在响应丢失时复用；用户确认后的新操作才获得新 ID。S1 选中时普通对话仍用无 Task 的 `ASSISTANT_V1`；S3 合法绑定仍走原路径。
- `create_task_with_initial_run` 在已有事务和 `chat_message_sources` 中记录同 Session、同租户 USER 原问题及摘要，现有创建命令继续负责幂等；读 API 只在消息、命令、Run 和摘要一致时回显来源。未增加表、路由或审批授权。
- 既有 Outcome 对 Task 所有者增加经过 Plan hash 校验的有限只读预览；Run DTO 区分 Assistant、旧只读 Chat 和专业 Investigator。没有改动调查决策、Gate、Worker、TaskControl 的权限、Approval 或 CAS。

## 本人执行的验证

| 验证 | 结果与证据 |
|---|---|
| 定向 RED | 后端原接口 2 项拒绝新来源字段；前端未传稳定 operation ID，1 项失败。见 `red-backend-targeted.log`、`red-frontend-targeted.log.gz`（原始字节压缩保存，避免 Git 把日志自带空白判为补丁问题）。 |
| 定向 GREEN | `tests/test_ar05_s1_session_bridge_01.py` 4/4；覆盖真实本地 Worker/MCP/HTTP、幂等、重放、不同 payload、跨 Session/租户、身份拒绝、摘要及 Plan 篡改。见 `green-backend-verified.log`。 |
| 相关后端回归 | 106/106，153.49 秒；S1/D2/D3、TaskControl、Web API/Approval、S2、Assistant 与 S3/C1 定向套件；见 `backend-regression.log`。 |
| 前端非浏览器 | 28/28；包括真实 API 保存 JSON → 现有对话投影、操作重放、S1/S3 路由、无 Plan/失效/拒绝/恢复表述和既有 S3 缓存回归。见 `frontend-projection-release.log`。 |
| 构建 | `npm run build`（含 vue-tsc）及变更文件 ESLint 退出码 0，见相应日志；`git diff --check` 通过。 |

命令：`python -m pytest tests/test_ar05_s1_session_bridge_01.py tests/test_m1_web_api.py tests/test_m1_task_control.py tests/test_d2_investigation.py tests/test_d3_actions.py tests/test_m1_web_approval.py tests/test_m2_02_s2_diagnosis.py tests/test_ar02_runtime.py tests/test_m4_c1_s3_prompt.py tests/test_m4_c1_hf_01.py -q --tb=short --basetemp .pytest-ar05-regression-20261106`；设置 `AR05_TRACE_PATH=docs/evidence/ar-05/s1-session-bridge-01/TRACE-verified.json` 后执行 `node --experimental-transform-types --test frontend/test/ar05-s1-bridge.test.ts frontend/test/assistant-entry.test.ts frontend/test/conversation.test.ts frontend/test/stage-b-closeout.test.ts frontend/test/stage-b-correction-sidecar.test.ts`；在 frontend 下执行 `npm run build`、`node_modules/.bin/eslint src/App.vue src/api.ts src/s1-bridge.ts`。构建复用同 lockfile 的本地依赖，不修改依赖锁。

## 六问与限制

**用户变化：** 可从原会话的问题确认创建 S1 调查，并在同会话读取已持久的状态、来源与方案；实际浏览器交互尚未验收。

**Agent 决策：** 旧 S1 调查仍由专业 Investigator 选择合法工具；本次工具顺序来自确定性替身，只证明接线，不证明真实模型自主性。

**观察驱动：** 本次 401 加匹配事实形成 READY/Plan；相关 D2 回归中主体 DISABLED 导向 NO_ACTION。二者不是同一浏览器真实模型成对实验。

**新增约束：** 原消息须同租户、同 Session、USER 且摘要一致；跨域及篡改被拒，同 Session 正例通过。同操作重放复用，异 payload 冲突，新意图可创建。

**责任与简化：** 复用原 Session、TaskControl、消息来源表、Worker、Investigator 和 D3；未增加独立状态机。删除了前端 S1 选中时强制切回旧 Chat 的分支；保留服务器的 TaskBinding 和独立审批。

**证据与停止线：** 浏览器和真实 Provider 为 `NOT_RUN`；新增同 Session 旅程没有进行审批或修复。既有 D3 回归包含隔离 Demo 内的模拟审批与写入，这不构成新入口的写入验收，也没有生产或外部业务写入。M2-02 的 S1 TTL/审批后 Revalidation 仍限制新写入口。S1 Task 事实未作为当前业务 Evidence 自动注入无 Task 的 Assistant 后续问题，用户可在 Task 结果区查看可信状态。F01 时间表述和程序预算提示歧义未在本切片扩展。历史 Claim、Gold、Trace 未改。
