# 可用简历亮点与证据索引

这些是可候选的准确表述；是否用于简历由用户和主 Agent决定，不能把离线结果扩张为真实模型成果。

| 候选表述 | 可核验依据 | 限制 |
|---|---|---|
| 使用 LangGraph/LangChain 构建了连续 Assistant：同 Session 支持协议咨询、用户配置解释、可信绑定后只读业务工具和来源化上下文。 | `opspilot/assistant.py`、`opspilot/domain/assistant.py`；`tests/test_r1_journey_readiness_01.py`；本轮 `TEST_LOG_TARGETED.txt`。 | 本轮正式路径使用 Fixture/MockTransport；不能称本次为真实 DeepSeek。 |
| 一次有界真实 DeepSeek 运行完成了授权协议 v1/v2 比较和配置材料分析；模型主动使用协议工具并区分文档和线上部署事实。 | `docs/evidence/vnext/r1-j2-live-recheck-01/REPORT.md`、`RESULTS.json`、`TRACE.jsonl`、`COST_LEDGER.md`。 | 仅历史 J1-01/J1-02；J2-01 FAIL、J2-02 PARTIAL；该 Campaign 已 STOPPED。 |
| 针对真实 J2 失败，在保持 12K Context 上限下精简模型侧历史摘要与当前业务观察重复元数据，同时保留来源引用、撤权和预算拒绝。 | `opspilot/domain/assistant.py::source_context_for_model`；`docs/evidence/vnext/r1-j2-f2-headroom-hf01/HEADROOM_REPLAY.json`、`REPORT.md`；本轮 28/28 定向测试。 | 效果是离线重建与 Fixture 回归；F1/F2 的真实模型行为尚待独立授权复验。 |
| 将可信 S1/S2 专业调查与统一 Assistant 结果回读接入同 Session，并以隔离 Demo/Domain 回执验证本地流程。 | `docs/evidence/vnext/product-01-bridge-closeout-01/REPORT.md`、`TRACE-S1-CLOSED-LOOP.json`、`TRACE-S2-OUTCOME-READBACK.json`。 | S1/S2 执行由既有 Investigator/D3 与本地 Demo 完成；真实新 Assistant 自主触发、生产环境及浏览器未证明。 |

避免未被证据支持的成功率、成本节省百分比、生产恢复、全自动审批、真实浏览器通过等说法。
