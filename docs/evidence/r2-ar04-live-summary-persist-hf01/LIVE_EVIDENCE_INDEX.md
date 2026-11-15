# 冻结真实运行证据索引

此前候选根目录的 `docs/evidence/r2-ar04-live-retention-recheck-01/RESULTS.json` 是**授权前/发出请求前快照**，不能当成实际停止后的结果。实际唯一真实请求及停止记录位于 `live_run_01/`，并由同目录父层的 `LIVE_AUDIT.json` 补充解释。本轮没有改写这些文件。

| 文件 | 作用 | SHA-256（本轮读取） |
|---|---|---|
| `r2-ar04-live-retention-recheck-01/RESULTS.json` | 授权前快照 | `08216b1326711a3fed644c36cf5a625d196bc0ba88ddc5ea4cd93b9184dfe6fc` |
| `r2-ar04-live-retention-recheck-01/live_run_01/LIVE_RESULTS.json` | 实际停止结果；1 次摘要请求，0 次回答 | `e19251494cf0bbb09b63fdad4c2f5cd794af777a914ad17a88e273b30e596c54` |
| `r2-ar04-live-retention-recheck-01/live_run_01/LIVE_REQUESTS.jsonl.gz` | 脱敏真实请求/响应 Trace，唯一摘要 Response ID `c3435ff4-fc27-4ffb-b053-bbfcabc600e0` | `3c6552bfe411a4bd362e355c7725f5185717fb621308cb0493dcd36aaa5d50f7` |
| `r2-ar04-live-retention-recheck-01/live_run_01/COST_LEDGER.json` | 实际发送计数、Usage、费用及停止原因 | `22e2f6a43f4daac82d9f1669c705b2532f8c400304048e784161982a46e16cf2` |
| `r2-ar04-live-retention-recheck-01/LIVE_AUDIT.json` | 真实摘要事实观察、失败类名、原始映射不可追溯声明 | `cc90eb247bd894f76a8048f1fef4a21f1e9a33099c538df95722c21e75e778e3` |
| `r2-ar04-long-context-journey-01/QUESTIONS.json` | 冻结问题与 Gold 指针 | `ea3d6554eafa433d1617dc5a5ba9f140471f3cb95f8ae10bcd25b807a4e7afe2` |
| `r2-ar04-long-context-journey-01/HISTORY_SNAPSHOT.json` | 29 条合成历史及原始消息体摘要核对 | `356512f611b046a04e33506a0fb1a88c6a08af93517b2134125dd6771b282c16` |
| `r2-ar04-compaction-audit-01/BENCHMARK_CASES.json` | 合成事实真值 | `95f94ef8aca5f04cd21c1a4708f872fcc956e77a9ea798e1af8933369f3c2fd2` |
| `r2-ar04-compaction-audit-01/case_traces/WP3_INFORMATION_RETENTION.json` | 原始 WP3 合成 Trace | `a588740709e104bb6204014297e81cc21aaa4b2516b309b944e3bf49dbf60034` |
| `r2-ar04-compaction-c06-hf01/RESULTS.json` | C06 冻结结果 | `c283bd91404f84b5908f528e8625bbe11e1f7c41dba13f71970ebacae88cc1e7` |
| `r2-ar04-compaction-c06-hf01/RED_REPRO_TRACE.json` | C06 RED 原始复现 Trace | `a820169936e3b4df2a2ca3120a606cdcd2df09d7dff92d0c590da3ea9b8ae13f` |
| `r2-ar04-compaction-c06-hf01/RED_REPRO.txt` | C06 RED 日志 | `c50a84527f5f331b22cebbd24be9d71061ace1bf4f8f0503972a01999ea3e3fc` |
| `r2-ar04-compaction-c06-hf01/TEST_RUN.txt` | C06 历史测试日志 | `7a828ca94734223d8ab29c3beeabb180c409f5730379c92011e06e1052d9b27d` |
| `r2-ar04-base-diff-edge-gate-hf02/F01_RUN.txt` | F01 既有失败记录 | `51226070f355aab33928c07f75fd6b53b880a9de5647b4c9377a3e995fb0f577` |

这些文件均有 Git 跟踪且本轮 `git status` 无修改。完整机器可读校验摘要在同目录 `RESULTS.json`。
