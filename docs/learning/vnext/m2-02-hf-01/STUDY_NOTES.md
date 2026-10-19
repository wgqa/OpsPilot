# M2-02-HF-01 源码学习笔记

## G6：把自然语言意图和可信资源边界分开

入口与策略判定主要在 `opspilot/investigator.py`。用户句子只是待解释的意图，不是资源授权。单纯用“scope/主体/服务”等词匹配会把否定句和历史讨论误当作越界请求；只看关键词也会漏掉同义表达。修复后的决策先区分肯定越界、否定/引用、混合目标，再把可执行子任务限制在可信 TaskBinding。测试应同时证明 Provider/MCP 是否被调用、Gate/Receipt/Draft 是否变化，而不只断言一条分类标签。

## 有界调查：Gate 的 NEED_MORE 必须有真实进展动作

`opspilot/investigator.py` 决定合法工具集合和调查循环；`opspilot/domain/s2_diagnosis.py` 负责持久化 Attempt/Gate 轨迹。`NEED_MORE` 的含义应是仍存在一个可执行且预期带来新证据的动作。预算用尽或证据重复时继续循环，只会制造更多 Gate 行。调查预算保持 8 次模型请求和 6 次 MCP attempt，另以 deterministic Gate identity 和每 Run 64 条的硬限制处理恢复重放。持久 Domain 记录用于解释业务决定，LangGraph 仍只负责执行进度。

## H 归一化：类型正确仍然是不可信数据

模型输出先校验版本化 Pydantic/JSON Schema，再作为候选线索传入策略。`uncertainty=high` 会真正选择澄清路径；Request ID 只有匹配本 Run 的新鲜 Probe 才收窄到该 Request 的授权事实读取。这样用户/模型候选能影响合法调查选择，但不能定义 tenant、TaskBinding、Evidence、Gate 或 Scope。Release 的 `normalizer_evidence` 同时记录已消费字段和策略行为，能分辨“写进日志”与“参与决策”。

## 证据当前性和 Request 关联

授权事实依赖同一 Request 的实际 Probe、Authn/Authz Event、当前 Grant/Policy 版本及资源绑定。工具策略若只读取 Evidence 而不取同 Run Observation 时间，会把刚产生的 Probe 误判过期；因此测试应推进 Domain 状态并使用真实当前时间，避免静态夹具在测试运行时自然过 TTL。MCP `get_scope_authz_facts` 的输入只接受 `request_id`，服务端仍从 TaskBinding 重新校验作用域。

## 评测的失败保留和评分校正

原始 Release 轨迹与最终计分器分开保存。发现 G8 把“不能认定成功”“不足以证明”当作成功肯定句时，不能重写旧结果或删掉失败；要保留旧分数、修复评分器、用输入哈希和 scorer commit 在一个独立目录重评同一 48 条。复评只修正评分，不增加模型或 MCP 调用。结果同时呈现 Correct Handling、Evidence Integrity、Control Safety、Boundedness，防止把安全合格误写成用户效用达标。

## 建议阅读路径

1. `docs/evidence/vnext/m2-02-hf-01/ACCEPTANCE_PLAN.md`：先理解冻结的可观察结果。
2. `opspilot/investigator.py`：跟踪 G6 intent、typed cues、可用工具、预算和 Gate 后路由。
3. `opspilot/domain/s2_diagnosis.py`：跟踪 Attempt、Evidence、Gate 的持久边界。
4. `tests/test_m2_02_hf_01.py` 和 `tests/test_m2_02_hf_01_release.py`：看 RED 变 GREEN 的断言。
5. `opspilot/smokes/m2_02_hf_01_release.py`、`docs/evidence/vnext/m2-02-hf-01/RESULTS.json`：看策略对照和各轴分数。
6. `runs/browser-e2e-final-752173a/browser-trace.json` 与 `DOMAIN-TRACE-SUPPLEMENT.json`：核实用户界面行为与可信 Domain 事实如何关联。
