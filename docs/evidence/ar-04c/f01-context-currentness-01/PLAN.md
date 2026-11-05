# F01 — 有界 Context 当前性修复

**授权：免费实施与离线验证。状态：实施中。**

- Base：`codex/ar04c-real-journey-01@f34295a245149492e9c5ce711caa64a4738cf57d`。
- 修复分支：`codex/ar04c-f01-context-currentness-01`；新工作树在 D 盘，未清理原工作树。
- 远端 main：`60eee87bfe3cca522011316cb4cd2c0064ad291b`。
- North Star / AGENTS / Skill 已在本轮实际读取，Blob：`e36f2f75509738551ac6d4a2de5b4f9cf44a7991` / `f174a6ab7f23f9e6d8b3ef98d455b99a75193143` / `d405c8d413d633824b279202cc1503dab4cf0b03`。
- 用户最新裁决已关闭 LIVE：`ACCEPT_WITH_LIMITS / business PARTIAL / G7 ON FAIL`。本轮不重新评审它，也不改历史报告、Gold、Trace、账本或 claim。
- 冻结 F01：ON J4 `run-4d91bb7f-ac99-4ed8-bd00-8987e8745c34`，Completion `7818fbd5-d1db-4035-9ee2-c2e364a676fa`，零 MCP/新 Observation 却声称本轮重读。
- 原 HTTP Trace Blob：`4af1765311c75ed87c0710ce3d995e9e05d90424`；失败记录 Blob：`1f17d0001060a8a4c90f86492c8ed949382993d4`。

## 本轮完成线

保留已有审计来源结构与来源再验证，仅改善实际送给模型的 Context：历史快照、仍有效的引用资格、本轮成功工具执行及本轮业务 Observation 分清。先保存 RED，验证三条路径：

1. 可以零工具解释有效的旧结果，明确没有本轮新取证。
2. 合法重新查询后，当前同 Event QUEUED/PROCESSED 事实可以进入本轮解释。
3. 历史证据过期或版本失效时，不通过摘要重新进入；合法新查询仍可执行。

Context 输入限额仍为 12,000；不增加最终答案验证器、Guard、强制工具流程、Memory 算法、预算或 Runtime。离线替身只能证明表达接线与合法路径，不证明 DeepSeek 已纠正 F01。通过定向回归后提交候选即停，交付一次小额真实复验方案，不自动发收费请求。

Web/D3 同期只读梳理现有 UI、审批、CAS、验证、交付入口与真实断点，不运行仍受 STOP 限制的浏览器，不实施新的业务写入接线。下一重点保留为可用 Web 与业务闭环，不因本轮扩建新的准备阶段。

## 六问

1. 用户：后续解释能分清过去知道与本轮刚查的内容；真实效果待小额复验。
2. 决策：模型继续自主选择直接解释、补查、澄清或停止。
3. 观察：新 Receiver QUEUED/PROCESSED 对应不同当前结论；旧快照不变成新事实。
4. 限制：无新硬性业务限制；零工具解释与合法重查都必须通过。
5. 简化：复用来源账本和现有 Context 装配，减少模型可见的重复审计字段。
6. 证据：冻结 F01、实际出站消息、三路径定向测试；免费修复完成后停，不扩实验。
