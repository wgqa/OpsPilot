# R1-J2-02 可信复测替代方案

现存结束态数据库不能安全转换为 J2-02 前状态。下一次需要比较真实模型表达时，建议完整地在新实验中按冻结顺序执行同一 Session 的 J1-01、J1-02、J2-01、J2-02。

## 执行身份和范围

- 使用全新 Campaign ID、Domain DB、Checkpoint、Runtime Grant、Ledger 与 one-shot Claim。
- 只读复用同一冻结 CASES/GOLD、模型及请求参数；不变更旧实验。
- 模型顺序、工具选择和补查保持自主，不注入“正确措辞”或预设工具轨迹。
- J2-02 没有业务回执时，评估客户草稿是否把建议误述为已启动、已安排或已承诺的后续工作。
- 原样保存首次 J2-02 PARTIAL 与新结果，做并列、非统计性比较。

## 冻结四轮输入与夹具

按 `docs/evidence/vnext/r1-j2-live-recheck-01/CASES.json` 原文，不改写：

| 轮次 | 用户输入 / 可信动作 |
|---|---|
| J1-01 | “请比较回调重试协议 v1 和 v2 的差异，并说明配置可能受影响的部分。” |
| J1-02 | `结合刚才的协议看这份配置：{"callback":{"retry":{"max_attempts":5,"backoff":"fixed"}},"event_id":"event-previous"}` |
| J2-01 | 先通过正式 `POST /api/sessions/{session_id}/assistant/order` 可信绑定 `r1-readiness-order`，再提交：“请核实 event-current 的当前回调投递和接收方处理状态。” |
| J2-02 | “我更正目标：请查 event-previous，不是 event-current；说明它是否已经处理，并给一份客户说明草稿。” |

隔离夹具保持 `event-current` Delivery=`HTTP 202 / ACKNOWLEDGED`、Receiver=`PROCESSED`；`event-previous` 只有历史 HTTP 202 transport attempt，当前 Receiver observation 缺失。两者不可混用。

## 预算建议（待主 Agent/用户单独批准）

- DeepSeek `deepseek-flash`；最多 12 次 Provider 请求。
- 应用侧预算最多 USD 8.00；每次出站前持久预留 USD 0.645600。
- 并发 1、超时 30 秒、零自动重试、零人工重发。
- 独立费用账本，UNKNOWN 保留预留并停止整个 Campaign。

该预算只是建议，不能创建 Claim，也不授权 Provider 请求。执行前重新核对价格、凭据、参数和隔离身份。若今后从新运行开始设计“只复测最后一轮”，必须在首次 J2-02 前保存并哈希成对的 Domain 与 Checkpoint 快照；该快照应由实际三轮执行产生，不可从结束态数据库倒删或人工拼装。
