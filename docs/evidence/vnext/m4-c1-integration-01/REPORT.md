# C1 最终整合记录

**状态：** 按主 Agent 已签署的 `ACCEPT_WITH_LIMITS` 完成授权合并；本报告是实施方整合记录，不是新的主 Agent PASS。

## 基线、读取与合并范围

- Repo：`wgqa/OpsPilot`；原远端 main：`77ea80e87e538f0f1fae8118ef231ec622601755`。
- 正式受验、开工核对及实际合入的候选均为 `f6db02b331ce4279ce0b00063bf19b917af423ff`，分支 `codex/m4-autonomy-c1`。远端 main 已从原基线 fast-forward 到该 SHA；没有新建合并提交。
- 在新建的干净 detached 工作树 `C:/Users/tu me manques/.codex/worktrees/c1-approved-integration-20261025/agent新项目` 集成。此前各工作区的用户未提交文件、开发目录和本地 main checkout 均未切换、覆盖或清理。原主工作区本地 main 仍为 `add47ec83f31fa76b9b6a5782e013311732bc496`；不要把它误认为远端 main。
- 从受验提交实际重读 North Star、AGENTS、C1 FROZEN/REV1、FIX-01、HF-01 及最终接线冻结合同和相关限制。两规则 Blob 为 `1f737712c7a36ceb34433ac09c3fbba3c3305542` / `30319000ed0054007e9b7b6b46bf98b1493c8179`。候选没有 `.agents/skills/opspilot-slice-review/SKILL.md`，未声称执行该 Skill。
- `77ea80e..f6db02b` 含 27 个提交，其中已有合并 `b133e895b01c390767cf5e95df760dcaf0be7688` 的第二父为原 main。实际 Diff 是 247 文件：227 新增、20 修改、0 删除；17,287 插入、47 删除。变更为 C1 前端、路由、Schema v15、Context 接线及兼容测试和四处 C1 证据目录。
- 按 Git blob 核对原基线的 3,218 份文档/规则，修改或缺失数为 0；现有 Gold、baseline、handoff、历史 RED、失败记录和原始证据保留。详见 `runs/preservation.json`、`git-file-status.log`、`git-commit-history.log`。

## 检查与新鲜复跑

完整 `git diff --check 77ea80e..f6db02b` **退出 2**，没有把它写成通过：162 项空白告警（158 个尾随空白、4 个 EOF 空行）。除两个新增测试文件的 EOF 空行外，均属于冻结 Markdown 或原始测试日志。`opspilot/` 与 `frontend/` 检查退出 0；源码/前端/测试未发现冲突标记，index 没有未合并项。未规范化原始证据，也未修改受验 SHA。完整输出在 `runs/git-diff-check.log`，测试空行在 `git-test-diff-check.log`。

合并后在同一干净来源树新鲜执行：

| 检查 | 实际结果 | 证据 |
|---|---|---|
| 完整 pytest，唯一排除冻结的实现前 RED | **343 passed, 1 deselected**，304.55 秒，exit 0 | `runs/pytest-full.log`、命令及退出码 |
| `npm ci --no-audit --no-fund` | 140 个锁定包安装完成，exit 0 | `runs/npm-ci.log` |
| `npm run build`，含 `vue-tsc --noEmit` | 类型检查与 Vite 生产构建通过，exit 0 | `runs/frontend-build.log` |

唯一排除的用例为 `test_explicit_protocol_followup_is_accepted_as_same_task_readonly_run_before_ttl_fix`；它是明确保留的实现前 RED，其断言及历史失败未修改，其他测试仍执行。没有通过减少正常回归分母制造绿色结果。

Python 复用候选已有 `.venv` 的锁定依赖，`PYTHONPATH` 和实际导入路径指向新集成工作树；这不是独立机器或重新安装 Python 依赖的证明。Python 3.12.14、pytest 9.1.1、LangChain 1.4.1、LangGraph 1.2.16、MCP 2.3.0；Node 24.16.0、npm 11.13.0。确定性子进程只注入非密钥模型配置占位值。完整环境和命令保存在 `runs/`，没有复制 `.env` 或输出凭据。

全量测试包含既有 C1/S3/Context、TaskControl、M1-HF、S1/S2 安全以及本地 HTTP/MCP/跨进程集成回归；**不等于新鲜真实 Provider 或浏览器旅程**。本轮未新跑付费模型、Web E2E 或生产外部系统，未将历史真实轨迹冒充本次运行。

一个旧测试固定向历史 `behavior-red-trace.jsonl` 追加了 1 条观察。本轮先核对它是受验内容的纯追加，将新行保存为 `runs/fresh-pytest-observations.jsonl`，再将此干净副本恢复为受验历史内容；原始历史文件没有进入本轮 Diff。核验记录在 `runs/trace-preservation.json`。测试临时数据库放在工作树旁的专用 `pytest-integration-01` 中，没有清理其他目录。

## 限制与下一工作提案

沿用已接受的限制：HF-01 真实旅程最后一次当前状态补查取得了新 Observation，但自然语言结果仍为 `PARTIAL / FOLLOWUP_BUDGET_OR_PROVIDER_EXHAUSTED`；历史 E2E-02/E2E-03 失败和错误 `ANSWERED` 质量样例保留；一个历史非 API 404 仍未定位。本轮整合不追加产品修补，不扩大预算。SQLite/回环 HTTP/演示角色不证明生产 IAM 或外部接收系统可靠性。

[订单回调连续自主调查提案](../../../proposals/ORDER_CALLBACK_CONTINUOUS_INVESTIGATION.md)仅为 `DRAFT_FOR_MAIN_AGENT_REVIEW`：最小追加式 Transport Attempt 事实、6 对拟议业务 Gold（其中 2 对留出）、合法自主调查选择、答案标准和公平 R/H/A。当前只读快照不足以证明每次回调历史；本轮未实现表、历史工具、Planner、Goal Manager、Runtime、调查循环或预算变更。

## 六项收尾与停止线

1. **用户变化：** 已接受的 C1 连续只读补查与来源续接进入远端 main；整合本身不增加新能力。
2. **Agent 决策：** 保留既有模型对解释/调查及合法只读行动的选择；本轮没有新的 Agent 行为。
3. **观察驱动：** C1 当前/历史来源边界保持，下一提案以真实 Event/Attempt 差异驱动不同补查，尚未实施或验证效果。
4. **新增约束：** 无产品硬限制；授权、TaskControl、只读不写 Diagnosis/回执及预算的既有双向回归继续通过。
5. **简化结果：** 复用已验收实现和现有测试，整合后只新增报告、原始运行证据和待审提案。
6. **证据与停止线：** 新鲜 343 项 pytest、前端构建及 Git blob 核验由实施方执行；不冒称主 Agent 独立复跑。合入依据是用户传达的 `ACCEPT_WITH_LIMITS`，本轮结束，不启动 C2/C3。

包含本报告的后续 main 提交仅为文档与证据，最终提交 SHA 以交接消息和远端引用为准；受验业务源码始终固定在 `f6db02b`。
