# M1-01 主 Agent 复核补正

**结果：PASS（本次补正）**。从 `main@e35eeab5f7fdf00c3af466ea84bf5ba5aafc50fb` 开始，只修改 TaskControl 的 revision 判定、只读 Run 的 Task 状态投影及对应回归测试。未进入 M1-02，未改架构/业务合同。

## 修正内容

1. `claim_task_run()`、`resume_task_run()`、`apply_pending_critical_inputs()` 先显式判断 `expected_control_revision is None`，然后比较整数值；合法 revision `0` 不再被 `or -1` 转换为缺失值。新增 revision=0 的 Run claim、无待处理输入检查、WAITING_APPROVAL 恢复回归。
2. `finish_task_run()` 仍记录 `CHAT_READONLY` Run 自身结果，但不再把该 Run 的状态映射到 `task_bindings`。新增 S1 回归：只读 Run 成功后 Task 仍处于 WAITING_APPROVAL，随后现有审批→REPAIR→在线 200→DELIVER 链路仍成功；交付后再完成只读 Run，Task 保持 COMPLETED，REPAIR/DELIVER Ledger 各一条。

## 本轮新鲜验证

环境沿用当前仓库 `.venv`：CPython 3.14.0、pytest 9.1.1。命令、原始 pytest 输出和检查日志位于本目录 `logs/`。

| 检查 | 命令 | 结果 |
|---|---|---|
| 新增用例定向 | `.\.venv\Scripts\python.exe -m pytest -q -s tests/test_m1_task_control.py -k "revision_zero or chat_readonly" --basetemp=.runtime/m101-review-fix-cases` | **2 passed, 9 deselected** |
| M1 TaskControl 全集 | `.\.venv\Scripts\python.exe -m pytest -q -s tests/test_m1_task_control.py --basetemp=.runtime/m101-review-fix-focused` | **11 passed** |
| 全量回归（含原 N1-09/10/11、F1–F3 与 D1–D7 测试） | `.\.venv\Scripts\python.exe -m pytest -q -s --basetemp=.runtime/m101-review-fix-full` | **75 passed / 75，50.71s** |
| 静态检查 | `.\.venv\Scripts\python.exe -m compileall -q opspilot tests` | PASS |
| 依赖检查 | `.\.venv\Scripts\python.exe -m pip check` | PASS：No broken requirements found |
| whitespace 检查 | `git diff --check` | PASS，exit 0；仅有 Windows CRLF 标准化提示 |

全量 pytest 内仍出现既有 `test_d3_smoke_preserves_failed_start_process_without_crashing` 的预期 `d3_smoke_result FAIL` 事件。该测试人为注入 provider timeout 并断言失败被保存；pytest 本身通过，不是本轮真实模型调用失败。N1-09/10/11 在本次全量与定向 M1 集中均通过。

## 边界

这次只处理主 Agent 指出的两个源码边界。没有实现 M1-02，没有改变只读调查、审批、修复、交付或 Task 终态合同。原 M1-01 运行报告及历史日志未覆盖；本补正有自己的命令与新鲜原始日志。代码提交和远端 `main` 的最终 SHA 由本轮交付回报中的 `git rev-parse HEAD` 给出。
