# Diff 与结果报告

## 审查前置核验

- Repo：`wgqa/OpsPilot`
- Branch：`codex/r2-ar04-v2-provenance-hf01`
- Base：`28d5d1e670801feec0bb6620bfc249ff850404f4`
- Runner 修复提交：`a9adae903740ca7799cecebd05095caaabe3f915`
- provenance 持久化断言测试提交：`32c207ea2cef666f8801edc689983496c5331a1b`
- 最终候选 HEAD：以最终推送的 `codex/r2-ar04-v2-provenance-hf01` 分支 SHA 为准；Base 到候选没有 merge commit。
- `PROJECT_NORTH_STAR.md`：已从 Base 实际读取；blob `43dabda468506717c6956e676dfad4304c4f38e6`。
- `AGENTS.md`：已从 Base 实际读取；blob `807b928686a4dd2cac7b15b3c354b9943c93c910`。
- Review Skill：`.agents/skills/opspilot-slice-review/SKILL.md` 已实际读取；blob `d405c8d413d633824b279202cc1503dab4cf0b03`。
- 适用冻结基线：`docs/baseline/v1.0-implementation-baseline.md`，blob `30e18d7ddbade7cdf7712d035d6fd8488bcb9676`。重点为 Context provenance 与离线 Gold/Trace 不可改写。
- 证据范围：V2 Runner、其测试、原始冻结 Provider Trace、Mock Runtime/Domain Trace。Provider、外部 MCP、浏览器、业务 HTTP 均未调用。

## 修复内容

1. 移除 Q02-A 对 `legacy.OLD_TRACE` 的隐式读取。Runner 现在使用逐 Case 冻结来源表：Q02-A 指向 retention recheck 的失败首轮响应，Q02-B/Q06-B 指向 ABC `live_run_02`。
2. Mock dispatch 前验证每个 Case 的 Trace 文件 SHA、Case/Logical ID、Request Body SHA 配对、Provider Response ID、原 Trace 的 `response_body_sha256`、模型与重新计算的 Summary 文本 SHA。任一字段漂移即停止。
3. 生成的 Mock provenance 同时保留来源 Trace、回复 ID、响应体摘要与 Summary 文本摘要。没有把真实回复混标成另一个 Provider Response ID。
4. 添加三项反向测试，分别注入错误 Response ID、保持旧摘要但替换正文、交换 Q02-A/Q02-B 来源；均证明请求数为 0 且没有 Mock Trace、账本或结果文件生成。

## 独立核验结果

- 完整调用链：3/3 Case 成功；每例 2 次摘要和 1 次回答；6 次摘要 + 3 次回答。
- 三例均持久化两份 Summary，第一份被第二份 supersede，第二份为 CURRENT；最终 Prompt 的四个阶段均为 `COMPLETE_TEXT_WITH_SOURCE`。
- Q02-A 第一轮回复使用 Response ID `c3435ff4-fc27-4ffb-b053-bbfcabc600e0`，摘要正文 SHA `2ef286e22a44b927352d3dd45797f34baa331bbe48ae65a247e2d56caf81a136`，来自 retention `live_run_01` Trace SHA `3c6552bf…`。
- Q06-B 的早期 `max_attempts` 仍标 `PARTIAL`；seq11 协议和参数变化保留为 `COMPLETE_TEXT_WITH_SOURCE`。
- 全套测试 `13 passed`，包括原有 C01–C08 和三个新反向测试。C06 RED 与 F01 遗留记录的历史文件继续与 Base blob 一致。
- Provider 请求：0；费用：USD 0.00；外部 MCP：0；真实模型语义评分：未执行。

旧 V2 根结果与历史 Trace/账本保持原样。新运行只写入本目录的 `mock_run_01/`。完整测试过程和先前失败修正记录见 [`TEST_RUN.txt`](TEST_RUN.txt)。

## 裁决边界

本次仅证明来源映射正确、真实摘要能够走完整应用 Mock 持久化路径及错配会在 Mock 发出前阻断。Mock 摘要和回答不能证明 Provider 的自然语言质量，也不构成 L3 真实模型复测授权。此候选提交后交由主 Agent 独立验收，再决定是否准入最后一次有界真实模型复测。
