# 本轮真实失败与未验证项

## F01：ON J4 虚构本 Run 重读事实

- J4 Run：`run-4d91bb7f-ac99-4ed8-bd00-8987e8745c34`。
- 实际 Provider=1、MCP=0、当前 Run Observation=0。
- 真实输入将 J2 来源标为 `HISTORICAL_LEAD_NOT_CURRENT_OBSERVATION`，含 J2 Run ID。
- 真实输出却写“可以相信（本 Run 内、有来源的）”“上面列的第 1 条事实我在本轮已重新读取确认过”。
- 归类：回答正确性/证据当前性错误；G7 FAIL、G8 PARTIAL。没有发现新的 Domain Observation、Diagnosis 或业务写入。模型仍承认下游最终完成未知，但这不能抵消虚构重读。
- OFF J4 同样没有新 MCP，却明确说旧快照不能当当前事实，作为相反样例保留。
- 不在本轮修复、重跑或加硬性调查流程。

## 其他真实局限

- ON 选择了授权的 `callback-ack-contract` v1.0.0，而 TaskBinding 合同版本为 2。引用来源真实，但适用性没有完全核实；它在 J4 承认文档/配置版本不能证明线上部署。不能把这个选择包装成 Memory 带来的质量提升。
- 两组均未加载可选 Skill，无法评价 Skill 的实际效果；这不是可选使用 Gold 的失败。
- 两组 J4 都选择直接解释并提出后续复查，而没有主动重新取证。OFF 的明确缺口符合冻结允许结果；不能将其统计为完成了一次新当前状态核查。
- 请求中 `parallel_tool_calls=false`，但 Provider 的工具响应包含多项提议（OFF 首次五项、ON 首次四项）。所有提议均为已暴露合法工具，持久计数正常；记录真实行为，不假定该参数保证响应只含一项，也不据此新增次数 Gate。
- 单个顺序固定的 OFF/ON 样本，无法隔离随机性、时间及身份差异，不能作统计或架构优势结论。

## 免费准备与审计记录

- 启动前显式 MockTransport 预检通过；真实 Provider=0，真实 claim 尚未创建。没有重跑 prelive 全套测试。
- 真实运行约 40.52 秒，退出码 0；8 次 HTTP 200，所有 Usage KNOWN，无超时、UNKNOWN、费用停止或 Provider 重试。
- 首次只读收尾脚本误用了不存在的 Memory 表名；这发生在真实 Campaign 结束后，没有启动 Worker/Provider，也没有改数据库。保留私有 `audit.log`，改用实际 `d5_memories` 后完成审计。
- 初始私有通用表提取没有展开实际 `d2_tool_observations`；补充只读审计通过 `attempt_run_id` 关联得到八条当前业务 Observation。原始私有文件未覆盖，补充证据保存在公开 `SOURCE_OBSERVATIONS.json`。

## 未运行

浏览器、额外付费探针、重跑样本、PROCESSED 扰动、撤权/UNKNOWN 的真实故障注入及全量 pytest 均未运行。既有 17 项 prelive 回归属于历史独立验收范围，本轮没有冒称亲自重跑。旧实验、失败、UNKNOWN 预留和冻结 Gold 保持原记录。
