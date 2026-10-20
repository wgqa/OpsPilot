# Context / Memory 与 Worker 有限审计

范围为任务卡 A/B/C 相关路径，非全仓库生产认证。原业务授权/事务、Schema、LangGraph主链、MCP工具、依赖版本均未改。完整审计基于 `c2f71e9`，P1修复后代码 `00d054a`。

## 已确认并处理

| 级别 | 发现 | 最小证据 | 处理 |
|---|---|---|---|
| P0 | 本次未发现可确认的跨租户/越权/受控写安全突破 | 既有回归227项、正常授权下真实6个Ledger、scope表前后完全一致 | 不等同全系统无P0保证 |
| P1 | 历史回答的MODEL_ATTEMPT父依赖只检查完成，未追溯祖先回答的Memory来源 | 独立冻结RED；修正测试准备后的RED02两类资产均在派生回答排除断言失败 | 原`_message_source_valid`加35行递归、作用域与环保护；26定向/227全量GREEN；没有改Schema或状态权威 |

真实修复后对照验证实际出站资产集合，但撤销前Evidence已过期、未形成目标Summary，所以**没有把真实传递撤销因果验证标成完成**。该限制不被单元GREEN覆盖。

## 已核对的机制

1. **Context优先级**：`context_engineering.allocate_context_blocks` 必须块先算；超过预算安全停止。`chat._prepare_context` 的有效Summary2000、历史1000+index、Memory20。正式初始/最新更正锚点另保留，不依赖可选摘要。
2. **当前事实**：`chat._current_evidence`核对同tenant/task/resource、TTL与当前Config/Principal/AuthPolicy；Probe before/after完整匹配且稳定。旧版本事实不因为仍在TTL内就变当前。
3. **Summary**：创建前/提交前/选用前都按现有来源函数复核。Summary version/digest与依赖递归检查，父摘要可允许superseded历史身份；环保护。模型JSON有结构/来源引用校验，但语义质量仍需实测。
4. **Episodic/Semantic**：作用域、不同来源Task、当前状态、版本/digest、expires_at及源回执/引用有效性。确认/撤销保持独立角色，未新增记忆类型。
5. **Chat/Investigator区别**：Chat带有效历史和Summary，Investigator从正式Task输入/Run控制、当前MCP与资产重建，非直接复用Chat摘要。两者必须有当前来源复核与provenance，不能用一个路径通过推断另一路径。
6. **恢复**：A同Run真实Checkpoint跨进程继续，预算8MODEL/6MCP未清零，撤销经验未重载。最新源码只改Chat祖先校验，原M1-HF恢复代码完全未变，227项包含其回归。
7. **Manifest与实际请求**：新观察49个序列化请求，资产正文/版本/集合、压缩源材料及排除消息/摘要均按结构核对。仍不能证明Provider内部推理或检查与发送原子性。

## 不扩范围的剩余清单

| 级别 | 风险/限制 | 可证事实与边界 | 本轮决定 |
|---|---|---|---|
| P2 | 压缩响应在来源再验证失败后未持久响应ID/Usage | 两次真实HTTP200/TaskControlError，Domain元数据空；具体错误码未保存 | 作为UNKNOWN计费，不猜数；不改通用Worker元数据事务 |
| P2 | S1 Scope意图守卫保守误拒否定表达，旧输入影响纠错后判断 | `_requires_scope_clarification`变更词/否定词匹配；两新Run WAITING_INPUT/0调用 | 保留失败和源码定位，不顺手重构NL守卫 |
| P2 | 真实摘要实验易被短TTL及准备延迟截断 | 第一次目标压缩未提交；第二次第1轮时Probe已约250秒龄 | 停在8+2上限，报告PARTIAL，不改TTL/Gold/预算 |
| P2 | 本地Token估算与Provider不同，输出预留非账单硬上限 | 46对input差值-960～449；压缩reported output1237 | 逐请求Usage，已知下界159690+3项UNKNOWN；不升级SDK或改参数 |
| P2 | UI“最近一次真实模型调用的Context Provenance”展示Investigator最后资产，可能被误读成最新Chat | 最终浏览器上方Chat Memory为空，下方Investigator历史provenance仍显示E3v2；真实新请求已无E3 | 明确观察面语义，截图原样保留；不把旧卡片当当前有效注入，不扩前端功能修复 |
| P2 | 来源最后检查和网络send之间非原子窗口 | 程序分别执行Domain校验和外部I/O，hook不提供事务 | 未观察该竞态泄漏，不声称消除；合同变更须另立任务 |
| P2 | 历史Worker缺异常细节导致根因无法归属 | 两旧Run只有generic code/retry状态；本轮只读匹配1个库中旧Run，无历史Lease快照 | ROOT_CAUSE_NOT_PROVEN；不猜测性改Scheduler |
| P3 | 深DAG递归的查询/缓存成本 | 新cache仅当前验证树，源码有限历史窗口，未做大规模性能测量 | 不建设通用缓存或新框架；以后先测量 |
| P3 | 句子级来源精度 | 当前整条助手/摘要保守依赖，源失效会丢弃部分仍正确说明 | 不开发事实抽取/知识平台 |

## Worker C1：能证明和不能证明的事

历史源文件 `docs/evidence/vnext/m3-02-03/runs/m303-final/FAILURE-original-web-task-b.json` 的SHA256在 `runs/worker-audit-01/RESULTS.json`。两Run分别 `run-8e65e032-5e99-4c24-96ea-867df3912a18`、`run-9e9834db-ca90-431c-8e6a-c5ca0948eb56`，均retry_count3/max3、WORKER_RETRY_EXHAUSTED，原异常class/stack缺失。有限只读候选库扫描及Lease/Outbox结果在HISTORY-READONLY.json；当前Lease不能证明历史owner。

冻结 `013b4a673611c4d5d64b23d72c6a30fac1920404` 后，两个合成DB里用真实wrapper/Domain/Fence注入：RuntimeError三次可重试、第四次阻断；TaskControlError STALE立即阻断。2/2通过，0真实Provider/MCP、0业务Ledger。测试直接驱动wrapper，不计实际backoff墙钟或全调度器吞吐。

源码 `_prompt_messages` 在出站Attempt前可能抛错，MCP初始化/tools/list也可能先于tools/call。故零计数**不能排除Context/Memory相关**，相似终态**不能证明同一根因**。Worker生产源码不变，结论ROOT_CAUSE_NOT_PROVEN。

## Diff范围

生产仅 `opspilot/domain/chat.py` +35/-0；测试 `tests/test_m3_hf02_lineage.py` +76/-0，其余新增本轮证据与学习材料。无Schema迁移、无依赖修改、无Scope写入、无新MCP工具、无业务合同改变。测试与夹具动作都明确标注，不冒充模型自主恢复。
