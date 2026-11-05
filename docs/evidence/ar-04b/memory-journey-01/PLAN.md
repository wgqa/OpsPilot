# AR-04B-MEMORY-JOURNEY-01 — 验证计划

## 冻结变量

- 保持 GOLD.md 原 G1–G10、J1–J6 和 E1–E6 判据，不修改 Gold。
- 正式路径：FastAPI → Worker → ASSISTANT_V1 → LangGraph/工具 → 既有 MCP/Domain → 持久 Chat Answer。
- OFF 仅是测试参数：令 _current_memories 返回空集；Runtime、工具、权限、Session、Task、事实与问题相同。
- ON 使用现有候选创建、可信角色确认和 Memory 来源选择。
- 只用 Fixture Model、隔离 SQLite、Checkpoint 和本地 MCP/Domain；Provider HTTP=0。
- Context 输入预算保持 12,000 Token，不固定调查工具顺序，不增添模型调用或业务写权限。

## J1–J6 与成对案例

| 旅程/案例 | 离线验证 | 重点证据 |
| --- | --- | --- |
| J1 来源任务产生并确认 | 正式 API 建立 Semantic Memory；E2/E3 从可信 S3 诊断、候选与 Approver 确认建立 Episodic Memory | 候选、确认者、来源 Task、版本与 Digest |
| J2 新 Task B | 新 Session/Task，来源 Task 与目标 Task 不同 | 历史 Memory 不是当前业务事实 |
| J3 当前事实改变方向 | E2 当前 Receiver=QUEUED；E3 同类 ON/OFF 当前 Receiver=PROCESSED | 同 Event Delivery 与 Receiver，202/ACK 与业务处理分离 |
| J4 不适用作用域 | E4：Tenant A Memory 对 Tenant B 不可见，B 的合法绑定订单仍可查询 | Manifest/Wire 无外租 Memory，合法工具继续可用 |
| J5 撤销与失效 | E5/G8：预留后撤销、checkpoint 读取后撤销、模型调用期间撤销 | 不发送或不提交失效来源；新鲜有效运行可继续 |
| J6 连续追问 | 同一 Session/Task 初始调查后再提交 follow-up | 第二 Run 带入上一轮实际答案作历史线索，并重新读取当前 Receiver |
| E1 相关 Semantic | 正式确认的相关 Semantic Memory ON/OFF | 实际处理器输入、Manifest/Wire 对齐、当前事实一致 |
| E2 相关 Episodic | 已确认历史方法 ON/OFF，当前 QUEUED | Memory 仅指导方法，当前 Observation 作答 |
| E3 当前事实冲突 | 同一 Episodic Memory ON/OFF，当前 PROCESSED | 新事实优先，ON/OFF 分别区分状态 |
| E4 不同作用域 | Tenant A Memory，Tenant B 合法订单 | 拒绝泄露且不误拒合法查询 |
| E5 撤销/失效 | 活跃与撤销后 ON/OFF、发送前与发送后竞态 | 失效内容不回流到新 Context/答案 |
| E6 不相关 Memory | 有效但无关的 Semantic Memory ON/OFF | 对比是否增加干扰或无必要工具调用 |

E2/E3 共用一个测试函数，但包含四个目标 Run（两个 Receiver 状态 × ON/OFF）。J6 是同 Task 连续追问补充测试。

## 执行命令与回归

最终 AR-04B 定向套件：

D:\学习\agent新项目\.venv\Scripts\python.exe -m pytest -vv -s tests/test_ar04b_memory_journey_01.py --basetemp=docs/evidence/ar-04b/memory-journey-01/runs/pytest-tmp-ar04b-final-03

回归结果与原始日志：
- runs/regression-memory-d5.log：M3 Episodic、M3 Semantic、D5 Context，共 28 项。
- runs/regression-assistant-taskcontrol.log：AR-02 Assistant、TaskControl，共 14 项。
- runs/regression-ar04a-context.log：AR-04A Context/取消相关，共 8 项。

本阶段未运行全量 pytest、真实模型或浏览器。

## 停止线

定向与相关回归完成即停止。提交状态为 ACCEPTANCE_CANDIDATE，交主 Agent 独立验收。真实模型 Level 2/3 需新的费用合同与用户授权。
