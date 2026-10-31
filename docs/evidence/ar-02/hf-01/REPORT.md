# AR-02-HF-01 报告

**状态：** `ACCEPTANCE_CANDIDATE`（等待主 Agent 独立验收）

**分支：** `codex/ar02-hf-01`

**修复基线：** `0beb5b16d98e0036011ac87c1ada055063ea0bc1`

**冻结提交：** `6fb540c6a6ab5f3e38c82e8c5f905ec561d63840`

**RED 提交：** `6d5748cfbfdf180bcff69f2cc6b9aa8e933477d3`

**源码提交：** `1aa9564fc6d2775b29ef656e7e3a4cea05be8a68`

## 用户可见变化

在授权资料查询确实返回文档时，回答可依据 MCP 返回的文档 ID、版本、摘要和来源引用。在查询结果为空时，助手仍可解释一般 HTTP 语义，但会说明没有检索到协议资料，不再声称引用了本次查询结果。

资料项目配置版本和 TaskBinding 版本继续用于选择检索版本。它们不再被描述成线上部署版本已经验证；本轮没有部署版本探测工具。

## 修复内容

- `opspilot/assistant_mcp.py`：将用户明确请求的合同版本与可信 TaskBinding 默认版本分开。保留 `user_requested_contract_version`、`requested_contract_version`、`trusted_binding_contract_version`、`applicable_contract_version`、`configured_contract_version`、`latest_available_contract_version` 及实际检索版本。`deployment_version_verified` 固定为 `false`，因为目前没有部署观察。
- `opspilot/assistant.py`：明确要求只有非空且引用匹配的 Knowledge 结果才能作为本次检索来源；空结果允许一般解释但不能虚构资料引用。
- `tests/test_ar02_runtime.py`：免费 FixtureModel 根据真实 MCP 工具返回内容回答，有命中时引用实际文档，无命中时使用一般解释。
- `tests/test_ar02_hf01.py`：覆盖命中/未命中、显式旧版本与绑定版本、绑定默认版本和无 Task 的版本选择。

没有改动 Schema、依赖、授权、TaskBinding 规则、业务 Gate、写入路径、历史 Gold 或生产 Investigator。源码提交为 4 个文件、27 insertions / 6 deletions。

## 证据和测试

先提交冻结标准与 S01/S02 输入，再提交 RED；原始日志保存在 `runs/`。

- RED：6 项中 3 项失败、3 项通过。失败分别复现空 Knowledge 结果仍被说成有来源、绑定版本被误报为部署验证、以及用户请求版本被绑定默认值覆盖。
- 定向 GREEN：`tests/test_ar02_hf01.py`、`tests/test_ar02_knowledge.py`、`tests/test_ar02_runtime.py` 共 30 项通过，两次运行。
- 全量活跃测试：439 项通过。按既有历史门禁排除旧分类契约文件 `tests/test_m4_autonomy_c1_red.py`；它使用已废弃的 Intent 表达，本轮未修改也未把它计作通过。
- 真实模型调用：0。所有模型输出均来自确定性 FixtureModel。
- 浏览器：未运行，遵守既有 STOP。
- 数据库：沿用测试创建的 SQLite，没有 Schema 迁移或正式业务写入。

`TRACE.jsonl` 中的五条记录从保存的测试运行事件中生成，原始本地运行记录位于 `runs/mcp-runtime-traces/`。知识命中实际返回 `receiver-ack-contract-v2` v2.1.0，digest `5fb3732339600ad1332960df08a00299358b8c4ea47c20f6fedc39b568c9850e`，并带有匹配 `source_refs`；空结果用例实际返回 `documents=[]`、`source_refs=[]`。绑定 v2、用户显式查询 v1 的记录分别保留请求版本 1、绑定版本 2、检索版本 1、适用版本 2，部署验证为 false。

已对 18 份本地运行 JSON 扫描常见凭证字段名与绝对用户目录路径，未发现匹配项；Trace 保留本地测试业务 ID 供复现。

本地业务 Trace `run-29b60b15-c48c-4e47-8148-48b3f4b9f37c` 来自真实本地 HTTP/MCP/SQLite 测试通道：订单接口 HTTP 200；目标 Event `event-aeee7d93-6316-4fa6-a1f4-d9444f736e40` 的 Delivery 返回 `receiver_http_status=202`；同一 Event 的 Receiver 当前状态为 `QUEUED`。这不是外部 Provider 或生产环境证据。

完整命令、退出码、原始日志和 Trace 哈希见 `RESULTS.json`、`TRACE_INDEX.json`。付费接口预检差距见 `COST_GAP.md`。证据提交的 SHA 在最终交接中给出，避免在该提交内部写入其自身的哈希。

## 失败和限制

RED 原样保留；修复后没有定向或全量活跃测试失败。Trace 选择脚本第一次使用了错误的 HTTP 字段名，随即依据原始 Observation 改为 `receiver_http_status` 后生成五条记录；筛选字段修正没有改动测试或业务实现。完整测试曾向无关的 C1 旧 Trace 追加一条测试记录；已按测试前确认的 Git Blob 将该文件恢复到原始字节，未提交该路径。

仍未证明真实模型是否遵循提示、真实收费上限是否可执行、或真实部署版本。检索继续使用既有有限领域检索；本轮没有扩建检索架构，也没有评估检索召回率。

## Skill 结项六问

1. **用户变化：** 可以区分“查到并引用了哪份资料”和“一般 HTTP 解释”；查询偏好不再伪装成部署事实。
2. **Agent 决策：** 本轮不声称模型自主性提升；回答行为由确定性 FixtureModel 验证。
3. **观察驱动：** 实际命中文档与空结果导致不同的引用行为；用户请求 v1 与绑定 v2 保留为两个独立事实。
4. **新增约束及合法路径：** 提示约束只阻止无来源的引用声明；合法资料查询和一般解释均有正例。没有新增授权或业务 Gate。
5. **简化结果：** 复用既有 Knowledge 检索、MCP 与来源结构；未新增 RAG、部署探测或预算服务。
6. **证据与停止线：** RED/GREEN、真实本地 MCP/HTTP、全量活跃回归已保存。付费模型与浏览器均未运行，main 未合并。至此停止，交主 Agent 独立验收。
