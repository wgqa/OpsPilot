# vNext M1-01 身份与访问矩阵

| 操作 | SUPPORT Task owner | 同租户其他 SUPPORT | 同租户 APPROVER | Executor service | 其他 tenant |
|---|---:|---:|---:|---:|---:|
| 创建 Session / 提交 Task Message | 允许 | 拒绝 | 只允许未绑定 Task 的只读 session，不可向该 Task 发命令 | 拒绝 | 拒绝 |
| 关键纠错 / Task abort | 允许 | 拒绝 | 拒绝 | 拒绝 | 拒绝 |
| 消费纠错 / claim owner Run | 允许 | 拒绝 | 拒绝 | 拒绝 | 拒绝 |
| Plan approval | 不可审批自己的 Plan | 不可因同租户关系代替 owner | 按既有 D3 scope 审批；旧审批回放仅为历史读取 | 拒绝 | 拒绝 |
| REPAIR / DELIVER | 不直接写入 | 不直接写入 | 不直接写入 | 只按持久 Intent、独立授权和 Domain 最终守卫提交 | 拒绝 |
| 读取自己的 Run / Task 状态 | 允许 | 拒绝 | 按既有批准的只读 scope | 按既有 executor scope | 拒绝 |

所有输入身份在 Domain 中重新核验 tenant/role/owner；`TrustedIdentity` 不是外部 token。当前身份来自本地预置信任表，是演示范围，不是生产认证系统。浏览器认证、CSRF、HTTP session 和多租户 IAM 还没有实现。

abort/correction 的权限只授给当前 Task 的可信 SUPPORT owner。`APPROVER` 不能借审核角色终止 Task；聊天内容和模型输出也不能自授审批或写权限。
