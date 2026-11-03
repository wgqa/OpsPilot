# AR-03-MATERIAL-01 — 交付报告

**状态：`ACCEPTANCE_CANDIDATE`**

**安全发布分支：** `codex/ar03-material-01-public`

**原始本地候选分支：** `codex/ar03-material-01`（保留未经改写的原始日志和提交链，不公开推送）。

**冻结 Base：** `01eb6f9c38d062f7de040e202713a352215014f2`

**实现开始前 HEAD：** `9e6cb589a1338378b462c5bae532dcd7d4df728d`

**远端状态：** 推送前通过 `git ls-remote` 核验远端 `main=ec8c3582f6d145eec9979c43607302731411ead8`，同名发布分支不存在；安全发布候选已成功推送，`main` 未修改。

## 用户现在可以完成什么

用户可把多行回调配置或日志交给统一 Assistant 请求解释。系统把原始消息作为未验证材料保留，不从其中取得订单授权、当前 Event 状态或其他业务权限；在没有 TaskBinding 时，仍可查询当前 Session 获准的协议资料，但不执行订单、Delivery 或 Receiver 查询。冻结的 MAT-02 JSON 日志和 MAT-03 缺字段日志都经正式 API/Worker 进入模型输入；Fixture 对 MAT-03 的结果明确指出 `receiver` 为空、`request_id` 缺失且当前状态未知，没有补造值。

协议升级问题可按需发现授权文档、读取有界原文、比较版本并加载可选分析 Skill。可信 API 绑定 `ar03-order` 后，Assistant 可以在同一调查 Run 中取得 Delivery 和 Receiver 的当前观察，依据同一 Event 区分 `202/ACKNOWLEDGED + QUEUED` 与 `PROCESSED`，并生成标明来源及未知项的未提交说明草稿。当前合同文档不能证明线上实际部署版本。

以上是**确定性 FixtureModel、正式本地 API/Worker、持久 SQLite 与 MCP 工具路径**的接线证据；不是 DeepSeek 自主调查或真实用户体验通过证明。

冻结 MAT-01 的实际 Fixture 答复摘录：

> 这是依据本次授权检索的原文作出的协议解释；来源 `callback-retry-contract` v1.0.0，`local:orders-async-demo/contract-v1`，第 1 行。……线上部署版本没有实时证据，仍未知。

拒绝样例：未授权的 `api-scope-current` 文档在 Domain 授权读取中抛出 `DocumentNotAuthorizedError`；含 `bind secret-order` 的未绑定用户材料没有触发订单/Delivery/Receiver MCP 工具，也没有创建 TaskBinding。前者是确定性 Domain 测试证据，后者是持久 Assistant/MCP 旅程证据。

## 实际离线轨迹

`TRACE.jsonl` 从通过测试所用 SQLite 的 `assistant_runs`、`assistant_calls`、TaskBinding 与持久答案导出，共 59 条记录：7 个 Run、7 个持久答案、26 次 FixtureModel 调用、19 次实际持久 MCP 调用。没有真实 Provider 请求。

这 19 次 MCP 调用包括：协议发现 5、原文摘录 5、Skill 加载 3、协议比较 2、Delivery 2、Receiver 2。次数反映固定 FixtureModel 在对应测试路径作出的提议与实际工具执行，不代表真实模型会采用这一顺序。无绑定用例没有业务读取；绑定的 QUEUED 和 PROCESSED 用例各自用可信 `ar03-order` 绑定，并验证 Delivery 与 Receiver 的 Event ID 相同。最终持久回答中的两种 Receiver 结果不同，均标出协议来源和部署版本未知。

静态协议摘录不建立 D2 业务 Evidence。订单事实只有在本 Run 的 Delivery/Receiver 工具完成后才包含 Observation 与 Evidence 关联。离线数据库的回执、Diagnosis、Ledger 计数为零；本次工具集合没有业务写工具。

## 实现差异

- `scoped_protocol_comparison.py` 增加受当前 Session 文档授权的原文摘录读取，最多 3 个精确行、总文本不超过 1600 字符；来源带文档 ID、版本、source、digest、节/行列范围和摘录 digest。超长行返回行/列继续游标，下一次读取从原文后续位置继续。出站来源复核重新检查授权、版本、文档内容、摘要及游标结果，任一变化则 fail closed。
- `assistant_mcp.py` 暴露只读摘录工具和按需 Skill 加载工具。Skill 提供方法提示，不授予权限或建立业务事实。
- `domain/assistant.py` 将历史摘录投影成有界历史资料，保留 ID/版本/digest，并标记 `NOT_CURRENT_BUSINESS_EVIDENCE`；每次后续模型调用前检查来源当前性。
- `assistant.py` 明确要求把用户粘贴的配置/日志作为未验证材料。没有更改 TaskBinding、Gate、预算、S3 写入或调查工具选择策略。
- 新增业务 Skill `protocol-upgrade-impact-analysis`，有 manifest SHA256 校验，可按需调用；没有默认注入每个 Prompt。
- 没有数据库迁移、业务权限扩展、Repair/Approval/Handoff 写能力或生产 Assistant 第二实现。

新增 MCP 的扩展入口在 `scoped_protocol_comparison.py` 的受限 Domain 函数、`assistant_mcp.py::run()` 的工具声明和 `domain/assistant.py::sources_current()` 的来源再校验。后续增加同类只读资料能力时，应先复用 Domain Session 授权与来源解析，再暴露 MCP，并为持久结果加对应 currentness 检查；Assistant Loop 不需要按主题加工具路由。业务工具仍由原 TaskBinding 和 MCP Server 托管。

Skill ON/OFF 使用相同冻结 MAT-02 输入和文档/权限条件：OFF 未加载新 Skill；ON 有实际 `load_protocol_upgrade_skill` MCP 记录及名称、版本、Digest、内容，并通过来源有效性复核。这只是内容接线对照，不能说明 Skill 改善真实模型准确率。

## 验证结果

- 冻结新场景：10 项通过（`green-12-material-final.log`）。覆盖纯协议查询引用、完整与缺失字段材料、用户材料未授权、按需 Skill、历史投影、有界原文及后续片段、来源撤权/摘要变化、同 Event QUEUED/PROCESSED 和未提交草稿。测试保留 MCP 单 Run 上限 6；12,000 Token Context 上限和 Task/Run 预算代码未改。
- 协议/Assistant 集成回归：71 项通过。
- 全量 pytest 在续读游标改动前执行：602 通过、4 失败，**不是全绿**。最终游标变更后新跑 10 项专项和 71 项协议/Assistant 回归；没有在游标变更后重跑全量。失败详情见 `FAILURES.md` 与原始日志。
- `py_compile` 通过；`git diff --check` 通过。
- 模型请求：0。浏览器：未运行且未获授权。外部业务写入：0。

全量测试中一个既有 C1 RED 测试会向两份已提交的 C1 Trace 追加自身运行记录。本轮发现后只把这两份文件精确恢复到本工作树 HEAD 的原始字节；复核后没有 C1 文件 Diff，未提交该副作用。全量测试原始日志仍保留。

## 失败、限制与停止

早期 RED 和调试失败保留于 `runs/`；`FAILURES.md` 区分有效产品 RED、测试准备/夹具错误、环境问题与既有全量回归失败。最终冻结 CASES 对齐期间曾有一次夹具错误导致 8 通过/1 失败，已保留日志；修正为复用 MAT-04 输入后 9 项通过。完整回归失败包括一个恢复进程用例、两个 Web Origin 断言和一个使用废弃 Intent 的历史 C1 RED。没有修改这些测试或合同来制造通过。

真实模型是否会发现合适的协议、使用 Skill、比较版本、结合当前 Observation、识别真实 JSON 配置是否需要修改并给出有据建议，仍未验证。Fixture 只证明冻结多行输入能进入正式调用、来源/权限边界能保持、结果可以关联持久回答；不证明配置修正语义正确。所有 token/usage 数值来自确定性替身，不作为成本或模型效果数据。历史 C1 证据保持原样；临时 SQLite 目录保留在本地，未打包进候选。

### 与 R1 / 真实模型验收的差距

- 需在独立授权下以真实 DeepSeek 验证它是否自主发现、读取并比较授权协议，是否按需调用 Skill，以及能否从用户 JSON/日志中提出不超出协议证据的实际修改建议。
- 需用真实用户输入核对建议、必要澄清、修改验证清单的质量；本轮 Fixture 固定答复不代表自主模型表现。
- 若 R1 包含浏览器端验收，仍需单独获准并使用允许的浏览器环境；本轮未运行浏览器，API/SQLite Trace 不替代浏览器验证。

**停止线已到：**本切片只提交离线实现候选，不执行 Provider、浏览器、业务写入，不合并 `main`，等待主 Agent 独立验收。

## 主 Agent 六问摘要（实施方自检）

1. **用户变化：** 可在统一对话中从授权协议原文和不可信用户材料推进到经绑定后的同 Event 说明草稿；证明级别限于 FixtureModel。
2. **Agent 决策：** 确定性替身提议并调用了摘录、比较、Skill 与业务只读工具；真实模型选择未验证。
3. **观察驱动：** 同一绑定订单的 QUEUED 与 PROCESSED 观察产生不同回答；这验证接线和业务事实传递，不证明模型决策质量。
4. **新增约束：** 摘录被限制在当前授权的 Session 文档、精确版本及 1600 字符内；验证授权拒绝/篡改失败，同时合法文档和业务只读路径通过。
5. **简化结果：** 复用既有 MCP、Session Grant、来源复核和 Skill 加载职责；没有新增 Guard、Runtime、预算平台或业务状态。
6. **证据与停止线：** 最终游标版本 10 项专项、71 项相关回归通过；较早的全量为 602/4，之后未重跑；Provider/浏览器未运行；旧 C1 文件无最终 Diff。候选提交后停止。

**实施方结论：`ACCEPTANCE_CANDIDATE`。不代表主 Agent PASS，也不请求合并或启动下一切片。**


## 公开候选文件审查

最终公开候选从冻结 Base 重新构建，不包含原始候选提交历史。对 Base 至原候选 HEAD 的 4 个提交、55 个变更文件逐项检查；未发现外部凭据、个人邮箱、私网地址或用户目录路径。5 个原始日志文件共回显 11 次本地 TestClient 合成口令，发布分支中的日志副本仅替换该回显，原始日志字节保持在本地原候选 worktree。逐文件原始/发布 SHA256 见 `PUBLIC_ARTIFACTS.md`。公开分支仅含文本代码、测试、冻结合同、脱敏证据和报告，不含截图、数据库、Checkpoint 或环境文件。
