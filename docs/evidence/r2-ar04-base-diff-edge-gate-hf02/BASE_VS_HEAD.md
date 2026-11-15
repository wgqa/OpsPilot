# R2-AR04 · Base 与 HEAD 差分归因

## 开工核验

| 项目 | 实际核验 |
|---|---|
| 仓库与隔离分支 | `wgqa/OpsPilot`，`codex/r2-ar04-base-diff-edge-gate-hf02`。复用 `ar04a-context-journey-01`，开工时已跟踪文件干净 |
| F01 对照 | 旧 Base `1cba32753f22e0a610aa7654ab5dc6cddd94ccf2`，候选 `ecbd7d3ebfebc3cb4ea1f75cbf4cfae6e7786011`。旧 Base 是候选的直接父提交 |
| 本切片 Base | `ecbd7d3ebfebc3cb4ea1f75cbf4cfae6e7786011`，与远端 HF-01 分支一致。开工时远端 `main` 为 `60eee87bfe3cca522011316cb4cd2c0064ad291b` |
| `PROJECT_NORTH_STAR.md` | 已从候选读取，Blob `43dabda468506717c6956e676dfad4304c4f38e6` |
| `AGENTS.md` | 已从候选读取，Blob `807b928686a4dd2cac7b15b3c354b9943c93c910` |
| `opspilot-slice-review/SKILL.md` | 已从候选读取，Blob `d405c8d413d633824b279202cc1503dab4cf0b03`。上述三个 Blob 在旧 Base 相同 |
| 本轮任务范围 | 用户消息中的 A–D。附带交接包用于定位历史证据，其第三方评议提纲是背景 |
| 冻结合同 | [v1.0 实施基线 §5](../../baseline/v1.0-implementation-baseline.md#5-memory--skill--context-p0-约束) 管来源和当前性，Blob `30e18d7ddbade7cdf7712d035d6fd8488bcb9676`。采用 [F01 当前性报告](../ar-04c/f01-context-currentness-01/REPORT.md) 中的历史快照和本轮观察语义，Blob `87ac327ba0a100346500e27fa4f4eef04b30542d` |
| 遗留门禁与上一阶段 | 核对 [F01 复验合同](../ar-04c/f01-recheck-01/CONTRACT.md)、[C06 报告](../r2-ar04-compaction-c06-hf01/REPORT.md) 和 [HF-01 结果](../r2-ar04-summary-fact-retention-hf01/RESULTS.json)。M2-01/M2-02 Deferred Gates 中的 TTL、源撤回和只读任务边界适用，其他受控写入门禁属于各自阶段。HF-01 候选记录了待归因的 F01 失败 |
| 证据等级 | 本轮亲自复跑确定性 Fixture，读取隔离数据库的持久请求，检查源码与 Git 历史。F01 初始 Run 使用真实本地 stdio MCP。真实 Provider、外部 MCP 和浏览器均为 `NOT_RUN` |

## 严格对照

用独立 Git index 检出两个提交到临时目录。两个快照使用同一 `D:\python\python.exe`（Windows Python 3.14.0、SQLite 3.50.4、pytest 9.1.1），核对锁定的 71 个包全部匹配，使用同一份经哈希检查的本地 `cl100k_base` 缓存。每次 pytest 都启动新进程，使用相同参数及从相同 Fixture 初始化的独立 Domain 和 Checkpoint。子进程环境采用系统变量白名单并禁用 pytest 插件自动加载，Python socket 审计只允许回环地址。测试使用合成数据和 Fixture 模型。

| 顺序 | 提交 | pytest 退出码 | 实际结果 |
|---:|---|---:|---|
| 1 | `1cba327` | 1 | `KeyError: 'completed_tools'`，F01 第 87 行 |
| 2 | `ecbd7d3` | 1 | 同上 |
| 3 | `ecbd7d3` | 1 | 同上 |
| 4 | `1cba327` | 1 | 同上 |

全部命令和 stdout/stderr 见 [F01_RUN.txt](F01_RUN.txt)。两种执行顺序、独立进程与独立数据库都重现了同一错误，本次未观察到顺序依赖或 Fixture 串用。

## 失败来自旧的 Prompt 字段断言

1. F01 测试经 `test_ar02_runtime.execute()` 调用 `run_assistant()`。绑定任务的追问先通过 `Loop.context()` 构造完整 `current_run`，其中含本轮已完成工具和业务观察。
2. `Loop.awrap_model_call()` 通过 `domain.assistant.source_context_for_model()` 重建写进 `WORK_CONTEXT` 的子对象。模型可见字段为 `run_id`、`business_observations`、`description`。完整的 `completed_tools` 仍在持久请求的 `source_refs.current_run` 里。
3. 历史提交 `922d815647dd096ddace5e8c54720dffa09dc664`（Fix R1 J2 event and context closeout）将原来的 `dict(payload['current_run'])` 改为显式选择模型字段。它是旧 Base 的祖先，F01 第 87 行仍按旧口径在模型输入取键。两个对照提交中的 F01 测试 Blob 均为 `78550c42654c2483ca4866f6fd8f452d0682eba2`，`opspilot/assistant.py` 和 `opspilot/domain/assistant.py` 的 Blob 分别为 `73d59acd98d46ad2bed5697854c58f1343f7398a` 和 `c154b03e6d5371ca877153d89c701972f3a15a02`，两边相同。HF-01 的生产差异位于 `domain/chat.py`。
4. 本次单独从四份 SQLite 快照读取持久请求。四个追问 Run 均为 `SUCCEEDED`，本轮 MCP 调用数为 0，审计 `completed_tools=[]`，模型输入业务观察为空且保留可引用的历史快照。原 F01 单测仍在第 87 行失败，其后断言不会执行。这些额外观测来自另行查询。

**归因**　F01 是旧 Base 已有的测试和 Prompt 契约失配，与摘要锚点修改无因果关系。把它登记为独立遗留项。涉及 F01 或整体验收时，需要确认断言应检查模型投影还是完整审计字段。冻结的真实 F01 结果及 G7 历史失败仍有各自适用范围。
