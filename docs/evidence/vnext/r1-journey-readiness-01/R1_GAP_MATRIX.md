# R1 发布差距矩阵

本矩阵汇总本轮可复核证据及既有已验收材料；它不替代主 Agent 的发布裁决。

| 能力/门槛 | 当前证据 | 本轮结论 | 尚缺/适用限制 |
|---|---|---|---|
| 普通 Assistant 连续协议/材料工作 | 正式 API/Worker/Runtime Grant + MockTransport + MCP/Domain；J1/J2 同 Session | 离线接线通过 | 本轮 FixtureModel，不是新一轮真实模型自主性证明 |
| 有授权的 Callback 只读核查与纠错 | event-current 当前 ACKNOWLEDGED + PROCESSED；event-previous 只有历史 202，无当前 Receiver | 纠错事实隔离通过 | 真实模型表现未运行 |
| S2 结果回读 | 正式本地调查、HANDOFF_READY、显式提交后 SCOPE_ESCALATED/PENDING_REVIEW、Receipt/Queue/Outbox 一对一 | 离线业务链通过 | 无真实 LLM、无浏览器；不代表 Scope 已授予或 403 已恢复 |
| S1 结果回读 | WAITING_APPROVAL 与隔离 Demo D3 完整因果链；同 Session 回读 DELIVERED 历史结果 | 离线业务链通过 | 不代表生产修复；没有真实 Provider/Web；本轮 S1 Demo 内产生 1 CAS 和 1 ticket entry |
| 来源撤权/版本重验 | Knowledge revoke/restore/version、协议比较来源重验、普通聊天不借用旧观察定向测试 | 13 项相关最终回归中的 3 项通过 | 不替代全量安全回归 |
| Runtime Grant 费用保护 | 持久预算正路径、无 Grant/Provider disabled 负路径、撤权发送前拒绝、过期价格暂停保留账本 | 相关定向测试通过 | 本轮没有真实付款或 Provider 计费实测 |
| 真实 Provider | Slice 02 历史四轮 DeepSeek 8 次请求/9 MCP，总体 PARTIAL；本轮没有新出站 | 仅引用历史证据 | Slice 02 配置推断超可见事实，需人工修订；新入口的自主性未测 |
| Web/Browser | 静态/API/Worker 证据与历史页面实现 | Browser `NOT_RUN` | Browser STOP 仍有效；不把 TestClient 当浏览器通过 |
| 全量 pytest | 上一历史 SHA：757 收集、741 通过、16 失败 | 不是本候选当前全量结果 | 本轮只跑适用定向回归，不改旧 Claim/Gold/Runner/C1 意图 |
| R1 结论 | R1-ENGINE 能力矩阵有代码和隔离 Demo 因果链 | 工程候选，非生产验收 | R1-INTERACTIVE 未完成；公开发布和 main 合并仍需独立裁决 |

## 发布限制与非阻断技术债

**当前旅程的限制：**真实 Provider 新调用尚未获准；浏览器 STOP 仍在；本轮未运行全量 pytest；此前 16 项失败来自不同 SHA，必须沿用其原始分类，不能计入本轮通过。

**不会阻止本次离线候选交付的债务：**历史 12 项 AR-04C 一次性 Claim/身份负例不可在新 SHA 重放；3 项旧 AR-03 Runner MockTransport Schema 白名单不兼容；1 项 C1 废弃 `READONLY_FOLLOWUP` RED。当前 `FOLLOW_UP + readonly_action=INVESTIGATE` 是有效合同，禁止恢复旧意图。另有 Windows 全局 pytest 临时目录权限问题，本轮通过 `python -m pytest`、`PYTHONPATH` 和工作树内独立 `--basetemp` 解决；未修改全局依赖。

下一条最短路径：主 Agent 独立审查候选 → 单独批准一个有界真实 Runtime Grant Campaign → 在发送前复核价格/报文/Grant 与资金上界并执行 J1/J2 + 受信结果只读回读 → 真实 Web 场景只有在 Browser STOP 正式解除后另行验收。
