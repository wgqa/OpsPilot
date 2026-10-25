# M4-EG01-HF-01 冻结验收计划

状态：`FROZEN_BEFORE_RED`（实施方冻结；不代表主 Agent 验收）。本文件先于本轮测试、源码变更提交。

## 基线与实际读取记录

- Repo：`wgqa/OpsPilot`；执行工作树：`C:\Users\tu me manques\.codex\worktrees\c1-approved-integration-20261025\agent新项目`。
- Base / `origin/main` / 当前 HEAD：`3db7fa80aebd4a92dea7205656d47a26500ee295`；父提交 `0c142e91f04ec1278b0cf547aeeeb480466466c8`；无合并历史。
- 用户主工作区 `D:\学习\agent新项目` 的 HEAD 为 `add47ec83f31fa76b9b6a5782e013311732bc496`，落后远端且有未跟踪资料；本轮不在其中修改或清理。
- 当前隔离工作树 tracked 状态干净；预存未跟踪 `docs/evidence/vnext/m4-eg-01/runs/{full-pytest-01,full-pytest-02,regression-fix-vs08}/basetemp/` 与 `frontend/.npm-cache/` 保留且不暂存。
- `PROJECT_NORTH_STAR.md`：已从目标提交逐段读取，Blob `1f737712c7a36ceb34433ac09c3fbba3c3305542`。
- `AGENTS.md`：已从目标提交完整读取，Blob `30319000ed0054007e9b7b6b46bf98b1493c8179`。
- `.agents/skills/opspilot-slice-review/SKILL.md`：目标提交不存在，未声称执行该 Skill。仓库内的 `docs/evidence/vnext/m4-c1-integration-01/REPORT.md` 也记录该 Skill 未合入目标候选。
- M4-EG-01 `ACCEPTANCE_PLAN.md` Blob `949938a3c269cf8069f0fb526930a9947e80e786`、`GOLD.json` Blob `9ef662173c3bcbdae05a20d24fe3673cd2dd8cbf`、`REPORT.md` Blob `44265410c740ed9f005f2150f0dc8ef868f4f442` 已读取。冻结提交 `18e9b0e0b7b5112befd767a3f9bef53ec43d1ac9` 与 RED 提交 `0c142e91f04ec1278b0cf547aeeeb480466466c8` 均为本基线祖先；原 Gold、留出、RED 和报告不修改。
- M2-01 `DEFERRED_GATES.md` Blob `2e65870acb26a7c1383fdd96b5b8619748dda6b9`；M2-02 `DEFERRED_GATES.md` Blob `2536030b5b942bf9e3765e0916607549fa919934`。
- 访问/控制/恢复合同：`docs/baseline/ACCESS_MATRIX.md` Blob `9d62359c3a97a2fe78678b178889288e551b3d7c`；`STATE_TRANSITIONS.md` Blob `cb34e6402cf3ce795260414b9b652f31b49f4de1`；`EVENT_RECOVERY.md` Blob `9ae6c3f35b93c8c139d598c4dfde42447cf5d0cc`；vNext 产品架构合同 Blob `04b0ff39710519adeb4a97a8410ceb06c46a520b`。均已实际读取。
- 当前用户任务卡来自本轮消息；不在目标提交内，无 Git Blob。优先级：本轮 HF-01 修订任务卡 → EG-01 冻结 Gold 与安全合同 → North Star / AGENTS 规则 → 历史报告仅作证据。

## 冻结问题与根因假设

测试前假设：Gate 的 `checked_fact_ids` 是裁决使用的最小事实集，不一定覆盖所有当前有效的 Run Observation；Chat 若把它当作完整可解释事实集，会漏掉同 Run、同 Event、仍具授权/版本/TTL 有效性的部分事实。此假设必须由 RED 证据确认。本轮不得改变 `_gate_from_evidence()` 的裁决规则。

## 验收用例与停止标准

| ID | 冻结场景 | 必须观察到的结果 |
|---|---|---|
| HF01-RED-01 / HF01-GREEN-01 | 有效 TaskBinding 与授权；同一业务 Run 通过当前 HTTP/MCP 路径取得订单 HTTP 200 和目标 Event 投递 HTTP 202；不为该 Run 查询 Receiver；所有 Observation 均同 Task/Run、版本匹配、未过 TTL；Gate 为 `INCONCLUSIVE`。 | RED 必须证明原 Chat Provider 入参缺少投递 Observation；修复后 Chat 入参及 Evidence refs 含订单与同 Event 投递事实、Event ID、独立 Transport Request ID、Observation/Evidence ID、版本与时间；没有 Receiver 当前证据时不出现 `PROCESSED` 或 `QUEUED` 事实。Gate、Task Outcome 和写表保持不变。确定性 Chat 准备/Provider 入参捕获是主证据；如可用真实 Provider，A/B/C 各最多一次，绝不调试重试。 |
| HF01-SEM-A | 有目标 Event HTTP 202，无匹配当前 Receiver Observation。 | 出站事实明确为已受理/处理状态未知；不能把 202、SLA 或业务表当前快照说成当前 QUEUED/PROCESSED。 |
| HF01-SEM-B | 目标 Event 有当前、同版本 Receiver=`PROCESSED` Observation；即使 SLA 未到。 | 出站事实允许确认同 Event 已处理；不得要求等待 SLA。 |
| HF01-SEM-C | 目标 Event 有当前、同版本 Receiver=`QUEUED` Observation。 | 出站事实准确显示排队；仅 SLA 决定等待或联系方向，不能称已完成或自动重发。 |
| HF01-NEG-01 | 尝试组合跨 Task 或不同 Event 的事实。 | Context 只包含绑定 Task/目标 Event 的经当前性核验事实；不泄露其他 Task/Event。 |
| HF01-NEG-02 | Scope/Principal 授权撤销、版本不匹配、Evidence/Observation 过期或来源关联错误。 | 当前事实 fail-closed；不得把失效事实传给 Chat。 |
| HF01-NEG-03 | 使用其他/历史 Run 的 Evidence ID，但当前诊断 Run 中无对应成功 Observation。 | 不得借历史 Observation 冒充当前 Run 观察。 |
| HF01-NEG-04 | HTTP 202 事实与 INCONCLUSIVE Gate。 | 不提升为 `DIAGNOSED`，不改变 Task Outcome/TaskControl，不创建 Approval、Plan、ActionIntent、Ledger、Handoff Queue/Receipt 或其他业务写入。 |
| HF01-POS-02 | 没有正式 `DIAGNOSED` 结论，但合法同 Run 部分 Observation 当前有效。 | 允许 Chat 解释当前可证实部分与未知项；不得因 Gate 不完整而全部屏蔽。 |

关键成功标准是“上下文事实经过 Domain 重新校验后准确进入实际 Provider 请求对象”，不是模型文字、Gate 状态或仅存在于冻结 Diagnosis 的原始 JSON。确定性验证使用实际 `prepare_chat_attempt()` 生成的出站 `messages`、`evidence_refs` 和 Context Manifest。真实 Provider 若执行，记录并人工核对输出；它不是授权、Gate 或业务结果证据。

## 验证范围、预算与停止线

- 修改前先添加并运行 RED；保存 pytest 原始日志和逐项 ID。随后只允许在 Chat 当前事实装配职责内实现最小改动。
- 使用与本次 RED 一致的 Task、Run、Observation、TaskBinding 和受控时钟；优先调用本地真实 HTTP 服务和 in-process MCP Server，禁止以模型自述或直接改写 Evidence 表冒充工具取证。
- M4-EG-01 报告记录 Provider 37 次 / 计划上限 40 / 硬上限 80 / USD 1.00 估算上限。修复前重新审计所有保存的 Trace 计数与配置；本轮计划新增最多 3 次（HF01 A/B/C 各一次），绝不重试用于调试。配置缺失、预算余量不足或累计费用预留超限则 Provider 为 `NOT_RUN`，保留确定性验收并记录原因；不得提高上限或修改 Gold。
- 不调用真实 Web 工作台重新演示旧功能；Provider 未运行时明确标记。运行定向 Chat/S3、授权撤销、历史 Evidence、S1/S2 安全回归；可运行完整 pytest，但既有 obsolete C1 RED 失败不得删除/改写/兼容处理。
- 停止条件：来源、授权、版本、TTL、跨 Task/Event、Run 隔离正反用例通过；Gate/TaskControl/业务写表与历史 Receipt 未变化；相关回归完成。不得改预算、Gold、前端、Memory、Gate 或当前任务以外的 C1 行为。

## 证据分级

- 真实 HTTP/MCP 取证 Trace：记录 HTTP 请求/状态、MCP 工具、Run/Attempt/Observation/Evidence IDs、Event/Transport Request IDs、版本、时间与 Gate；对固定 fixture/API 的来源明确标记本地 Demo，不等同生产服务。
- Deterministic Chat context：记录 `prepare_chat_attempt()` 真正输出的消息与 provenance 索引；它证明出站载荷构造，不代表 Provider 已收到或给出正确自然语言答案。
- Provider：仅实际执行后记录模型 ID、请求 ID、Token/响应/失败；未执行写 `NOT_RUN`。
- 不记录或提交 Secret、Authorization、Cookie、完整私有环境变量。

## 本轮范围外

不修改冻结 Gold、S3 Gate、TaskControl、Action/Handoff 权限语义、业务 Fixture、前端、Memory、Knowledge、预算常量或旧 C1 测试；不启动后续阶段。
