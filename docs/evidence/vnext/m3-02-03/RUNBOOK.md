# 本轮运行与证据复核

## 自动化

在仓库根目录，使用既有`.venv`和锁定依赖：

```powershell
.\.venv\Scripts\python.exe -X utf8 -m pytest -q --basetemp=.runtime/pytest-m302-final-continuation-03
# frontend/ 内
npm run build
npm run lint
```

完整结果225/225；每次原始日志和exit-code位于`runs/continuation-01/`。不要覆盖旧basetemp或历史日志，重跑时使用新目录。

## 真实Web副本与环境

复用`opspilot.smokes.m1_03`的`_server_environment`、`_start_api`、`_start_vite`、`_kill`。只对属于本次的子服务执行kill/restart；未停止或重配用户原8000/5173。模型配置从本地`.env`读取，不提交密钥。

- Semantic补证：SQLite backup源`.runtime/m303-debug-7db68a1b.sqlite3`及相邻Checkpoint → `.runtime/m303-continuation-01/`。API8001、Vite5174。副本由独立演示口令登录support-a/approver-a，原源Task A/B及已确认版本保留。用户在真实Web确认撤销。真实新Run/Provider/MCP由Web工作台触发。
- 长会话：SQLite backup源`.runtime/m302-context-web.sqlite3`及相邻Checkpoint → `.runtime/m302-continuation-01/`。API8002、Vite5175；`OPSPILOT_CONTEXT_INPUT_BUDGET_TOKENS=1400`、HYBRID。源数据库含真实26轮，不是手工重新插入消息。
- OS崩溃：运行时只读监控确认MCP/Checkpoint或Summary已落库，再调用既有`_kill`强制终止对应子服务进程树。文件命令通知控制器用相同Domain/Checkpoint启动新进程。日志父PID与`api.log`实际Uvicorn子PID需区别查看。
- 浏览器操作使用Codex CUA；截图是实际运行页面，未生成模拟图。任务中的真实APPROVER确认由用户操作；测试身份只代表本地Demo角色。

本地运行时控制器位于相应`.runtime/*/service_control.py`，不提交运行库或密钥。这些副本已停止。新机器应按项目现有启动说明准备Demo数据、可信身份与本地模型配置，通过同一工作台重走输入旅程；不能将本地旧DB不存在误称为功能失败。

## 只读导出

```powershell
.\.venv\Scripts\python.exe -X utf8 docs/evidence/vnext/m3-02-03/export_continuation_trace.py .runtime/m303-continuation-01/domain.sqlite3 .runtime/m303-continuation-01/checkpoints.sqlite3 docs/evidence/vnext/m3-02-03/runs/continuation-01/TRACE.json
.\.venv\Scripts\python.exe -X utf8 docs/evidence/vnext/m3-02-03/export_continuation_trace.py .runtime/m302-continuation-01/domain.sqlite3 .runtime/m302-continuation-01/checkpoints.sqlite3 docs/evidence/vnext/m3-02-03/runs/long-recovery-01/TRACE.json
```

导出白名单不含credentials或web_auth_sessions。Trace包含备份继承的历史行，必须按run_id、created_at区分本次调用和历史记录。Git/source hash字段记录导出时工作区，不能据此推断更早进程加载的代码。

## 源码版本与实验解释

Semantic补证进程在c57cd28的Python实现启动，Inspector/Investigator没有发生业务语义变更。长会话第27轮在摘要优先级修复后、原文锚点修复前执行；第28轮在最终e2c48e7源码重启后执行，文件字节摘要可与最终源码核对。原始策略对照为以前独立Release，不因本次成功而改写。

当前证据待主Agent审查，不等于M3整体PASS。尤其不能把Semantic项目约定当成Episodic业务案例来源，也不能把安全预算停止当成已完成模型回答。
