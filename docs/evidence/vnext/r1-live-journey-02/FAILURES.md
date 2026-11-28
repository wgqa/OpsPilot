# 失败、限制与未运行项目

## 本轮阻断

- 当前任务卡明确要求新 Campaign 的真实 Provider 发送另行取得用户明确授权；本轮未取得该授权。因此 J1-01、J1-02、J2-01、J2-02 及 J3/J4 的新真实运行均为 `NOT_RUN`。此项是授权边界，不是代码失败。
- 首次离线编写 R1-LIVE-JOURNEY-02 测试时，RED 为缺少该 Campaign 的冻结策略函数；补充精确政策后，最终相关回归 24/24 通过。
- 初次用 `pytest` 控制台入口启动时，Python 导入路径未包含仓库包，出现 `ModuleNotFoundError: opspilot`；改用 `python -m pytest` 后可正常导入。
- `python -m pytest` 默认选择用户 C 盘 Temp 目录，因目录枚举权限报 `PermissionError`，在测试 Setup 前失败。使用仓库内本次专属 `--basetemp` 后测试通过；没有更改或清理此前用户已有的 `.pytest-tmp-r1-live-*` 目录。

## 继承的历史失败

- 上一 `R1-LIVE-JOURNEY-01` 的四个真实 Run 均失败：Provider 返回 HTTP 200/有效 Usage/tool_calls，但 MCP 为 0。历史 Runtime 账本保存了响应，旧 Assistant Call 标为 UNKNOWN。
- 已证实 Runtime 层 gzip 解码后残留 `Content-Encoding`/`Content-Length` 可导致再次解码；当前实现和 gzip 回归已修正。旧真实 HTTP 捕获没有保存 `Content-Encoding`，不能断定它就是四次真实失败的实际根因。
- 历史原始异常 cause chain 未保存。当前模拟的已知响应解析失败可记录完整异常类型链，但不能补造旧 Run 的原因。
- 两组捕获真实 tool_calls 已可离线通过正式 Worker/Assistant/MCP 执行；后续模型答复是 Fixture，因此不证明新真实 Agent 旅程成功。

## 仍未运行

- 本次真实 DeepSeek Campaign 与 J1/J2 用户旅程：授权未满足。
- Browser/Playwright：未授权且未运行。
- S1/S2 真实业务写入、审批、Repair、Deliver：未执行；离线回放中业务副作用为 0。
- 完整全仓 pytest：未运行。本轮只执行与 Campaign 预算、真实 tool_calls 离线回放及压缩响应解码直接相关的回归。
