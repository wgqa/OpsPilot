# M3-01-HF-01 冻结验收计划

## 固定边界

- 起始源码基线：`main@22823acc519789c14e2cefe8e0f4c16a05fb4b72`；开工核对的 HEAD、branch 和 `origin/main` 与任务卡一致。
- 本轮仅补证 M3-01；不进入 M3-02，不增加 Memory 能力或业务写权限。
- 原 M3-01 Gold、Rubric、评测协议、历史报告/结果/轨迹/失败、paired-eval-01..05、web-chain-07 和其他阶段证据只读。变更与新证据只放在 `docs/evidence/vnext/m3-01-hf-01/`；代码只在冻结安全要求有真实 RED 证明违例后允许最小修改。
- 原 M3-01 8 对/16 臂、12/16、P03/P04 ON/OFF HANDOFF_READY 与允许结论不符、`UTILITY_NOT_PROVEN`、`NOT_REPORTED` 费用等结论不得改写；本轮不重跑评测。
- 只允许最终主 Agent 签署阶段裁决。本计划不预先判定 PASS。

## 可观察验收门禁

| ID | 冻结断言 | 证据判据 |
|---|---|---|
| HF01-01 | 开工基线与本地改动得到保护 | 记录原始 HEAD、main、origin/main、状态、环境、锁文件哈希、模型 ID、脱敏 MCP 命令摘要；不清理/暂存已有改动 |
| HF01-02 | 历史 M3 证据保持原样 | 记录 Git 跟踪的 M3-01 证据 SHA-256；最终重算一致，原目录无差异 |
| HF01-03 | 最终源码真实 Web 旅程可复验 | 同一新鲜隔离 DB 中，Edge/Playwright 完成 Task A→候选→审批激活→不同 Task B 的真实 401→MCP/DeepSeek 使用来源 Memory→Web 撤销→后续调查/聊天排除→追问；至少 8 张本次截图 |
| HF01-04 | 外部和 Domain 轨迹可关联 | 记录源/目标 Task、Run、Memory、Attempt、Provider usage/模型、MCP tools/list/call/Observation、HTTP 与 Domain 回执；不记录凭据 |
| HF01-05 | 来源和业务权限正确 | A 与 B 不同；A 有 COMMITTED REPAIR、真实 HTTP 200 VerificationReceipt、冻结 Report/Evidence；仅可信 APPROVER 激活/撤销；B 无未批准 REPAIR/DELIVER、Scope 或 Policy 写入 |
| HF01-06 | 撤销后新 Context 不复用 | 撤销版本递增且状态 REVOKED；之后的新 Investigator/CHAT Provider 实际入参及 Provenance 都排除该 Memory |
| HF01-07 | Prompt/attempt/撤销竞态闭合 | C01-C03 使用确定性屏障记录线性化顺序；C01 构造后/预留前撤销必须拒绝或重建；C02 已预留、首个 Provider I/O 前撤销不得带旧 Memory 出站；C03 Provider 已开始后再撤销需准确记录请求先于撤销，不要求撤销网络调用 |
| HF01-08 | Checkpoint 与历史回答不复活撤销资产 | C04 活跃引用 Checkpoint 后撤销、跨进程重启，新实际 Provider Context 不含该资产；C06 撤销历史 Assistant 来源后，保留审计消息，但后续实际 Chat Provider Context 不含依赖内容 |
| HF01-09 | 过期/版本/来源失效有效 | C05 分别验证过期、版本/状态变化、来源失效后新上下文排除；不从缓存/Checkpoint 恢复 |
| HF01-10 | 新鲜回归通过并可从提交仓库读取 | 新鲜全量 pytest、M3 定向、S1/S2 关键安全回归、前端 build/lint、必要真实 MCP/HTTP smoke；保存完整命令、stdout/stderr、退出码和分子/分母 |
| HF01-11 | 失败记录和版本绑定齐全 | 每次失败保留独立编号目录、命令、原日志、退出码、原因；真实 Web 运行绑定到运行源码 SHA 和代码树摘要 |
| HF01-12 | 无安全硬红线/范围漂移 | 没有越租户泄露、未批准写入、假恢复、重复动作或新增功能；无法证明的门禁标记 UNVERIFIED/NOT_RUN 并升级报告 |

## 冻结的竞态测试语义

- 线性化点必须由代码路径内的同步屏障/事务事件/调用捕获证明。仅靠随机延迟不构成竞态证明。
- 每个用例必须观察最终真正传给 Provider 的 messages/context 与相应出站事件，不能只断言构造中的 Python 对象。
- “Provider 开始”定义为确定性 fake/capture Provider 已接收实际请求参数；真实 DeepSeek 的 HTTP 请求一经发出不可假定可取消。C03 只验证先后关系与审计归属。
- 任何失败先写入 `FAILURES.md` 与独立 `runs/<id>` 原始日志；如 C02 RED 证实违例，先提交 RED 测试/日志，再做最小修复并重跑受影响回归。
- 跨进程恢复测试使用独立临时 DB 和两个真实 Python 进程；重启后必须观察实际 Provider 参数。

## 本轮文件范围

允许新增本目录下的任务卡副本、验收计划、基线和历史哈希、测试/运行脚本、运行日志、截图、报告、机器结果和轨迹。实现修复只允许触及已存在的 Investigator、Memory/Chat Domain 路径及定向测试；只有实际 RED 后才能触及。不得编辑原 M3-01 证据目录、Gold、Rubric、冻结评测或用户本地资料。
