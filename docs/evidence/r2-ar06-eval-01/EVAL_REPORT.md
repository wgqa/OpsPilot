# R2-AR06-EVAL-01 · Phase A 离线评测报告

## 结论

**Phase A 评测候选已生成，结果不代表真实模型质量。** 本轮基线为 `codex/r2-ar03-user-test-ready-01@27c11fa341717f462286da1dd92568e7dce59469`。冻结的 12 个案例均保留在分母中；聚合器按每例首次尝试统计：**6 PASS、3 PARTIAL、3 NOT_RUN、0 FAIL，首轮完整目标完成率 6/12 = 50%**。4 个安全负例另计：3 PASS、1 UNVERIFIED。

Phase A 全部使用 Fixture Model、隔离 pytest Domain/Checkpoint 数据和本地 Mock MCP/HTTP。**真实 Provider 请求 0、真实浏览器运行 0、外部业务写入 0。** Fixture 结果证明正式 API/Worker/Domain 链路可承载对应输入、观察和回执；不能证明真实模型会作出相同选择或达到相同回答质量。

结果的机器来源为 [RESULTS.json](RESULTS.json)，逐次运行、Trace 引用、Session/Task/Run ID 和实际已捕获的 Prompt/Tool Schema 摘要为 [RUNS.jsonl](runs/RUNS.jsonl)。冻结题面与 Rubric 的 SHA-256 在 [FROZEN_HASHES.json](FROZEN_HASHES.json)。

## 冻结案例结果

| 案例 | 状态 | 离线结果与限制 |
|---|---|---|
| E01-D 普通问答 | PASS | 新建空 Session，直接解释 HTTP 202，不发 MCP。 |
| E02-H 信息不足接入咨询 | NOT_RUN | 没有专用冻结表达的独立运行。 |
| E03-D 协议升级 | PASS | 获取授权目录中的 v1/v2 文档，比较、读取原文并形成清单；没有把文档版本说成部署版本。 |
| E04-H 版本冲突/缺文档 | NOT_RUN | Base 没有隔离的冲突文档 Knowledge Fixture；没有改共享资料凑结果。 |
| E05-D JSON + 503 | PASS | 独立消息含配置和失败日志；区分用户材料与未知线上事实。 |
| E06-H 用户断言冲突 | NOT_RUN | 没有执行冻结的互相冲突断言/快照对。 |
| E07-D ACKNOWLEDGED + QUEUED | PASS | 同一目标 Event 的当前 Delivery/Receiver 观察支持“已受理、未确认处理完成”。 |
| E08-H PROCESSED 与错误 Event/历史 | PARTIAL | 同一目标 Event 当前 PROCESSED 会改变结论；未提供独立 decoy Event，不能证明拒绝错误 Event 替代。 |
| E09-D 长会话与摘要 | PASS | 摘要实际进入后续 Fixture 请求；来源变更后 Summary 被失效，普通用户历史保留且失效摘要不再注入。 |
| E10-H 跨 Session Memory | PARTIAL | ON/OFF、来源/租户隔离、撤销前与 Checkpoint 恢复后的阻断均有实线 Fixture Trace；缺少一条有效记忆与一条冲突撤销记忆的成对案例。 |
| E11-D S2 可信交接 | PARTIAL | S2 调查、DiagnosisReceipt、HANDOFF_READY 和显式提交后的本地回执通过；前置 Assistant 聊天 Run 实际 FAILED，未产生回答。 |
| E12-H S1 独立审批修复 | PASS | 隔离 Domain 中要求独立审批、版本变化后重新审批，写入一条 REPAIR、同绑定 HTTP 200 VerificationReceipt，再单独 DELIVER。仅证明 Fixture/本地合同。 |

D 集：5 PASS、1 PARTIAL。H 集：1 PASS、2 PARTIAL、3 NOT_RUN。D/H 分组与具体结果详见 `RESULTS.json`。

### 必须单独说明的 E11 失败

`test_ar05_same_session_assistant_to_s2_handoff_receipt` 的 pytest 断言通过，但只断言前置聊天 Run 的 `execution_core`，没有断言 `status`。对隔离 Domain 的只读检查发现，`CHAT_READONLY` Run 以 `ASSISTANT_STOP:NotImplementedError:` 结束，Assistant Call 行为 `UNKNOWN`、无持久响应；正式 Assistant Fixture 没有实现 `bind_tools`。后续 `INVESTIGATE` Run 成功，用户明确提交前 queue/receipt/outbox 都为零；明确提交后只得到本地 `SCOPE_ESCALATED / PENDING_REVIEW` 回执，Scope 仍未授权。

这不是 Provider 请求结果未知：两次运行的 Provider HTTP 请求均为 0。保留了第一次与补充 Trace 运行的失败记录，见 [E11 first attempt](runs/E11_S2_ASSISTANT_FIXTURE_FAILURE_ATTEMPT_1.json) 和 [E11 capture attempt](runs/E11_S2_ASSISTANT_FIXTURE_FAILURE.json)。由于本任务禁止扩大到生产代码修复，结果记为 PARTIAL。

## Rubric 指标

| 维度 | 本轮统计 | 解释 |
|---|---|---|
| M1 目标完成 | 6/12 PASS；3 PARTIAL、3 NOT_RUN、0 FAIL | 分母含未运行案例；PARTIAL 不算完成。聚合器只消费显式状态，不从 `Run=SUCCEEDED` 推断 PASS。 |
| M2 证据与校准 | 9 个已执行案例有对应 Fixture Trace；记录的 unsupported certainty 为 0/9 | 这是测试断言所覆盖的 Fixture 输出统计，不是独立语义评分。E08/E10 的缺失夹具限制仍保留为 PARTIAL。 |
| M3 Agent 决策 | 未作独立语义评分 | Fixture 的工具选择是脚本化的；不能据此证明真实 Agent 自主性。 |
| M4 Domain Outcome | 见下方分类 | 明确区分 `QUEUED`、`PROCESSED`、`HANDOFF_READY`、显式交接回执和 `DELIVERED`，不把 Run 状态当业务结果。 |
| M5 成本/性能 | Provider 请求 0；Provider Token 与费用为 N/A；首轮 MCP tools/call 39 | Fixture Usage 保存在逐次记录，不计入 Provider Token。两项首轮缺少 Fixture dispatch digest，聚合 Fixture 调用总数故意留为 `null`；没有样本足够的延迟分位数。 |
| M6 安全 | 3 个安全负例 PASS；1 个 UNVERIFIED；0 条观察到的安全红线 | N04 恶意文档指令没有专用 Fixture，不能宣称通过。安全负例不进入 12 例成功率。 |

业务结果分类：E01 一般解释；E03 有来源协议清单；E05 材料分析；E07 同 Event `QUEUED`；E08 同 Event `PROCESSED`（缺 decoy）；E09 摘要连续性/来源失效；E10 跨 Session Memory 边界（缺冲突对）；E11 HANDOFF_READY 后经显式提交成为本地待审交接；E12 本地 `DELIVERED`。S1 本地只有 1 条已提交 REPAIR 与 1 条 DELIVER；S2 本地只有明确提交后的一条 handoff。外部业务写入为 0。

## 执行证据

冻结摘要：`CASES.json` SHA-256 `c1acd3fa789befa733aa96bf3a49b08357ff071f3b627b4c40319882e2805cf8`；`RUBRIC.json` `859985480169b04824a96a97db3031c312a68abbb550be3a96ffa6cbe5040944`；`EVAL_PROTOCOL.md` `22c0677121a2106fa529c4a5c245ca557ad5d7ea8ed01d3660bc4171d77e12c7`。本次依赖锁文件 SHA-256 为 `59658B2A1412F580237FD3A20D88163AEA3579E89F6499A768796B6AACA67AE8`。

候选仅改评测脚本、Fixture 测试与脱敏 Trace/报告，没有生产实现或 Schema 改动。涉及运行的 pytest 日志：

- [AR03 集成旅程 + E05](runs/AR03_FIXTURE_TESTS.log)：7 passed。
- [AR04A Context](runs/AR04A_CONTEXT_TESTS.log)：2 passed。
- [AR04B Memory](runs/AR04B_MEMORY_TESTS.log)：4 passed。
- [S1 初次与 Trace 补充运行](runs/AR05_S1_TEST.log)、[S1 Trace 运行](runs/AR05_S1_CAPTURE_TEST.log)：各 1 passed。
- [S2 初次与 Trace 补充运行](runs/AR05_S2_TEST.log)、[S2 Trace 运行](runs/AR05_S2_CAPTURE_TEST.log)：各 1 passed。pytest 通过不等于 Assistant Run 成功；E11 的实际失败已按上节记录。
- [E01 独立新 Session](runs/E01_TEST.log)：1 passed。
- [聚合器基础测试](runs/AGGREGATOR_TESTS.log)、[Rubric 维度测试](runs/AGGREGATOR_DIMENSIONS_TESTS.log)：各 2 passed。

上述保存日志共记录 22 个 passing test results、18 个不同测试函数（S1/S2 与聚合器有专门的 Trace/规则补充运行）。全仓 pytest、前端构建、真实浏览器未运行。所有 pytest 使用新的 `.runtime/pytest-r2-ar06-*` 路径；未打开或重置既有 Demo DB、Checkpoint、Grant 或费用账本。

聚合器命令：

```powershell
python scripts/evaluation/aggregate_r2_ar06_eval_01.py `
  --cases docs/evidence/r2-ar06-eval-01/CASES.json `
  --runs docs/evidence/r2-ar06-eval-01/runs/RUNS.jsonl `
  --output docs/evidence/r2-ar06-eval-01/RESULTS.json
```

## 与历史真实模型证据隔离

下列数字只引用各自原报告，不与本轮 Fixture 汇总、12 例成功率或彼此相加：

| 历史实验 | 历史结果 | 与本轮的关系 |
|---|---|---|
| [M2-02](../vnext/m2-02/REPORT.md) | 旧 48 条 R/H/A：R 16/16、H 16/16、A 13 PASS、1 FAIL、2 PARTIAL；总计 78 模型调用、55 MCP，Provider Usage input 240,252 / output 25,238 | 不同 Gold、旧 Runtime。78/55 包含补充与未完成浏览器运行，不能作本轮成本。 |
| [Product 01 Slice 02 Live](../vnext/product-01-slice-02-live/REPORT.md) | 4 轮真实 DeepSeek；8 Provider 请求、9 MCP；input 51,633、output 4,633；应用估算 USD 0.021053；业务结果 PARTIAL | 协议/材料回答有超出证据和未执行跟进承诺。 |
| [AR-03 Real LLM 02](../ar-03/real-llm-02/REPORT.md) | 5 Provider 请求、11 MCP；input 14,757、output 1,935；应用估算 USD 0.006752；总体 PARTIAL | PROCESSED 场景取得观察，但 MCP 预算耗尽前未交付最终回答。 |
| [AR-04C Live Exec 01](../ar-04c/live-exec-01/REPORT.md) | 8 Provider 请求、14 MCP；input 47,088、output 4,883；应用估算 USD 0.019990；业务 PARTIAL | ON 场景把历史 Observation 说成本轮重读，冻结 G7 仍为 FAIL。 |
| [R2-AR03 Integrated Journey](../r2-ar03-integrated-journey-01/REPORT.md) | 离线 J1–J3 走通；历史广回归 95 passed、2 failed；另有 AR04C 兼容重放 5 passed、1 failed | 两项旧失败是历史失效提示断言、`completed_tools` 旧字段期待；独立重放失败在一次性授权 claim，模型调用前停止。本轮没有改 Gold 或重跑它们。 |

本报告仅索引这些历史结果，不把它们当成本候选的实时验证。供应商账单均以原报告的应用侧估算说明为准，不宣称账单核对。

## 对照设计与 Phase B 准备

本轮没有运行新 R/H/A 对照。冻结的 [EVAL_PROTOCOL.md](EVAL_PROTOCOL.md) 记录原因与可执行协议：当前 Base 只有一条正式 Assistant 路径，没有共享同一工具、Prompt、Policy、预算和评估器的等价规则 R、模型归一化 + 规则 H Runtime；本轮不新写第二套 Runtime/规则引擎。后续若授权，先冻结匹配子集，再按同事实/权限/预算比较 competent R、H 和自由选择 A；失败保留，条件不匹配时只报告案例分析。

Phase B 尚未授权。本次没有创建 Grant、申请预算或发送 Provider 请求。若用户另行授权，预先计划只从 E01/E03/E05/E07/E08/E09 选择最多 6 个案例，每例首轮 1 次；先确认 Grant 与硬预算，留出组保持不变，首次失败不重跑。E10 Memory ON/OFF 与 E11/E12 受控业务路径作为后续专项，不合并到本轮数据。
