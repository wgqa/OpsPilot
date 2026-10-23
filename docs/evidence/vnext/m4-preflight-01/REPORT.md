# M4-PREFLIGHT-01 — Evidence TTL 与重复取证验证

**审查基线：** `bd58c66003c4e7fea660967c7a6a30aebcd63cd7`  
**验证结果：** S3 缺陷稳定复现（RED）；未修改正式业务源码；证据包通过隔离审查分支交付，`main` 保持不变。  
**本轮范围：** 复现、影响分析、最小修复层评估。

## 结论

1. **可以稳定复现。** 在两个独立 pytest 数据库运行中，第一次 Gate 均为 `DIAGNOSED / WAIT_FOR_RECEIVER_PROCESSING`。受控时钟推进 301 秒后，新 Run 重新执行三次 MCP 查询；三次 Observation 都是 `OK`，订单 HTTP Probe 再次返回 200，订单、投递、接收状态及版本均未变化。但 `s3_delivery` 和 `s3_receiver` 复用旧 Evidence ID，Gate 继续读取旧行的 `fetched_at`，将两项排除为 `S3_EVIDENCE_EXPIRED`。第二次 Gate 为 `NEED_MORE / EVIDENCE_INSUFFICIENT`，持久诊断降为 `INCONCLUSIVE`。
2. **实际影响是 S3 用户重新调查可能无法取得与当前事实一致的诊断。** 等待中的状态可能被显示为证据不足；在需要联系接收方或回调运营人员的情形，缺少被排除的投递/接收事实也可能阻断相应处理方向与交接资格。本轮实际验证的是 WAIT 情形；后两种业务状态的相同后果是由同一 Gate 路径推断，未在本轮另行运行。
3. **最小正确修复应落在 Domain 的 Evidence 当前性判定与 Observation 来源关联。** 不要修改旧 Evidence 的 `fetched_at`，也不要关闭 TTL 或为了“刷新”而改变内容去重。D2 已把每次成功工具结果（包含该次 `observed_at`）写入 `d2_tool_observations.result_json`，并通过 `attempt_id` 可关联可信 Run。S3 Gate 可以在对应 Run 内验证成功 Observation、工具名、Evidence 内容/版本关联后，用该 Observation 的时间判断本次取证新鲜度；持久诊断复核则限定在诊断原 Run，避免后续查询让旧诊断复活。Evidence 行继续作为不可变、按事实内容去重的审计事实。

## S3 复现证据

修正后的复现记录位于 `runs/TRACE-red-02.jsonl`。样本标识：

- Task：`task-c9ee76eb-8203-496c-8597-49b6c49d67e8`
- 第一次 Run：`run-6ae1b9eb-7576-4a28-9001-a91b17663077`
- 第二次 Run：`run-a1c6ba1a-9857-4b8b-887b-4ab40b4c1d57`
- 受控时钟：`2026-10-23T15:40:42Z` → `2026-10-23T15:45:43Z`，差 301 秒；TTL 为 300 秒。
- 两次观察到的业务版本相同：`config=1, contract=1, delivery=2, grant=1, order=2, policy=1, principal=1, receiver=2, scope_policy=1`。
- 业务快照前后相同：订单 `COMPLETED/v2`；投递 `ACKNOWLEDGED/v2`；接收方 `QUEUED/v2`，SLA 为 3600 秒。
- 两次 HTTP Probe 都是 200，使用绑定的 `tenant-a / orders-async-demo / async-integration-a / async-principal-a`。Request ID 分别为 `1b227dc2a75c54e8` 和 `cc347b72015a3bdc`。
- 第二次仍产生三条新的成功 MCP Observation。`s3_order` 因新 HTTP Request ID 得到新 Evidence ID；内容不变的 `s3_delivery` 与 `s3_receiver` 分别复用 `evidence-f3350951-bc7c-4cd9-95eb-1ae47da00ac9` 和 `evidence-74aca6c0-5c13-4f1c-a100-91b996cb6b0a`。它们的 Evidence `fetched_at` 仍是第一次观察时间。
- 第二次 Gate：`NEED_MORE`，缺少 `s3_delivery`；排除上述两个旧 Evidence，原因均为 `S3_EVIDENCE_EXPIRED`。`persist_s3_diagnosis` 保存的第二条诊断为 `INCONCLUSIVE`，原因 `S3_INSUFFICIENT_CURRENT_FACTS`。
- `d2_tool_observations` 的第二组三条记录仍为 `status=OK`、`progress_added=0`（两个重复事实）。其 `result_json` 保存新的 MCP 事实和 `observed_at`；现有 S3 TTL Gate 没有使用它。表的 `created_at` 为 SQLite 默认当前时间，不随测试注入时钟推进，因此修复若使用该字段，测试时钟也必须与其来源协调。

首轮 `red-01` 原样保留。该轮的 Gate RED 同样出现，但业务快照查询未限定 tenant/service，取到了另一条同名 fixture 行，因此不把该轮“业务事实未变化”字段作为有效证明。已修正查询并以 `red-02` 重新运行；`red-02` 按 tenant、service、order 读取真实绑定行，前后快照相同。

## S1 / S2 范围检查

- **S1：存在同根代码路径风险，但本轮没有完成 S1 的 TTL 动态复现。** `record_tool_observation()` 对 D2 共享 Evidence 表按 task、fact type、resource 和内容 digest 去重；`evaluate_evidence_gate()` 对该 Evidence 的 `fetched_at` 执行 300 秒检查。S1 的静态集成配置、主体状态和认证策略在资源版本不变时可能复用旧 ID；Endpoint Probe 通常因新的 Request/Auth Event ID 而生成新 Evidence。若新的 S1 Run 再次使用这些静态事实，旧 `fetched_at` 可能导致 Gate 判定过期。该结论是由共享写入/判定代码路径推出，尚未通过 S1 真实端到端 TTL 用例证实。
- **S2：未发现与本次 S3 用例完全相同的跨 Run 故障，但有一个较窄的待验证边界。** `s2_diagnosis._run_evidence()` 按 Run 读取 Observation，并对同一 Evidence ID 选最新 Observation；Gate 对 Probe 和普通事实用 `observation_at` 检查新鲜度。例外是 `scope_authz_decision`，它明确使用不可变 `fetched_at`。正常新 Run 会先产生新的 Probe Request ID，匹配授权事实也随之使用新 Request ID，通常产生新的 Evidence ID；若同一 Run 对同一 Request ID 的授权事实在 TTL 后重查，是否会遇到相同问题仍未动态验证。
- 本轮另运行了三个窄回归：S1 相同版本重复 Probe、S2 最新 Probe 取代旧 Probe、S2 的 401/404/过期策略区分；均通过（3 passed）。这几项没有覆盖上述 S1 静态事实 TTL 或 S2 同 Request ID 授权事实 TTL 边界，不能据此宣称这些边界已被排除。

## 方法与限制

RED 测试使用真实本地 HTTP 服务和现有 in-process MCP Server 的 `call_tool()` 路径；没有模型调用、付费 Provider、fixture 直写 Evidence、业务写动作或交接。D2 与 S3 模块被注入同一个 `ControlledDateTime`，两边看到相同的 301 秒变化。fixture 业务快照只读取，没有在两次调查间修改。

源代码定位：

- `opspilot/domain/d2.py`：Evidence 内容摘要与去重、`record_tool_observation()`；`evaluate_evidence_gate()` 按 `fetched_at` 判定新鲜度。
- `opspilot/domain/s3.py`：`current_s3_evidence()` 按 `d2_evidence.fetched_at` 做 TTL 检查；S3 Gate 在 `evaluate_s3_gate()` 调用该函数。
- `opspilot/domain/s2_diagnosis.py`：Run-scoped `_run_evidence()`、Observation 时间选取和 `scope_authz_decision` 的时间例外。
- `opspilot/investigator.py`：S1/S2/S3 Investigator 将实际 MCP Observation 与 Evidence ID 关联；新 Run 的输入处理路径可影响哪些既有 Evidence ID进入 Gate。

没有执行全量 pytest；本轮不是修复或发布任务。全部原始日志、pytest 临时数据库、结构化 Trace 与 RED 测试均留在本目录。工作区仍在审查基线，正式业务源码无差异。

## 原始材料

- RED 测试：`RED/test_evidence_ttl_repeated_mcp_fetch.py`
- 第一次 RED（快照查询待修正）：`runs/red-01-pytest.log`、`runs/TRACE-red-01.jsonl`
- 第二次 RED（修正快照后稳定复现）：`runs/red-02-pytest.log`、`runs/TRACE-red-02.jsonl`
- S1/S2 窄回归：`runs/s1-s2-spotchecks.log`
- 命令、退出码与机器结果：`RESULTS.json`
