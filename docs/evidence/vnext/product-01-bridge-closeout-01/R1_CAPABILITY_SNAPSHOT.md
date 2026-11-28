# R1_CAPABILITY_SNAPSHOT

## A. 已有真实模型证据

`docs/evidence/vnext/product-01-slice-02-live/REPORT.md` 与 `RESULTS.json` 记录了先前真实 DeepSeek Flash 四轮连续技术支持旅程：8 次 Provider HTTP、9 次 MCP，单 Session 持久化，所有四轮模型 Run 完成。模型发现/比较了回调协议、分析用户 JSON、查询同订单当前 Event，并响应用户纠错查询 event-previous。结果为 **PARTIAL**：事件区分和来源引用有用，但模型曾从传输字段过度推断配置是否生效，并在草稿中承诺没有实际开始的后续跟进。此结论保持原样。

可准确陈述：曾运行真实 DeepSeek，观察实际模型自主选择的协议、Knowledge、业务工具及后续决策，并保留 Usage、工具观察、答复和失败分析。

不能写：真实模型全程准确、完全自动解决工单、已经证明 Memory/新 Bridge 提升效果。

## B. 已有离线专业业务证据

本候选的 S1/S2 使用确定性模型，但通过正式 FastAPI/Worker、真实本地 MCP、Loopback HTTP 和隔离 SQLite：

- S1：同 Session 的可信 401 Investigator 产生 `WAITING_APPROVAL` Plan，Assistant 读回并明确未修复；单独隔离 D3 闭环演示完成 Revalidation、CAS、同身份 HTTP 200、VerificationReceipt、冻结报告及 DELIVER，得到 `DELIVERED`。
- S2：读回草稿时 `HANDOFF_READY`、没有 Receipt/Queue；显式提交后才得到一个本地 HandoffReceipt 和 `SCOPE_ESCALATED / PENDING_REVIEW`。没有增加 Scope，也没有声称 403 恢复。
- Source 读取由可信 Session/Task 关联和服务端当前性校验约束；本轮未改变 TaskControl 或 Domain 写入语义。
- 结果数量遗漏、刷新后 Assistant Sources 恢复与 CLI reset 清洁入口均有 RED/GREEN 或定向回归。

可写：实现并验证了统一 Assistant 到现有专业调查及结果回读的离线桥接；利用确定性模型、真实本地 MCP/HTTP 和事务性 Domain 证据验证权限、待审批、已交接与已修复状态的区别。

不能写：以上是新的真实 LLM 用户旅程、浏览器端到端验收或生产修复。

## C. 尚未完成验证

- 新 Bridge 中真实 LLM 是否主动提出 S1/S2 调查或读取 Outcome。
- 浏览器中确认 CTA、刷新恢复、来源撤权后的显示及完整用户操作。
- 用户生产身份、企业系统、外部工单和生产可用性。
- 当前全量 pytest 仍有 16 项失败：12 项实验身份/历史 claim 绑定，3 项旧 AR-03 Runner MockTransport 出站未触发（根因 UNKNOWN），1 项废弃 C1 RED。
- main 合并未执行。

简历或面试应区分真实模型探索性 PARTIAL、确定性离线业务桥接、尚未验证的 Web/真实 LLM 路径。\n