# M3-03：Agent Handbook 阅读地图

| 手册章节 | 阅读重点 | M3-03 的项目映射 |
|---|---|---|
| [第 5 章：Context 构建](https://aliyun.github.io/ai-agent-handbook/build/chapter-05.html) | 为外部知识和历史内容保留清晰来源与上下文位置 | Episodic 与 Semantic Guidance 作为独立 Context 区块，Provenance 记录选用与排除原因 |
| [第 8 章：Agent 执行](https://aliyun.github.io/ai-agent-handbook/run/chapter-08.html) | 工具和模型应围绕当前任务逐步交互 | Task B 的真实 Investigator 仍需调用 MCP 获取当前事实，记忆只能提示调查方法 |
| [第 15 章：治理](https://aliyun.github.io/ai-agent-handbook/governance/chapter-15.html) | 权限和治理由可信控制面执行 | Task owner 创建候选、项目授权的 APPROVER 确认，撤销由 Domain 记录；记忆不授予访问或业务权限 |
| [第 21 章：上下文优化](https://aliyun.github.io/ai-agent-handbook/optimization/chapter-21.html) | 控制外部上下文的数量和预算 | Episodic 选择有上限与扫描边界；Semantic 当前限制为少量项目约定 |
| [第 22 章：记忆与摘要](https://aliyun.github.io/ai-agent-handbook/optimization/chapter-22.html) | 记忆应有生命周期并关联来源 | `episodic_memory.py` 使用来源回执；新增 `semantic_memory.py` 记录候选、确认、修订、撤销与过期事件 |
| [第 23 章：评估与优化](https://aliyun.github.io/ai-agent-handbook/optimization/chapter-23.html) | 用冻结评估和失败证据判断实际效用 | M3-01 的历史 8 对/16 arms/12 gold match 仍为 `UTILITY_NOT_PROVEN`；M3-03 的 Web 复用链路未完成，不可宣称跨 Task E2E 已通过 |

手册提供通用概念；权限合同、数据模型、选择上限和验收状态来自 OpsPilot 冻结任务卡及实际代码，不是手册规定。
