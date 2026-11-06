# PRODUCT-01-SLICE-02 启动记录

`BLOCKED_BEFORE_PROVIDER_SEND`。任务卡要求在收费前确认模型及费用额度。本轮等待用户确认 `deepseek-flash`、一轮 Campaign、最多 24 次 Provider 请求及 USD 2.00 应用费用上限。Provider HTTP 0，模型 Usage 0，已结算与未决预留各 USD 0，外部业务写入 0。四轮输入已冻结，当前尚无持久模型回答。

- 基线为 `3ff5678a2f067ad2bef7945095395d26d59b5328`。已读取总纲、AGENTS 和评审 Skill，Blob 分别为 `4850247350f71635d176699e304a5208d72adf0c`、`b606084799e463a6fb6ffeb6b18aa1f6b4afa64d`、`d405c8d413d633824b279202cc1503dab4cf0b03`。适用本轮任务卡、M2-01/M2-02 延期门禁和既有只读边界。
- 本机配置存在对应凭据。独立 Domain SQLite 中已有两条本地 HTTP 202 传输记录，目标订单的当前投递为 `event-current / ACKNOWLEDGED`，Receiver 为 `PROCESSED`。`event-previous` 留有该事件的历史传输记录。正式一次性 Claim 尚未创建。
- 复用正式 Provider 工厂及现有授权、预留、结算与 UNKNOWN 停止逻辑。新身份用同一独立账本计入回答和压缩，保留标准 Task、Run、MCP、Context 与时间限制。
- 价格版本为 `DEEPSEEK_FLASH_PEAK_2026-11-07`。非缓存峰值每百万输入 USD 0.30、每百万输出 USD 1.20。按官方上下文和最大输出容量的组合上界，单次发送前保守预留 USD 0.668468。有效 Usage 按峰值结算，未知结果保留原预留并停止。账本金额为应用侧估算。[官方模型与费率](https://api-docs.deepseek.com/quick_start/pricing/)，[Chat Completions 参数与 Usage](https://api-docs.deepseek.com/api/create-chat-completion/)。
- 三项定向检查通过，覆盖新身份的授权、持久预留、同一预留防重发、数据库绑定，以及历史授权和 UNKNOWN 行为。单次显式 MockTransport 用于检查发送边界。真实旅程尚未启动。

| 可核对项 | SHA-256 |
| --- | --- |
| 冻结四轮合约摘要 | `b137b56b6509e72128b8e9ef2411531dd8b14ab4b7d0ab332f9b68555cad6e84` |
| 私有执行入口 `run.py` | `3e779b09a0a66e33f77de40558006c487bc1356a54b35b9ad55ec4dfe8e551ee` |
| 私有隔离夹具记录 `fixture.json` | `5764bdfeebab6a5f1269c2d01f843c28efa33112054aa650261253bb15009bdf` |
| 定向检查日志 | `2335ec9e2bcbd36a3908572c534ad60ce6a66434592f7155554933f60ee96465` |
