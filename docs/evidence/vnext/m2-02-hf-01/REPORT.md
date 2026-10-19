# OpsPilot vNext M2-02-HF-01 修复报告

状态：实现与本轮验证已完成，等待主 Agent 独立验收。此报告不宣称 M2-02 整体验收通过，也不授权进入 M2-03。

## 基线和提交

- 开发起点：`main@f75eb8b4ee209c0578395543f5a6f679504b2edc`
- 冻结验收标准：`313dbe703de9c4d81ecc0069f689e935689199bf`，先于 HF RED 和实现提交。
- 核心修复：`b102454`（G6 意图边界、有界调查、H 候选消费与定向测试）；其后为 TTL 测试夹具、Domain Trace 字段对齐及 G8 评分器修正。固定真实 R/H/A Release 的应用代码提交记在 `runs/release-ee94eac/RELEASE.json`：`ee94eacbeadd03b08a979e29596714afe840936e`。
- 最终计分器提交：`20624cffea1f00f4aa80bf7c1153a1f2d657ab0f`。该次重评只读同一组已保存的 48 条 Release Trace，没有重跑 Provider 或 MCP。
- 本报告、最终机器结果和索引随最终证据提交一并进入 `main`；最终提交 SHA 由交付消息给出。

## 结论

HF-A 至 HF-D 的限定实现已完成。新鲜全量 pytest 为 **171/171 通过**；真实 Microsoft Edge 闭环、DeepSeek Provider、MCP stdio、loopback HTTP 和既有 S1 401→200 smoke 均有本轮证据。独立对照 Release 分母固定为 48，最终按修正后的评分器重评：R **16 PASS / 0 FAIL / 0 PARTIAL**，A **16 / 0 / 0**，H **2 / 12 / 2**。三种策略的 Control Safety 与 Boundedness 均为 **16/16 PASS**。

H 的正确处理只有 4 PASS / 12 FAIL；证据完整性是 2 PASS / 14 PARTIAL。常见情况是归一化结果把用户线索标记为高不确定性，策略确实据此请求澄清，安全上正确，但在冻结 holdout 的任务效用评分中未完成诊断。这个差距如实保留；本协议不要求动态 Agent 胜过规则策略，也不把 H 宣称为通过。

旧 M2-02 的 48 条冻结结果仍是 **45 PASS / 1 FAIL / 2 PARTIAL**。`LEGACY_SHA256.json` 中六个旧 Gold、Rubric、Results、Report、Failures、Trace 文件的 SHA-256 均再次校验为一致，没有回写或重算旧评测。

## HF-A：越界意图和 G6

修复将“想查询其他服务/主体/集成”的肯定越界意图与否定句、历史引用、说明性讨论及混合目标分开处理。肯定的未绑定目标在任何 Provider/MCP 调用前安全停止；不泄露其他资源是否存在。否定/引用不会因为关键词而误杀；混合意图只澄清不明确部分或推进明确绑定任务内的只读步骤。常见同义表达覆盖于定向测试。自然语言始终不能覆盖可信 TaskBinding、Scope、Gate 或授权。

原版 RED 与逐次 GREEN 见 `runs/development-logs/` 和 `runs/green-dev-*.txt`；对应测试在 `tests/test_m2_02_hf_01.py`。

## HF-B：10,003 次 NEED_MORE 的原因及有界停止

历史 `20261019-browser-01` 记录了 10,003 条 Gate Trace，均为 `NEED_MORE / S2_EVIDENCE_STALE_REQUERY_ALLOWED`；记录中的 MCP/模型预算已分别达到 6/8。Run 在 `RUNNING` 与 `INTERRUPTED_RECOVERABLE/WORKER_RUN_FAILED` 间反复变化。历史日志没有 Worker 异常堆栈和逐 Gate Run ID，因此无法确认最初的 Worker 异常触发点；报告不把推断伪装成确定原因。

现有证据能确认的循环机制是：Gate 允许 stale/no-progress 重查，但预算耗尽后没有将无进展状态稳定终结；Graph 重放又使用随机 Trace ID，产生重复 Gate 记录。另一个实现问题是工具策略查询未带同 Run 的 Probe 观察时间，导致一个刚完成的 Probe 被误判为 stale。

最小修复为：把同 Run Probe 时间用于策略当前性；只有仍有合法且可执行的增量动作时才继续 `NEED_MORE`，无进展、无合法动作或预算耗尽即持久结束为 `INCONCLUSIVE`；模型和 MCP 原预算保持 8/6，不提高上限；Gate Trace 使用确定性身份并以每 Run 64 条硬限制收尾。测试覆盖 stale/错误 Request、no-op、预算边界、版本冲突、崩溃恢复和 Trace 幂等。原 10,003 条记录仅作为历史诊断证据，不复制为通过的故障注入结果。

## HF-C：真实浏览器纠错、调查与只读追问

Microsoft Edge 的新鲜旅程在同一浏览器会话和 Task 中完成登录、初始调查、正式关键纠错、新 Run、真实 Provider/MCP 查询、Receipt/Draft 生成及只读结果追问。浏览器 Trace 在 `runs/browser-e2e-final-752173a/`：

- 初始 Run `run-5c70e2bd-ecc0-4a3d-aa40-d2d2c9a07e78`，Request ID `94f8d87c2a8a04cf`。
- 正式纠错来自 Message sequence 2；应用控制版本为 2。纠错后 Run `run-6f370cf8-2037-4d27-a2df-9798d4bd7912` 使用不同的 Request ID `2db9734a1ddeae2f`，并重新产生匹配的 Probe 与授权查询。
- 新鲜业务事实是 HTTP 403、`AUTH_ACCEPTED`、缺少 `orders.read`、Domain 授权决定 `DENY/SCOPE_INSUFFICIENT`。结果为当前 `HANDOFF_READY` DiagnosisReceipt 与冻结 Draft；Task `WAITING_HANDOFF`，`submitted=false`，未创建 HandoffReceipt/Queue。
- 结果追问经独立 `CHAT_READONLY` Run 成功；前后可信业务投影相同。没有 Plan、Approval、ActionIntent、Ledger 或 Scope/Grant/Policy 写入。
- 截图：`screenshots/01-initial-diagnosis.png`、`screenshots/02-formal-correction.png`、`screenshots/03-corrected-diagnosis-draft.png`、`screenshots/04-readonly-result-followup.png`。浏览器网络/交互记录见 `screenshots/browser-trace.json`；Provider、MCP、SSE、Run、Event 与 Domain 快照在同目录 `RESULTS.json` 的 `browser_trace` 和 `domain_trace` 中。

`browser-e2e-final-6299ff2/` 中的第一次重跑因验收脚本对否定措辞的断言过严而失败，原始失败已保留；随后调整为按句义核对，并由 `browser-e2e-final-752173a` 实际通过。更早浏览器失败也全部保存在 `browser-e2e-01` 至 `browser-e2e-04`、`browser-e2e-final-ce9b790`，没有从索引中隐藏。

## HF-D：归一化线索影响合法策略

H 使用带版本的严格 Schema 验证模型归一化结果。候选内容保持不可信：例如 `uncertainty=high` 实际被策略读取并改变为 `ASK_FOR_CLARIFICATION`；通过验证的 Request ID 仅当与同一 Run 的新鲜 Probe 匹配时，才收窄到该 Request 的只读授权事实查询。候选不会进入 Evidence、Gate 决策或授权字段。Trace 记录 `consumed_fields` 和 `policy_action`，定向测试验证其影响是实际策略行为而非仅写入日志。

48 条 H 评测显示此策略目前过于保守，很多案例停在澄清阶段。该效用局限保留在 RESULTS 与每条 Trace 中，未通过调高预算、修改 Gold 或挑选样本来掩盖。

## 真实运行和回归

| 验证 | 结果 | 原始证据 |
|---|---|---|
| 冻结 HF 定向测试 | 15 passed；之后补充 G8 否定/非证明措辞测试 4 passed | `runs/green-dev-18-targeted-pytest.txt`、`runs/green-dev-25-g8-nonproof-pytest.txt` |
| 全量 pytest（最终源代码） | **171 passed in 132.17s** | `runs/full-pytest-20624cf.txt` |
| Vue/TypeScript 生产构建 | PASS，Vite 8.3.4 | `runs/frontend-build-final.txt` |
| Microsoft Edge Provider/MCP Web 端到端 | PASS；正式纠错、新 Run、Request 关联、Receipt、Draft、只读追问 | `runs/browser-e2e-final-752173a/` |
| 真实 MCP stdio | PASS；tools/list、工具调用、403 事实、同 Request 授权决策及越界负例 | `runs/mcp-stdio-s2-final.txt` |
| 既有 S1 业务 smoke | PASS；同绑定调用方 401 (v7/cred-v1) → CAS 后 200 (v8/cred-v2)；DISABLED 仍 401 | `runs/s1-smoke-final.txt` |
| R/H/A 独立对照 Release | 48/48 实际试次；重评修正计分器的 G8 否定误判 | `runs/release-ee94eac/`、`runs/release-ee94eac-rescored-20624cf/` |

可复跑命令（本地 Provider 配置和项目 venv 已就绪时）：

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_m2_02_hf_01.py tests\test_m2_02_hf_01_release.py --basetemp=.runtime\hf01-targeted
.\.venv\Scripts\python.exe -m pytest --basetemp=.runtime\m2-02-full-20624cf
npm.cmd run build --prefix frontend
.\.venv\Scripts\python.exe -m opspilot.smokes.m2_02_hf_01 --evidence-dir docs/evidence/vnext/m2-02-hf-01/runs/browser
.\.venv\Scripts\python.exe -m opspilot.smokes.m2_02_hf_01_release --runtime-dir .runtime\hf01-release --evidence-dir docs/evidence/vnext/m2-02-hf-01/runs/release
.\.venv\Scripts\python.exe docs/evidence/vnext/m2-02-hf-01/rescore_release.py --source-results docs/evidence/vnext/m2-02-hf-01/runs/release-ee94eac/RESULTS.json --output-dir docs/evidence/vnext/m2-02-hf-01/runs/release-rescored
.\.venv\Scripts\python.exe -m opspilot.smokes.m2_s2_mcp
.\.venv\Scripts\python.exe -m opspilot.smokes.s1
```

Release 锁定依赖、Provider 型号/端点主机、提示/工具/知识/Skill 摘要、依赖锁摘要和 48 条每次试验所携带的 Token/耗时字段记录于 `runs/release-ee94eac/RELEASE.json` 与 `RESULTS.json`。无 Token 返回的试次以 `null` 留空，不作补值。本次 48 条中 30 条提供 Token 数据，可用 `total_tokens` 合计 181,893；剩余试次的 Token 数据不可得。

## 安全边界和限制

- S2 运行期 Scope/Grant/Policy 写入为 0；HandoffReceipt/Queue 写入为 0；`SCOPE_ESCALATED` 和 `REPAIRED_VERIFIED` 不作为本轮结果。
- 未新增 HandoffReceipt、Queue、Scope 自动授权、Memory 平台、多 Agent 或 M2-03 功能。
- Provider 轨迹中的模型答案不能单独授予授权；Domain Evidence、Gate 和 TaskBinding 仍是可信事实来源。
- 本次浏览器和 Domain 是本地演示环境，不能推导生产级 IAM 能力。
- H 的诊断效用仍未达到冻结 Gold 的多数正确处理要求，必须在主 Agent 评审中作为明确遗留项审阅。

完整目录索引见 `RUN_INDEX.md` 和 `TRACE.json`；失败来源见 `FAILURES.md`。源码学习材料见 `docs/learning/vnext/m2-02-hf-01/`。
