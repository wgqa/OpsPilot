# M3-HF-02 最终补证报告

结论提交主 Agent 独立裁决：**A技术门禁PASS；B真实目标Summary DAG仍PARTIAL；C审计和学习材料完成但有明确限制**。原E2E-03的真实Provider Payload观测缺口已补齐，可提交 **PASS_CANDIDATE**；不自行签署M3总体验收，不因本轮单元GREEN改写旧CLOSEOUT PARTIAL。

## 1. 基线、提交和范围

开工实际main/远端均 `c2f71e9b4e3db9fdc3cd522115f304e6a53dfaae`，未建立分支/PR。本轮直接main，用户未提交AGENTS.md、PROJECT_NORTH_STAR.md、开发目录/及旧临时资料保护，不覆盖/暂存/删除。

| 阶段 | 已产生的独立提交 |
|---|---|
| A/B/C总范围先冻结 | `d10385ebaf1e9f646a8f4b5536f92a5258f74338` |
| 原B准确身份与固定输入 | `f747d9e3abf3e6bceb112293af29ccdaf2d8f541` |
| 两个Worker有限故障协议 | `013b4a673611c4d5d64b23d72c6a30fac1920404` |
| 两跳P1 RED协议 | `4ea16579c3e6d9b39ea6ecf14d41e5f2168abba6` |
| RED测试和原失败 | `ba44a5c36ab37ab000096e042e23c6b7f022b6b0` |
| 最小生产修复与定向GREEN | **`00d054aeba196b972255dafd0e7faa03fcd0ce41`** |
| 唯一修复后真实对照身份 | `73fc3a9fdd9d3edc4d082a3725641b3f4ab2421f` |
| 最终证据提交 | 以包含本报告的最终Git commit（`git rev-parse HEAD`）及最终交付消息中的SHA为准，避免在同一文件中写不可能的自引用SHA |

生产差异只有 `opspilot/domain/chat.py` +35/-0；新增回归 `tests/test_m3_hf02_lineage.py` +76/-0。没有Schema迁移、依赖升级、MCP新增、业务安全合同修改、Worker重构、Memory新类型或下一阶段开发。

本轮读取的用户任务卡原文归档 [TASK_CARD.md](TASK_CARD.md)。模型为现有真实 `deepseek-flash`，langchain-openai1.7.2/OpenAI3.33.0/httpx2 2.13.1，锁文件不变。启动源码hash、PID和参数见原始provider-observations/process-events。

## 2. A：实际Provider Payload与跨进程撤销

独立观测器挂在**原httpx2客户端序列化请求后、Transport send前**；无完整原始Prompt落Git，没有改变消息/Tool Schema/timeout/retry。先在尚无业务Task时用固定非敏感标记成功验证491 Token与Provider响应，再开展正式业务。

新鲜源Task A `task-3098a94b-a9d9-4e99-b54d-f54b9a474125` 通过独立APPROVER正常认证Web API批准原Plan，持久REPAIR/DELIVER Intent分别消费，真实配置v7→v8、同身份固定业务路由HTTP200与订单CONFIRMED、冻结报告及工单回执。E1来自该真实回执，经人审v2 ACTIVE。

不同目标Task B `task-c139d0d1-9e07-4055-9b95-10316384903a` 的真实MCP取当前v9/401，实际Investigator与Chat请求选用E1v2；逐字段核对来源、版本、digest、经验内容及HISTORICAL_METHOD_HINT_ONLY，不把来源200当当前事实。

APPROVER撤销E1为v3，新的Chat和正式关键纠错后的Investigator实际请求均不带旧Memory；Manifest排除依赖助手，与实际assistant正文集合一致。同Run `run-7258d97f-4f8c-458f-8163-8fb564bef838` 在5个Checkpoint、一次新MCP后杀隔离API进程，再从原库/Checkpoint恢复，实际两个PID的请求都排除旧经验，最终WAITING_APPROVAL；MODEL/MCP预算8/6未清零。14/14 A核对通过，原始快照保留该时间点零目标业务写入。

之后为B实验准备，目标B又经**新的独立审批**真实完成v9→v10；不能把A时间点“零目标动作”扩成整个实验从未修复Task B。新的前一目标Task D也在P1对照准备时获新审批完成v11→v12。三个来源案例整体为3次REPAIR、3次独立DELIVER、3份HTTP200验证/报告/交付。3次事故准备fixture（v8→v9、v10→v11、v12→v13）明确另列，**不算Agent自主恢复**。Scope运行期写入0，最终目标E无业务动作。

新真实对照启动的是修复后源码，仍正确排除早已撤销的E1/E2并只选E3当前v2；其撤销后Chat实际资产为空。因TTL混杂不宣称它单独证明两跳撤销因果。A无Summary，不能用A直接证明B的摘要链。

## 3. B：限定真实摘要实验，结果PARTIAL

原B和唯一一次修复后对照均预先提交准确身份、相同B_INPUTS与预算。HYBRID输入3600、预留512、余量1024、窗口16384，SDK0retry、每Run含摘要最多3次，最多8 ACTIVE +2撤销/重启；没有提高上限或第三次实验。

原B已证明真实Memory→助手；第7轮提交1份真实Summary并被后续真实请求选用，但只覆盖用户seq1/2，不含目标助手/Memory。下一次压缩实际源材料含目标助手/E2/父Summary，HTTP200后跨过当前Probe300秒TTL，提交抛TaskControlError，目标Summary未形成。

修复后对照的真实前6轮含E3并区分历史v11→v12/200与当前v13/401。准备过程耗时导致第1轮开始时Probe已约250秒；第7轮真实压缩也跨TTL，在来源再验证处失败，0份Summary。第9/10轮无旧资产，但TTL先失效、之后才撤销，不能隔离撤销因果。两个实验的Chat各10/10成功，**不算目标DAG成功**。

完整身份/时序/摘要版本、来源图与证明矩阵见 [SUMMARY_LINEAGE.md](SUMMARY_LINEAGE.md)。保留所有原失败和UNKNOWN，不延长TTL、改Gold或直接插Summary。本轮B目标仍**未证明**，遵守任务卡允许的有界停止。

## 4. C：审计发现与唯一最小修复

发现P1：当Token裁剪移除直接Memory块、却保留依赖Memory的历史回答时，派生回答只引用父MODEL_ATTEMPT。原函数只查模型成功/响应digest，不递归检查父助手来源，撤销后可能继续选用派生回答。

先独立冻结RED；RED01保留测试准备问题，修正fixture后的RED02两类资产（Episodic、Semantic）均复现真正断言失败。仅向原 `_message_source_valid()` 加35行祖先来源递归、tenant/session/task核验、cycle guard与单次局部cache，不改TaskControl、审批、事务或存储。GREEN26/26，完整227/227。

Worker历史两次耗尽仍缺原异常/堆栈。新鲜有限只读记录和两次合成故障注入说明当前分类与有界重试正常（2/2），不能证明原根因，保留 **ROOT_CAUSE_NOT_PROVEN**，未改生产Worker。零Attempt不排除Context/MCP初始化边界错误。

P2/P3未顺手修：否定表达Scope保守误拒、压缩提交失败后的响应/Usage缺口、TTL与准备耗时导致实验中断、本地估算差异、UI旧Investigator provenance与新Chat观察面不同、外部发送竞态及深DAG性能。逐项证据和限制见 [SOURCE_AUDIT.md](SOURCE_AUDIT.md)。

学习交付 [M3-REVIEW](../../../learning/M3-REVIEW/ARCHITECTURE.md) 五份文件：架构、实际函数调用阅读路线、设计取舍、真实失败、20组面试追问。区分Handbook参考、项目实现、单元验证、真实E2E与未证明；没有把Procedural概念当新增Memory实现。

## 5. 新鲜测试结果

| 类别 | 实际结果 | 原始证据 |
|---|---|---|
| 修复后全量pytest（含旧M1/M1-HF/M2/S1/S2安全回归） | **227/227，162.42秒，exit0** | runs/regression-02/pytest-full.log |
| Context/Memory定向，含新增2项 | **26/26，14.38秒，exit0** | runs/lineage-green-01.log |
| 修复前完整基线 | 225/225，163.79秒 | runs/regression-01/pytest-full.log |
| 修复前原定向 | 24/24，15.03秒 | runs/regression-01/pytest-focused.log |
| 独立两跳RED | RED02 **2/2失败**，非PASS | runs/lineage-red-02.log |
| frontend typecheck/build/lint | **3/3命令exit0** | runs/regression-02/frontend-*.log |
| 有限合成Worker注入 | **2/2通过**，0真实模型/MCP | runs/worker-audit-01/RESULTS.json |
| A直接来源/恢复证据核对 | 14/14 | runs/journey-01/A-VALIDATION.json |
| 全出站脱敏集合/来源与业务一致性核对 | 11/11，非独立模型样本 | RESULTS.json.safety_checks |
| 真实模型序列化请求 | 49次，48个HTTP200响应头，1次崩溃无返回 | provider-observations.jsonl / TRACE.json |
| 实际完整Provider Usage | 46/49，另外3项UNKNOWN | TRACE.json.requests |
| 真实MCP stdio tools/call | 18个Attempt /18个Observation | Domain白名单快照 |
| tools/list次数 | NOT_SEPARATELY_INSTRUMENTED | 不杜撰分母 |
| 浏览器 | 标记/源完成/恢复/长对话与最终同Session可见，6张真实截图 | runs/journey-01/screenshots/ |

真实浏览器和正常认证Web API渠道均记录。独立审批/确认/撤销走正常Web API授权/CSRF/幂等流程，不称人工浏览器点击。第一个B的部分Chat为浏览器输入，其余和修复后固定输入由API提交，浏览器展示真实持久结果。CLI/单测未冒充浏览器。

实际运行命令（PowerShell，仓库根目录；测试目录均在本仓库）：

```powershell
.\.venv\Scripts\python.exe -X utf8 -u docs/evidence/vnext/m3-hf-02/service_control.py
# 继续同一持久实验而不reset，仅用明确--resume：
.\.venv\Scripts\python.exe -X utf8 -u docs/evidence/vnext/m3-hf-02/service_control.py --resume
.\.venv\Scripts\python.exe -X utf8 -u docs/evidence/vnext/m3-hf-02/lineage_real_green.py
.\.venv\Scripts\python.exe -X utf8 docs/evidence/vnext/m3-hf-02/worker_fault_probe.py
.\.venv\Scripts\python.exe -X utf8 -m pytest -q tests/test_m3_hf02_lineage.py tests/test_m301_memory.py tests/test_m302_context.py tests/test_m303_semantic_memory.py --basetemp=.runtime/m3-hf-02/pytest-lineage-green-01
.\.venv\Scripts\python.exe -X utf8 -m pytest -q --basetemp=.runtime/m3-hf-02/pytest-full-02
```

前端在frontend/执行 `npm run typecheck`、`npm run build`、`npm run lint`。上表为本次实际使用的测试文件和目录；以后复验应使用新的pytest临时目录。测试控制器拒绝覆盖已有库；实验重放需在新运行目录显式规划，不能重复执行有副作用helper来“刷新”旧证据。

## 6. Token与成本

已知输入125992、输出33698、合计**159690 Token下界**；3项UNKNOWN（1次崩溃模型、2次压缩提交失败），不按零计费。逐请求response与usage、估算差值见TRACE，已知46对input差值-960～+449，均值-49.696；本地估算非Provider硬限制。货币单价/账单未获取，不虚构金额。

本轮没有重新做Memory ON/OFF、公平R/H/A或生产性能评估；不宣称经验提高成功率。最终业务成果为三个真实来源案例的受控恢复；最后目标仍WAITING_APPROVAL，绝非已恢复。

## 7. 证据入口与停止

- [RESULTS.json](RESULTS.json)：阶段状态、分母、已知成本下界、未知与安全检查。
- [TRACE.json](TRACE.json)：49次真实请求关联、usage、三个来源回执、Memory事件、Summary依赖和进程时序。
- [PROVIDER_OBSERVATION.md](PROVIDER_OBSERVATION.md)：观察层、内容检查与局限。
- [SUMMARY_LINEAGE.md](SUMMARY_LINEAGE.md)：两次限定摘要实验的真实来源图与PARTIAL。
- [SOURCE_AUDIT.md](SOURCE_AUDIT.md)：P1修复、Worker未知根因及P2/P3。
- [FAILURES.md](FAILURES.md)：准备错误、工具失败、RED、压缩失败、UNKNOWN与汇总脚本修正。
- runs/journey-01/TRACE-*.json为阶段只读白名单快照，checkpoint只导出ID/父链，不导出完整blob；旧阶段资料不改。

隔离8003/5176已停止，原8000/5173服务仍运行；所有临时DB/合成口令均在忽略的`.runtime/m3-hf-02/`，未提交。最终Diff/脱敏清单见AUDIT.json和EVIDENCE_INDEX.json。提交推送main后立即停止，等待主Agent独立审核；不自动进入M4、新业务或下一轮摘要调参。
