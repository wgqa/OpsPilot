# R1-J2-LIVE-RECHECK-02 — 离线准备与执行边界

**状态：`EXECUTION_READY / AUTHORIZATION_REQUIRED`**
**准备日期：** 2026-11-08
**仓库：** `wgqa/OpsPilot`
**基线：** `codex/r1-j2-f2-headroom-hf01@1be7739a454f27fb48141dd6f5f507f45253a826`
**执行分支：** `codex/r1-j2-live-recheck-02`
**冻结 CASES Blob：** `320bab6afc5668c675455d370e6a3ded51119b08`

## 范围

只准备冻结的 J1-01、J1-02、J2-01、J2-02 同 Session 用户旅程；验证 F1 当前查询输入/历史任务锚点分离、F2 来源投影和摘要去重、12K 预算前拒绝、正式离线 API/Worker/Assistant/MCP/Domain 路径及授权/Runtime 回归。真实 DeepSeek 行为只能由新 Campaign 的实际 Provider Trace 证明。

冻结输入和 Gold 直接来自 `docs/evidence/vnext/r1-j2-live-recheck-01/CASES.json`，不复制改写。前次 Campaign `R1-J2-LIVE-RECHECK-01` 保持 `STOPPED / CAMPAIGN_FINISHED`；本次没有读取、复用或修改其私有 DB、Checkpoint、Grant、账本或 Claim。

## 远端与源码基线

- Base 分支远端 SHA：`1be7739a454f27fb48141dd6f5f507f45253a826`。
- 远端 `main`：`60eee87bfe3cca522011316cb4cd2c0064ad291b`；`git ls-remote` 与 GitHub compare 独立核验。
- Base 是 `main` 的后代，当前比 `main` 领先 45 个提交；本任务不合并 main。
- 新候选分支在准备开始时不存在；基于精确 Base 建立，不覆盖其他工作树。
- 实际读取文件 Blob：`PROJECT_NORTH_STAR.md` `43dabda468506717c6956e676dfad4304c4f38e6`；`AGENTS.md` `807b928686a4dd2cac7b15b3c354b9943c93c910`；项目 Skill `d405c8d413d633824b279202cc1503dab4cf0b03`。
- 冻结 CASES 的 Git Blob 与任务卡一致；本地文件 SHA-256 和历史公开证据哈希见 `EVIDENCE_HASHES.json`。
- 本次仅增加证据文件；没有生产源码、测试源码、Gold 或历史报告改动。

## 拟定真实执行合同（仅供单独授权后使用）

| 参数 | 冻结建议 |
|---|---:|
| Provider / Model | DeepSeek 官方 API / `deepseek-flash` |
| Thinking / `max_tokens` | disabled / 2048 |
| 输入预算 | 12,000 tokens |
| 请求数 / 应用费用池 | 最多 12 / USD 8.00 |
| 每次发送前持久预留 | USD 0.645600；12 次总预留 USD 7.747200，低于上限 USD 0.252800 |
| 超时 / 并发 / 重试 | 30 秒 / 1 / 自动和人工重试均为 0 |
| 报文 | `stream=false`；有 tools 时 `tool_choice=auto`；`parallel_tool_calls=false` |

当前官方文档在本次准备日显示：Flash 版本 DeepSeek-V4.1-Flash-1017，Context 1M、最大输出 384K；峰值 cache-miss 输入 USD 0.30/M、输出 USD 1.20/M。按 12K 输入与 2048 输出估算，峰值单请求约 USD 0.0060576，12 次约 USD 0.0726912；应用账本仍按批准的较大保守预留保护。价格会变，真实执行当天必须重查。[DeepSeek Models & Pricing](https://api-docs.deepseek.com/quick_start/pricing/)；参数能力见 [Chat Completions API](https://api-docs.deepseek.com/api/create-chat-completion/)。

离线正式请求由 MockTransport 实际捕获并断言 `deepseek-flash`、`thinking.type=disabled`、`max_tokens=2048`、`stream=false`、有工具时 `tool_choice=auto`、`parallel_tool_calls=false`。官方 Chat Completions 页面没有明确列出 `parallel_tool_calls` 字段；这属于文档未明确覆盖，并非已证实的不兼容。首次真实执行前须再次核对官方接口与最终序列化报文。

## 停止条件与当前授权

用户提供的本任务卡明确说“实施与复验计划不自动构成新 Campaign 的付费发送许可”。当前对话没有独立授权 `R1-J2-LIVE-RECHECK-02` 的收费执行。因此本轮不创建真实 Runtime Grant、Campaign 数据库、Checkpoint 或 Claim，不检查/输出凭据，不发送 DeepSeek。未来只有获得新 Campaign 的明确用户授权后，才能以当时的最终候选 SHA、冻结 CASES Digest 和独立资源建立一次性执行身份；旧 STOPPED Campaign 永不复活。

授权后只运行一次四轮旅程；Provider UNKNOWN、Usage 无效、费用或身份/价格异常、超预算、越权、或 Campaign STOPPED 均停止全部真实发送。没有外部写入、审批、Repair、Deliver、Handoff 或浏览器自动化。

## 六维检查

1. **用户变化：** 若获授权并完成，用户可在同一 Session 得到协议比较、配置解释、当前 Event 事实及 Event 更正后的客户说明；本轮尚未产生这些新真实用户成果。
2. **Agent 决策：** 冻结旅程仍由模型选择合法 Knowledge/MCP、顺序、澄清、补查或停止；离线 Fixture 不代表真实模型决定。
3. **观察驱动：** event-current 的 PROCESSED 与 event-previous 只有历史 HTTP 202、无当前 Receiver Observation，应该得到不同且有限的结论；本轮用保存的旧真实失败和离线对照说明，不称新真实复验。
4. **双向约束：** 可信 TaskBinding 保留同订单内合法 Event 查询，跨 Event 事实不混用；12K 超额在 Provider 发送前拒绝，正常工具后续在预算内可继续。任务不增加新硬 Gate。
5. **简化结果：** 仅复用现有 Assistant、Context、Runtime Grant、MCP 和 Domain；未引入新状态平台或另一个 Loop。
6. **证据与停止线：** 离线 28/28 与额外 MCP 2/2 通过；相关回归 59/60，保留一项既有断言差异；真实 Provider/新 Campaign 为 0；当前停止于需要独立付费授权。
