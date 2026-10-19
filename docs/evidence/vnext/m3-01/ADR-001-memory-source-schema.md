# ADR-001：M3-01 S1/S2 案例来源与 D5 Schema

状态：冻结，待实现与测试验证
基线：SQLite user_version=8，现有 d5_memories 和 d5_memory_events

## 决策

采用方案 A：在原 D5 注册表内进行无损 v8→v9 迁移；不建立平行 Memory 注册表或独立审批/撤销生命周期。

最小数据形状包括：nullable 的旧 S1 专用 source_report_ref/source_verification_id、source_outcome、schema_version、source_refs_json、experience_json 和 content_digest。保留 memory_id、tenant/project、problem_type、source_task_id、source_evidence_ids、state、version、审批/撤销字段、expires_at、原唯一约束、索引及 d5_memory_events 对 d5_memories 的 FK。迁移给历史行标明 legacy schema，不伪装为新抽取案例。

## 取舍

方案 B（另增 case provenance 表）仍无法在原 d5_memories 的 NOT NULL S1 列中无失真表示 S2，且会形成双注册表、状态同步和检索绕行；若再增平行 Candidate/Event/API，将重建生命周期。方案 A 只重建一张父表，迁移风险通过临时 v8 数据库、row/event 计数、FK check、重复 initialize 和完整旧 D5 回归验证。

迁移在一个 Domain SQLite schema transaction 中完成：保留原表快照计数；建 v9 表并复制原值；切换表名；校验行数、每个 event 的 FK 与 schema version；最后设 user_version=9。任何异常回滚，原 v8 可重试。不得修改仓库或用户本地真实运行 DB；测试均使用临时文件。

## 失败与回滚

若外键完整性、历史行兼容、并发初始化或 Candidate/API 兼容任一测试失败，不允许继续接入 S2 Memory。修复范围限于迁移。已有 v9 中已写的 S2 Candidate 在回滚前需保留 DB 备份；本阶段尚无生产迁移/外部数据承诺。
