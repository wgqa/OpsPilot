# vNext M1-01 身份与访问矩阵

| 操作 | SUPPORT Task owner | 同租户其他 SUPPORT | 同租户 APPROVER | Executor service | 其他 tenant |
|---|---:|---:|---:|---:|---:|
| 创建 Session / 提交 Task Message | 允许 | 拒绝 | 只允许未绑定 Task 的只读 session，不可向该 Task 发命令 | 拒绝 | 拒绝 |
| 关键纠错 / Task abort | 允许 | 拒绝 | 拒绝 | 拒绝 | 拒绝 |
| 消费纠错 / claim owner Run | 允许 | 拒绝 | 拒绝 | 拒绝 | 拒绝 |
| Plan approval | 不可审批自己的 Plan | 不可因同租户关系代替 owner | 按既有 D3 scope 审批；旧审批回放仅为历史读取 | 拒绝 | 拒绝 |
| REPAIR / DELIVER | 不直接写入 | 不直接写入 | 不直接写入 | 只按持久 Intent、独立授权和 Domain 最终守卫提交 | 拒绝 |
| 读取自己的 Run / Task 状态 | 允许 | 拒绝 | 按既有批准的只读 scope | 按既有 executor scope | 拒绝 |

所有输入身份在 Domain 中重新核验 tenant/role/owner；`TrustedIdentity` 不是外部 token。当前身份来自本地预置信任表，是演示范围，不是生产认证系统。浏览器认证、CSRF 与 HTTP session 在 M1-02 新增，仍不构成生产 IAM。

abort/correction 的权限只授给当前 Task 的可信 SUPPORT owner。`APPROVER` 不能借审核角色终止 Task；聊天内容和模型输出也不能自授审批或写权限。

## M1-02 Web 入口补充矩阵

| HTTP 操作 | 未登录 | SUPPORT owner | 其他 SUPPORT / tenant | 同租户 APPROVER |
|---|---:|---:|---:|---:|
| 登录 | 凭已配置的本地角色密码可建立会话；仅凭 actor_id 不可登录 | 受信 registry 决定 tenant/role | 不可指定其他身份 | 与 SUPPORT 分开登录 |
| 读 Session/Message/Event | 401 | 只读本人 Session | 404，不泄露对象是否存在 | 本卡无独立审批 Session 读取权 |
| 读 Task/Run/Plan 摘要 | 401 | 只读本人 Task | 404 | 仅同租户且 Task/Plan 正处于授权待审批状态时可读 |
| 创建 Task/Message、纠错、abort | 401 | 通过 CSRF + Origin 后由 Domain 校验权限 | 404 或 Domain 拒绝 | 403；不得 abort 或提交纠错 |
| SSE | 401 | 仅本人 Session 的持久事件 | 404 | 无额外通道权限 |

会话 Cookie 为随机 bearer 值且仅以 SHA-256 摘要持久化；使用 HttpOnly、SameSite=Strict、过期和撤销。当前本地 HTTP 下 Secure=false；HTTPS 部署会启用 Secure。写操作校验固定 Origin 和 CSRF digest。`X-Actor-ID`、`X-Tenant-ID`、`X-Executor-ID` 等 Header 不参与身份解析；extra JSON 身份字段拒绝。该本地 Demo 不是生产 IAM。
