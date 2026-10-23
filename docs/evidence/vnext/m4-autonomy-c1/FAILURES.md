# C1 冻结与 RED 失败记录

本文件保留预冻结 RED 的全部执行，不把夹具错误算作产品复现，也不抹去第一次失败。

| Run | 结果 | 说明 |
|---|---|---|
| `c1-red-01` | 有效 RED，exit 1 | 已创建绑定 S3 Task、即时真实业务 HTTP Probe、有效 DIAGNOSED Diagnosis，再发起协议补查。当前 classifier 将 `READONLY_FOLLOWUP` 拒为 `INVALID_MODEL_CLASSIFICATION`，HTTP 502。初次运行未输出 Trace。原始日志保存在 `runs/red/c1-red-01-pytest.log`。 |
| `c1-red-02` | 测试准备错误，exit 1 | 为 Trace 补充统计时假设 `s3_http_observations` 存在 `task_id` 列，SQLite 报 `no such column: task_id`。这是测试查询错误，不是产品行为；原始日志保存在 `runs/red/c1-red-02-pytest.log`。 |
| `c1-red-03` | 有效 RED，exit 1 | 将统计改为该隔离测试数据库内的总行数后重跑，复现同一 `INVALID_MODEL_CLASSIFICATION` / HTTP 502；已开始写入实际 ID Trace。 |
| `c1-red-04` | 有效 RED，exit 1 | 补齐 Diagnosis Gate/currentness、Task 状态、来源消息与 Run、动作表计数后再次复现。Trace 显示初始 Diagnosis 是 `CURRENT / DIAGNOSED / RECEIVER_PROCESSING_UNCONFIRMED`，控制版本 0、纠错数 0、无交接/动作副作用；补查没有 MCP/Provider 调用或自己的持久 Run。 |

全部有效 RED 都运行在冻结基线 `add47ec83f31fa76b9b6a5782e013311732bc496`。C1 没有业务实现修改。没有将 `c1-red-02` 的夹具错误纳入缺陷判断。

## 分类

- **产品失败：** 在支持的新只读补查意图进入当前分类/受理入口时返回 502；合法的同 Task 来源补查没有可用调查 Run，用户无法完成 C1-01。
- **安全失败：** 本 RED 未观察到；控制版本未变化，未创建正式纠错、审批、Plan、ActionIntent、Ledger、Queue 或 Receipt。
- **策略不足：** 本轮未测；分类被程序拒绝，模型策略没有实际运行。
- **业务能力不足：** C1 目标所需的只读 Run/Knowledge 来源结果链在当前基线不存在；本轮只定位，不实现。

没有证据表明模型“选择了不查”；Provider 与 MCP 在补查部分均为 0 次，故不应这样描述。
