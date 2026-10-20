# 参考思想、工程选择与实验结论

## 1. 三者必须分开

| 层次 | 可以主张什么 | 不能由此推出什么 |
|---|---|---|
| 外部参考 | 方法帮助划分 Context、持久状态、能力资产和评估 | 参考文章不会替本项目提供实现或验收 |
| 工程实现 | 当前代码采用有限分层、Hybrid、来源 DAG、独立 Domain | 源码存在不等于真实业务或 Provider 实验成功 |
| 实际结果 | 本轮有新鲜请求、回执、失败、Usage 与测试结果 | 单次成功不等于泛化收益或生产可靠性 |

## 2. 经过核对的 Handbook 参考

阿里云《AI Agent Handbook》[第5章“信息：上下文、状态与可复用能力资产”](https://aliyun.github.io/ai-agent-handbook/build/chapter-05.html) 将运行信息放进有预算的上下文，并讨论可复用资产与任务引导。OpsPilot 从中采用的是“按职责和优先级管理输入”的参考思想；具体块优先级、Token 预算和授权边界是项目实现选择，非手册给出的保证。

[第8章“Agent状态存储与语义资产”](https://aliyun.github.io/ai-agent-handbook/run/chapter-08.html) 区分事件、执行快照、产物与可复用语义资产的存储职责。OpsPilot 以 SQLite Domain 保存业务权威、LangGraph Checkpoint 保存执行进度，避免把历史模型文字和副作用事实混在一起；这里的本地事务不能外推成跨服务强一致性。

[第22章“Agent优化：Badcase”](https://aliyun.github.io/ai-agent-handbook/optimization/chapter-22.html) 提供从失败样本和验证任务反推优化的参考。OpsPilot 因此分别报告回答质量、实际业务结果与控制安全，保留首次失败并冻结对照输入。本轮不以提高模型轮数或改 Gold 来消除失败，也没有重新证明 Memory ON 一定优于 OFF。

以上标题在本轮核对官方页面。旧学习材料若采用其他标题，属于历史引用，本轮不回写它们，也不把手册章节当作 OpsPilot 的已实现证明。

## 3. 为什么保留 Hybrid

最近窗口容易保留新消息，但会遗忘早先明确的否定和约束。全量历史开销不断增长，也保留已经过期的事实。滚动摘要能压缩，但可能失真、丢来源，且摘要本身可能过期。现有 Hybrid 组合“必须的可信状态/正式输入锚点 + 有效摘要 + 预算内近期历史 + 可选资产”，没有改建通用 Context Runtime。

这是受控工程折中，并非本轮证明了最高任务成功率。3600 预算实验会裁剪直接 Memory；本轮因此发现派生回答仍需追溯 Memory。使用 Summary 也没有延长 Evidence TTL，压缩调用返回时来源过期仍要拒绝提交。

## 4. 为什么用来源 DAG，而不只查撤销词

模型可能改写方法而不复述 Memory ID；后续回答也可能只引用先前回答的 Attempt。Summary 进一步改写文字。因此权限/有效性按消息、Attempt、Memory、Summary、Evidence 的 ID/version/digest/作用域递归校验。

本轮 bug 说明只有直接边还不够：A 回答依赖 Memory，B 回答只依赖 A 的 MODEL_ATTEMPT，撤销后不能把 B 当独立来源。35 行修复沿现有 chat_run_answers 找祖先并重复同一验证。没有复制一套新存储或删掉原校验。

代价是递归查询和保守排除：某个来源失效会移除依赖它的整段回答，可能损失仍正确的通用解释。这里优先可审计安全，未建设句子级事实抽取。后续性能优化应先测量，不能顺手把校验缓存跨调用持久化。

## 5. 为什么可信状态独立于模型

模型能解释、选择合法只读工具；Plan、Approval、ActionIntent、Ledger 和回执来自 Domain。历史 HTTP 200、用户说“批准”、Memory 的成功经验、Summary 的“已经修复”都不能创建许可。

S1 的 REPAIR 和 DELIVER 分别幂等；S2 的 Queue/Receipt/Outbox 原子提交。未知模型请求允许 UNKNOWN，而业务动作未知时先回查持久身份和 Ledger。业务“恰好一次效果”和模型 HTTP“恰好发送一次”是不同承诺。

## 6. 为什么本轮不改 Worker 调度

历史零 Attempt 不足以定位失败位置。两个有限故障注入只证明当前错误分类和有限重试，不证明历史根因。没有原始堆栈就记录 ROOT_CAUSE_NOT_PROVEN。重写 Scheduler 会扩大影响且不能补回旧日志，违背任务范围。

## 7. 为什么观测器只能在独立验收入口

旧 hook 挂在错误 HTTP 客户端，Manifest 无法证明网络请求。新观察位于原 httpx2 序列化后、Transport 前，逐项核对资产正文摘要和结构，保留请求 body hash。它仍不能证明 Provider 实际推理使用了每条文本，不能恢复崩溃后未知 Usage，也没有让来源检查与发送原子化。

在生产里加入调试猴子补丁不值得；本轮只在隔离验收进程给原客户端安装公开事件 hook，不改参数、重试、超时或 Tool Schema。脱敏输出也不包含完整原始 Prompt。

## 8. 什么结果会改变下一步

- 如果实际请求继续发送撤销资产，判安全阻断，先 RED 再最小修复。
- 如果目标 Summary 在固定轮数内未形成，记录具体预算/TTL/策略限制，停止该实验，不追改旧 Gold。
- 如果 Worker 原因未知，保留未知并列需要补齐的原异常证据，不做猜测式修复。
- 只有主 Agent 独立审核本次 SHA 和证据后，才可裁决阶段是否通过。M4/M5 或新业务不由本卡自动授权。
