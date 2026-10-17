# 限制与实际偏差（由真实审查决定接受）

不修改冻结合同，不用措辞替代验证。D1–D5 已有主 Agent 的阶段审查；下面未新增“第三方已接受”的结论。D7 交付后主 Agent、独立第三方和用户分别决定是否接受当前边界。

| 原定基线 | 已实现差异 | 是否有证据证明差异合理 |
|---|---|---|
| D7 干净目录按锁文件可复现；Skill SHA-256 完整性保持 | 初始 Windows autocrlf 导出将 SKILL.md 转成 CRLF，E01 在模型调用前 FAIL、pytest 61/64；a2517fd 只把该文件 Git 属性固定 LF | **有定向证据**：D7 原始 TRACE/失败日志、零动作投影、新 venv 第二次 E01 13/13 和 64/64。安全校验未放宽，属于复现阻断的最小修正，待 D7 验收。 |
| E10 跨任务实验必须公开失败 | D6 首次 D5 smoke 失败，隔离重跑通过，场景族保持 PARTIAL；旧嵌套 stdout/stderr 缺失，更深根因不完整 | **只证明失败和证据缺口，不证明根因已解决**。D6 ATTEMPT-01、原始 run、Domain 投影保留；D7 不改 Gold/分母，不借新 E01 覆盖 E10。 |
| 来源可靠的事件经验辅助新任务 | 生命周期、人工确认、真实 Prompt 注入与撤销恢复已做，但 `MEMORY_SUMMARY` 是固定通用 401 方法，与 Skill 重叠 | **有生命周期/不扩权证据，没有独特经验提取或收益证据**。D6 REAL-TRAJECTORIES 与 D7 控制回归可核查。差异由主 Agent/用户明确接受或标限制，D7 不建设记忆平台。 |
| D6 探索性 Memory ON/OFF | 公平对照未执行，NOT_RUN | **无收益证据**；不宣称统计或效率改善。冻结计划允许探索性消融延期，是否接受由主 Agent 决定。 |
| E07 工具注入控制 / 类型应真实 | 初始 CASES 把 E07 错标 MODEL_PLUS_CONTROL，后改 CONTROL；实际是真 MCP+确定性 Gate，未调用模型 | **有源码与原始分类版本**：冻结 commit 151a1cea，当前 CASES classification_amendments；Gold/断言不变。不能称模型抗注入 benchmark。 |
| 动作结果未知时回查持久回执，不确定就等待人工 | 有回执恢复相同 action/Ledger；无回执的终态返回 ACTION_OUTCOME_UNKNOWN，需人工对账 | **有真实 crash/replay 和 unknown 控制测试**，并非全故障自动恢复承诺。D7 WORKERS/RECOVERY_SUMMARY、D4 terminal_checkpoint_without_domain_receipt。 |
| SQLite Demo Domain 中事务 CAS、Intent/Ledger 和交付去重 | 仅同机同库内原子性；没有把远端配置系统和工单 API 放进事务，也没有分布式 exactly-once | **符合冻结 P0 本地边界**；D7 展示实际 SQLite/loopback HTTP，未证明生产系统语义。生产远端适配尚未实现。 |
| 两个本地可信作用域与角色即可展示权限边界 | CLI 可选择预置身份名，缺公网身份认证、密钥管理系统、真实企业委派 | **符合冻结边界但不能推广为生产 IAM**。源码 trusted_operators/executor_services、scope 回归；用户必须理解本地进程属于信任根。 |
| C1 默认 MODEL≤8、MCP attempt≤6；单调用和活跃调查阶段时限分别计算 | 持久次数预算、MODEL 30s/MCP 12s 超时已做；没有独立的活跃阶段总 wall-clock 截止校验；审批恢复不沿用旧调查时间淘汰 | **次数/单调用有源码与测试；总时限没有已实现证据**。这是明确剩余差异，交审查决定是否阻断，不以 D7 文档宣告完全符合；不据此扩大 Runtime。 |
| 无执行授权时不修改业务；负例正确转交 | NO_ACTION/INCONCLUSIVE 生成本地报告和状态，不接真实客服外发/通知系统 | **有零受限写入和本地报告证据**；只能称“输出转交结论”，不能宣称已通知真人或真实外部工单系统已处理。 |
| 同一 Plan 批准，REPAIR 与 DELIVER 独立授权消费 | 一次可信 Plan 批准生成两条许可；没有要求每种动作再次弹出审批 | **符合 F3**；源码 submit_plan_approval 和两个 action_permissions/Ledger 的实际业务表投影，不把“独立授权记录”夸为两次人工审批。 |
| Memory 来源为可信成功经历；恢复与工单状态分开 | 来源校验 REPAIR、在线 RECOVERED、冻结报告和 Evidence，不把 DELIVER 作为来源硬前提 | **已公开契约解释**：基线允许 RECOVERED+DELIVERY_PENDING；D6 E10 的 Task A 实际完整交付。是否已完整结案必须另查 DeliveryRecord，来源准入不能作为工单证明。 |
| 模型通过只读工具自主选择查询 | 单一已验证模型端点；模型可能提出多个并行调用，程序只发送第一个并将其余标未发送；D7 有真实越界参数工具错误后补查 | **真实 Trace 支持有界处理，不证明跨模型泛化**。D7 7 model/6 MCP/1 scope TOOL_ERROR 全保留；次数预算不能隐瞒错误。 |
| D7 本轮应提供新鲜证明、历史材料可复用需标明 | 新鲜 E01 和全量/恢复；D7 没再做 E02/E03/E10 模型实验，明确引用 D6 SHA/UTC；源导出无 .git，原 helper git_head 为空、通用命令字符串不精确 | **有 PROVENANCE/SOURCE_HASHES/RUNS 的外部来源链**；原 TRACE 不改写。历史模型轨迹不计入 D7 Provider/Token 分母。 |

未实现的 Multi-Agent、向量检索、第二 Skill/Memory 类型、Redis、前端、生产 IAM 和通用平台均属范围外 P1，不是 D7 待补功能。当前未观察到越权写入、重复副作用、越权读取或伪造成功回执；有限测试不能替代第三方审计。
