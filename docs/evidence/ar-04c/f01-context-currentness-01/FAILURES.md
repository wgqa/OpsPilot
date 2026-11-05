# 原始失败与范围限制

- 原真实 F01 保持 `G7 ON FAIL / G8 PARTIAL`，其输入、回答、Completion 和 Trace 没有修改。主 Agent 的 LIVE 限定验收已接受，本轮不重审、不回填 PASS。
- 新定向 RED：4/4 失败。除纯投影用例提示新函数尚不存在外，三个实际 Assistant/MCP 路径都证明旧出站 Context 没有本轮查询/Observation 的明确记录。
- 初次 GREEN：3 通过、1 失败。保存的 HTTP 消息为 dict，测试解析 helper 只接受 LangChain Message；只修正测试解析器，未改变预期、Gold 或生产行为。对应原始日志保留。
- 修正后冻结 F01 投影用例 1/1 通过；最终一次限定回归 11/11 通过，43.41s，退出 0。

离线替身按预设行为解释或查询，只证明实际 Context 已接入、来源校验未放宽和合法路径仍能完成。它不能证明 DeepSeek 已纠正当前性错误；静态重放的 Token 减少也不是智能效果证明。真实效果等新的小额授权后验证。

未运行真实 Provider、浏览器、外部业务写入和全量 pytest。未重跑旧 AR-04C Campaign，未创建新付费 claim。Web/D3 仅源码梳理，实际 UI 和业务动作验收仍待合法环境及对应授权。
