# M4-03 复跑指南

在仓库根目录 `D:\学习\agent新项目` 执行。Python 测试使用仓库 `.venv`。真实 Provider 实验从本机 `.env` 读取 `OPSPILOT_MODEL_API_KEY` 和 `OPSPILOT_MODEL_NAME`；不要把凭证写入命令历史或证据文件。

```powershell
# 全量测试
.venv/Scripts/python.exe -m pytest -q --basetemp=.runtime/m4-03/pytest-full-rerun

# 冻结真实 Provider/MCP R-H-A。每次生成新的 evidence release；不要编辑 GOLD.json。
.venv/Scripts/python.exe -m opspilot.smokes.m4_03_rha

# 冻结知识检索词法/BM25-lite 对照（不调用模型）
.venv/Scripts/python.exe -m opspilot.smokes.m4_03_retrieval

# 真实 DeepSeek 跨 Task Memory、冲突、无关与撤销实验
.venv/Scripts/python.exe -m opspilot.smokes.m4_03_memory

# 有界真实 Provider/MCP 知识查询选择检查；每次必须使用新的 release 名称
.venv/Scripts/python.exe -m opspilot.smokes.m4_03_knowledge_live --release knowledge-live-rerun-unique

# M3 Summary 隔离来源漂移实验；要求现有 M3 continuation fixture
.venv/Scripts/python.exe -m opspilot.smokes.m4_03_summary

# 真实 Edge/API/Provider/MCP/HTTP Web 全旅程
.venv/Scripts/python.exe -m opspilot.smokes.m4_03_web

# 前端 production build
Push-Location frontend
npm run build
Pop-Location
```

`m4_03_rha`、`m4_03_memory`、`m4_03_web` 会创建真实外部调用和数据库副作用；运行于隔离本地 Demo Domain，并保留每次结果到 `docs/evidence/vnext/m4-03/runs/`。RHA 的冻结 Gold 只由测试准备器创建事实，不进入模型 prompt。Web/API smoke 使用临时端口、独立 Domain 与 checkpoint 数据库；必须检查结果 `status` 和 Trace，不能把启动成功当作验收。

最终记录使用的直接版本为 Python 3.14.0，Node 与 npm 版本见 `RESULTS.json`。应用依赖按 `pyproject.toml` 固定：langchain 1.4.1、langchain-openai 1.7.2、langgraph 1.2.16、langgraph-checkpoint-sqlite 3.1.2、mcp 2.3.0、pydantic 2.14.1、fastapi 0.137.1、uvicorn 0.49.0、tiktoken 0.14.0；dev pytest 9.1.1 与 httpx 0.28.1。浏览器验收使用本机 Microsoft Edge 和 Playwright 1.64.1；前端 Vue 3.5.44、Vite 8.3.4、TypeScript 5.9.3。

此 Demo 是单机 SQLite、预注册本地租户和受控接收队列；不能据此宣称生产 IAM、分布式队列或真实外部回调修复能力。

最终验收记录于 `RESULTS.json`；最终浏览器运行使用 release `web-20261023T101521Z`，其原始 API、Vite、浏览器及 UTF-8 launcher 日志和六张截图保存在 `runs/web-20261023T101521Z/`。最新全量测试日志为 `runs/pytest-full-final-postreview-20261023.log`，S3 定向日志为 `runs/pytest-s3-final-20261023.log`。Knowledge 选择实验已按冻结预算停止，复跑不能替换或删除旧 release。
