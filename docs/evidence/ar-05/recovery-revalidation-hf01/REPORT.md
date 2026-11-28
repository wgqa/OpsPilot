# AR-05-RECOVERY-REVALIDATION-HF01

**ACCEPTANCE_CANDIDATE**

## 开工核验

| 项目 | 核验结果 |
| --- | --- |
| Repository / Branch | `wgqa/OpsPilot` / `codex/ar05-recovery-revalidation-hf01` |
| 远端基线与开工 HEAD | `codex/ar05-integrated-acceptance-prep-01@6cf71f161ca42759daacb928fb45302c55aa60f6` |
| 远端 main | 开工和回归结束时均为 `60eee87bfe3cca522011316cb4cd2c0064ad291b`，是基线祖先 |
| 实施 Diff | 基线以上七个测试文件与本目录证据。生产源码、Schema、锁文件和治理文件的 Diff 均为空 |
| `PROJECT_NORTH_STAR.md` | 已读，Blob `e36f2f75509738551ac6d4a2de5b4f9cf44a7991` |
| `AGENTS.md` | 已读，Blob `f174a6ab7f23f9e6d8b3ef98d455b99a75193143` |
| 项目评审 Skill | 已读，Blob `d405c8d413d633824b279202cc1503dab4cf0b03` |
| D4 历史合同与 E04–E09 | 读取 v1.0 baseline 第 4、6、7 节及 D4 报告，Blob `30e18d7ddbade7cdf7712d035d6fd8488bcb9676` / `5723955489a019ae02044dd2c233eb40b11bb3c0` |
| M2-02 Deferred Gates | 已读，Blob `2536030b5b942bf9e3765e0916607549fa919934` |
| AR-05 HF01 当前复核合同 | 基于 `65612ff1cb72664c124ec5aa70cbcfa8f869eced` 及保存的报告，Blob `3c78eaa260b46d01b95834ecdf1eb19367b1a61f` |
| 前次集成失败 | 核对 741 项 pytest 原始失败清单及报告，Blob `10e41cf18e063a35ddd791345326c0bbf779322c` / `1e077a6a8a815f68321030140ace23bd1accedad` |

以当前任务卡及 HF01 的持久复核、撤权规则校准旧 D4 夹具。D4 的动作身份、合法历史回查和禁止重复副作用要求继续作为断言。旧 Gold、RED 与原始报告保持原件。以下结果来自实施方实际复跑，待主 Agent 独立核验。

## 实施与结果

原 27 项在当前合同下均执行到目标断言并通过。其中 D4 24 项，M1 聊天证据与事件进程恢复各 1 项，M4 已交付任务的旧纠错拒绝 1 项。逐项用例、原始失败行、本轮断言和 Trace 索引见 [CASES.md](CASES.md) 与 [RESULTS.json](RESULTS.json)。

- 共享夹具通过 TaskControl 创建 Demo Session 和调查 Run，将 READY Plan 绑定到源 Run，通过可信 APPROVER 提交批准。REPAIR 用例由关联的 `APPROVAL_RESUME` Run 和 `executor-a` 调用 Domain 正常生成 `VALID` 回执。复核记录包含实际 loopback HTTP 401、请求和 Authn 事件，以及四条新 Evidence。测试走原有摘要、来源和 TTL 检查。
- 进程测试保留原 `os._exit(75/76/77)` 故障点和并发屏障。Graph 用例按原故障窗口布置持久 Checkpoint，子进程读取真实审批链接并执行正式 `run_investigation()`。重启重新取得 OS Worker 锁，恢复原审批 Run。Checkpoint 测试由明确拒绝模型调用的替身隔离 Provider。
- 取消及替代测试核对未消费许可变为 `REVOKED`，已消费许可仍为 `CONSUMED`。已提交动作保留原 Intent、Ledger、验证及交付引用。原 M1/M4 断言继续覆盖旧聊天证据失效、提交后事件回查、已交付任务拒绝旧纠错。

| 实际运行 | 数量与退出码 | 原始证据 |
| --- | --- | --- |
| 基线定向 RED | 6/6 复现，exit 1 | [red-baseline.txt](logs/red-baseline.txt) |
| 共享夹具首次对接 | 3 通过、3 失败，exit 1，已修复 Session 返回值 | [fixture-direct.txt](logs/fixture-direct.txt) |
| 定向 GREEN | 8/8，exit 0 | [fixture-focus.txt](logs/fixture-focus.txt) |
| 新增双向边界的反例 | 10/10，exit 0 | [paired-boundaries.txt](logs/paired-boundaries.txt) |
| D4 / D3 / M1 / M4 / AR-05 相关回归 | 129/129，166.54 秒，exit 0 | [原始日志](logs/related-regression.txt) · [JUnit](logs/related-junit.xml) |

实际命令和测试文件 Blob 见 [RESULTS.json](RESULTS.json)。Windows CPython 3.14.0，`requirements.lock.txt` Blob `de16e1113ac250511cee8d7b6a079b88b1ca4f99`。使用已安装的 pytest 9.1.1、FastAPI 0.137.1、HTTPX 0.28.1、LangChain 1.4.1、LangGraph 1.2.16、checkpoint-sqlite 3.1.2 和 MCP 2.3.0。每次 pytest 使用独立的 `D:/tmp` basetemp，进程环境关闭付费 Provider，清空模型密钥及实验身份，模型备用地址限制在 loopback。AR-05 旧 Trace 输出路径在相关回归进程中置空。

## 四组配对证据

| 分组 | 允许 | 拒绝 |
| --- | --- | --- |
| 新鲜事实 | 同一审批下，真实 401 新观察形成 `VALID`，CAS 成功。相关组中的原 D3 TTL 用例也证实旧观察到期后可用新证据延续审批 | 有 RUNNING 审批 Run 但无回执、来源返回 UNKNOWN 或主体 DISABLED 时，均为零新 Intent、Ledger 和工单。DISABLED 同时撤销旧许可 |
| 取消与替代 | 取消后可取回已提交 REPAIR、DELIVER 的原 Ledger。替代竞争中提交在先，旧 REPAIR Ledger 仍可读 | 取消或替代先发生时，未提交 Intent 拒绝执行，未消费许可撤销。相关测试同时核对既有修复可保留而未交付工单仍为零 |
| 崩溃与重放 | 提交前进程退出后，仍有效的 Intent 可重试一次。提交后响应丢失，重放取得原 Ledger | 真实提交前崩溃后追加取消、推进至回执 TTL 之后、改变配置版本，三组重试分别得到 `PLAN_NOT_ACTIVE`、`REVALIDATION_RECEIPT_EXPIRED`、`RESOURCE_VERSION_OR_CREDENTIAL_PRECONDITION_FAILED`。重试前后 Domain 状态相同 |
| Graph 恢复 | 五个原故障窗口都恢复原审批 Run。已有 Intent、冻结报告或 Ledger 继续使用，HTTP 200 验证后只交付一次 | 缺 Run、Executor、HTTP 或 Run 尚未 claim 时拒绝复核。伪造的 Checkpoint 完成状态缺少 Domain 回执，持久 Run 停在 `WAITING_INPUT / ACTION_OUTCOME_UNKNOWN` |

## 实际 OS 退出与持久状态

[OS_CRASH_REPLAY_TRACE.jsonl](OS_CRASH_REPLAY_TRACE.jsonl) 保留本轮 pytest 原始输出中的结构化记录。移除的是 pytest 用例名和 M1 日志前缀，JSON 载荷保持原样。逐项记录包含子进程 PID、退出码、Plan 与审批 Run、回执摘要、Intent/Ledger ID、计数及业务 Outcome。

| 观察窗口 | 退出后的 Domain 重读 | 重试或重启结果 |
| --- | --- | --- |
| REPAIR 提交前，exit 75 | 版本 7，REPAIR Ledger 0 | 原 Intent 执行后版本 8，REPAIR Ledger 1，`REPAIR_COMMITTED` |
| REPAIR 提交后响应丢失，exit 75 | 版本 8，REPAIR Ledger 1 | 原 `ledger-cffb84c1-500e-431e-9aff-5336b9556c6b`，版本及数量保持 |
| DELIVER 提交前，exit 75 | 验证已完成，DELIVER Ledger 及工单均 0 | 原 Intent 提交 DELIVER 一次，工单 1，`DELIVERED` |
| DELIVER 提交后响应丢失，exit 75 | DELIVER Ledger 及工单均 1 | 原 `ledger-c8305f0b-050e-4cbd-8ce2-eebd3d99c05d`，工单仍 1 |
| 持久 Intent 后、Checkpoint 前，exit 76 | 一个 REPAIR Intent，版本 7，Ledger 0 | 同 Action ID、幂等键、请求摘要，CAS 未发生 |
| Graph 的 Intent 或 Report 已持久化，exit 77。REPAIR/DELIVER 提交后响应丢失，exit 75 | 五次实际进程退出。按窗口保留原 Intent、报告或 Ledger | 五次不同 PID 重启均 exit 0。同一审批 Run `INTERRUPTED_RECOVERABLE → SUCCEEDED`，原动作引用、HTTP 200、一个 REPAIR、一个 DELIVER、一个工单，Outcome `DELIVERED` |
| M1 提交进程正常退出码 0，但未进行 SSE 投递 | 版本 8，一个持久的 `REPAIR_COMMITTED` 事件 | 新 Web 进程通过 HTTP 200 读回同一动作事件，Intent、Ledger 和事件各 1 |

三个并发测试在最终运行均观测到动作先提交。取消或替代先发生的顺序由单独确定性反例覆盖。拒绝写入时以 Plan 资格、许可、版本及 Ledger 为准。历史批准仍可见，单独的 `APPROVAL_ACCEPTED` 不表示发生修复。

## 六维自检

1. **用户变化**。当前审批流程遇到进程退出时，测试证明可以回查已发生的动作并继续合法交付。取消或证据变化可以阻止尚未提交的动作。
2. **Agent 决策**。本轮验证审批后的程序执行、恢复与拒绝行为。模型决策质量未评估。
3. **观察驱动**。同一资源真实 401 且事实匹配时允许续行。过期回执、版本漂移、UNKNOWN 或 DISABLED 改变允许的下一步。
4. **新增约束**。本轮只改测试前置条件与断言，按现行合同验证许可撤销和历史回执回查。
5. **简化结果**。四处回归和子进程共享已有 TaskControl 与 Domain 入口，真实复核走原审批和动作事务。
6. **证据与停止线**。原 27 项和相关 129 项均为本轮实施方实际运行。全仓 pytest 未重跑，历史 AR-04C 与 C1 失败留待原范围处理。付费 Provider 0，外部业务写入 0，浏览器保持 `NOT_RUN`。提交候选供独立审查。
