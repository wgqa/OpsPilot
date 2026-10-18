# M1-HF-01 复现运行手册

在仓库根目录 PowerShell 执行，使用 `.venv` 与 `requirements.lock.txt`。

```powershell
.venv\Scripts\python.exe -m pytest -q tests/test_m1_hf_worker.py tests/test_m1_web_approval.py --basetemp .runtime/pytest-m1-hf-targeted-final-20261019-1
.venv\Scripts\python.exe -m pytest -q --basetemp .runtime/pytest-m1-hf-full-final-20261019-1
.venv\Scripts\python.exe -m compileall -q opspilot tests
.venv\Scripts\python.exe -m pip check
git diff --check
```

输出分别保存在 `logs/pytest-targeted-final.txt`、`logs/pytest-full-final.txt`、`logs/compileall.txt`、`logs/pip-check.txt`、`logs/git-diff-check.txt`。独立进程测试由 pytest 调用 `tests/m1_hf_approval_resume_worker.py` 和 `tests/m1_hf_precheckpoint_worker.py`；故障点、PID、Run/Task、Worker owner/epoch、恢复结果在相关原始日志中。

本轮定向集 31 项，全量 140 项。测试需要 Windows 子进程、SQLite 和本地 MCP stdio Server。模型替身只捕获真实组装的 Prompt，不需要 Provider 凭证；本轮没有调用付费 Provider。结果不代表多 Worker、生产 IAM、远程数据库或真实业务系统验收。
