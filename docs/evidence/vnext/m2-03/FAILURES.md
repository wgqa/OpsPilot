# M2-03 失败与修复记录

所有记录按发生顺序追加；原始 RED 日志不可改写。最终评估时逐项标注修复提交与新鲜 GREEN 命令。

## RED-01 — 冻结基线缺少交接能力

- **冻结标准提交：** `35af8d763176705adc844859cd65dc96b087a54c`
- **执行代码 SHA：** `35af8d763176705adc844859cd65dc96b087a54c`
- **命令：** `python -m pytest tests/test_m2_03_handoff.py -q --tb=short --basetemp=.runtime/m2-03-red-01`
- **结果：** 5 failed，1 warning；退出码 1。
- **观察：** 三条 Domain 路径因不存在 `opspilot.domain.s2_handoff` 失败；旧 Draft 当前性用例同样显示缺少 Domain 错误码/拒绝边界；Web `GET /api/tasks/{task_id}/handoff` 返回 404。
- **归因：** M2-02 基线只有诊断 Receipt 和冻结 Draft，没有 Queue、持久 HandoffReceipt 或受控 Web 提交 API。此 RED 符合预期，不是环境失败。
- **原始记录：** `runs/red/red-01/META.txt`、`runs/red/red-01/pytest.log`。
- **处理：** 尚未修复；测试与日志先提交保留，再开始实现。
