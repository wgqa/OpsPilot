# M3-02：AI Agent Handbook 阅读地图

这份地图把手册中的上下文管理主题映射到 OpsPilot M3-02 的实际实现。手册提供通用设计原则；下面的预算、字段和安全边界是本项目冻结合同及代码选择，不应归因给手册。

| 手册章节 | 阅读重点 | OpsPilot 对应实现 |
|---|---|---|
| [第 5 章：Context 构建](https://aliyun.github.io/ai-agent-handbook/build/chapter-05.html) | Context 是有预算的输入；区分当前任务事实、历史交互和外部材料；为摘要保留来源 | `opspilot/domain/context_engineering.py` 的 Token 估算、预算分配和 Recent Window；`opspilot/domain/chat.py` 的 Context 准备、来源清单与摘要依赖 |
| [第 8 章：Agent 执行](https://aliyun.github.io/ai-agent-handbook/run/chapter-08.html) | Agent 每轮由上下文、模型与工具执行组成，工具结果应回到后续决策 | `opspilot/domain/chat.py` 持久化多轮消息和 Run；`opspilot/investigator.py` 组装实际模型/MCP 调查上下文 |
| [第 15 章：治理](https://aliyun.github.io/ai-agent-handbook/governance/chapter-15.html) | 把信任、权限和治理放在 Agent 外围 | 项目的可信 TaskBinding、TaskControl、Evidence、Gate、Approval 和 Domain 事务；摘要和记忆不产生权限 |
| [第 21 章：上下文优化](https://aliyun.github.io/ai-agent-handbook/optimization/chapter-21.html) | 上下文裁剪与预算管理 | `context_budget_for_model`、`allocate_context_blocks`，按模型配置和优先级保留必需块 |
| [第 22 章：记忆与摘要](https://aliyun.github.io/ai-agent-handbook/optimization/chapter-22.html) | 摘要和记忆需要控制范围并能服务后续调用 | Rolling Summary 与 Hybrid 路径；来源被撤销或过期后重新验证依赖，派生摘要不可作为事实权威 |
| [第 23 章：评估与优化](https://aliyun.github.io/ai-agent-handbook/optimization/chapter-23.html) | 用运行结果比较策略，不以单次成功代替评估 | `runs/strategy-comparison-03/TRACE.json` 保留真实 Provider 用量、延迟、失败与策略结果；当前效用结论仍为 `NOT_PROVEN` |

## 阅读结论

M3-02 的核心是每次模型调用前可解释地构建、预算和检查 Context。Recent Window、Rolling Summary、Hybrid 是本项目比较的策略；测试保留真实失败，因此不能把压缩路径宣传为优于近期窗口。模型只提出只读调查动作，Domain 仍决定当前事实、权限和业务状态。
