# M4-TTL-FIX-01 运行报告

**状态：** ACCEPTANCE_CANDIDATE
**冻结基线：** bd58c66003c4e7fea660967c7a6a30aebcd63cd7
**候选分支：** codex/m4-ttl-fix-01
**源码提交：** 00be81c53f090fd8934aa645ac2b16c59c9a7c78
**证据包提交：** fb09352b8d62f1179f52e367ba27d750664b3e87
**验收人：** 主 Agent

## 结果

Run B 在 301 秒后通过本地 HTTP 服务和 in-process MCP 再次成功读取事实时，原实现仍按不可变 Evidence 的旧 fetched_at 判过期。现在 Gate 使用本次 Run 自己成功完成的 Observation 判新鲜度；同一事实的 Evidence 行仍按 digest 复用且保持不变。Run A 与 Run B 的观察由 Attempt 关联到各自可信业务 Run，不允许跨 Run 借用。

每条候选 Observation 都核对 Task、Run、Attempt、调用和工具 ID、工具名、参数摘要、状态、结果摘要及 Evidence 内容关联。Observation 持久时间必须位于 Attempt 的预留与完成时间之间，并与工具结果报告时间相差不超过 30 秒；未来时间及超过 300 秒的观察均拒绝。业务 Gate 仍逐次核验当前 TaskBinding、租户、Principal、Scope/Grant、HTTP Authz 请求和事件、事实摘要及资源版本。

Diagnosis 在创建时冻结 Evidence 与 Observation 引用。之后复核仅使用诊断自己的 Run 和观察 pin；Run B 不会更新 Run A 的观察，也不能复活已过期的 WAIT 诊断。S3 调查把“新内容进展”和“本 Run 有新的成功观察”区分开；同 Run 同工具同参数的当前观察会抑制重复调用，避免把每次重试都算作进展。Chat/Inspector 不再以无 Run 的实时 Gate 代替冻结诊断。

## 源码变化

- opspilot/domain/d2.py：在 Attempt 与 Observation 写入时持久记录 UTC 时间；Evidence 与新 Observation 在一个 SQLite 写事务内建立或复用，复用时不更新旧 Evidence。
- opspilot/domain/s3.py：按可信业务 Run 选择 Observation，校验关联、时间、摘要、授权和当前业务事实；Diagnosis 冻结 Observation pin，历史结果只复核其原始来源。
- opspilot/s3_investigation.py：生产 S3 路径显式传 Run；刷新观察可继续合法调查但不增加事实进展，精确重复调用停止。
- opspilot/domain/chat.py：S3 当前事实只来源于当前有效的冻结 Diagnosis，不提供无 Run 的 Evidence fallback。
- tests/s3_observation_support.py、tests/test_m4_ttl_fix_01_integrity.py 及相邻 S3/HF 测试：建立可信 Attempt/Run 观察夹具，覆盖伪造、失败、时间异常、重复刷新及旧诊断。

未修改 S1/S2 Gate 或 Gold。D2 的通用 Observation 持久化时间改用同一 UTC 来源；S1/S2 安全回归 104 项通过。

## 真实运行证据

完整的实际 ID、UTC 时间、版本、HTTP 请求、Evidence、Observation、Attempt、Run、Gate 和不可变性检查见 TRACE.jsonl。核心旅程使用本地真实 HTTP 测试服务和实际 in-process MCP Server，不调用付费模型。

任务 task-8f2cfe81-b2ca-44d4-b9e8-35d738d79760：

| Fact | Run A Evidence / Observation / Attempt | Run B Evidence / Observation / Attempt | 结果 |
|---|---|---|---|
| s3_order | evidence-6635da38-428d-4026-b47c-f309285e2a6b / observation-29b43400-621a-422d-a4ce-545003d0fab1 / attempt-fdd9f058-e6bd-4ecc-9546-efaac3d4d90a | evidence-ea1bd789-f719-4411-9cfd-ab5aa58e3800 / observation-7e0f08ef-1da3-4ff4-9b4c-b3ec868ffc6b / attempt-51b2666a-2948-452c-b625-3a9327c7f10a | HTTP Probe 含新 request_id，因此形成新事实摘要 |
| s3_delivery | evidence-49584b25-27b1-4634-b4f3-048a0c6a29e7 / observation-68ec190b-5a94-4a36-9c6a-e8fb7d9dffad / attempt-08197896-89bc-4037-9f2d-552ff09dc91d | 同一 Evidence / observation-3256618d-1966-424d-98cc-6a3570389983 / attempt-575bb51a-5b47-4e44-a44d-340a43fbf06e | Evidence 不变，新 Run 观察有效 |
| s3_receiver | evidence-053f2eb8-36be-4fbb-aa17-efe1230bea64 / observation-a5c6eb81-0e75-48ab-ac16-aefcfadbe092 / attempt-8cb96a4a-81f7-4387-b264-39901ddefb8a | 同一 Evidence / observation-c223c2a4-564c-457f-a9af-149b3bfddfc7 / attempt-730c6829-04a7-4d61-ade6-1307dc640a18 | Evidence 不变，新 Run 观察有效 |

Run A 与 Run B 的 MCP 观察时间相差 301 秒。旧 Evidence 行、Run A Diagnosis 正文与 digest 均保持不变。旧 Run A 当前性复核排除 3 条过期 Evidence，且把 Run A 的观察 pin 错传给 Run B 会因 Run 关联不符被拒绝。Run A 与 Run B 的新 Diagnosis 均为 DIAGNOSED / WAIT_FOR_RECEIVER_PROCESSING；Run B 成功刷新相同 delivery/receiver Evidence 后不再得到 S3_EVIDENCE_EXPIRED。299 秒与 300 秒仍有效，301 秒的旧观察失效。

HF-02 的新鲜 SLA 集成回归通过：旧 WAIT 在 deadline 失效，后续独立 Run 通过真实 HTTP/MCP 路径取证并得到 CONTACT_RECEIVER_OPERATOR；由 owner 确认后仅提交一次交接。精确边界 now < deadline、now = deadline、now > deadline 均由确定性时钟测试。

## 验证

Windows 工作区；Python 3.14.0、pytest 9.1.1、MCP SDK 2.3.0、LangGraph 1.2.16、langchain-openai 1.7.2、FastAPI 0.137.1。所有最终 pytest 原始日志保存在 runs/green/。完整命令、退出码和依赖版本见 RESULTS.json。

runs/ 下的日志、Trace 与退出码文件使用局部 Git 属性保留原始字节，包含原始换行与失败输出。

- 新 TTL 与 Observation 完整性：3 passed。
- TTL + HF-01 + HF-02 + S3 回归：77 passed。
- S1/S2 安全回归：104 passed。
- 全量 pytest：319 passed。
- 编译检查和 git diff --check 通过。

全量测试为避免本机缺失 Provider 配置触发测试 Worker 早退，使用了仅供测试的 dummy model key/name 与 127.0.0.1:9 base URL。此配置不会访问真实模型；核心 S3 集成也不依赖模型。

## 已知限制

候选验证覆盖本地 SQLite、真实本地 HTTP 与 in-process MCP。未运行外部 Provider、远程 MCP Server 或生产部署环境。S1/S2 仅作为共享 Observation 存储的窄安全回归；没有改变其 Gate。最终代码与证据仍待主 Agent 独立验收，本报告不代表最终 PASS。
