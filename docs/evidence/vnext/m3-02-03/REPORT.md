# M3-02 + M3-03 实施与证据报告

**状态：PARTIAL，等待撤销后的新请求与恢复验证及主 Agent 独立验收。** 本报告不自签 PASS。M3-02 的 Context Engineering 与 M3-03 的最小 Semantic Memory 已进入代码和自动化回归；候选创建、独立 APPROVER 确认、Task B 的真实浏览器 Provider/MCP 使用均已完成。撤销后的后续模型调用和跨进程恢复尚未完成。

## Git 与冻结顺序

- 任务卡基线：`main@5ade2b5deedbb3704b09e9d6fbbfbffa3ab8deb8`。
- 冻结标准：`3cb826d`，文件见本目录 `ACCEPTANCE_PLAN.md`、`TEST_MATRIX.json`。
- M3 RED：`48be70422f03b567b09a6bd45efc42d7a98ad598`。
- M3-02 实现：`f9f9d8a7c724a477578ff9eed2a48f4972078ee0`。
- M3-03 实现提交：`a0ac67836c5dc641d316628689621c986e91b57a`。本次证据包会单独提交；真实 Task B 未完成，验收状态继续标为 PARTIAL。
- 本地 `AGENTS.md`、`PROJECT_NORTH_STAR.md`、`开发目录/` 和其他历史 pytest 临时目录均未纳入本轮暂存范围。

## M3-02 结果

Context Builder、按模型配置生成 Token 预算、结构化块优先级、Recent Window / Rolling Summary / Hybrid、Summary 依赖及来源复核、Chat/Investigator Context Manifest 和 Web Inspector 已实现。摘要仍是可重建的非权威派生内容；TaskControl、Domain、MCP Evidence、Gate、审批、Ledger 与 Checkpoint 保持原权威边界。

最新保存的 M3-02 主线回归为 `215 passed, 1 deselected`。被排除的是当时尚未实现的 M3-03 语义记忆存储 RED 项，见 `runs/verification-01/full-pytest-m302-core.log`。M3-03 合入后首次全量为 `222 passed, 1 failed`；失败来自旧 M3-01 测试仍 monkeypatch 已替换的查询符号。更新测试替身并兼容缺省 applicability metadata 后，新鲜完整 pytest 为 `223 passed`，日志见 `runs/m303-final/pytest-full-final.log`。首次失败原始日志保留在 `pytest-full-episodic.log`。

真实 DeepSeek `deepseek-flash` 的同源策略对照保留在 `runs/strategy-comparison-03/TRACE.json`：Recent Window 成功，Provider 实际用量 1,123 输入 + 1,676 输出 = 2,799 Token，耗时 21,088 ms；Rolling Summary 失败为 `CHAT_ATTEMPTS_EXHAUSTED`，记录 6,020 Token；Hybrid 也以该状态失败，记录 4,640 Token。后两者均先遇到一次 `RuntimeError`，随后各有两次摘要调用成功，但没有完成最终聊天回答。压缩策略效用为 `NOT_PROVEN`，没有把这些失败隐藏或改写。

真实 Web 长会话记录为 26 轮、21 个成功 Run、5 个失败 Run；保留的失败原因包括 `CHAT_ATTEMPTS_EXHAUSTED` 与 `SUMMARY_SOURCE_EXCEEDS_COMPRESSION_BUDGET`。本轮可确认预算确实触发压缩和安全停止，但不能把体验描述为全程稳定。刷新/恢复曾执行；独立进程 PID 与 Run 的完整关联没有保存成可复核原始 Trace，因此 CTX-07 的真实跨进程 Web 证据仍为 `UNVERIFIED`。

S1/S2 回归保留在 `runs/verification-01/`：真实 S1 从 v7/401 到 v8/200，同 integration、principal 和业务 route；主体禁用负例仍为 401。真实 MCP stdio S2 记录 403、`SCOPE_INSUFFICIENT`、关联 request ID 和跨作用域拒绝。最新全量 pytest 覆盖原 M1/M2/M3-01 回归。

## M3-03 结果

M3-03 在真实 v9 Schema 上向前迁移至 v11，增加项目 Semantic Memory、事件、幂等命令和显式项目 APPROVER 授权表；迁移可重复，旧 Episodic Memory 行和事件保留。新候选只能从同 Task 持久化用户消息创建，候选不进入模型上下文；同租户且具有目标项目显式授权的 APPROVER 才能确认。确认后的 Semantic 内容可进入不同 Task 的 Chat 与 Investigator Context，并以非权威 Guidance 记录 Provenance。修订、撤销、到期及来源失效由 Domain 状态和事件审计控制。

真实 Task A `task-9444df29-9e21-4b7f-9b26-df6ff17cf123` 经 Web 创建；真实 DeepSeek 产生 5 个 Provider 响应，其中 4 个调用 `probe_endpoint`、`get_auth_policy`、`get_integration_config`、`get_principal_status` 并返回 MCP 观察。Task A Run 到达 `WAITING_APPROVAL`。Support 在 Web 创建候选 `semantic-8669bb64-f2b1-41a9-ae9c-10c3ef5a7626`；用户随后在独立 `approver-a` Web 会话确认。Domain 当前记录为 `ACTIVE v1`，创建者 `support-a`、确认者 `approver-a`，事件为 `CANDIDATE_CREATED` → `CONFIRMED`。完整脱敏记录见 `runs/m303-final/TRACE-task-a.json`。

本轮额外完成 Episodic 检索理由与排除 Trace：选择按同租户/项目、Task 不同、问题类型、服务、状态、有效期、内容摘要和来源回执检查；默认仍选 1 条以保持既有风险上限，调用方最多可显式选 3 条，扫描上限为 100 条。Inspector 现在展示选用理由和同项目内未选记录的原因。当前 MCP Evidence 与确定性 Gate 仍优先，Episodic/Semantic 只提供历史方法提示。

本轮在本地隔离 Domain 克隆上通过真实浏览器创建 Task B `task-7379b52e-d364-4836-84e5-579e5d3aad31`，Run `run-733ea4a7-56c8-4679-a899-02dbb914427a` 到达 `WAITING_APPROVAL`。真实 DeepSeek `deepseek-flash` 共 5 次调用、18,731 Provider Token；TaskBinding 范围内真实 MCP stdio 共 4 次成功查询，分别读取 Endpoint Probe、Principal、Auth Policy 与 Integration Config。5 份 Context Provenance 均记录了来源 Task A 的 `semantic-8669bb64-f2b1-41a9-ae9c-10c3ef5a7626 v1`。Task B 用户声称 403，但实际 Probe 为 401，Gate 仍为 `AUTHENTICATION_FAILURE_REMAINS_S1`；调查维持 S1，Plan 等待独立审批，没有 REPAIR、DELIVER 或 Scope 写入。脱敏轨迹见 `runs/m303-final/TRACE-task-b.json`。浏览器截图已在本轮交互中捕获并显示，但尚未写入证据目录。

**未完成门禁：** Task B 的真实 Provider/MCP 与跨 Task Provenance 已核实；仍未在 Web 撤销该经验，也未验证撤销后新模型调用及 Worker 跨进程恢复不会再次加载它。原始主数据库中的第一次 Web Task B (`task-8f2720b8-72b4-4e67-9fad-bae863de3c1d`) 因 `WORKER_RETRY_EXHAUSTED` 阻断且 0 Provider/MCP 调用，失败记录保留，根因没有被证实。成功的 Task B 使用主数据库的隔离克隆及当前源码服务，不能替代撤销与恢复门禁。浏览器截图在交互中已捕获，但没有保存成仓库文件；保留了浏览器可访问性状态、Domain 审计和脱敏 Provider/MCP Trace。

## 最新验证与运行环境

最新保存的专项日志：`runs/m303-final/pytest-episodic.log`（13 passed）、`pytest-m301-red-compat.log`（1 passed）以及 `frontend-build-episodic.log`。M3-03 新增语义测试 6 项；Episodic 检索新增测试覆盖多候选、最大选择数及条件不匹配排除理由。

依赖和命令记录在 `runs/m303-final/environment.txt`、`pytest-full.command.txt` 与相邻日志中。当前已记录 Python 3.14.0、FastAPI 0.137.1、LangGraph 1.2.16、langchain-core 1.6.12、tiktoken 0.14.0、pytest 9.1.1、Pydantic 2.14.1、Uvicorn 0.49.0；没有记录 Provider 未返回的金额成本。

具体逐项矩阵见 `RESULTS.json`；全部原始 RED、失败及修复过程见 `FAILURES.md` 和 `runs/`。本轮没有进入 M4、S3、新业务工具或通用 Memory 平台。
