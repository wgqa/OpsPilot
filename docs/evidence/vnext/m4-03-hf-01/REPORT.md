# OpsPilot M4-03-HF-01 修复与验收证据

基线为 `main@30b1b466fbdd2c58e36c90b510ba04f7ee6af3d0`。本轮按单人流程直接在 `main` 实施，没有创建分支或 PR。冻结验收提交为 `bc4adb4f456737fef49827e8bd073887fcf5a17e`；源码和原始运行日志提交为 `e6aeab5e078f057b6afb6754deb217a973b153cd`；本报告、机器结果和逐项关闭说明作为后续证据提交。

这次修复只涉及 S3 的当前授权、诊断当前性和既有交接事务。S1/S2、M4-03 的业务 Gold、Knowledge/Memory 资产和已提交的历史回执格式没有改变。

## 第三方问题关闭情况

| 审查问题 | 修复 | 新鲜证据 |
|---|---|---|
| P1：撤销 Scope 后 MCP、诊断、Chat 和交接仍可能使用旧事实 | `get_s3_binding()` 现在通过同一 Domain 检查验证当前 Principal 状态、Integration 与 Accepted Credential 关系、Route Scope Policy、Principal Grant 和版本。S3 首次资源绑定、目录读取及后续 MCP 查询复用此检查。Evidence 版本新增 `scope_policy_version`、`grant_version`；HTTP 订单事实还必须关联当前版本的可信 ALLOW Authz Decision。缺失、格式异常或 Scope 不足均拒绝。 | `test_m4_03_hf_01.py`：Principal 禁用、凭证错配、Policy/Grant 缺失与变更、撤权、旧证据恢复、三种 MCP 事实工具、Web 资源读取和旧诊断交接。S3 定向组 `50 passed`。 |
| P1：撤权后历史回执边界不清 | 支持人员只在当前 S3 授权有效时读取当前诊断或其任务回执。撤权后，支持人员读取受限 S3 视图和提交重放会被拒绝；同租户 APPROVER 只能读取已经提交的不可变 Receipt/Queue 审计摘要，不能读取诊断事实或创建交接。授权恢复后，旧 Evidence 的 Policy/Grant 版本不匹配，仍不能恢复新交接资格。 | `test_historical_receipt_is_approver_read_only_after_scope_revocation`、`test_scope_restore_requires_new_evidence_versions`；原有响应丢失/重放测试仍在 S3 回归中。 |
| P2：SLA 内冻结的 WAIT 诊断跨过 SLA 后仍为 CURRENT | Gate 使用可注入 UTC 时钟计算接收 SLA 截止时间，并把 `valid_until` 冻结在诊断内。读取当前结果时重新计算 Gate；截止时间已到后，旧诊断返回 `INVALIDATED_BY_CURRENT_FACTS`、`S3_SLA_EXPIRED`，交接资格关闭。历史诊断和回执本身不被改写。新的受控 Run 重新读取 HTTP/MCP/SQLite 事实并得到 `CONTACT_RECEIVER_OPERATOR`。 | `test_receiver_sla_invalidates_wait_diagnosis_before_evidence_ttl` 固定 `accepted_at = now - 299s`，不用等待真实时间；随后把时钟前进 2 秒。验证旧页面提交被拒、Chat/Web 无资格、旧诊断字节和 digest 不变、新 Run 取得 CONTACT 诊断并成功交接。 |

交接与关键纠错、Task Abort、Scope 撤销使用各自 Domain 事务和独立 SQLite 连接竞争；合法事务按 SQLite 写锁顺序获胜，另一方拒绝或安全回放。相同诊断使用不同 `operation_id` 并发提交只产生一条 Queue、Receipt 和 S3 Outbox。首次写入仍在现有 `BEGIN IMMEDIATE` 事务内检查 TaskControl、当前授权和当前诊断，没有重写 TaskControl 或增加权限框架。

## 运行环境与命令

运行于 Windows 工作区，Python `3.14.0`，pytest `9.1.1`。项目锁定依赖见根目录 `pyproject.toml`；本轮不调用付费模型，也不更改依赖。

最终 S3/M4-02 定向回归命令：

```powershell
.\.venv\Scripts\python.exe -m pytest -q --basetemp docs/evidence/vnext/m4-03-hf-01/runs/s3-final-tmp tests/test_m4_03_hf_01.py tests/test_m4_03_s3.py tests/test_m4_02_s3.py
```

结果：`50 passed in 86.04s`。原始输出见 `runs/s3-final-01-pytest.log`。

S1/S2 安全回归命令：

```powershell
.\.venv\Scripts\python.exe -m pytest -q --basetemp docs/evidence/vnext/m4-03-hf-01/runs/s1-s2-security-tmp tests/test_d2_investigation.py tests/test_d3_actions.py tests/test_d4_recovery.py tests/test_m1_task_control.py tests/test_m1_hf_worker.py tests/test_m1_worker_recovery.py tests/test_m2_01_facts.py tests/test_m2_02_s2_diagnosis.py tests/test_m2_03_handoff.py tests/test_m4_01_dialogue_update_safety.py
```

结果：`104 passed in 82.22s`。最终全量命令：

```powershell
.\.venv\Scripts\python.exe -m pytest -q --basetemp docs/evidence/vnext/m4-03-hf-01/runs/full-pytest-rerun-tmp
```

结果：`292 passed in 284.02s`。原始输出见 `runs/full-02-pytest.log`。第一次全量运行是 `291 passed, 1 failed`；失败是边界测试夹具在准备过程中依赖实际墙钟，已固定接收时间与传输响应后重跑通过。原始失败保存在 `runs/full-01-pytest.log`。

所有验收命令、结果和完整日志索引见 `RESULTS.json`、`FAILURES.md` 与 `runs/`。`TRACE.jsonl` 是由这些真实测试结果提取的摘要，不添加合成请求 ID。测试临时数据库不纳入提交；既有 `开发目录/` 和其他预存未跟踪材料没有加入暂存区。

## 已知边界

- S3 仍是本地 SQLite Demo，结果不代表生产级 IAM 或远端回调平台能力。
- MCP 撤权回归通过实际注册的 MCP Server `call_tool` 接口运行；本轮没有另起 MCP stdio 子进程，也没有调用外部 Provider。
- 诊断过期只改变其当前性展示和新交接资格；不可变诊断、历史回执及审计记录保留。

本报告是交给主 Agent 的验收候选证据，不替代其独立验收。提交推送后停止开发。
