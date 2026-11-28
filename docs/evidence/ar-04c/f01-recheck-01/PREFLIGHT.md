# 真实复验执行前免费预检

- Base：`08b007dda384b03a3b7d1ac6351d8c4ee1dcfb45`；分支 `codex/ar04c-f01-context-currentness-01`；main 开工为 `60eee87bfe3cca522011316cb4cd2c0064ad291b`。
- 本轮实际读取 North Star / AGENTS / 项目 Skill；Blob 分别为 `e36f2f75509738551ac6d4a2de5b4f9cf44a7991` / `f174a6ab7f23f9e6d8b3ef98d455b99a75193143` / `d405c8d413d633824b279202cc1503dab4cf0b03`。
- 用户批准一次新身份 `AR04C-F01-RECHECK-01` 的付费复验；合同见 `CONTRACT.md`。旧实验身份和 Claim 不复用。
- 新身份复用现有账本、Task policy、一次性授权/Claim 和正式 Worker；仅其单请求预留为 USD 0.668468，总额仍为 USD 5.25、最多 8 次 Provider。
- 旧 F01 Context 测试与新身份/MockTransport/正式 API Worker MCP 联合预检：11/11，通过时间 21.35 秒。新增旧身份授权兼容检查：1/1，通过时间 0.83 秒。以上均为离线模型替身，非真实 LLM 行为。
- 新身份未接线时定向 RED：3/3 失败；测试日志显示旧默认额度与缺少新授权路径。初次脚本的控制台输出因 Windows 编码失败，原 pytest 日志已写盘并保留。
- 模拟验证：发往 MockTransport 前 Claim 已持久消费、独立数据库已绑定、USD 0.668468 已持久预留；请求经正式 Worker 和真实本地 MCP。未授权、错误预留、重复 Claim、更换数据库、8 次额度耗尽和 UNKNOWN 后的新 Run 均拒绝。
- 原始日志保留本地 `.log`；公开 `.txt` 仅规范化编码、换行和行尾空白。真实 Provider 请求=0；正式 Claim 未创建；外部业务写入=0。
- 官网上的 Flash 峰值未命中输入和输出价格分别为 USD 0.30/M 与 USD 1.20/M；目录示例上下文为 1,048,576、最大输出 393,216。每次预留依据此包络向上取整，不依赖缓存优惠。执行前再次复核。

执行时将固定源码 Commit 和合同摘要，准备新隔离数据与一次性授权，严格按合同发送。价格或前置条件不能核实时停止，不修改历史记录或扩大授权。
