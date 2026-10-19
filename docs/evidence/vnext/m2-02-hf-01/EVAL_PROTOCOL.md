# HF-01 对照评测协议

状态：冻结标准（实施前）  
协议版本：`m2-02-hf-01-rha-v1`  
旧 Gold 继承：`docs/evidence/vnext/m2-02/GOLD.json`（只读）

## 策略

- **R**：确定性规则调查器；与 H/A 接收相同结构化输入、TaskBinding、实时 Domain/MCP、Gate、技能/知识和预算。R 可以澄清、停止或执行有依据的只读查询。
- **H**：调用同一模型将自然语言整理为版本化、严格类型化的候选线索；服务器验证候选，再由规则策略消费至少一个合法候选字段。候选始终是不可信提示。
- **A**：真实模型按同一用户上下文及工具 Schema 动态选择合法只读工具；TaskBinding、MCP 参数核验、预算及 Domain Gate 与 R/H 相同。

R/H/A 均使用 16 个既有 holdout 的完整对话轨迹，每种策略各 16 次，总分母固定 48。每条试次单独创建 Domain DB 和 Checkpoint DB。输入、用户答复、认证资源绑定、Skill/Knowledge、工具及 Gate 策略保持等价；除各策略被冻结的决策机制外不隐藏 Gold、不给额外线索。

## 试次和发布证据

在实现代码先行提交后，冻结单一 Release。每一条 `RESULTS.json` 记录必须带完整 `release_ref`：实现提交 SHA、模型 ID、Prompt/Skill/Knowledge/Tool Schema digest、8/6 预算策略和解析依赖版本。每次调用、MCP attempt、Gate、Task/Run 关联、Evidence、Receipt/Draft、Token/时长（Provider 可提供时）、安全计数和 Trace 文件均保留。所有失败和未运行项目列在分母中；运行环境、费用或 Provider 限制以 `NOT_RUN` 表示。

人工/自动评分只读本协议、冻结 Gold、可信 Domain 和脱敏 Trace。Outcome 需与证据完整性、版本、Task/Run/Request/Event 关联、控制安全及运行有界性联合评分。不得将 Gold 标签送入产品提示，不得只以 `business_outcome` 字符串评分。R/H 与 A 的用户体验、安全合格率和动态效用分别报告；不要求 A 的结果优于 R/H。

## 历史隔离

旧 `docs/evidence/vnext/m2-02/RESULTS.json`、原始日志和浏览器 Trace 均为历史不可变观察。HF Release 的结果、错误、修复补充、截图与原始日志全部存放于 `docs/evidence/vnext/m2-02-hf-01/` 子目录中；不得把补充试次回写旧矩阵。
