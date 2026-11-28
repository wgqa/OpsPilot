# R1-J2-02-REPEAT-01 复现性审查

## 结论

**`BLOCKED_BEFORE_PROVIDER_SEND`；重复性结论 `UNDETERMINED`。** 原私有归档保留了完整 Campaign 结束后的 Domain 与 Checkpoint 数据库，但没有 J2-02 开始前成对、可验证的数据库快照。不能在不删除后续数据库记录、不伪造历史输入、也不复用已消费 Claim 的条件下重建第四轮起点。因此本轮没有启动 DeepSeek、没有创建新 Grant/Claim，也没有尝试把旧 Campaign 恢复。

单次 J2-02 的 PARTIAL 结果不足以判断“无回执的后续工作承诺”是单次生成偏差还是可重复的表达问题。再次得到 PASS 也不能覆盖第一次 PARTIAL；可比较的第二个样本目前尚未产生。

## 核验基线

| 项目 | 实际值 |
|---|---|
| 原真实执行源码 | `7f8df218415fbbcf4df33001fc593bd772ab880e` |
| 上轮证据提交 / 本候选 Base | `9e9f7b05afcdd51e05c4c4af605bb225c53bd2bd` |
| 冻结 CASES Blob | `320bab6afc5668c675455d370e6a3ded51119b08` |
| North Star Blob | `43dabda468506717c6956e676dfad4304c4f38e6` |
| AGENTS Blob | `807b928686a4dd2cac7b15b3c354b9943c93c910` |
| Review Skill Blob | `d405c8d413d633824b279202cc1503dab4cf0b03` |
| 远端 `codex/r1-j2-live-recheck-02` | `9e9f7b05afcdd51e05c4c4af605bb225c53bd2bd` |
| 远端 `main` | `60eee87bfe3cca522011316cb4cd2c0064ad291b` |

冻结输入位于 `docs/evidence/vnext/r1-j2-live-recheck-01/CASES.json`；其 Blob 与任务卡给定值一致。原有 J2-02 结果见 `docs/evidence/vnext/r1-j2-live-recheck-02/LIVE_RESULTS.json` 与 `LIVE_REPORT.md`，未改写。

## 原始证据检查

私有归档中发现 `domain.sqlite3`、`checkpoint.sqlite3`、`domain_snapshot_private.json`、`FINAL_PRIVATE_SUMMARY.json`、`ONE_SHOT_CLAIM.json`、`turns_private.jsonl`、`provider_http_private.jsonl`、`assistant_calls_private.jsonl` 及 Campaign 授权/Fixture 元数据。文件名与修改时间均指向完整 Campaign 结束时保存的最终材料；未发现 `before-J2-02`、`pre-run`、备份或等价的前置 Domain/Checkpoint 快照。

只读 SQLite 核验显示最终 Domain 库包含 1 个 Session、8 条 Message、4 个 Assistant Run、4 个持久答案、20 条 Assistant Call、4 个 Task Run 与 2 条 S3 transport attempt。最终 Checkpoint 库有 22 个 checkpoint、53 条 write，跨 4 个 run thread。`domain_snapshot_private.json` 仅包含最终 Campaign 元数据与计数，不是数据库快照。最终 Campaign 为 `STOPPED / CAMPAIGN_FINISHED`，记录 9 次 Provider send；旧 Claim 状态为 `CAMPAIGN_FINISHED`。

上述私有文件 SHA-256 与归档 `PRIVATE_HASHES.json` 一致。原始文件留在私有目录，未复制到仓库。主要哈希如下：

| 私有材料 | SHA-256 |
|---|---|
| `domain.sqlite3` | `6f423bff6b539755ac77480d32182905c660fee904df733792b5b6010c253441` |
| `checkpoint.sqlite3` | `93120b7dd7f2760ffcb8379e19dfab14eb8657dd54e84b96bfbb6e98a0177a98` |
| `domain_snapshot_private.json` | `6364f20ab90f04d82dac82e711c255d92ca11c542fff556856238dfd46e0268a` |
| `ONE_SHOT_CLAIM.json` | `d272cb350c66145db3edc4eec623393effe0c6e7b0449b6ec69d2a19e3b7bcaf` |
| `turns_private.jsonl` | `0bd9cc43b11fe2aa434932e9bdce4edb45e5686ad28603aa8df944b18672c8cc` |
| `provider_http_private.jsonl` | `ef3a9d78001dc6a25048c92869fb76a0cffcbc03bafa0d9679bb2f73b4c2e9fa` |
| `assistant_calls_private.jsonl` | `d28a229a84536e49c32d0ca8a413a30cf3aa6b95cdb96439c97ef8ed126efb9a` |
| `FINAL_PRIVATE_SUMMARY.json` | `4d1f2f74dbde7425e330f5df3435a3ad63c78ad3715711cb19cf31b94b48f74d` |

### 为什么不能只重跑 J2-02

1. 使用最终 Domain DB 会把首次 J2-02 的用户消息和答案留在同一 Session 历史里，改变待测模型上下文。
2. 从最终库删除 J2-02 记录或回填成前三轮状态违反任务卡，也会破坏原始证据。
3. 手工创建新 Session 并粘贴前三轮消息、工具结果或模型回答，不能证明它们是本轮 API/Worker 实际产生的可信历史；这会构造测试前置状态。
4. 旧 Campaign 已结束且一次性 Claim 已消费。重启、复用 Claim 或改库复活均不允许。

故现存材料可以审计首次 J2-02，但不能忠实提供独立复测所需的精确起点。此限制是运行材料缺少事前快照，不是已证实的产品代码缺陷。

## 首次 J2-02 结果保留

原结果为 **PARTIAL**：模型正确区分 `event-current` 的当前 `PROCESSED` 与 `event-previous` 的历史 HTTP 202 / `QUEUED`，并明确 `event-previous` 当前 Receiver 状态未知；但客户草稿承诺“后续将由相关团队进一步核实并同步”，该承诺没有任何工单、交接或行动回执支持。第一次结果继续保持 PARTIAL，不因本次无法复测而更改。

## 本轮执行计数

- Provider HTTP：0；MCP：0；浏览器：0；业务写入：0。
- 新 Campaign / Runtime Grant / one-shot Claim：均未创建。
- 测试：未运行 pytest；本轮无源码改动，仅进行了 Git、归档清单、哈希及只读 SQLite 核验。
- 旧 Campaign、旧 Claim、原始 Trace、冻结 Gold：未修改。

## 最短替代路径：完整四轮重新执行

为了保持同 Session 连续性且不伪造前三轮，下一次实验应从新隔离环境完整执行冻结的 J1-01 → J1-02 → J2-01 → J2-02：

1. 建立新的 Campaign ID、Domain SQLite、Checkpoint、Runtime Grant、账本与一次性 Claim；不复制或复活任何旧 Campaign 状态。
2. 按原冻结 CASES/GOLD 和原模型参数，在同一个新 Session 中实际执行前三轮，再执行唯一待测 J2-02。
3. 记录每轮实际模型输入、工具提议与执行、Observation、回答、Completion、Usage 和账本；无回执的未来承诺按原 Gold 评分。
4. 费用授权需单独批准。可供裁决的预算建议为最多 12 次 Provider、应用费用池不高于 USD 8.00、每次预留 USD 0.645600、并发 1、30 秒超时、零自动/人工重试；这是建议值，不是本轮或未来的执行许可。若要仅比较最后一轮，可在新运行时先保存不可变的可信前三轮快照，再独立开启 J2-02 复测；不得从本次最终库倒删生成该快照。
5. 将新结果作为独立样本与原 PARTIAL 并列分析，不覆盖原始结论。一次复测只能提供第二个样本，不能据此声称具有统计意义的模型稳定性。

## 六维自检

1. **用户变化：** 本轮没有新的模型成果；确认了现存证据不能支持可信的 J2-02-only 重复实验。
2. **Agent 决策：** 未再次调用模型，因此自主补查与措辞是否重复仍未知。
3. **观察驱动：** 首次运行的两个 Event 状态区分证据保留；缺少第二次回答，不能比较表达是否重现。
4. **边界：** 没有放宽授权，没有改 Gold 或历史账本；未获得独立付费执行许可。
5. **职责复用：** 没有改代码或增加平台，只核验已有私有 Domain/Checkpoint 和公开结果。
6. **证据与停止：** 已验证归档哈希与最终计数；因缺少配对的事前快照且未授权收费，停止在真实请求之前。

**实施状态：`ACCEPTANCE_CANDIDATE`。** 这不是 PASS，也不是重复性结论；主 Agent 可基于本报告决定是否批准完整四轮新实验。

## 提交与发布状态

报告已在本地隔离分支 `codex/r1-j2-02-repeat-01` 提交。普通 Git push 因无法连接 `github.com:443` 失败；随后仓库连接器创建 Git blob 收到 HTTP 403 `Resource not accessible by integration`。远端候选分支未创建，未尝试绕过该权限限制或改动 `main`。
