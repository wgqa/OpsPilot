# R1-ENGINE 集成评审输入

实施状态：ACCEPTANCE_CANDIDATE。以下是供主 Agent 独立复核的证据，不是实施方 PASS 或 MERGE_READY 结论。

## 唯一候选

- 分支：codex/r1-final-integration-01
- 代码 Base：6b5bfb16c461afcf1cdafaad9ebe08dd6a004b27
- 合入的文档路线提交：aba552cebda5b0ec4c3da22aaca98ec944d9d8cb
- 完整候选 SHA：应以本报告、Results 与证据提交完成后远端该分支解析出的精确 SHA 核对。
- 远端 main：60eee87bfe3cca522011316cb4cd2c0064ad291b；本轮未推送或修改 main。

## 已有可信用户工作证据

- 真实 DeepSeek 曾在 PRODUCT-01 四轮 Session 中解释协议、分析用户配置材料、调查同 Event 的订单回调状态、响应用户 Event 纠错并生成草稿；结果 PARTIAL，不能掩盖配置推断超证据。
- 确定性模型 + 正式本地 API/Worker/MCP/Domain 已证明 S1/S2 的专业调查结果能回到原 Session；S1 的隔离演示能完成本地受控修复验证与交付，S2 的隔离演示能完成待审交接。
- 有证据的本地 Demo 事实、真实 Provider 事实、程序限额通知和真实用户模型回答在各自来源报告中区分。

## 三项 AR-03 UNKNOWN 的结论

请求没有进入内层 MockTransport。Recording transport 的 begin 先验证冻结的 ALLOWED_TOOLS；当前 Assistant Schema 新增两个 S1/S2 工具，旧实验 Runner 未列入，因而在调用 Mock handler 前抛出 UNAPPROVED_TOOL_SCHEMA_EXPOSED。当前失败后 Run=FAILED，测试 SQLite 的 assistant dispatch=UNKNOWN/Usage UNKNOWN；外部 DeepSeek HTTP=0。

最新已知测试基线 8df557dabb6f7440b371828c39974239363ee6d9 为 3/3；集成候选当前为 0/3。它们是旧 Runner 与新增 Assistant Schema 的实验 Harness 兼容失败。没有证据显示普通 Assistant/S1/S2 用户路径受影响；本轮 77 项相关回归为 77/77。收费请求门禁没有被修改，亦未发送真实请求。

这三项仍阻止对完整旧实验 Runner 回归作全绿声明；不会仅因该实验债务把无关隔离只读代码开发宣称为失败。发布适用性由主 Agent裁决。

## 历史 16 FAIL 与当前适用范围

上一完整 pytest 结果是 757 项收集、741 通过、16 失败，来自之前报告的 SHA，不是当前 SHA 的全量结果：

- 12 项：AR-04C 一次性授权、Claim、冻结执行身份和旧实验目录绑定。这些负例必须保留，不能伪造身份或删除已消费 Claim。
- 3 项：AR-03 Runner MockTransport Schema 冲突，当前根因已定位，如上。
- 1 项：C1 测试仍要求旧 READONLY_FOLLOWUP 意图。现行 FOLLOW_UP + readonly_action=INVESTIGATE 正例已在此前证据通过；历史 RED 保留。

本轮没有重跑完整 pytest，不将 741 项算作本候选新 SHA 的 PASS。所有历史失败原样保留。

## 安全与运行结论

- 新增安全/业务错误：本轮未发现。
- 本地临时 S1_POS fixture：创建一份隔离 SQLite，仅本地 Demo。
- 正式本地服务：单 Worker、loopback、本次使用随机临时 DB/Checkpoint，API health=200、Worker ready=true；Provider 开关关闭并移除了凭据环境变量。
- 正常运行路径不消费或依赖 AR-04C/AR-03 实验 Claim；Provider disabled 时 health 与离线 Demo 启动不需要 Provider key。真实 Provider 发送仍受应用现有 allowlist、实验授权和发送前检查约束。
- 真实 Provider HTTP：0。
- 浏览器：NOT_RUN / BROWSER_STOP_ACTIVE。
- 外部业务写入：0。
- main：未修改。

## 尚未验证

1. 新 PRODUCT Bridge 下真实模型是否选择调查提议或同 Session 结果回读工具。
2. Vue 页面上的用户确认、结果呈现、来源展开和刷新恢复；本轮 Browser STOP 不允许执行浏览器。
3. 完整 pytest 在本候选 SHA 的全量结果；当前为历史基线加本轮 77 项适用定向回归。
4. AR-03 冻结 Runner 的兼容处理；不在本轮放宽工具 Schema 门禁。
5. 全局 Python OpenTelemetry 包版本一致性；npm audit 已知 11 个 moderate 依赖告警亦未在本轮修复。

## 建议裁决边界

如主 Agent 选择 ACCEPT_WITH_LIMITS，建议限制为：

- 仅接受当前隔离 R1-ENGINE 集成代码、真实模型历史证据与确定性 S1/S2 本地业务链的组合候选。
- 不批准把它描述成真实模型已完成完整 S1/S2 业务闭环。
- 不批准 R1-INTERACTIVE、生产部署、真实 Provider 新调用或 main 合并；分别等待各自审批。
- 将 3 项 AR-03 Runner MockTransport 失败、历史 Claim 身份冲突和 C1 退役合同作为发布回归说明，不把旧全量 741/757 冒充本候选全量结果。

最终接受、发布放行和下一阶段授权由主 Agent独立决定。
