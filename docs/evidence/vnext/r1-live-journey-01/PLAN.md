# R1-LIVE-JOURNEY-01 执行计划与状态

**状态：** `BLOCKED_BEFORE_PROVIDER_SEND / ACCEPTANCE_CANDIDATE`

## 基线

- Repo：`wgqa/OpsPilot`
- Base：`0be2131eab5412226c507c5322cb5d4fccc5f9f2`
- 分支：`codex/r1-live-journey-01`
- 本次开工 HEAD：`0be2131eab5412226c507c5322cb5d4fccc5f9f2`
- 开工远端 main：`60eee87bfe3cca522011316cb4cd2c0064ad291b`
- 任务卡 SHA-256：`ea0b53649b32f1d68d020a6b1a0574e8f444b1b733bc590640d89dd8aa3318c9`
- North Star Blob：`43dabda468506717c6956e676dfad4304c4f38e6`
- AGENTS Blob：`807b928686a4dd2cac7b15b3c354b9943c93c910`
- Review Skill Blob：`d405c8d413d633824b279202cc1503dab4cf0b03`
- TASKS Blob：`1f08ee3a8e538d7ece4d2b2841c7c53e25737b7c`
- 冻结 J1–J4 `CASES.json` Blob：`c31afbed3bf1cb11fa25906f1d7290ee9cdbfadd`
- 适用 Deferred Gates：`docs/evidence/vnext/m2-01/DEFERRED_GATES.md`、`docs/evidence/vnext/m2-02/DEFERRED_GATES.md`

## 冻结范围和许可

- 真实 Provider：DeepSeek `deepseek-flash`，只走正式 `ASSISTANT_V1` 与 Runtime Grant。
- 最多 16 次发送、单并发、单次超时不超过 30 秒、零自动/人工重试、输出参数不超过 2,048 tokens、应用侧上限 USD 11.00。
- 输入 Context 上限 12,000 tokens；不依赖 cache-hit 或 off-peak 价格。
- 仅新隔离 Demo DB 和本 Campaign 的 Runtime Grant；不复用实验 Claim。
- 不启动 Legacy Provider，不做浏览器自动化、外部业务写入或 main 合并。
- J1/J2 使用冻结问题；J3/J4 只读回读已有受信 S1/S2 结果，不重跑 Investigator。

本轮对官方当前价、正式 Runtime Grant 源码和配置做了一次有界发送前核验。当前官方最大容量的保守费用界超过授权额，且 Runtime Grant 的实际预留与该界不一致；因此没有创建 Campaign Grant、Domain/Checkpoint 数据库或发送 Claim，也没有发出真实 HTTP 请求。按合同标记 `BLOCKED_BEFORE_PROVIDER_SEND` 后，继续完成离线证据与 R1 工程收口材料。

冻结案例原文副本保存在本目录 `CASES.json`，其字节与 Base 中对应文件一致；没有更改 J1–J4 的 Gold、输入或成功定义。
