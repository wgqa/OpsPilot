# 失败与未完成项

## 1. 首次启动：发送前阻断，已修正私有 Runner

第一次启动记录 `ModuleNotFoundError`。Runner 位于仓库外的私有目录，启动时只把 `tests/` 加入 `sys.path`，没有加入正式工作树根目录；因此本地 `opspilot` 包不能导入。该失败发生在创建隔离 Domain DB、Runtime Grant、Campaign 账本和任何 Provider HTTP 之前：没有 DB 文件、没有 HTTP Trace、发送数为 0。只在私有 Runner 中补入仓库根路径后，继续原授权的单次 Campaign；原阻断事实保留。

## 2. 四轮真实 Assistant Run 全部失败

四次真实 DeepSeek Chat Completion 都收到 HTTP 200，返回有效 Usage、Completion ID，并产生格式有效的模型工具提议。随后正式 Assistant Run 均以 `OpenAIConnectionError` 结束：

- `task_runs.status=FAILED`，错误为 `ASSISTANT_STOP:OpenAIConnectionError:Connection error.`
- `chat_attempts.error_class=OpenAIConnectionError`，无 Assistant 成功答复。
- `assistant_calls.status=UNKNOWN`，Runtime 调用状态为 `RESPONSE_STORED`，含 HTTP 响应、Usage、Completion ID。
- MCP 工具调用数为 0，Observation 数为 0；用户看到的是程序生成的失败通知，不是模型回答。

因此，本次工具提议不能算作工具执行或业务事实，HTTP 200 不能算作用户目标完成。程序通知称“费用状态未能确认、已预留额度仍保留”，但 Runtime Ledger 实际已有有效 Usage 并按单次费率完成结算；该通知与账本状态不一致，作为后续产品问题保留。本轮不追改历史用户答复、不重启 Campaign。

### 可能相关的响应解码缺陷

针对请求完成后抛 `OpenAIConnectionError`，用显式离线 HTTPX MockTransport 对 Runtime 响应包装做了定向复现。HTTPX 先解码 gzip 正文，Runtime 包装层再将已解码正文与原始 `content-encoding: gzip`、`content-length` 头重建，导致外层 HTTPX 抛出 `DecodingError: incorrect header check`。新增 RED 后已修复：重建响应时去除对应的内容编码与传输分帧头，保留其余响应元数据；回归测试通过。

这证明存在一个确定的 Runtime HTTP 包装缺陷，但本次真实响应记录没有保存 `Content-Encoding` 头，故不能证实该缺陷就是四次真实失败的唯一根因。真实失败的异常 cause chain 也未被原 Run 持久记录。真实模型响应本体经离线 ChatOpenAI MockTransport 解析成功，说明记录到的 JSON/工具调用结构可被当前 SDK 解析；仍无法据此证明真实响应头路径。

## 3. J3/J4 未运行

新建隔离 Campaign DB 中没有已有的可信 S1 Outcome、S2 DiagnosisReceipt 或 HandoffReceipt（计数均为 0）。按冻结范围没有运行新的 Investigator、没有制造结果，也没有用其他 Session 的回执伪装回读。J3/J4 为 `NOT_RUN`。

## 4. 测试环境第一次启动错误

一次相关回归调用指定了不存在的外部 pytest 临时目录父目录 `D:\OpsPilot-pytest`，导致 42 个 fixture 在 setup 阶段失败、2 项无需该 fixture 的用例通过。创建该外部临时目录后，重新运行同一组相关测试，结果为 44 passed，31.56 秒，退出码 0。该问题是测试命令环境路径，不是代码失败；首次错误已在测试日志中保留。

## 5. 下一次真实执行前置

本 Campaign 已停止且没有可复用的请求额度。任何真实复验都必须由新的明确授权和独立 Campaign/预算账本启动；不得恢复本次已停止身份或重发这四个逻辑请求。优先核实 HTTP 解压头在真实返回中的记录，并保存异常 cause chain，再检查 Runtime Ledger 与用户失败提示的一致性。真实 Provider 重跑不属于本次范围。
