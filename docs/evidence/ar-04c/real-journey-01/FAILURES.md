# AR-04C-REAL-JOURNEY-01 — 失败与未完成项

本清单保留失败事实；修复后的日志与原始失败日志均保存在 `runs/`，不以最终绿色结果覆盖失败。

## 已修复的本切片测试问题

下列初次测试问题由本候选中的最小修正处理；日志保留：

- Runner/pytest 入口与解释器环境不一致：直接使用系统 Python 时缺少项目依赖。后续使用 `D:\学习\agent新项目\.venv\Scripts\python.exe` 执行，保留 `pytest-ar04c-redgreen-01-python-module.log` 和 `pytest-ar04c-green-venv-*.log`。
- 新隔离 Campaign 价格校验阻断：官方价格表显示 Flash 峰值输出为 `$1.20/M`，不是草稿中的 `$1.32/M`。初稿曾无法同时满足 8 次/条件和 `$5.25` 预算；纠正了 AR04C 专属费率与预留，保留 `pytest-ar04c-price-red-01.log`、`pytest-ar04c-final-price-corrected*.log`。任何旧实验价格版本和账本未修改。
- Fixture 回答与 MCP 请求脚本的多轮响应曾不匹配，及初始测试断言/导入错误：保留 `pytest-ar04c-redgreen-01.log`、`pytest-ar04c-green-venv-01.log` 至 `-06.log`。最终当前源码专项结果见 `pytest-ar04c-final-evidence-01.log`，6/6 通过。

## 当前未关闭

1. **扩大回归 TestClient shutdown 停滞：** `pytest-ar04c-regressions-final.log` 的 AR-03 `test_remainder_mocktransport_formal_worker_observes_same_event_and_serializes_live_contract` 到达 Starlette `TestClient.wait_shutdown` 后未及时退出，60 秒 faulthandler 捕获现场后中断，退出码 1。业务测试主体之前有通过记录，但此次扩大套件没有完整结束。根因尚未证实，可能涉及 Worker/ASGI 关闭等待或测试间状态；本报告不猜测。没有第三次或更多全量重跑。
2. **真实 LLM 与真实费用：** 未授权、未运行；真实模型行动、Usage、供应商账单及 ON/OFF 质量差异均 `NOT_RUN`。
3. **Skill 使用：** 目标 Skill Loader 在两组均可选暴露；固定 Fixture 轨迹没有实际调用它，不能评价 Skill 效果。
4. **浏览器验收：** 未运行。
5. **PROCESSED 对照：** 不属于本次冻结首轮旅程；本轮只验证冻结的 `202/ACKNOWLEDGED + QUEUED`。

## 当前测试状态

- AR-04C 定向：6 passed。
- AR-04A/04B、AR-02 prepaid HF01、M4 CONT-UX Stage A 适用回归：46 passed。
- 扩大 AR-03 回归：中断于上述 shutdown 等待，不能记为 PASS。
- `py_compile`、`git diff --check`：通过。
- 全量 pytest：未完成。

所有原始失败、超时堆栈与中间日志仍在 `runs/`。本切片不通过改写 Gold、过滤该失败或重跑直到成功来改变结果。
