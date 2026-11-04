# 失败与未完成记录

保留失败原貌；没有删除测试、改变 Gold 或把未完成执行记为通过。

| 执行 | 结果 | 归因 |
|---|---|---|
| 首次 quiet pytest 尝试 | 中断，无可用摘要 | 约 8 分钟无输出后停止；未计为通过。 |
| 首次完整 pytest，675 项 | 670 passed / 5 failed，exit 1 | 两项 one-shot 测试把当前集成评审分支误当付费授权分支；两项 M1 Web Server 断言遗漏候选已有的 `assistant_model_factory` 参数；一项旧 C1 RED 使用废弃的 `READONLY_FOLLOWUP` 意图。前四项纯测试夹具/期望已最小修正并有目标测试 GREEN。 |
| C1 历史 RED | 仍失败 | 旧意图被当前分类器拒绝，返回 `INVALID_MODEL_CLASSIFICATION` / HTTP 502。对应冻结报告确认现行意图为 `FOLLOW_UP + readonly_action=INVESTIGATE`。保留历史测试，不给生产分类器添加过时兼容。 |
| 修复后完整 pytest 复跑 | 中断，exit 1，无 pytest 汇总 | 31% 附近长时间没有输出。只读临时 DB 显示重复 MCP 读取的 Run 已 `SUCCEEDED` 且有 11 个 OK Attempt，但进程未退出；人工中断。单测独立复跑 1/1 通过。整体复跑结果仍未验证。 |
| `npm run lint` | exit 1 | 仅两个历史问题：`frontend/e2e/m4-03-s3-journey.mjs` unused `access` 和 undefined `setTimeout`。该文件 Blob 与 main 一致；未修改该无关文件。 |
| `git diff --check` | exit 1（仅 evidence） | 全候选报告 476 条历史证据空白告警，源码、测试和 `TASKS.md` 路径检查无告警。未改写原始日志。 |
| 浏览器验收 | `NOT_RUN / BLOCKED_BY_TOOL_ENVIRONMENT` | 既有 Computer Use STOP 未解除；本轮没有使用替代浏览器自动化。 |

首次完整 pytest 的 5 个失败项原名：

- `tests/test_ar03_material_remainder_live_01.py::test_live_authorization_requires_a_new_exact_one_shot_claim`
- `tests/test_ar03_material_remainder_live_01.py::test_one_shot_claim_is_atomic_and_cannot_be_reused`
- `tests/test_m1_web_server.py::test_server_uses_configured_vue_origin_for_exact_origin_guard`
- `tests/test_m1_web_server.py::test_server_defaults_origin_to_same_loopback_api_origin`
- `tests/test_m4_autonomy_c1_red.py::test_explicit_protocol_followup_is_accepted_as_same_task_readonly_run_before_ttl_fix`

## RED/GREEN 夹具修复

原全量运行中的四项候选相关失败已保存于 `runs/pytest-full-attempt-02.log`。测试修正仅将 one-shot 测试中的 Git branch 查询模拟为已授权分支，并额外验证非授权 checkout 会拒绝；Worker 的原子 claim、授权记录摘要、token 摘要及重复 claim 拒绝逻辑未改。Server 测试现在检查实际传入的模型工厂和 Origin；Server 实现未改。

GREEN：`tests/test_ar03_material_remainder_live_01.py` 与 `tests/test_m1_web_server.py` 共 7/7 通过；11 次同名只读 MCP 真实 Worker 测试独立运行 1/1 通过。全量套件在此之后未取得新鲜完整摘要。


## 2026-11-04 收口诊断补充

- 受控全量 pytest 收集 675 项，在约 31% 的目标 Worker 测试上下文退出处停滞；60 秒 faulthandler 栈定位到 TestClient.wait_shutdown / TestClient.__exit__。业务 Run SUCCEEDED，11 个 MCP Attempt 均 OK。人工停止，无全量摘要，最终进程退出码未捕获。
- 邻接组合 8/8（13.31 秒）；原顺序前缀 213/213（198.84 秒，临时 task dump 插件改变调度）；现行 FOLLOW_UP + INVESTIGATE 正式只读路径 1/1（4.87 秒）。均非全量结果。
- shutdown 的具体未完成 asyncio Task 未查明，无生产代码修复；不能排除 Worker 生命周期风险。
- 三个 SQLite 只读复核未发现真实凭据或客户数据；旧 SQLite 阻断判断由本轮证据更新，不再单独阻断。
