# M4-EG-01 RED 与失败记录

## 有效业务 RED

- `runs/red-sla-05/pytest.log`：冻结的定向用例执行结果为 **5 failed, 1 passed**，退出码 1。
- 四个独立 Chat Readonly 用例在真实 `prepare_chat_attempt()` 出站消息上均未找到同一事件的 PROCESSED、QUEUED/SLA、HTTP 202/UNKNOWN 规则。其 Gate 和当前观察状态已经正确，缺口位于 Chat 解释 Context。
- 版本化 Knowledge 检查发现 `receiver-ack-contract-v2` 仍为 `2.0.0`，内容没有明确规定“当前同事件 PROCESSED 即可证明完成，即使尚未到 SLA”。
- 同次 RED 中 Memory ON/OFF 的实际 Investigator `model_call()` 消息捕获通过：已批准 Memory 可进入目标 Run 的出站上下文，OFF 时不注入且记录 `EVALUATION_MEMORY_OFF`。

## 测试准备失败（保留，但不是业务证据）

- `runs/red-sla-01/pytest.log`：第一次 pytest 的 `--basetemp` 父目录未创建，4 项 setup error；另 1 项因待修复的 Knowledge 断言失败。不能作为业务 RED。
- `runs/red-sla-02/pytest.log`：临时目录问题修正后，测试 harness 错把 `prepare_chat_attempt()` 返回值当成带 `run_id` 的对象，并未先 claim Investigator Run；6 个失败不作为产品结论。
- `runs/red-sla-03/pytest.log`：改正 Run claim 后，S3 测试时钟早于实际 Observation 导致全部证据超前于假时钟；此日志是时钟准备失败，不作为产品 RED。
- `runs/red-sla-04/pytest.log`：统一时钟后，SLA Gate 和当前 Evidence 均通过；Memory 用例的工具名断言错误地要求工具名出现在消息正文，而工具 schema 是模型调用的独立 tool binding；不作为产品 RED。
- `runs/red-sla-05/pytest.log`：最终冻结定向 RED。4 个 SLA Chat Context 规则缺失，Knowledge 版本/内容不满足新合同；Memory 出站测试通过。

所有失败日志均原样保存；后续 GREEN 使用不同的运行目录，不覆盖以上文件。
