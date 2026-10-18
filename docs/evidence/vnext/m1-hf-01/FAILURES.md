# M1-HF-01 失败与修复记录

本文件与 `logs/` 一起保留失败证据；RED 文件没有被成功日志覆盖。

## 原版缺陷 RED

| 场景 | 实际观察 | 日志 |
|---|---|---|
| HF-01 | ABORTED Task 的旧可恢复 Run 仍为 `INTERRUPTED_RECOVERABLE` | `pytest-hf01-red-venv.txt` |
| HF-02 | 正式纠错后旧 Run 仍可恢复，控制版本失效未收口 | `pytest-hf02-red.txt`, `pytest-hf02-red-corrected-order.txt` |
| HF-03 | 缺模型配置后 Run 仍是 `QUEUED` 且无失败分类 | `pytest-hf03-red.txt` |
| HF-04～06 | REPAIR、验证、报告、DELIVER 提交窗口的 APPROVAL_RESUME 被 `APPROVAL_RESUME_LINK_INVALID` 拒绝 | `pytest-hf04-hf05-hf06-red-original-gate.txt` |
| HF-07/08 | 首 Checkpoint 前进程退出后，新 Worker 无法以原始来源上下文创建首个 Checkpoint/Prompt | `pytest-hf07-hf08-red-original.txt` |
| HF-10 | health 响应缺少 API liveness 字段，测试得到 `KeyError: 'api'` | `pytest-hf10-red.txt` |

这些是本轮在基线代码上执行所得，不使用第三方历史 `40/40` 或 M1-06 结果代替。

## 中间环境与测试夹具失败

- `pytest-hf-worker-red.txt` 与 `pytest-hf07-hf08-red.txt` 一次使用默认系统临时目录时遇到 Windows ACL `PermissionError`。之后指定仓库 `.runtime/pytest-m1-hf-...` 为 `--basetemp` 后可以执行。`pytest-hf-worker-red-02.txt`、`pytest-hf-worker-red-local-basetemp.txt`、`pytest-hf01-green-1.txt` 等零字节日志是 PowerShell 管道未捕获输出的尝试，保留但不作为结果证据。
- `pytest-hf02-green-1.txt`、`pytest-hf04-repair-green-debug.txt` 记录早期故障注入顺序/夹具状态不匹配。调整 setup 后由 `pytest-hf02-green-2.txt`、`pytest-hf04-repair-green-debug2.txt` 通过。
- `pytest-hf09-green-1.txt`、`pytest-hf09-green-2.txt` 首次负例先被更早的 TaskControl/请求前置门禁拒绝，且一项测试遗漏导入。修正测试夹具和导入后，`pytest-hf09-cold-recovery-final.txt`、`pytest-hf09-precheckpoint-control-green-1.txt` 与最终定向集通过。
- `pytest-hf07-hf09-green-1.txt` 的 Plan 冷恢复负例最初触发更早的 Task phase guard；有效初始恢复阶段夹具在 `pytest-hf09-cold-start-existing-plan-green-1.txt` 和最终定向集通过。

带 `debug` 的日志保留调试输出；带 `red` 的文件可能为产品 RED，也可能是上述环境错误，应结合本表阅读。

## 最终状态

最终全量 140/140、定向 31/31 通过，原始输出在 `pytest-full-final.txt` 和 `pytest-targeted-final.txt`。静态检查输出在 `compileall.txt`、`pip-check.txt`、`git-diff-check.txt`。无最终测试失败。真实模型 Provider、浏览器 smoke 和外部业务系统没有调用，属于未执行能力，不能标作已验证。
