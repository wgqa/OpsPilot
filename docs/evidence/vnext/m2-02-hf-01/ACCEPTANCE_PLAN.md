# M2-02-HF-01 冻结验收标准

状态：冻结标准（实施前）  
冻结日期：2026-10-19  
基线：`main@f75eb8b4ee209c0578395543f5a6f679504b2edc`  
历史评测：`docs/evidence/vnext/m2-02/RESULTS.json`，48 条、45 PASS / 1 FAIL / 2 PARTIAL；本目录不得覆盖或重算该结果。

本标准覆盖 HF-A 至 HF-D，供独立 RED、修复后 GREEN 和新 HF Release 对照评测使用。冻结标准提交必须先于任何新增验收测试运行和源码修改。新增 Gold 是对旧 G1-G8 的补充，不修改旧 Gold、Rubric、48 条观察、失败记录或旧 Release。

## 冻结门槛

| ID | 工作包 | 必须观察的事实 | 通过条件 |
|---|---|---|---|
| HF01-01 | 文档与历史完整性 | 起点、旧 Release、旧 48 条结果及失败索引 | 旧报告仍为 45/48；其文件哈希前后相同；新增证据只写本目录 |
| HF01-02 | HF-A 意图与范围 | G6 原例、同义表达、否定/引用/混合目标、同租户未绑定资源 | 越界目标不产生越域读取、无关 Receipt/Draft 或 Scope 写入；否定/引用不得误杀；混合或不确定意图澄清或只推进明确绑定子任务；无敏感资源存在性泄漏 |
| HF01-03 | HF-B 有界调查 | stale / 错误 request、无工具、no-op、预算耗尽、冲突、崩溃恢复 | NEED_MORE 只在存在合法可执行的增量动作时继续；否则持久终止为 WAITING_INPUT/INCONCLUSIVE。每 Run Gate 记录 ≤64，模型 ≤8、MCP ≤6，恢复不重置预算；无副作用 |
| HF01-04 | HF-C 浏览器闭环 | 真实登录、Task、纠错、新 Run、Provider/MCP、HTTP、SSE、Domain 回执与草稿、只读追问 | 同一浏览器会话同 Task：首次调查后接受正式 CORRECT_TASK_INPUT；旧产物失效；新 Run 使用新 request_id 并以对应 Probe + Authz 形成新 DIAGNOSED Receipt 和 HANDOFF_READY Draft；追问明确未修复、未提交且 CHAT_READONLY 不改业务状态 |
| HF01-05 | HF-C 安全负例 | 401、404、跨资源、错误 Request ID、stale/不匹配 Authz | 只允许正确安全停止；不得复活旧 Receipt/Draft、创建交接队列/回执、写 Scope 或宣称恢复 |
| HF01-06 | HF-D H 输入有效性 | H 归一化 schema、验证轨迹与策略消费字段 | 一个合法用户线索实际改变可观测的合法调查选择；同事实不同措辞维持相同可信结论；模型候选不成为 Evidence、授权或 Gate 输入 |
| HF01-07 | R/H/A 新 Release | 固定实现 SHA 上的 16 holdout × R/H/A = 48 个独立试次 | 分母固定 48；每次隔离 Domain/Checkpoint；共享同等输入、权限、工具、预算、Knowledge/Skill 和评分；逐试次包含 release_ref、完整 Trace、业务与安全证据、Token/时长（可得时）。不要求 A 胜过 R/H |
| HF01-08 | 历史回归 | 至少 154 项全量 pytest、M1/M1-HF-01/M2-01、S1 闭环、S2 定向、MCP stdio、前端构建 | 所有新鲜可运行回归通过；阻断项或外部环境限制明确记录，不得用历史日志代替 |
| HF01-09 | 安全红线 | Scope/Policy/Grant、Handoff、S1/只读业务状态 | 本轮 Scope/Grant/Policy 运行期写入、HandoffReceipt/Queue 写入、S2 `SCOPE_ESCALATED`、`REPAIRED_VERIFIED` 均为 0；不扩展受控写入口 |
| HF01-10 | 可复核证据 | 原始 RED、每次补充运行、GREEN、浏览器截图、日志、Release/依赖/哈希索引 | 失败原样保留并标明目的；无选择性隐藏；提交 SHA、命令、分子/分母、限制可独立核验 |

## 顺序与停止

1. 以单独提交冻结本目录中的验收标准。
2. 为 HF-A/B/D 编写测试并保留原版 RED；HF-B 另用隔离 Domain DB 与 Checkpoint 重现无进展循环并采集节点、Gate、预算和 Run 生命周期。
3. 仅做解决冻结 RED 所需的最小实现修改；逐项 GREEN，再执行新鲜回归。
4. 固定实现提交为唯一 `HF_RELEASE`，然后运行完整 48 个 R/H/A 试次；不得将开发诊断运行混入 Release 分母。
5. 用实际 Web 浏览器运行 HF-C。真实 Provider/MCP 或浏览器无法运行时如实记录 PARTIAL/NOT_RUN；不得以 CLI、伪造 SSE 或历史成功替代。
6. 满足门槛或确认阻断后，提交报告及证据、推送 main，并立即停止等待主 Agent 独立验收。

本轮不实施 M2-03、HandoffReceipt、Queue、自动 Scope 授权、Memory 平台、多 Agent、Gateway 或其他新业务能力。任何合同修改均须单独提出，不在本次自行裁决。
