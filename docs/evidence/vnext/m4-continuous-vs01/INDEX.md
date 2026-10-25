# VS01 证据索引

- [REPORT](REPORT.md)：真实用户对话在前，随后职责、简化、测试、成本、限制与六维交回。
- [RESULTS.json](RESULTS.json)：全部测试与 32 个实验、3 个 Web Task；状态仅 ACCEPTANCE_CANDIDATE。
- [冻结计划](ACCEPTANCE_PLAN.md)、[Gold](GOLD.json)、[实验登记](EXPERIMENT_REGISTRATION.json)、[后续补充登记](EXPERIMENT_AMENDMENT.md)。冻结先于 RED 和实现。
- [R/H/A 机器对照](RHA_RESULTS.json)：修正准备后的预算组与 R/H；不是最终响应修复版的完整性能评测。
- [TRACE.jsonl](TRACE.jsonl)：从真实保存行索引的 484 条观察/Run/控制/模型记录，不是合成调用序列；各行 source_file 指向原始完整 Trace。
- [Provider Ledger](PROVIDER_LEDGER.jsonl)：唯一 request_id、预留、实际输出/usage、失败与 Token/费用，包含分类及 Chat。
- [FAILURES](FAILURES.md)：原始失败、准备错误、未解决的聊天 SLA 解释错误和旧 lint/RED 限制。
- [最终有效 pytest](runs/regression-final-05/pytest.log)、[原样未过滤 pytest](runs/full-01/pytest.log)、[新定向 GREEN](runs/response-preview-green-01/pytest.log)、[纠错续接回归](runs/correction-continuity-green-02/pytest.log)。
- [第一次 RED](runs/red-01/pytest.log)、[长响应截断 RED](runs/response-preview-red-01/pytest.log)、[纠错高水位 RED](runs/correction-continuity-red-01/pytest.log)、[接收协议 RED](runs/receiver-contract-red-01/pytest.log)。
- [首次准备缺陷组](runs/budget-01/RESULTS.json)、[修正准备预算组](runs/budget-02/RESULTS.json)、[R/H 组](runs/controls-02/RESULTS.json)、[公开 R-only Gold](runs/fact-gold-01/RESULTS.json)、[一次封存留出](runs/holdout-01/RESULTS.json)。
- [真实纠错 Web](runs/web-02/JOURNEY.json)、[最终源码 Web](runs/web-03/JOURNEY.json)、[完整模型答复](runs/web-03/01-final-source-investigation.txt)、[带质量问题的连续解释](runs/web-03/02-followup-explanation.txt)。每个 Task 的原始 Trace 同目录。
- [前端最终构建](runs/frontend-final-02/build-final.log)、[改动文件 lint](runs/frontend-final-02/scoped-lint.log)、[旧整仓 lint 错误](runs/frontend-final-01/lint.log)。
- [环境/依赖](ENVIRONMENT.json)、[源码地图与面试问答](SOURCE_WALKTHROUGH.md)、[原任务卡](../../../handoff/vnext/M4-CONTINUOUS-VS01-ORIGINAL.md)。

本索引不构成主 Agent 独立验收。留出结果版本、旧失败和未知事项以 REPORT/RESULTS 为准。
