# R2-AR04-COMPACTION-C06-HF-01

**Status:** `ACCEPTANCE_CANDIDATE`
**Base:** `d3f197f7ddbfb41e9d35c83a3b6cb5352f1e57d0`
**Branch:** `codex/r2-ar04-compaction-c06-hf01`

## 根因与修复

冻结的 C06 Trace 中，14 轮合成会话的第一条 User 材料进入 `ROLLING_SUMMARY`。初始 `probe.context()` 调用 `chat._prepare_context()`，需要 6,176 tokens 的首批摘要材料，但摘要输入上限为 6,000。它抛出 `ContextBudgetExceeded(SUMMARY_SOURCE_EXCEEDS_COMPRESSION_BUDGET)`。这发生在 `_run_assistant` 普通执行错误处理边界外，异常落到 Worker 通用错误分类，Run 因而记为 `WORKER_RUN_FAILED`，且没有可读的预算说明。

`opspilot/assistant.py` 现在只在首次 `probe.context()` 边界捕获 `ContextBudgetExceeded`，用原有 `_close_terminal_assistant_failure` / Domain 限制记录路径终止 Run，并保留具体错误码和预算值到 Trace。普通异常仍由既有通用失败路径处理。`_assistant_failure_notice` 为此错误码生成简短程序说明，指出本轮没有模型答复、原始消息保留且未被静默删改，并明确程序没有完成调查或业务处理。

本补丁不让超长 User 消息成功摘要，也不修改压缩分块或算法。修复后 C06 仍安全失败，但错误可识别、可见、幂等；没有模型调用、压缩尝试、Answer 或业务动作。

## 证据与结果

- 修复前 RED：`RED_REPRO.txt` 和 `RED_REPRO_TRACE.json` 使用冻结审计 harness 的 `_run_case`，实际 Domain/Worker 重放同一合成材料。它记录 `WORKER_RUN_FAILED`、内部错误 `6176 > 6000`、0 个目标 Run 模型调用、0 次压缩及 0 条程序通知。
- 冻结原始 Trace：`docs/evidence/r2-ar04-compaction-audit-01/case_traces/C06_USER_OVERSIZE.json`。首条消息正文 Digest 为 `289865aa0634a87f4391ae65cf4a68d07a3e1ab9fdb02e4f6699db758e090f78`。
- 修复前测试 RED：`RED_TEST_RUN_T01_FINAL.txt` 显示原实现实际返回 `WORKER_RUN_FAILED`，与稳定预算码断言不符。其他历史尝试记录也保留；仅修整了终端渲染的行尾空白，测试内容与结论未变，且未算作通过。
- 修复后 Fixture 测试：T01 在真实本地 API/Worker/Domain 路径中保留相同正文和 Digest；目标 Run 以 `SUMMARY_SOURCE_EXCEEDS_COMPRESSION_BUDGET` 结束；0 个模型调用、0 次压缩、0 个 Answer、无 delivery attempt；实际消息接口返回一条 `PROGRAM_LIMIT` 说明。Run 关闭重放后，通知和事件仍各只有一份。
- T04 对照：同一审计生成器的长 Assistant 历史仍成功完成两次压缩、3 次 Fixture MODEL 调用并提交 Answer；原长 Assistant 消息 Digest 与冻结 Trace 相同。
- T05 短对话正常得到 Fixture 答案。T06 `RECENT_WINDOW` 未创建 Summary，实际模型输入选择消息序号 18–29（12 条）。T08 注入普通 `RuntimeError` 后仍报告 `WORKER_RUN_FAILED`，没有被误报为压缩预算错误。
- T07 来源失效、取消、UNKNOWN 与重放回归均由既有测试覆盖并在同一测试命令中通过。完整用例状态见 `RESULTS.json`。

所有生成结论来自 Fixture、Domain/API 实际运行或 Mock 注入断言；自然语言提示的语义检查由确定性子串断言完成，未声称真实模型记忆或 Provider 效果。19 项目标测试通过；完整全仓测试未运行。

## 外部活动与限制

- Fixture MODEL 调用：依用例而异；T01=0、T04=3、T05=1、T06=1、T08=0。详情见 `RESULTS.json`。
- 真实/付费 Provider：0，`NOT_RUN`。
- 实时外部 MCP / 外部 `tools/call`：0，`NOT_RUN`。
- 外部业务写入：0，`NOT_RUN`；程序失败说明及失败事件仅是本地 Domain 记录。
- 浏览器自动化：0，`NOT_RUN`。
- 完整 700+ 测试套件：`NOT_RUN`。

修复前 RED 与历史审计材料保持独立；原始审计 Trace、历史 `RESULTS.json`、C06 RED 和既有测试记录没有改写。未改变 6,000/512 Token 参数、最近 12 条窗口、策略触发条件或 Domain 授权语义。

## 冻结基线读取记录

以下文件均从 Base `d3f197f7ddbfb41e9d35c83a3b6cb5352f1e57d0` 读取，并核对其 Git Blob：

- `PROJECT_NORTH_STAR.md`: `43dabda468506717c6956e676dfad4304c4f38e6`
- `AGENTS.md`: `807b928686a4dd2cac7b15b3c354b9943c93c910`
- `.agents/skills/opspilot-slice-review/SKILL.md`: `d405c8d413d633824b279202cc1503dab4cf0b03`
- `docs/learning/OPEN_SOURCE_AGENT_REFERENCES.md`: `890ddf8918f976401c4df849eda6394770ed1997`
- 冻结审计 `RESULTS.json`: `ece761f81ca2357c4007738f9ed1d06098a02187`
- 冻结 `C06_USER_OVERSIZE.json`: `4ed598187bfe25ad27be955235b165368a798f91`
- 冻结 `C06_ASSISTANT_EXCERPT.json`: `0df804c21f49cfd03e771897e3190f6d532cf668`
