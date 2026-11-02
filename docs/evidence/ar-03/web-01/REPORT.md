# AR-03-WEB-01 安全发布报告

## 用户可见结果

- **新的确定性浏览器流程：** SUPPORT 选择已授权的回调资料项目与测试订单，一次提交冻结问题。页面展示协议 v1/v2 对比、HTTP 202 已受理、同一事件 Receiver 仍为 QUEUED、部署版本未知，以及“草稿未提交”。刷新后问题、答复、来源保持关联；没有额外 POST。
- **历史真实模型结果回放 A：** 历史 DeepSeek Run 与原用户消息/答复关联正确，但业务 Evidence 已失效。页面显示来源失效提示，不把旧内容当作当前事实。这是安全的 PARTIAL 回放，不是新模型成功。
- **历史结果回放 B：** 原 `PROGRAM_LIMIT` 明确显示为程序限制，未伪装成模型答复。
- **撤权验证：** 在一次性测试 DB 副本撤销 Scope 后，受保护答复被隐藏；来源端点在刷新前后均返回 403 `S3_SCOPE_DENIED`。

脱敏截图只保留能核对页面信息层次的部分。事件/订单标识和内部状态码已遮挡，相关业务事实及答案关系由脱敏 Trace 摘要支持。完整截图和原始日志保留在本地（原始候选提交或本地未跟踪日志），不进入公开分支。

## 源码修复

`frontend/src/App.vue` 的 Session 初始读取之前把 `sessionHistoryReady` 绑在 Inspector 刷新结果上。设置 Task 又触发并行 Inspector 请求；较晚的失败结果会让已通过授权校验的消息一直无法进入对话投影。现在消息接口返回已受信且完成来源清洗后即可显示；会话身份和现有响应代次仍过滤迟到旧响应。没有修改 Domain、权限、Task 状态、来源当前性或业务写入。

安全发布版本还把测试口令改为运行时 `AR03_WEB_LOCAL_PASSWORD`，并从 fixture server 输出中移除本机数据库绝对路径与完整 fixture 结构。代码修改未增加业务能力。

## 验证等级

- 原始候选真实 Edge 浏览器：已有记录；没有在本任务重跑。
- 原始候选正式 API/Worker/MCP/Domain：已由原候选日志和审计记录支持；安全副本未伪称重新执行。
- 原始候选选定回归：21 项通过；全量 pytest 未运行。
- 安全发布分支新鲜检查：Node/Python 语法检查通过；`npm run build` 通过。
- 本轮新增真实 Provider 请求：0；业务写入：0。
- 在线远端：`UNVERIFIED`，GitHub:443 在执行环境不可达。

## 限制

- 没有重新运行浏览器，也没有新的真实模型调用。
- Scenario A 历史回答的正文因原业务来源过期，当前 UI 按安全规则隐藏正文。
- 全量 pytest、跨租户浏览器旅程未运行。
- 安全发布只纳入审核后的前端修复、脱敏验收摘要/截图和两个安全化测试入口；原始失败、完整 API/DB JSON、原始日志和原图不公开。

## 主 Agent 复核摘要

1. **用户变化：** 历史合法答复不再因并行 Inspector 时序卡在未关联视图；能查看刷新后仍稳定的安全消息。
2. **Agent 决策：** 本任务不改变 Agent 决策；真实模型结果仅历史回放。新端到端流程由 FixtureModel 驱动。
3. **观察驱动：** 当前 Fixture Observation 区分 HTTP 202 ACKNOWLEDGED 与同 Event Receiver QUEUED；本任务不新增自主性。
4. **新增约束：** 没有新增业务硬限制；现有消息授权/来源过滤保持不变，合法同 Task 消息仍展示。
5. **简化结果：** 移除 `sessionHistoryReady` 对 Inspector boolean 的依赖，复用 `/messages` 现有清洗和响应 fence。
6. **证据与停止线：** 原候选 21 项选定 pytest和真实浏览器日志；安全分支新鲜 build/syntax 通过；没有浏览器重跑或 Provider 请求。候选交主 Agent审查。

状态：`ACCEPTANCE_CANDIDATE`。不合并 main，不进入下一阶段。
