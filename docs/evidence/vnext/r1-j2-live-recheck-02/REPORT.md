# R1-J2-LIVE-RECHECK-02 — 准备结果

**状态：`EXECUTION_READY / AUTHORIZATION_REQUIRED`**
**实施状态：`ACCEPTANCE_CANDIDATE`**
**Base / 分支：** `1be7739a454f27fb48141dd6f5f507f45253a826` / `codex/r1-j2-live-recheck-02`
**远端 main（本轮核实）：** `60eee87bfe3cca522011316cb4cd2c0064ad291b`

## 结果摘要

任务卡中的 F1/F2 修复已在本次 Base：F1 把当前问题与历史 `ORIGINAL_TASK_INPUT` 锚点分开呈现；F2 从模型输入中消除严格同内容、同作用域的重复历史摘要，同时保留各自来源引用、当前 ToolMessage 和三条 Observation。F2 保持 12,000-token 上限；保存样本的上次重建结果为三条实际工具结果后 10,594 tokens、余量 1,406（见前次 `HEADROOM_REPLAY.json`）。本轮定向测试覆盖这些行为，但没有再次重新计算私有 Provider 样本。

正式离线 API/Worker/Assistant/Runtime Grant/MCP/Domain 测试和相关边界测试 **28/28 通过**；额外同订单材料/MCP 测试 **2/2 通过**。与上次同范围的 Context/Assistant/Runtime Grant 回归 **59/60**；唯一失败仍是 `test_zero_tool_followup_can_explain_valid_historical_snapshot` 断言 `current_run.completed_tools` 存在，而模型输入投影刻意不含该字段。这个断言差异在之前 Headroom HF 已记录，本轮未改测试或 Gold。日志见 `TEST_LOG_TARGETED.txt`、`TEST_LOG_MCP.txt`、`TEST_LOG_REGRESSION.txt`。

## 真实旅程与授权

本轮没有收到覆盖新 Campaign `R1-J2-LIVE-RECHECK-02` 的单独付费授权。任务卡本身明确不是收费许可。因此没有创建真实 Campaign DB、Runtime Grant 或一次性 Claim，也没有读取或动用凭据；**Provider HTTP=0，MCP 真实出站=0，浏览器=0，外部业务写入=0**。四轮 J1-01、J1-02、J2-01、J2-02 本轮均为 `NOT_RUN`，不是失败或 PASS。

可作技术准备结论：冻结案例与代码边界核对通过；MockTransport 实际请求序列化参数通过；离线 Agent/Domain 路径通过定向旅程。由此只能报告 `EXECUTION_READY / AUTHORIZATION_REQUIRED`，不能报告新真实 Agent 行为通过。真实模型自主性、工具决策、Completion、Usage、Observation 驱动的最终回答和 J2 草稿质量仍未验证。

当前 DeepSeek 官方价格页（2026-11-08 检查）标注 `deepseek-flash` 对应 DeepSeek-V4.1-Flash-1017，1M context、384K max output，峰值 cache-miss 输入 USD 0.30/M、输出 USD 1.20/M。Chat Completions 文档接受 `thinking.type=disabled`、`max_tokens` 与工具调用；有工具时 `tool_choice=auto` 为默认值。项目 MockTransport 另行验证冻结报文及 `parallel_tool_calls=false`。官方 Chat Completions 参考没有明确记录 `parallel_tool_calls` 字段，因此这项属于文档未覆盖，非已证实不兼容，真实启动当天须再次确认。详见 [官方价格](https://api-docs.deepseek.com/quick_start/pricing/) 和 [官方 Chat Completions 参数](https://api-docs.deepseek.com/api/create-chat-completion/)。

## 历史结果不变

前次 `R1-J2-LIVE-RECHECK-01` 真实结果仍为 J1-01/J1-02 PASS、J2-01 FAIL、J2-02 PARTIAL，8 次 Provider 请求、9 次本地 MCP、Campaign `STOPPED / CAMPAIGN_FINISHED`。本报告不续跑、编辑或复用旧 Campaign。其私有运行数据没有在本轮触碰；公开报告、Trace、成本及失败文件的本地 SHA 记录在 `EVIDENCE_HASHES.json`。

前次离线 F1/F2 证据说明：合法同订单 Event 能查询，跨订单拒绝；不同 Event 的历史和当前观察不互相借用；没有当前 `event-previous` Receiver Observation 时不应宣称已处理。当前离线验证没有替代真实模型对这些改动的再次判断。

## 后续条件

获得针对本新 Campaign 的独立明确用户付费授权后，才可按 PLAN 冻结的预算、模型、参数、独立数据库/Checkpoint/Grant/Claim 运行一次。首次发送之前仍须检查密钥可用性（只记录状态）、当前价格、运行身份、最终序列化报文、持久预留与停止守卫；缺任一项即不发送。不能使用旧 STOPPED 余额或通过重启/新 Session 重置预算。

本轮未执行全仓 pytest、真实 Provider、浏览器或 R1-INTERACTIVE 验收。

## 六维验收

1. **用户变化：** 本轮没有新真实用户结果；离线正式路径保持可执行。先前真实 J1 协议/配置用户目标成功，J2 真实目标仍未完成。
2. **Agent 决策：** 离线夹具证明机制可接收合法工具决策；真实 DeepSeek 本轮没有运行，因此自主工具行为未验证。
3. **观察驱动：** 离线用例区分 event-current PROCESSED 与 event-previous 历史 HTTP 202；未获得新的 Provider 最终答复验证这种观察是否改变模型结论。
4. **新增约束：** 本轮没有新增硬约束；保留原有 TaskBinding、来源有效性、撤权检查、12K 预算与发送前拒绝。合法工具路径 28/28 通过；超大返回拒绝测试包含在定向回归。
5. **简化结果：** 复用 Assistant/Context/Runtime Grant/MCP/Domain；只新增可复查的预检证据文件，不改生产代码或安全合同。
6. **证据与停止线：** 离线日志 28/28、2/2，相关回归 59/60；真实 Provider、浏览器、外部写入均 0。由于缺少本 Campaign 的独立付费授权，停止在真实发送之前。
