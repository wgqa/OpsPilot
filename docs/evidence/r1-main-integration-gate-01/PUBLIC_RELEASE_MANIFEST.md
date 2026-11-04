# R1 候选公开发布清单

审查对象：`main@ec8c3582f6d145eec9979c43607302731411ead8` → `codex/r1-integration-web-journey-01@91a067aa083c2d4446d88a09d84164ea4c3bb956`。

## 文件盘点

| 类别 | 数量/位置 | 检查方式与结论 |
|---|---|---|
| 实现文件 | 18 个 `opspilot` 模块、6 个前端文件、2 个项目 Skill 文件及其他实验/Knowledge/配置文件 | 核对 Assistant/Worker、MCP、Domain 授权、Context、UI 投影；未见本轮新增业务写权限。 |
| 测试 | 42 个测试文件 | pytest 收集 675 项；完整结果与遗留失败见 `REPORT.md`、`FAILURES.md`。 |
| 证据文档、日志、Trace 与机器结果 | 974 个 `docs/evidence` 文件 | 扫描候选完整 Git blob 集；常见 API Key、Token、私钥、凭据和邮箱模式未发现可确认真实凭据。历史日志空白告警保留。 |
| 浏览器截图 | `docs/evidence/ar-03/web-01/screenshots/` 下 3 张：`deterministic-full-flow-safe.png`、`program-limit-replay-safe.png`、`real-replay-a-invalidated-safe.png` | 人工查看；截图包含遮盖带，没有可见凭据或业务标识。它们是历史截图，不是本轮浏览器运行。 |
| 历史归档压缩包 | `docs/evidence/ar-02/real-journey/runs/` 下 9 个 `.zip`（`formal-worker-trace-01/02/03`、`frozen-red`、`green-scope-01/02/03`、`regression-01/02`） | 均可读取，记录为小型历史测试日志包；没有把其内容当作本轮复跑。 |
| 其他资产 | 构建清单、README/TASKS、JSON/YAML、固定夹具和 Skill | 作为源码/文档依赖审查；没有发现需要运行或授权的外部业务动作。 |

## 拟公开的本轮新增文件

`docs/evidence/r1-main-integration-gate-01/` 下仅含：

- `REPORT.md`、`RESULTS.json`、`FAILURES.md`、本清单；
- `runs/` 下的测试摘要日志、退出码和脱敏完整 stdout。Windows 工作目录前缀已替换为占位符；原始本机日志留在私有本地 evidence 目录，不进入候选 Git。
- `TASKS.md` 中的当前路线索引，只记本任务卡要求与未合并状态，不声称历史路线共识已经入库。

本轮没有生成新的屏幕截图、Provider Trace 或业务数据。

## 早期资产评估（后续复核已更新）

以下三个完整 SQLite 数据库属于私有授权/账本执行状态，尽管未找到 API Key，仍不符合公开发布合同：

1. `docs/evidence/ar-02/conn-02/runs/authorization.sqlite3`（28,672 bytes）
2. `docs/evidence/ar-02/live-connection-diag-02/runs/authorization.sqlite3`（28,672 bytes）
3. `docs/evidence/ar-02/live-connection-diag-03/runs/authorization.sqlite3`（28,672 bytes）

这段是早期评估；2026-11-04 的只读结构与凭据复核已确认这些是模拟/历史测试资产，未发现真实凭据或客户数据。该项不再单独阻止发布或合并。


## 2026-11-04 资产复核更新

本节更新早期清单中授权 SQLite 阻断公开发布的评估，不改写原历史提交或扫描记录。三个数据库只读打开均为 quick_check=ok，仅含授权/attempt 表；未发现 API Key、Bearer Token、私钥、邮箱或客户/订单实体。宽泛数字模式仅命中模拟实验授权 ID 和 ISO 时间戳。此前 1,027 个 Git blob 扫描结论仍为未发现可确认真实凭据。

按当前任务提供的数据分类，这些文件是模拟/历史测试资产，不单独阻止公开发布或 main 合并。后续新建运行态数据库是否加入版本控制属于维护建议。本轮没有清理或改写历史。
