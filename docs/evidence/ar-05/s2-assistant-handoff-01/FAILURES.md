# 失败与限制记录

## 本轮测试/包装器失败

原始失败文件保存在本地证据目录；可提交日志与私有原始文件的差异仅限 `RED-GREEN.log` 中个人 Windows 临时目录路径的脱敏。它们未暴露产品代码缺陷。

| 日志 | 原始失败 | 归因 | 收口 |
|---|---|---|---|
| `RED-GREEN-SANITIZED.log` | pytest 在 fixture setup 阶段因默认临时目录的 `os.scandir` 返回 `WinError 5 PermissionError`，用例主体未执行。 | 当前 Windows 默认 pytest 临时根目录权限问题，不是产品失败。公开副本仅将个人临时目录路径替换为占位符；原始日志保留在本地忽略文件 `RED-GREEN.log`。 | 后续命令显式使用当前隔离工作树内唯一 `.pytest-tmp-*` 目录；定向用例和回归正常通过。 |
| `RED-GREEN-02.log` | `KeyError: 'recovered'`。 | 测试错误假设 pre-submit API 必须返回可选字段。 | 断言改为：如有该字段不得为 true；既有状态/权限断言保留。 |
| `GREEN-01.log` | `sqlite3.OperationalError: no such column: event_type`。 | 审计测试误用事件表列名。 | 使用实际 `event_kind` 列，并核对事件历史。 |
| `GREEN-02.log` | `sqlite3.OperationalError: no such column: task_id`。 | 审计查询误假设命令表含 `task_id`。 | 按现有 `target_ref` 及 `command_kind` 读取。 |
| `GREEN-03.log` / `GREEN-04.log` | 完整旅程通过。 | RED 后首个 GREEN。 | 原样保留。 |
| `GREEN-FINAL.log` | 在最终测试文件（含原始用户问题 Trace 字段）上，1/1 通过。 | 最终验证。 | 保留。 |

Windows 控制台/`Tee-Object` 对非 ASCII Trace 的显示存在代码页乱码；测试直接以 UTF-8 写出 JSON Trace。该 JSON 已用 UTF-8 重新解析，并检查字段和状态。不要把控制台乱码当成业务文本损坏。

## 未运行 / 未验证

- `git push -u origin codex/ar05-s2-assistant-handoff-01` 被 GitHub 返回 HTTP 403；随后 `git ls-remote` 也返回 HTTP 403。候选仅在本地，远端存在性未验证；未绕过权限或重试。
- 全量 pytest 未运行。已知 TestClient lifespan shutdown 停滞由先前任务独立记录，本轮不重开该问题，也未声称全量通过。
- 浏览器自动化未运行，既有浏览器 STOP 仍有效。
- 真实 Provider 请求未运行，模型能力与自主工具选择未验证。
- Ruff 未运行，因为当前环境没有安装 `ruff`；前端未修改，因此 typecheck/build 未运行。
- 没有执行真实企业队列、生产 Scope/Policy/Grant 写入、审批、修复或业务恢复。
