# Stage B 集中收口：冻结验收计划

状态：`FROZEN_BEFORE_RED`。本计划细化用户于 2026-10-27 授权的 Stage B 集中收口任务，不修改既有 CONT-UX Gold。当前任务卡明确允许 Inspector 读取响应增加受信 `task_id`，该授权在此处优先于早期计划中只允许扩充 Message 读取字段的限制。

## 基线与边界

- Repo `wgqa/OpsPilot`；基线及 fetch 后 `origin/main`：`e0ecb9463dcce8e1390a30f812d5f8b42cea9f4a`；复用的独立 worktree 为 detached HEAD，跟踪文件无改动。主工作区 `D:/学习/agent新项目` 有未提交资料，不修改或清理。
- 总纲 Blob `1f737712c7a36ceb34433ac09c3fbba3c3305542`；AGENTS `32c45506cceeaa8c76a5c56bf8360ff476b58856`；Skill `d405c8d413d633824b279202cc1503dab4cf0b03`；Gold `1290ef276690f00b6e9683f0251302f376a70098`。
- Stage B 计划 `3cba9bb63b42ce5f02042709058ce9dcd496623c`；Supplement 01/02 计划 `c6482d72e8c1f4344abee40c540810966e4f1b94` / `859ec7fc1d617b9c8592b7010b7bfe1afb010f4b`。M2-01/02 延期门禁继续有效。
- 不修改业务 Gate、预算、TaskControl、Agent Loop、业务写入和历史证据。禁止 Computer Use、替代浏览器自动化与付费 Provider；浏览器验收为 `NOT_RUN / BLOCKED_BY_TOOL_ENVIRONMENT`。

## RED 与 GREEN 判据

| 编号 | 必须保留的真实或确定性输入 | 正向结果 | 反向结果 |
|---|---|---|---|
| CLOSE-01 | 持久 S3 Task、初始调查答复、C1 Follow-up；经本地测试服务 HTTP 读取 Inspector 与同 Session `/messages` 原始 JSON，直接送入生产 `projectConversation()` | 两个答复与其受信 Run 分别归到原问题；Inspector Run 的 `task_id` 来自 Domain | 不同 Task、错误 Run/source、缺失 Run/来源不挂到其他问题；Scope 撤销后真实 API 与投影不暴露受限答复/Receipt/Evidence |
| CLOSE-02 | 正式纠错问题、确认 Assessment、已应用的纠错 Message、关联新 Run、最终持久 Answer 和带相同 `report_ref`/Run 的诊断 | `RUNNING`、`ANSWERED`、`PARTIAL` 和适用流式/补查结果归到原纠错问题；持久来源 ID 不改 | 未确认、取消、过期、未应用、错 Task/Run/source 不能重映射；无效、错 Run 或错 Receipt 的 Diagnosis 不能冒充新答案的当前诊断 |
| CLOSE-03 | 受控 Promise：SSE 并行启动 Message 与 Inspector 刷新，Inspector 先完成 | 授权始终有效时，稍后返回的新消息仍被接纳；重授权后安排可见的新鲜消息读取 | 先前授权读取在新失权快照被接纳后不得复活；同 Task 最新请求和其他 Task 隔离继续成立 |
| CLOSE-04 | 现有用户问题投影及真实失败、PARTIAL、额度耗尽和纠错状态 | 主体正文自然说明进展、结论与未知；内部身份和来源在可展开工程详情内 | 不把程序限制说明标成模型答复，不隐藏失败或未完成 |

## 执行与证据

先提交本冻结计划，再添加上述测试并在任何业务实现改动前运行，保存三个缺陷的独立 RED 与真实 API 响应。实现后新鲜运行 GREEN、11 项既有前端投影测试、相关 API/S3 Scope/C1 Follow-up/TaskControl/SSE 安全回归，以及 TypeScript、生产构建和改动文件 ESLint。报告每条命令、退出码和失败；真实 API JSON/投影是本地测试服务证据，不冒充真实浏览器或 Provider。

完成获准非浏览器工作后提交 `INTERMEDIATE_IMPLEMENTATION`，停止等待主 Agent 审核；真实 Web/DOM/刷新/SSE 验收仍是阶段 B 后续出口。
