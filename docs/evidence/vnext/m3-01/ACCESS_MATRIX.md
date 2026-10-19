# M3-01 权限矩阵（冻结版）

所有 actor/tenant/role 来自已认证 Web Session 和 Domain trusted_operators。任何请求体里的 actor、tenant、role、project、source outcome 或 receipt refs 都不是身份/来源权威。写路由走既有认证、Origin、CSRF、严格 body 校验和 Domain 复核；每个写请求都要求 Idempotency-Key，重复同请求回放，键复用但目标/摘要不同则冲突。

| 主体 | 自有 Task 来源预览/提候选 | 候选/经验管理列表 | 确认 | 撤销 | Task B 检索 |
|---|---:|---:|---:|---:|---:|
| 当前可信 SUPPORT Task owner | 允许 | 仅自有来源与当前可读 Task | 禁止 | 禁止 | 只限可信 tenant+project+service+problem type |
| 同租户 APPROVER | 按 reader 策略；不得读取源 Task 私密正文 | 允许列出同租户 Memory 摘要与来源引用 | 允许，Domain 重验来源 | 仅 ACTIVE 可撤销，Domain 重验 | 不以 approver 身份扩大 Task 读取 |
| 同租户非 owner SUPPORT | 禁止来源详情/候选创建 | 禁止枚举 | 禁止 | 禁止 | 禁止访问他人 Task |
| 跨租户用户 | 禁止且不泄露资源存在性 | 禁止 | 禁止 | 禁止 | 返回空/统一拒绝，不泄漏 |
| 模型、用户聊天文本 | 可提出意图 | 禁止 | 禁止 | 禁止 | 只能提供非权威方法提示 |

APPROVER 为当前本地可信租户角色，不代表生产级项目 IAM。项目和服务适用性由 TaskBinding 和 Domain 检查；跨项目 Memory 不进入目标上下文。ACTIVE 前绝不可检索；撤销后后续模型出站、恢复和新 Chat 不得使用该资产或依赖它的历史助手回答。

禁止的副作用：配置、Scope/Grant/Policy、工单、ActionIntent/Permission/Ledger、Plan/Approval 或 Task 业务状态变化。M3-01 的写入仅限 Memory 候选/生命周期审计与既有命令幂等记录。
