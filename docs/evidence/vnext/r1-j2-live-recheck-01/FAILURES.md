# 失败、停止与历史完整性

## 本次冻结案例

### J2-01 — FAIL

TaskBinding 已由可信订单 API 创建，且当前输入明确指定 event-current。模型调用了 4 次 Knowledge/协议 MCP，未调用任何 Delivery/Receiver 工具；最终又要求用户重复指定 Event。它没有越权读取，也没有声称已查询。原任务 Gold 不满足。

真实输入在 context 中被包装为 ORIGINAL_TASK_INPUT (UNTRUSTED USER INPUT)。SYSTEM 同时说明同一 TaskBinding 内明确 Event ID 是合法只读查询目标。模型将“不可信输入不能授权”错误泛化为“不能把当前 Event 用作查询目标”。这是本次真实模型策略失败，不是 Domain 授权拒绝。

### J2-02 — PARTIAL

模型自主提议了 3 个工具并获得成功结果：

- Delivery 和 Receiver 的当前记录属于 event-current；
- 指定 event-previous 的传输历史有一条 HTTP 202，记录不能证明当前 Receiver 状态。

后续模型调用在发送前被 ContextBudgetExceeded 拒绝，估算 12,199，高于 12,000 限额。最终没有模型答案、未知状态解释或客户说明草稿；持久 Run 为 FAILED，用户收到程序预算通知。没有把 event-current 的 PROCESSED 说成 event-previous 已处理，但也没有最终回答证明这一点。

这不是 Provider UNKNOWN：前一请求是 HTTP 200、Usage 有效且已结算，之后没有出站请求。

## Campaign 状态

- Campaign 持久结束：STOPPED / CAMPAIGN_FINISHED。
- Provider：8 次 SEND_GRANTED / 8 个 HTTP 200 / 8 个有效 Usage；未知、重试、人工重发均为 0。
- MCP：9 次调用，均 OK。
- Runner exit code 2 表示 PARTIAL，不表示基础设施 UNKNOWN。
- 真实运行后未改源码、未重启、未消费第二个 Claim，也未发送额外请求。
- 外部业务写入、Approval、REPAIR、DELIVER、Handoff、浏览器自动化为 0。

## 历史证据完整性

原 R1-LIVE-JOURNEY-02 运行数据库、Checkpoint、执行 JSONL、Provider HTTP JSONL 的运行前/后 SHA-256 一致：

| 文件 | SHA-256 |
|---|---|
| domain.sqlite3 | 3f2e5996aaea033d7ca13476c23bfa18ea898e732dc3aaf7d51c7afd4f7b793c |
| checkpoint.sqlite3 | c13596fb117e08afae021b4d2f3fa2b3634aafaaa54844c2ee16e9ae485da412 |
| execution.jsonl | 416149bcc85c749aef2662d57f329f289bde4cf855084499c7f495e67bc5fa28 |
| provider_http.jsonl | cdaa6f7fc24e912b62df921551690495dc407cfbf8e61924e3c53ef1e5d234a5 |

新运行的原始私有材料哈希列于 REPORT.md。API Key 只在进程环境中使用；本地扫描未发现该值出现在新运行日志或公开 TRACE。

## 下一步建议

不要复用或恢复此 STOPPED Campaign。若后续要验证 J2 完成，先在离线环境针对两件事作最小修正和回归：让上下文清楚地区分可信订单范围与不可信文字授权；在不改变 12K 限额且保留当前 Observation 的前提下，减少下一模型调用中的重复历史负荷。之后须为新的真实 Campaign 单独授权；本次授权已消费。
