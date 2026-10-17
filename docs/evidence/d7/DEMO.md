# 最短演示（在源码根目录、已安装锁定依赖并配置本地 .env 后）

演示 S1：真实模型通过只读 MCP 调查，Gate READY 后暂停；测试程序以独立可信角色 approver-a 自动批准，随后事务 REPAIR、同身份业务 200、冻结报告和单条 DELIVER。**自动批准不是人手决定**；真实人工两进程操作见根 README。

```powershell
$demoRun = Get-Date -Format 'yyyyMMdd-HHmmss'
.\.venv\Scripts\python.exe -m opspilot.cli d3-smoke --db ".runtime/d7-demo-$demoRun.sqlite3" --checkpoint-db ".runtime/d7-demo-$demoRun-checkpoints.sqlite3" --evidence-dir ".runtime/d7-demo-$demoRun-evidence"
Get-Content ".runtime/d7-demo-$demoRun-evidence/TRACE.json"
.\.venv\Scripts\python.exe -m pytest -vv -s tests/test_d4_recovery.py -k 'langgraph_replays_committed' --basetemp=".runtime/d7-recovery-$demoRun"
```

实际 D7 第二次演示输出：`d3_smoke_result` 的 13 个 `checks` 为 true；配置 7→8；VerificationReceipt 为 HTTP 200、`demo-order/CONFIRMED`；REPAIR Ledger `ledger-1452d727-ce5c-45cc-a1c6-1d32e651c1cd`，DELIVER Ledger `ledger-a807829b-e634-4d94-b54c-e07355d10fbb`，`ticket_entry_count=1`。请查看自己运行产生的字段，不要将这些历史 ID 当作新输出。

新鲜证据：[E01 TRACE](attempt-02/e01/TRACE.json)、[崩溃子进程](attempt-02/d4-recovery/WORKERS.json)、[完整报告](REPORT.md)。首轮 Skill 换行校验失败仍保留；D6 E10 保持 PARTIAL。每次 smoke 会重置指定 Demo DB，以上使用新名称；实际模型结果可能不同，失败需保留。
