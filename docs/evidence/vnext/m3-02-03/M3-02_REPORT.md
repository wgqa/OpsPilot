# M3-02 Context Engineering 报告

**实现提交：** `f9f9d8a7c724a477578ff9eed2a48f4972078ee0`。**验收状态：PARTIAL，交主 Agent 复核。**

实现统一 Context Builder 的结构化块、模型 Token 预算、估算器版本、预算溢出策略、上下文三策略、摘要来源依赖、Chat 出站重验、撤销/版本变化排除及 Web Context Inspector。摘要从 Domain 当前状态和可用原始来源重建；模型文本不会提升为 Domain 事实、权限或业务完成状态。

同源真实策略比较由 DeepSeek `deepseek-flash` 执行。Recent Window 成功，真实 usage 为 2,799 Token，耗时 21,088 ms；Rolling Summary 和 Hybrid 都未完成最终回答，分别消耗 6,020 与 4,640 Token，均以 `CHAT_ATTEMPTS_EXHAUSTED` 结束，起始压缩调用有一次 `RuntimeError`，后续摘要调用成功但仍未得到聊天回答。结果为 `UTILITY_NOT_PROVEN`。

真实 Web 长会话共 26 轮，21 个成功、5 个失败。失败记录保留于 `runs/web-01/`。安全行为有自动测试和真实 S1/S2 smoke 支持；独立进程 PID 与恢复 Run 的关系未形成可复核持久 Trace，故 CTX-07 / E2E-01 标记 PARTIAL 或 UNVERIFIED，不用本地测试冒充真实恢复证明。

冻结标准见 `ACCEPTANCE_PLAN.md` 和 `TEST_MATRIX.json`；最终完整 pytest 在 M3-03 合入后重新运行，单独的 M3-02 主线结果和被排除 M3-03 RED 见 `runs/verification-01/`。M3-01 历史的 8 对 / 16 臂、12/16、`UTILITY_NOT_PROVEN`、P03/P04 均未更改。
