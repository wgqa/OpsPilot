# R2-AR04-LONG-CONTEXT-JOURNEY-01 — Phase A Plan

**Status:** `AUTHORIZED_FOR_OFFLINE_EXPERIMENT` / execution candidate only
**Repository:** `wgqa/OpsPilot`
**Base / initial HEAD:** `04b01d5c1e542910c4841bd12a065878f06456b4`
**Branch:** `codex/r2-ar04-long-context-journey-01`
**Scope:** synthetic WP3 long-context information availability (L1/L2); no production changes and no Phase B execution.

## 开工核验

- `PROJECT_NORTH_STAR.md` Blob `43dabda468506717c6956e676dfad4304c4f38e6`; `AGENTS.md` Blob `807b928686a4dd2cac7b15b3c354b9943c93c910`; `opspilot-slice-review/SKILL.md` Blob `d405c8d413d633824b279202cc1503dab4cf0b03`。均从 Base 检出内容实际读取。
- 冻结审计文件：`ALGORITHM.md` `d1018ca3035151195feaa4ed1d6c7dc79aaa588d`；`BENCHMARK_CASES.json` `b17f72ae2ab9d2009b0bdfbb74ef9972ba3bce9a`；`CONTEXT_BREAKDOWN.md` `0a4409e4ae7c08a2d6dbb22deb988dbf811cb2c7`；`WP3_INFORMATION_RETENTION.json` `908d9d57cf11764efe683104872ea2fe1e22445a`；旧 `RESULTS.json` `ece761f81ca2357c4007738f9ed1d06098a02187`；Harness `run_audit.py` `e0c96c443697abb2196684a405cac5b0f0de7115`。
- C06-HF-01 证据：`REPORT.md` `3b887411ee21b5e5638530b0a2496161f481f385`；`RESULTS.json` `9dce73ce5726036a1cb5d1b09463df974e743d26`；`TEST_RUN.txt` `50dcafb52af6fd78bbd1b218eb3d235d00174210`；`DIFF_REVIEW.md` `be17c2ee997bc153937301376b3a0f0242a46b52`。C06 已改进首预检错误分类；单条超长 User source 仍 fail-closed。
- 已读取 `docs/evidence/vnext/m2-01/DEFERRED_GATES.md` Blob `2e65870acb26a7c1383fdd96b5b8619748dda6b9` 与 `m2-02/DEFERRED_GATES.md` Blob `2536030b5b942bf9e3765e0916607549fa919934`。本切片是离线上下文评测，不新增 M2 业务写能力，不触发这些写入门禁。
- `HEAD` 在开工时等于 Base；远端 `main=60eee87bfe3cca522011316cb4cd2c0064ad291b`，目标候选远端分支不存在。唯一匹配 Base 的现有 Worktree 是 `.worktrees/ar04a-context-journey-01`；其 tracked files 干净，留有上一轮创建的未跟踪 `.pytest-tmp/`。为保留该记录，不删除或纳入提交；根 Worktree 另有无关未跟踪材料，未触碰。
- 历史 WP3 Trace 共 30 行：前 14 个完整对话轮是 seq 1–28，seq 29 是包含 Q11 答案的最新观察用户消息，seq 30 是对该消息的 Fixture 答复。原最终用户消息包含 Q11 的观察答案，不能原样当作提问。本实验在 14 个完整轮之后，将 seq 29 的同一观察规范化为一条共同历史用户材料，并且不生成它的助手答复；之后才在每个独立克隆中新增一道固定题。由此每题均从 29 行、同一消息序号与 Digest 的提问前历史开始，Gold 与问题文本分离。原 WP3 Trace 不改写。

## 六问与范围裁决

1. **用户变化：** 不增加产品功能；用户和面试讲解者会得到可复核答案：在长会话中哪些早期事实仍进入真实模型输入、哪些只有 Domain 原始历史保留、哪些因摘要/近期窗口而不可见。
2. **Agent 决策：** 本轮不测模型选择或语义记忆；Fixture 只生成确定性摘要/回答。Q12 仅检查下一步所需观察与只读边界在 Prompt 是否可见，真实模型如何决策留给 Phase B。
3. **观察驱动：** 若 Prompt 只见 `Receiver=QUEUED` 且未见完成回执，合理答案应保留未完成状态并只读补查/请求可信回执；若最新可信回执证明已完成，合理下一步才会不同。本轮不构造第二个业务事实实例。
4. **新增硬限制：** 不加生产门禁。实验只冻结问题与隔离要求：必须阻止 Gold/评分规则泄漏和 Q 间答案污染，同时允许模型输入自然含有真实历史事实；以问题字符串检查和每题独立 DB/checkpoint 克隆作正反验证。
5. **责任归属与简化：** 复用 AR-04 的 `AuditFixtureModel`、`_seed_turns`、真实本地 FastAPI/Worker/Domain 与 Context Manifest；只加评测编排/证据提取，不改压缩服务、不改预算/策略、不复制 Agent Runtime。
6. **证据与停止线：** A/B/C 各 12 个问题，采用相同历史快照、`W=16,384 / L=12,000 / O=512 / M=1,024`、Schema 和 Fixture 配置；D 为 `HYBRID` 高预算完整历史参考，`W=65,536 / L=60,000`，单列不排名。确认 48 次目标 Run、L1/L2 来源、Summary/Manifest/Request Wire 与本地 Token 口径后停止。真实 Provider/语义准确率固定 `NOT_EVALUATED`，Phase B 只提交 proposal。

## 冻结旅程与复现方法

- 逐条 Gold 依据冻结 `BENCHMARK_CASES.json::wp3_ground_truth` 与 `WP3_INFORMATION_RETENTION.json` 原始序号/正文核对，细则见 `QUESTIONS.json`。
- 保留 WP3 原始 14 个 seed body；合成长结果仍由 `AuditFixtureModel` 对 `EMIT_FIXTURE_TOOL_RESULT` 按原始 Harness 返回。前 14 轮经本地 FastAPI/Worker；最后的无标签 seq 29 观察通过隔离 Domain fixture 作为 user-only source row 插入，不制造额外回答。先在 `W=50,000/L=45,000` 高 seeding 预算生成一次前置快照，再用 SQLite backup 克隆到每个独立提问；复核序列 1–28 与冻结正文 Digest 相同、seq 29 仅移除评测标记，且 48 个克隆在前 29 行的 message ID、Digest、序号完全一致。
- A/B/C 的策略依次为 `HYBRID`、`ROLLING_SUMMARY`、`RECENT_WINDOW`；同配置固定 12,000 输入上限，不为任何策略单独调参。D 使用 `HYBRID` 并提供足够上下文容量。
- 仅把 `question` 字段发送给 Assistant；Gold、来源规则和评分字段仅用于 Run 完成后的离线分析。捕获各压缩/答复调用的持久 `request_json`、Summary JSON、Context Manifest、源消息和 token estimates，按 question/run 记录 Digest 并 gzip 去重保存。
- L1 从独立快照中的 Domain 正文按固定来源断言逐题核验，并记录所需序号与完整事实组；L2 用最终答复调用实际 wire/selected IDs/当前 Summary/Manifest 逐 fact 判定。每题状态为指定枚举之一，并另记 raw/summary/both/policy source contributions。L3 `NOT_EVALUATED`；Fixture answer 不作为正确率数据。
- 禁止付费/真实 Provider、外部 MCP、浏览器、业务写入及 main 合并。实际全套自测只限此脚本与验证命令；如基线历史事实无法一致复现，保留 Trace 并报告 `BLOCKED`，不修改 Gold。

## 实验变量和停止条件

A/B/C 共享问题、历史、系统提示首段、工具 Schema Digest、模型 ID 与配置预算。D 组预算更大，仅作可回答性上界参照。每个问题每组只执行一次，12 个问题分别从相同前置快照克隆；上一题模型答案不进入下一题。

停止条件：48/48 组题 Run 均有状态，或每个失败有原始失败证据；所有摘要引用映射到当前 Domain 行且 current summary 仅被当前 Manifest 引用；每道题均有 L2 状态与来源；策略 Token/压缩成本及遗漏清单可重算；Phase B proposal 明确未执行。无需为无损继续调预算、修改 Prompt 或扩展 Memory/Context 平台。
