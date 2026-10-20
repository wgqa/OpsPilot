# M3-03 分层 Memory 报告

**验收状态：PARTIAL，等待真实跨 Task 浏览器链路后交主 Agent 复核。**

**实现提交：** `a0ac67836c5dc641d316628689621c986e91b57a`。

M3-03 扩展既有 D5 Episodic Memory，并添加最小项目 Semantic Memory 生命周期。SQLite 从真实 v9 幂等升级至 v11。Semantic Candidate 必须引用同 Task 持久化用户消息；同租户、对目标项目有显式 Domain 授权的 APPROVER 确认后才成为 Active。记录版本、来源 digest、TTL、命令幂等和事件历史；修订要求当前版本匹配，撤销或到期后不再进入后续 Chat/Investigator Context。模型上下文把它标为非权威指导。

Episodic Memory 现在把同项目内的选择和排除理由带入 Context Provenance，并限制单次最多 3 条、候选扫描 100 条。默认仍选 1 条。服务/问题类型、来源 Task、ACTIVE、TTL、digest 与 Domain 来源收据共同决定适用性；当前 MCP Evidence 和 Gate 优先。Web Inspector 展示选择理由及排除原因。

真实浏览器已完成 Task A、候选生成与 `approver-a` 确认。Task A 真实 DeepSeek Provider 记录 5 次响应，4 次真实 MCP 查询成功；独立 Approver Domain 事件确认为 `CONFIRMED`。但 Task B 真实 Web 调查、Memory 进入其实际 Provider 输入、撤销后新请求及恢复尚未运行，E2E-03 为 `UNVERIFIED`。因此不报告 M3-03 完成或 PASS。

自动化依据：M3-03 语义测试和 M3-01 Episodic 回归；最终新鲜完整 pytest 为 `223 passed`，见 `runs/m303-final/pytest-full-final.log`。首次完整运行中有 1 个旧 Investigator 测试仍 monkeypatch 已移除的 `list_applicable_memories` 符号；调整测试替身指向新的选择器并兼容不带理由字段的合成记录后全绿。首次失败原始日志仍保存在 `pytest-full-episodic.log`，历史失败和现有局限见 `FAILURES.md`。真实 Task A 脱敏轨迹为 `runs/m303-final/TRACE-task-a.json`。浏览器截图没有保存成文件，不能把访问性树日志称为截图。
