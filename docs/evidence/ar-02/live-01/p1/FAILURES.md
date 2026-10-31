# AR-02-LIVE-01 P1 失败与停止记录

所有失败和停止点均保留；没有重试任何 Provider 请求。

## F-00：Python 解释器环境不含项目依赖（预运行）

- 命令：系统 PATH 中的 `D:\python\python.exe` 导入 `langchain`。
- 结果：`ModuleNotFoundError: No module named 'langchain'`。未读密钥、未构造模型、未访问网络、未创建 Run。
- 处理：切换到仓库既有 `D:\学习\agent新项目\.venv\Scripts\python.exe`；版本为 Python 3.14.0 / LangChain 1.4.1 / httpx 0.28.1 / FastAPI 0.137.1。该次环境失败单独保留，不属于 Provider 请求。

## F-01：临时 runner 仓库根目录偏移（预运行）

- 首次启动在 import `opspilot.assistant` 前因 `ModuleNotFoundError: No module named 'opspilot'` 退出。
- 原因：runner 的临时路径计算多向上一级；该错误发生在任何 Run/Provider dispatch 前。
- 原始终端失败摘录见 `runs/runner-path-failure-console.log`，初始 runner 日志和结果见 `runs/runner-path-failure.log` 与 `runs/runner-path-failure-results.json`。错误生成的临时目录已复制记录后清理；没有删除任何用户资料。
- 修正仅触及忽略目录中的临时 runner；正式源码、模型、请求参数均未变。修正后健康与隔离预检通过。

## F-02：冻结 S01 的 Provider 连接失败（强制停止）

- 真实 API：S01 Message `message-0bada149-3f9d-4944-94fc-708f225723c3` 被接受，Run `run-5ca4293b-872c-4806-bd1a-2a48cb66fd1a`，Session `session-ade03c4c-b6a8-48a6-aa80-ea5c3817f4e8`。
- Run 终态：`FAILED`，持久原因 `ASSISTANT_STOP:OpenAIConnectionError:Connection error.`；没有答案 Message/Answer，也没有 Model response、Completion ID 或 Usage。
- 应用账本：MODEL dispatch `ar02-live-dispatch-59a12db9-c08a-4531-915e-2f71150211e8` = `UNKNOWN/UNKNOWN`，预留 USD 0.645600、结算 USD 0。供应商实际是否收到请求及是否计费：`UNKNOWN`。HTTP 捕获器没有观察到请求，不能据此宣称免费。
- 尝试数按持久账本计 1/16，MCP 0/12，应用已保留 USD 0.645600/10.50。无自动重试，未再次发送。
- S02 五轮均 `NOT_RUN`。S01 不属于模型行为或质量评价样本。
- 本次触发授权任务卡“连接/未知费用结果立即停止”条件；不更换网络方式、不重新建库、不重试。

## F-03：失败 Run 后的聊天尝试状态

- 只读 DB 观察发现 task_run 为 FAILED，但对应 `chat_attempts.status=STREAMING`，`error_class` 和 Provider 元数据为空。
- 该状态不改变本次停止结论；当前授权只允许执行冻结实验，未批准产品修复。作为独立运行接线/持久状态缺口交主 Agent复核。

## 未运行项

- S02 五轮、所有真实 Knowledge/业务 MCP、订单绑定、HTTP 事实核验、草稿交付、Usage/实际费用分析：`NOT_RUN`。
- 浏览器和全量 pytest：任务明确禁止/本次未执行。
