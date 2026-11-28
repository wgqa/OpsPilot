# R1-J2-LIVE-RECHECK-02 — 失败与未完成项

## 旅程质量缺陷

### J2-02 客户草稿包含未执行的后续承诺

- 真实回答先正确说明 `event-previous` 只有 HTTP 202 / 当时 QUEUED，当前处理结果未知；`event-current` 的 PROCESSED 不适用于目标 Event。
- 同一草稿随后写“后续将由相关团队按正式流程进一步核实……并在有结论后同步给您”。本轮没有工单、交接、联系接收方或其他后续动作回执。
- 根因归类：模型生成的用户交付措辞问题。程序没有伪造 Observation 或业务动作；程序也没有阻止该承诺进入最终答复。
- 影响：客户若直接发送草稿，会误以为后续核查和反馈已被承诺。
- 结果：J2-02 `PARTIAL`，Campaign 不重跑；最小离线修复需另行授权或任务卡。

## 调查效率 / 预算观察

- J2-01 的同一 Run 已得到订单、Delivery、Receiver Observation，模型仍再次发现并读取协议。
- 模型提出 7 个该 Run 内的 MCP 工具调用；6 个成功执行。第 7 个 `read_scoped_protocol_excerpt` 通过 ToolMessage 收到 `ASSISTANT_RUN_MCP_LIMIT`，响应明确 `executed=false`。它不在实际 MCP 成功记录中。
- 最终答案仍由已获得的协议比较与当前业务 Observation 支持，没有因此影响该案例 Gold。
- 影响：冗余调用消耗本 Run 容量；本轮不据此添加禁止重复查询的 Gate，也不改变预算常量。

## Provider / Campaign 硬停止

- 无 Provider HTTP 错误；9/9 为 HTTP 200 且有 Usage。
- 无 UNKNOWN dispatch、无未知 Usage、无重试。
- Campaign 以 `CAMPAIGN_FINISHED` 正常停止；使用 9/12 次发送上限。

## 发送前 Runner 阻断（均为零 Provider 请求）

以下均发生在第一次 HTTP 出站之前，不能归为模型失败：

1. 私有 Runner 初始化时出现 `NameError: name 'private' is not defined`。该次未创建 Claim/DB，也未发送 Provider。修正局部变量引用后继续。
2. 隔离 DB、Fixture、Runtime Grant 和唯一 Claim 创建后，测试凭据模块导入失败：`ModuleNotFoundError: No module named 'test_ar02_assistant'`。当时 Claim 状态仍为已配置、发送数 0，账本无 spend、Checkpoint 不存在。修正 Runner 的 `tests` 导入路径后，没有重建 Grant 或数据库，而是复用同一 Claim。
3. 恢复路径核对数据库时发现私有 Runner 查询了不存在的 `assistant_runtime_spends.request_key`；实际主键为 `dispatch_id`。Runner 改为读取 `dispatch_id AS request_key`。该检查发生在恢复发送前，状态仍为零发送。

前两次 Runner 输出的原始 stdout 未持久化；私有 `PRE_SEND_SETUP_FAILURES.jsonl` 保存了错误类型、消息、阶段和零发送状态，并明确标注时间戳未保留。不能将其冒称为完整终端原始日志。

## 测试重录未完成

本次为保存当前 SHA 回归的独立日志而重复运行预算专项测试时，pytest 进程超过两分钟无输出且没有可观察的测试进度。进程由实施方中止，PowerShell 退出码为 1，pytest 输出没有被管道刷新到日志文件。该次复测是 `INCOMPLETE/INTERRUPTED`，不计通过。

此前同一源码 SHA `7f8df218415fbbcf4df33001fc593bd772ab880e` 上，定向预算测试已有实际 `42 passed`、退出码 0 的结果；本次中止的重录与该既有结果分开记录。预备阶段另有 28/28、2/2 通过及 59/60（`test_zero_tool_followup_can_explain_valid_historical_snapshot` 的 `KeyError: completed_tools`）日志，均原样保留于本目录的既有 `TEST_LOG_*` 文件。

## 未运行

- 真实浏览器 / Playwright：未运行。
- 全量 pytest：未运行。
- J3/J4：未运行。
- 外部业务写入、审批、Repair、Deliver、Handoff：0。
