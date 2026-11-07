# R1-JOURNEY-READINESS-01 执行计划

## 基线

- Repo: `wgqa/OpsPilot`
- Base: `d324c8d6b64936ba84d1b50d18ce54356dec2c40`
- Branch: `codex/r1-journey-readiness-01`
- 开始时远端 `origin/main`: `60eee87bfe3cca522011316cb4cd2c0064ad291b`
- North Star / AGENTS / Review Skill / TASKS Blob 已从 Base 实际读取；摘要见本目录 `REPORT.md`。

## 冻结范围

- WP1：冻结 J1–J4 的用户目标、可信事实、允许/禁止结论。
- WP2：经正式 FastAPI、Worker、Runtime Grant、Assistant、MCP、Domain 验证 J1/J2；复用正式 S1/S2 路径验证 J3/J4 回读。
- WP3：区分普通 Assistant、可信结果读取、专业调查、审批/写入和未授权能力。
- WP4：只核对 Provider 协议与价格、给出单次有界运行建议；不创建真实 Grant、不发送收费请求。
- WP5：归纳 R1 证据与发布差距，不重跑完整 pytest、不改旧 Claim/Gold/失败。

## 证据等级

新增 J1/J2 Runtime Grant 测试使用显式 HTTPX `MockTransport` 和确定性响应；J3/J4 使用项目已有确定性模型 Fixture 和正式本地 API/Worker/MCP/Domain。它们证明接线、来源和 Domain 状态，不证明本轮真实模型自主性或浏览器体验。

## 硬边界

- Provider 外部 HTTP = 0；浏览器 = 0；外部业务写入 = 0。
- 不消费历史 Claim，不启动 Legacy Provider；J3/J4 仅使用测试作用域明确开启、并由 Fixture 替代的 Legacy Investigator。
- 不修改生产 Provider 语义、冻结 Gold、历史 Trace/Claim、`main`。
- 只在证实 S2 回归用例未显式表达它所验证的 Legacy 授权时，补充测试夹具环境；不放宽生产门禁。

## 停止线

J1–J4 离线链路和安全正反例、Provider 预检、R1 差距表完整后，提交隔离候选并停止。下一步仅是经独立审查后申请真实 Provider 授权；不自动进入 Live。
