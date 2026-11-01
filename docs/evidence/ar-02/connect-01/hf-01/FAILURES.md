# HF-01 原始 RED 与修复记录

## RED-01（实现修改前）

运行命令：

```powershell
D:\学习\agent新项目\.venv\Scripts\python.exe -m pytest -q tests/test_ar02_conn01_hf01.py --basetemp=D:\学习\agent新项目\.worktrees\ar02-live-01\.runtime\ar02-conn01-hf01\red-01 -p no:cacheprovider
```

原始日志：`runs/pytest-red-01.log`；退出码：`runs/pytest-red-01.exit`。

结果：2 failed。

- `test_offline_mock_is_explicitly_injected_into_openai_client`：RED 观察到旧 `local_mock_success()` 构造 SDK 时没有传 `http_client`（测试拦截在真正创建 SDK Client 前），即依赖默认 client 后再改私有 `_transport`。测试没有发出任何 HTTP。
- `test_consumed_send_once_authorization_is_hard_stopped_without_marker_or_ledger`：RED 观察到在临时新目录且没有 STOP 文件/账本时，旧 `send_once()` 继续读取配置。测试把配置读取替换为立即失败的 sentinel，因此没有创建 Client、预留或发出请求。

本 RED 不是原事故的二次复现；不调用真实 Provider、不使用 `.env` 凭据、不改写原事故 401 或原 P1 UNKNOWN 证据。后续所有失败和 GREEN 日志另行追加，禁止覆盖本记录。
