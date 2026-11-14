# R2-AR06-LIVE-EXEC-01 · Trace 索引

所有 Trace 都是现有导出器生成的单 Session 脱敏 JSON。下列 `runs/` 文件是按字节复制的审阅副本；SHA256 与 `.runtime` 原件相同。未修改 E01 历史数据库、Checkpoint 或原始 Trace。

## E01-D（既有历史首次尝试，本轮未重跑）

- Runtime：`.runtime/user-demo-r2-e01-1114a`
- Session：`session-57d5d0a8-bb16-4be9-ab6a-c58f18049976`
- Run：`run-7ff06937-6268-4fa3-a51e-4ce63100436e` (`SUCCEEDED`)
- 冻结输入 SHA256：`bfc28bababb48805409563fd27a1911723781167a9aee76e994fa12dcfa6e3c4`
- Provider Response ID：`814c3218-c068-4aff-a0c4-2b55ac6a1ade`
- 1 请求；2,487 输入 / 491 输出 Token；USD 0.001336；MCP 0。
- Trace 原件：`.runtime/user-demo-r2-e01-1114a/evidence/session-57d5d0a8-bb16-4be9-ab6a-c58f18049976.json`
- 审阅副本：[LIVE_E01-D_HISTORICAL_TRACE.json](runs/LIVE_E01-D_HISTORICAL_TRACE.json)
- Trace SHA256：`abdd1c66c9a8e33ee30e237131e2575a8ddad0e4b1866d453f65b694d7493688`
- 原 Domain DB SHA256：`5d225e8bb0d5fdd0ab0cf27cf3cab28b05c04274b5923fc4c0e148212638cae5`
- 原 Checkpoint SHA256：`5507a716fdbf1c9d48a8e50700602bdac77f26c9ed9b935f55edd89f8f1c9b2b`
- 候选评分：[E01_CANDIDATE_SCORE.json](E01_CANDIDATE_SCORE.json)，`PASS_CANDIDATE`。

## E05-D（本轮真实首次尝试）

- Runtime：`.runtime/user-demo-r2-e05-live01`
- Session：`session-36f1742a-826c-4d25-9712-43fbe0037ff2`
- Run：`run-4b15215e-3f49-445d-be88-98999d85e63d` (`SUCCEEDED`)
- 冻结输入 SHA256：`645d998ad89484df6119d20df0c61c46be87ece0915f425c227fd8823bc3af7f`
- Provider Response ID：`527572e1-b29a-4c47-a809-8df1ee9347c7`
- 1 请求；2,537 输入 / 426 输出 Token；USD 0.001273；MCP 0。
- Trace 原件：`.runtime/user-demo-r2-e05-live01/evidence/E05-D.json`
- 审阅副本：[LIVE_E05-D_TRACE.json](runs/LIVE_E05-D_TRACE.json)
- Trace SHA256：`64bd52b76243ed0c51d6290f539e09a06a32ef0ac5b56dfa05f558ac973043cb`
- Runner 原结果：[LIVE_E05-D_RUN_RESULT.json](runs/LIVE_E05-D_RUN_RESULT.json)，SHA256 `ed79247bdc7598ee2191387de354024e4943b67cb411e1d8e8b3ddfec33b5e62`。
- Domain DB SHA256：`e1fc8f8ebfc7409b714a666098f4936c92ecda9a148003a81322256c3d6be70b`；Checkpoint SHA256：`a48cada6e30b2141eee421389338c835d1ea97c03c4b9e3ec7fb2dde94a3f687`。

## E07-D（本轮真实首次尝试）

- Runtime：`.runtime/user-demo-r2-e07-live01`
- 业务数据 Fixture：`r2-e07-queued`（仅 MCP 数据配置；模型为真实 DeepSeek）
- Session：`session-300f9d82-85f7-4bff-a3d6-6da8d99324b3`
- TaskBinding：`task-73c28480-0392-47c4-866d-8a5e505ae619`
- Run：`run-c6be60b9-e6b0-4310-8c8f-853c00934d4f` (`SUCCEEDED`)
- 冻结输入 SHA256：`58a3fa04a1ff5197fb8ff6f604bfd8c5e4975a7fac202f5850f58ee37e6a9354`
- Provider Response IDs：`377d6ab2-2aca-49d3-bd79-cd9e77008be5`; `c88b0aa9-67af-41a5-9f3d-ceab2b8035d1`。
- 2 请求；7,629 输入 / 675 输出 Token；USD 0.003099；3 次 MCP；3 条 Observation；3 条 Evidence。
- 目标 Event：`event-00000000-0000-4000-8000-000000000001`。
- Delivery Observation / Evidence：`observation-7cec1a2c-6651-4bf5-8d51-63f3ba969f73` / `evidence-44f90cd1-8f0c-4376-a0a6-29f0446565e1` (`ACKNOWLEDGED / HTTP 202`)。
- Receiver Observation / Evidence：`observation-7299a755-b33a-412e-8f42-750520853656` / `evidence-8ae9387e-31a9-45be-a4e6-c497c5027af4` (`QUEUED`)。
- Trace 原件：`.runtime/user-demo-r2-e07-live01/evidence/E07-D.json`
- 审阅副本：[LIVE_E07-D_TRACE.json](runs/LIVE_E07-D_TRACE.json)
- Trace SHA256：`aacf15bdb81a24461b612551a23800a12c86f54a275f95185a3d24cdb34ebb59`
- Runner 原结果：[LIVE_E07-D_RUN_RESULT.json](runs/LIVE_E07-D_RUN_RESULT.json)，SHA256 `d31a82dd7f39e961a8b0398d6b554b40f6b5d609d8b66362989489cd0494ebd0`。
- Domain DB SHA256：`31698951bf1987a26ba536c4dc8785bcdb9af08b718ea51638d7130f917ec8ce`；Checkpoint SHA256：`b93f063546e7edf8ae2ca47f06fda73b7f037eb5be7507c0debdcd193db9bf84`。
- 候选评分：`PARTIAL_CANDIDATE`。订单 Observation 没有 Event ID，最终回答的“三个来源 Event ID 一致”超出实际来源支持；Delivery/Receiver 的同 Event 证据本身有效。

## 汇总

- [`LIVE_RESULTS.json`](LIVE_RESULTS.json)：结构化案例结果、Usage、成本、来源、候选评分与样本限制。
- [`LIVE_EVAL_REPORT.md`](LIVE_EVAL_REPORT.md)：候选分析和错误/限制。
- [`INTERVIEW_BRIEF.md`](INTERVIEW_BRIEF.md)：面试表达补充。
- E05/E07 服务均已停止；Grant 保留至到期时间；Runtime、账本和 Checkpoint 均保留在本地 `.runtime/`。
