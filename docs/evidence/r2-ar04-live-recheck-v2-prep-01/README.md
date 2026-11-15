# R2-AR04 Live Recheck V2 Prep

本目录是零 Provider 请求的离线准备候选，所有 Runner 入口均限于 MockTransport 和零费用配置预检。

## 结果

- 完整 Assistant / Runtime Grant / Domain Mock 链：3/3 Case。
- Mock 账本：6 次摘要 + 3 次回答；全部 9 个 logical slot 有记录。
- 冻结 Q02-A 首轮 DeepSeek 摘要通过当前 `chat.py` 的完整 Domain 持久化路径。
- 两轮摘要均落库，最终 Prompt 有对应事实与来源；所有回答为合成 Mock，未进行语义评测。
- C01–C08 离线验收通过；C06 历史 RED 与 F01 既有测试记录未改写。
- 零费用预检：`READY_FOR_AUTHORIZATION`；Provider 请求 0、费用 USD 0。

## 可复跑命令

在仓库根目录执行：

```powershell
python docs/evidence/r2-ar04-live-recheck-v2-prep-01/run_v2.py mock --output docs/evidence/r2-ar04-live-recheck-v2-prep-01/mock-rerun
python docs/evidence/r2-ar04-live-recheck-v2-prep-01/run_v2.py preflight --mock-results docs/evidence/r2-ar04-live-recheck-v2-prep-01/MOCK_RESULTS.json --output docs/evidence/r2-ar04-live-recheck-v2-prep-01/PREFLIGHT-rerun.json
python -m pytest -q --basetemp docs/evidence/r2-ar04-live-recheck-v2-prep-01/.pytest-rerun docs/evidence/r2-ar04-live-recheck-v2-prep-01/test_runner_v2.py
```

每次 Mock 运行输出目录必须是新路径。预检不发送请求；它读取主仓库 `.env` 并只保存配置存在状态及非敏感运行结果。Runner 不接受 `live` 子命令。

## 文件

- [`PLAN.md`](PLAN.md)：范围、开工核验及正式六问。
- [`V2_RUNNER_DESIGN.md`](V2_RUNNER_DESIGN.md)：适配方式、版本 pins 和证据限制。
- [`FROZEN_INPUTS.json`](FROZEN_INPUTS.json)：源代码、问题/Gold、历史摘要、Trace、运行参数及依赖摘要。
- [`MOCK_RESULTS.json`](MOCK_RESULTS.json)、[`MOCK_TRACE.jsonl.gz`](MOCK_TRACE.jsonl.gz)、[`MOCK_COST_LEDGER.json`](MOCK_COST_LEDGER.json)：最终 3 Case 证据。
- [`MOCK_REPLY_PROVENANCE.jsonl.gz`](MOCK_REPLY_PROVENANCE.jsonl.gz)：冻结真实响应正文与合成 Mock 回复来源标识。
- [`PREFLIGHT.json`](PREFLIGHT.json)：只到 `READY_FOR_AUTHORIZATION` 的离线配置预检。
- [`FAILURE_MATRIX.json`](FAILURE_MATRIX.json)：C01–C08 的验收矩阵。
- [`TEST_RUN.txt`](TEST_RUN.txt)：实际命令、日志摘要、退出码与首次临时目录故障。
