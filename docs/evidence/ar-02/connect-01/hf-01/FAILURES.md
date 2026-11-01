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
## 实施期失败记录（均为本地 Mock / SQLite）

### GREEN-ITERATION-00（未形成独立原始日志）

首次代码试跑在工具会话输出了 4 failed / 6 passed。失败点为：SDK 构造函数被测试包装后，版本签名检查误检查包装器；双进程测试的内联子进程脚本参数/启动方式不正确。该试跑没有写入仓库原始日志文件，故仅记录为实施过程摘要，不将其冒充可复核原始日志。随后以独立日志重跑。

### GREEN-ITERATION-01

原始日志：runs/pytest-green-01.log；退出码：runs/pytest-green-01.exit。

结果：2 failed / 8 passed，均为测试实现问题：HTTPX2 将 Authorization header 名标准化为小写，测试却只查找大写键；跨进程断言使用了未初始化的局部变量。未触发真实网络。

### GREEN-ITERATION-02

原始日志：runs/pytest-green-02.log；退出码：runs/pytest-green-02.exit。

结果：10 passed。修正 Header 查找与双进程测试后，定向用例全绿。

### 最终扩展定向验证

原始日志：runs/pytest-green-final.log；退出码：runs/pytest-green-final.exit。

结果：15 passed。覆盖显式 SDK 注入、两个 URL 路径、代理/SDK/端点失配、假 Key 脱敏、本地连接故障、发送硬停止、线程/进程竞争及账本复制/UNKNOWN。

最后一次冻结代码复跑：runs/pytest-green-final-02.log；退出码：runs/pytest-green-final-02.exit；结果仍为 15 passed。该次增加了拒绝 MockTransport 子类的断言，并在此后进行源码检查。

提交前最终复跑：runs/pytest-green-acceptance.log；退出码：runs/pytest-green-acceptance.exit；15 passed。源码语法编译退出码见 runs/pycompile.exit。

### AR-02 既有本地协议回归

原始日志：runs/pytest-ar02-regression.log；退出码：runs/pytest-ar02-regression.exit。

命令执行 tests/test_ar02_live_hf02.py、tests/test_ar02_smoke_provider_factory.py、tests/test_ar02_runtime.py，结果 28 passed。测试代码使用本地 Mock/Fixture；本轮未调用真实 Provider。
