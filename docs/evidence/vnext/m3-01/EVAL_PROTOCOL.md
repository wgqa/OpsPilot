# M3-01 真实 Memory ON/OFF 评测协议（冻结版）

## 试次和唯一变量

Gold 固定为 8 个 Task B pair、16 个计划试次。每 pair 包含同一运行策略、同一 DeepSeek deepseek-flash、相同模型 Prompt 主版本/工具 Schema、Skill、Knowledge、身份/权限、Task B 初始 Domain 状态和预算的 ON/OFF 两臂。允许 tool sequence 由真实模型动态选择；不能人为固定其中一臂的工具答案。

每个 pair 的 ON 与 OFF 从同一个 source snapshot 复制到两个隔离的 Domain SQLite 文件，再各自创建不同的新 Task B。每个目标 Task B ID 均不同于源 Task A ID。Memory OFF 只关闭经验提示，不删除 Memory 行，不改变查询工具、权限、证据、Skill、Knowledge、系统规则、模型或当前 Domain 状态。

目标 B 的 Provider Context 不包含来源 A 的用户消息、助手回答、Gold/期望标签或来源 Task 的当前状态。只有经批准、脱敏、结构化且来源可复核的 Memory 方法提示可以跨 Task 使用；来源 A 的原始内容只留在审计 DB，不作为 B 的对话历史注入。

试次顺序按 pair 交替 ON/OFF（先后顺序写入 TRACE）；真实 Provider 的随机性、延迟、限流和失败不重跑覆盖，任何补跑都增加实际试次并保留原始记录。

## 预算与测量

- 模型：DeepSeek Provider、deepseek-flash。对真实 Request/Response 保存脱敏 ID、Prompt digest、ContextManifest、Provider usage；不保存 API key。
- 工具：真实本地 MCP stdio Server/Client 与其固定 TaskBinding；保存 tools/list、tools/call、调用次序、request_id、observation/evidence IDs、时延和错误。
- HTTP：对实际 Demo API 记录状态、业务路由与脱敏业务字段；禁止记录凭证或 Authorization。
- 单试次硬预算：最多 8 model requests、6 MCP call attempts；重试照计，耗尽时按安全停止/失败记录。
- Token 记录 Provider 实际 usage；本地估算单列。Provider 若不返回价格，不以未经冻结的价格表回填，费用字段为 NOT_REPORTED。
- 真实 Web 旅程单独报告，不计入 16 次 Gold 分母。

## 评分

按 RUBRIC.json 逐试次评分：来源有效性、Memory 是否被正确选入/排除、当前事实处理、实际调查选择、可信业务 Outcome、安全、使用量与失败。Gate 与 Domain Receipt 决定业务判分；Provider 文字和“我使用了 Memory”的自述不能定分。

必须提供至少一条 Source A→Task B 正向完整 Trace、一条“历史经验与当前事实冲突”反例，以及撤销前后 Trace。撤销后另做恢复/重启后新 Provider attempt 检查。

仅当 Memory 对实际合法工具选择产生可追踪影响且无安全/正确性退化时，把样本内结果标为 UTILITY_PROVEN。ON 无提升或更差照实列出；不可声称因果或统计显著，不允许为追求提升调整 Gold、提示答案或预算。

## 快照、脱敏与失败

每个 snapshot 记录文件 hash、schema version、来源 Task ID 和目标 Task ID。Gold 标签与期望结果只供运行器外的评分步骤读取，绝不序列化进 Provider Context、MCP 参数或 source Memory。

原始 stdout/stderr、Provider/MCP/HTTP 脱敏轨迹、浏览器网络日志、pytest/build/lint 日志和所有失败均 append-only 保存在 runs/。纠错仅新增 run 目录及失败说明，不覆盖 RED 或旧 M2 证据。
