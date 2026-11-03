# AR-03-MATERIAL-01 — 失败与修复记录

## RED-01 — 首次整合测试（测试准备缺陷 + 产品 RED）

- 命令：`python -m pytest tests/test_ar03_material_01.py -q --basetemp docs/evidence/ar-03/material-01/runs/red-01-tmp`
- 结果：5 failed，退出码 1；原始日志 `runs/red-01.log`、`runs/red-01.exitcode`。
- 两项有效产品 RED：`read_scoped_protocol_excerpt` 不存在；正式 Assistant 的 `load_protocol_upgrade_skill` 提议未执行并记录为 `ASSISTANT_TOOL_NOT_EXPOSED`。
- 测试准备问题：把包含换行的 `HumanMessage` 与 Python 对象 `repr` 字符串比较，断言方式错误。已改成直接比对 `HumanMessage.content`。原始日志保持不变。
- 同次绑定场景中 Skill 工具未暴露，故状态断言失败；这与 Skill 入口缺失一致。

## RED-02 — 修正断言后的整合运行未退出

- 原始尝试使用同一 pytest 命令；进程开始时间 2026-11-03 10:45:19（执行环境本地时间）。因工具会话未返回退出码且无完整日志文件，结果标记 `INCOMPLETE / NOT_COUNTED`。
- 独立 SQLite 临时数据表明该尝试已运行首轮正式 Assistant 路径：无绑定请求实际执行文档发现、原文提议被拒绝；绑定请求执行发现、比较、当前 Delivery/Receiver，但 Skill 提议被拒绝。临时数据库保留在 `runs/red-02-tmp/`。
- 本轮只终止自己启动的两个 Python 测试进程（PID 12516、32896）；没有清除临时库。此 Windows Worker/TestClient 回收问题不等同业务断言通过，后续将用窄化的独立进程测试复核。

## RED-03 — 独立 Domain/来源投影冻结复现（有效）

- 命令：`python -m pytest tests/test_ar03_material_01.py -q -k 'authorized_protocol_excerpt or fails_closed_after_grant or skill_is_integrity_checked or history_projection' --basetemp docs/evidence/ar-03/material-01/runs/red-03-tmp`
- 结果：4 failed、3 deselected，退出码 1；原始日志 `runs/red-03.log`、`runs/red-03.exitcode`。
- 原文读取与授权/摘要重验证两项因 `read_scoped_protocol_excerpt` 尚不存在而失败。
- Skill 正反完整性用例因 `PROTOCOL_UPGRADE_PROBLEM_TYPE` 和对应完整性入口尚不存在而失败。
- 历史原文来源没有专用有界投影，当前退化为 `HISTORICAL_TOOL_RESULT_REFERENCE_ONLY`，不能支撑下一轮对刚才引用条款的指代续接。
- 以上 RED 在生产源码修改前执行；冻结 CASES/Gold 未修改。

## 后续修复记录

实现与 GREEN 结果追加于本文件后续章节。失败日志不覆盖、不重命名、不改写。
