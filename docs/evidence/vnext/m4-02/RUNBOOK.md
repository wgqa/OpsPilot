# M4-02 独立复跑（PowerShell）

在仓库根目录执行。使用项目已有 Python/前端锁定依赖；本轮没有新增依赖。模型配置沿用本地 `.env` 的 `OPSPILOT_MODEL_API_KEY`、`OPSPILOT_MODEL_NAME` 和可选 `OPSPILOT_MODEL_BASE_URL`。不要将密钥写入日志或提交。

```powershell
.venv/Scripts/python.exe -m pip check
New-Item -ItemType Directory -Force .runtime/m4-02 | Out-Null
.venv/Scripts/python.exe -X utf8 -m pytest tests/test_m4_02_s3.py -q --basetemp=.runtime/m4-02/your-unique-focused-run
.venv/Scripts/python.exe -X utf8 -m pytest -q --basetemp=.runtime/m4-02/your-unique-full-run
```

每次选择新的 basetemp 名称。pytest 会清理它自己的旧 basetemp，不能指向用户目录、开发资料或现有业务数据库。历史默认临时目录权限失败见 RED 日志。

```powershell
.venv/Scripts/python.exe -X utf8 -m opspilot.smokes.m4_02
.venv/Scripts/python.exe -X utf8 -m opspilot.smokes.m4_02_assets
.venv/Scripts/python.exe -X utf8 -m opspilot.smokes.m4_02_web
```

上述程序在仓库 `.runtime/m4-02/` 创建独立测试库，原始结果写入本证据目录下时间戳子目录，不覆盖已有运行。Web 程序使用已安装的 Microsoft Edge 真实浏览器、真实 API/Worker/Vite 和随机演示口令，验证创建任务、模型/MCP 调查、追问、刷新和 API 进程重启；不会操作用户当前 5173 主工作台。前端依赖须先按既有 `frontend/package-lock.json` 安装。

```powershell
Push-Location frontend
npm run build
Pop-Location
.venv/Scripts/python.exe -X utf8 -m opspilot.cli d3-smoke --db .runtime/m4-02/your-unique-s1.sqlite3 --checkpoint-db .runtime/m4-02/your-unique-s1-checkpoints.sqlite3 --evidence-dir docs/evidence/vnext/m4-02/runs/your-unique-s1
```

S1 smoke 是有独立审批者与真实业务写入的历史回归，只运行在新命名的隔离测试库。S3 的准备函数 `opspilot.domain.s3.prepare_s3_fixture` 仅属于显式本地测试准备，会注册独立 S3 principal/policy/grant 并向本地接收端实际 POST；从未注册为 MCP 工具或 Web 业务修改接口。不要把准备动作说成 Agent 修复。

界面选择“订单 200 但下游未收到回调（只读）”时，服务端映射固定注册资源；缺少准备数据应拒绝创建，不会依据聊天文字伪造订单或放开资源 ID。S3 诊断后可以继续问“200/202分别说明什么，为什么不算恢复？”。S3 从不自动重发回调。

已有冻结运行的离线汇总可用 `python docs/evidence/vnext/m4-02/tools/summarize.py` 重建；该程序只读取原始证据，不运行模型、不改写 Gold。新运行的结果应保留独立目录，再由审阅者明确选择评测 Release，不能覆盖冻结记录。
