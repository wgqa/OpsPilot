# 失败与未验证项

## 原始真实失败（保留）

- **J2-01 FAIL：** 原真实模型未按明确的 `event-current` 只读查询目标继续调查，转做四次协议/Knowledge 查询并请求再次确认。其原始 Provider Trace 未修改。
- **J2-02 PARTIAL：** 三次业务 MCP 已完成，但下一次模型请求估算为 12,199 tokens，超过原 12,000 限额；系统在发送前拒绝，用户未获得该轮模型最终答案。原停止记录与账本未修改。

## 本轮 RED/GREEN

- F1 首次 pytest 启动在 Windows AppData pytest 临时目录遇到访问拒绝；这是测试环境初始化失败，不是产品 RED。之后改用独立 `D:\temp\pytest-r1-j2-closeout-fix-02-*` 临时目录运行。
- F1 正式离线旅程 RED 复现了错误 Run 状态/当前 Event 输入断言；修复后正式 API/Worker Fixture 路径通过。
- F2 RED 确认旧投影重复携带 `completed_tools`、完整版本与 Digest；第二个 RED 确认若移除显式 Domain `call_id` 到模型 `tool_call_id` 的映射，Observation 无法与原 Tool Call 精确对应。
- 修复后当前测试 5/5 通过，适用相关回归 50/50 通过。

## 未验证 / 限制

- 未用新真实 DeepSeek 请求验证模型是否会稳定把 Event 选择理解为只读查询；当前只能确认保存的旧失败与离线上下文修复。
- 对超出 12K 的额外工具结果，行为是安全停止；没有声称任意数量的补查都能继续。
- 本轮未运行浏览器，也未执行 S1/S2 写入路径；二者均在任务授权范围之外。
- 没有修改或恢复已 STOPPED 的 `R1-J2-LIVE-RECHECK-01`。

## 推送阻断

- 本地候选已提交，但远端未发布。`git push` 因到 `github.com:443` 连接失败；GitHub 连接器只读核验成功，但写 Blob 操作返回 `403 Resource not accessible by integration`。远端新候选分支不存在。需在网络可访问且有写权限的终端从该工作树执行普通 push。
