# M4-03 Trace 索引

所有 Trace 均为本地演示环境记录，可能包含本地 Task、请求和回执标识；Provider 凭证未写入证据目录。

| 实验 | Trace / 证据 | 关联标识与结果 |
|---|---|---|
| 冻结 R/H/A | `runs/rha-20261023-frozen-01/RESULTS.json` 与 `S3-01`…`S3-08` 的 `*-{R,H,A}/TRACE.json` | Gold `m4-03-frozen-v1`；DeepSeek `deepseek-flash`；8×3 单元，prompt provenance v1；见每单元 Task/Run/HTTP request、MCP observations、Evidence、Gate、Token。后续 prompt v2 Knowledge 补验单独列出，未重跑冻结矩阵 |
| 浏览器业务闭环 | `runs/web-20261023T101521Z/TRACE.json`、`JOURNEY.json`、`JOURNEY-STAGE.json`、`HANDOFF-BEFORE-RESTART.json`、`NO_AGENT_BUSINESS_MUTATION.json`、`launcher.log` | Task `task-50ba3bd0-d26f-4a52-8318-e2f137bee8f6`；纠错 Run `run-2de277c8-226d-4929-85b7-baccf04452cc`；follow-up Run `run-4180ea04-8349-4c35-b18a-e05bde236e39`；Receipt `s3-handoff-7809c635-d2d9-4884-a169-18fb2e972b0f`；重复确认回放同 Receipt；API PID 29524→33832
| Web 截图 | `runs/web-20261023T101521Z/screenshots/` | 6 张 Edge 截图：确认订单绑定、首轮实时证据、纠错后新调查、交接回执、服务重启后恢复及结果追问
| Memory 跨任务 | `runs/memory-20261023T092400Z/` 下 `TASK-A-SOURCE-AND-APPROVAL.json`、`TASK-B-MEMORY-ON.json`、`TASK-C-CONFLICTING-CURRENT-FACTS.json`、`TASK-D-UNRELATED-CASE.json`、`TASK-E-AFTER-REVOKE.json`、`MEMORY-REVOCATION.json` | 来源 Task `task-03e74333-6e13-4046-8ee8-f53d42dba640`；Memory `episodic-1030d506-5e94-4034-8e7d-5c413025ad0b`；目标 Task ID、模型调用、MCP 工具、ContextProvenance 和 Gate 均在逐任务文件 |
| 知识排序 | `runs/retrieval-20261023T074302Z/RESULTS.json` | 冻结查询集 `m4-03-retrieval-v1`；每个词法/BM25-lite 排名、相关性标签和耗时 |
| Knowledge 实际选用补验 | `runs/knowledge-explicit-red-20261023T094100Z/`、`runs/knowledge-explicit-green-20261023T094300Z/`、`runs/knowledge-explicit-green-v2-20261023T095000Z/` | RED 0 次检索；一条候选 GREEN 检索 v2 的两份合同；Prompt 版本 v2 新鲜复验又 0 次检索。Gate 始终 `RECEIVER_PROCESSING_UNCONFIRMED`、零业务写入；按冻结停止规则报告 PARTIAL |
| Summary 来源失效 | `runs/summary-20261023T085730Z/` 的 `RESULTS.json`、`TURN-1-SUMMARY-USED.json`、`SOURCE-VERSION-DRIFT.json`、`worker-turn-1.log`、`worker-turn-2-attempt-1.log` | 来源摘要 v24 被真实上下文使用；隔离源 digest 漂移后失效，摘要和依赖回答从后续上下文排除；3/4 Provider 预算 |
| 原有 S1 与 MCP | `runs/s1-smoke-final-20261023.log`、`runs/mcp-stdio-final-20261023.log` | S1 config v7/旧 credential 401→CAS v8/新 credential 200；MCP stdio tools/list/call 及跨租户拒绝 |
| 前端与全量回归 | `runs/frontend-build-final-20261023.log`、`runs/pytest-full-final-postreview-20261023.log`、`runs/pytest-s3-final-20261023.log` | 构建通过；最终源码 275/275 pytest 与 12/12 S3 定向测试通过

浏览器 E2E 的外部准备（接收端从首轮 PROCESSING 场景变为可观察失败事实）有独立记录 `EXTERNAL_PREPARATION-AFTER-FIRST-RUN.json`。它由验收脚本在 Agent 再调查前完成，不计作 Agent 写入。Agent 在浏览器业务旅程中订单/安全配置写入计数为零；唯一人工交接由 owner 明确提交，并在同一 Domain 事务中落队列、Receipt、命令和 Outbox。
