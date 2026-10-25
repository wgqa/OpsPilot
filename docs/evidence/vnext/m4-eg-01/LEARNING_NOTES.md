# M4-EG-01 源码学习笔记

## 从业务事实到 Agent 提示

OpsPilot 中，用户输入不是业务事实。S3 当前事实来自 TaskBinding 作用域下的 Domain/MCP/HTTP Observation；Domain Gate 用任务、事件、版本和新鲜度验证它们。对话模型可以解释这些事实、选择只读查询和给出方法建议，但不能把历史 Memory 或用户描述提升成当前 Evidence。

本轮在 `opspilot/domain/chat.py::_prepare_context()` 为 `orders-async-demo` 的受信 S3 Task 状态追加解释规则。这个层负责把业务状态转成 Chat 解释所需的上下文。它没有更改 `s3.py` 的 Gate 或当前性计算，也没有产生业务状态写入。

## Context Engineering 与 Memory

- **Working context**：当前消息、同 Task 的可信状态和当前 Run Observation，是本轮判断的工作上下文。
- **Episodic context**：`d5_memories` 中经 APPROVER 确认且来源仍有效的历史案例。它跨 Task 提供排查顺序/方法，不代表 Task B 的 Event 状态。
- **Semantic knowledge**：`knowledge/async-callback/manifest.json` 管理协议版本、摘要、来源、适用时间。本轮保留 v2.0 文件，新增 v2.1 文件并改为活动文档。
- **Procedural knowledge**：既有 Skill 提供按需调查方法。本轮没有新增 Skill。

Task B 的真实 Prompt Provenance 直接证明 Memory ID 和来源 Task ID 进入模型请求；同 Task 当前 Observation 与历史经验冲突时，后续 provenance 把来源列入 `CURRENT_EVIDENCE_CONFLICTS_WITH_MEMORY`。这体现了“历史方法提示”和“当前业务状态”应分层处理。

## Knowledge 版本为什么要追加

修订协议时新增 `receiver-ack-contract-v2-1.md` 并更新 manifest 的版本、digest、source 和 valid_from，而不是原地改写 v2.0 正文。测试 `test_vs08_response_source_change_is_not_reused` 也应跟随 manifest 的活动文件路径；硬编码旧文件会使版本升级后的来源失效测试实际上改错文件。

## Web 资格与可信来源

Memory 候选 UI 之前只检查传统业务 outcome。S3 不写成旧 M1 `DELIVERED` 等终态；因此 UI 需要把当前性为 `CURRENT` 的 S3 诊断作为可申请候选的来源，同时明确拒绝过期/失效 S3 结论。UI 的候选展示不是授权：候选确认仍由可信 APPROVER/API 完成。

## 测试夹具与真实外部调用的区分

确定性测试验证 Context 和状态转换；真实 Provider 运行验证模型实际读到了 prompt 并产出自然语言；MCP/HTTP Trace 验证 Agent 查询了当前绑定事实；浏览器/API 记录证明用户操作进入持久 Domain。SLA 四次 Provider Chat 使用持久测试 Observation 作为隔离事实准备，不能误称为四次真实 MCP 流程。真实 Web Task B 则确有六条实际 MCP Observation。

## 测试 Worker 配置修复

`test_hf_b_stale_gate_stops_after_no_tool_progress` 在独立子进程启动 deterministic `NoToolModel`，但 Worker 入口先检查模型配置变量。测试原来因变量缺失在到达要测的 stale-Gate 分支前失败。测试现在只在子进程环境设置非敏感占位值，并继续替换成 `NoToolModel`，不读取密钥、不连接 Provider。其定向回归与全量第二次运行均不再触发该失败。
