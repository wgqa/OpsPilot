# 执行与审计方式

- 执行源码：`codex/ar04c-real-journey-01@c4922957a82a557dee8dfb254af4f740c3b34c4b`。
- 私有 Runner 使用 `--prepare` 完成全新数据准备与一次显式 MockTransport 报文检查；随后只调用一次 `--execute`。两个退出码均为 0。
- `--execute` 在同一进程读取私有 API Key、建立精确授权记录、调用已验收的 `_ar04c_create_one_shot_claim()`，随后按 OFF→ON 调用正式 API 和 Worker。一次性 token 仅在该进程内存在。
- 授权 JSON 放在私有运行目录，进程将既有 `AR04C_AUTH_RECORD` 文件位置指向该私有文件；使用原有固定 claim 路径，没有改生产源码或绕过校验。
- 每组通过已有 `assistant/order` 接口提交 J2 完整原句，可信建立绑定；在 Worker 启动前配置已批准的实验 policy。J4 使用同 Session/Task 的 `assistant/messages` 接口，一次 Operation 仅提交一次。
- 模型仍由正式 `create_assistant_model()` 构造。私有 HTTPX 传输记录器包裹原生零重试 Transport，在已验收的 claim 守卫内部观察发送边界，核对已消费 claim、数据库绑定、持久预留、12K Context、实际报文与工具 Schema，然后进行真实网络发送。它不生成模型答案、不选择工具。
- 实际采用 FastAPI TestClient 驱动正式 API 与 lifespan Worker。这是 API/Worker 真实模型执行证据，不是浏览器或 UI 验收。
- 私有观察器只等待 `_dispatch_run()` 返回和 Worker 空队列后关闭 TestClient；没有修改 Worker 行为。模型 HTTPX 客户端由正式 Worker 关闭。
- `PROVIDER_HTTP.jsonl` 中的 `send_boundary` 是 HTTPX 传输边界；`response` 保存脱敏原始响应和 Usage。每个响应的 Tool Calls 数组是模型提议顺序。
- `TRACE.jsonl` 的 `assistant_call_persisted` 是结束后的提取事件；工具真实受理/完成时间以其 `created_at/completed_at` 和 `SOURCE_OBSERVATIONS.json` 中的 `reserved_at/completed_at` 为准。
- 审计进程只读 SQLite，未创建 Provider 客户端或新 claim。八条业务 Observation 通过真实 `d2_attempts` 的 `attempt_run_id` 关联，避免把 Observation 表的任务归属冒称 Run 归属。
- 公开 `prepare.txt`/`execute.txt` 只规范化了 Windows 控制台日志的编码和换行；私有原始日志字节未修改，其哈希保留在索引中。
- 两组 Protected 表快照、完整费用行和未决预留均在 `BUDGET_LEDGER.json`。原始私有文件与执行脚本哈希在 `EVIDENCE_INDEX.json`，不把一次性执行脚本公开成可重跑授权入口。
