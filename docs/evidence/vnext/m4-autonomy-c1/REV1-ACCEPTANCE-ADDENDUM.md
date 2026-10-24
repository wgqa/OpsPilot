# M4-AUTONOMY-C1-REV1 验收补充冻结

**补充冻结提交前基线：** `b133e895b01c390767cf5e95df760dcaf0be7688`  
**集成后的 TTL 主线：** `main@77ea80e87e538f0f1fae8118ef231ec622601755`  
**用途：** 只追加 C1 行为验收，不覆盖 `FROZEN_PLAN.md` 中的 C1-01～C1-08 Gold、历史 RED 或原始运行证据。

## 修订说明

REV1 取代旧 C1 任务卡，并保留原冻结语义。TTL Run-scoped Observation 已经进入 `main`；因此从本补充冻结起，S3 Evidence/Observation 夹具必须经可信 Task→Run→Attempt 关联，正式重新取证只认可当前 Run 的成功 Observation。

第一次在新主线重跑原 RED 时，测试在 Gate 断言阶段因直接写入没有 Attempt/Run 关联的旧式 Observation 而失败。原始日志保存在 `runs/rev1/readonly-followup-red-baseline-01.log`，退出码见同名 `.exitcode.txt`。该失败属于**TTL 合入后的测试准备错误**，不是本轮产品缺陷证据。为保留原 RED 断言的意义，只调整其 S3 测试夹具以使用 `tests/s3_observation_support.py` 的 Run-scoped 记录方式；不改其用户目标、分类期望、路由断言或安全断言。原始失败日志不可覆盖。

## 新增行为验收：C1-FU-01

给已诊断的 S3 Task 发送一条 `CHAT_READONLY` 用户消息，语义是按当前绑定协议核对 HTTP 202 并给出可核对依据。分类器仍返回现有合法意图 `FOLLOW_UP`；另由 Agent 选择是否需要本轮只读调查。本冻结样例的确定性决策固定为 `INVESTIGATE`，只用于验证 Domain/Worker 路由，不作为真实 Agent 自主性证据。

实现前可观察预期：

- 用户原文、同一 Task、来源 Message 与独立只读调查 Run 可持久关联；
- 该 Run 不提升 TaskControl revision，不创建 `CORRECT_TASK_INPUT`；
- 不写入正式 S3 Diagnosis/Receipt，不更改已有 Diagnosis digest、Outcome 或业务状态；
- 不创建 Approval、Plan、ActionIntent、Ledger、Handoff Queue、Receipt 或对应业务 Outbox 副作用；
- 当前消息仅以 `USER_INPUT_UNTRUSTED` 进入 Investigator Context；工具/Knowledge 读取仍由 TaskBinding、当前授权和既有 Task 累计预算约束。

当前实现没有 FOLLOW_UP→只读 Investigator 路由，所以该测试须先 RED。之后 GREEN 不要求固定内部 Run kind 名称；只要求同一消息有独立、可恢复、可核对的调查结果，且既有 C1-01～08 与安全合同保持不变。

## 本轮冻结判定分类

- **安全失败：** 越租户/越资源、旧 Run 观察借用、权限失效后读取、伪造来源、改变 TaskControl、写业务副作用或覆盖正式 Diagnosis。
- **产品失败：** 合法 FOLLOW_UP 被当成普通回答却未履约，或者调查完成但用户无法核对来源/结果。
- **策略/成本问题：** 合法但冗余的只读调用、可以直接引用时仍检索 Knowledge；记录实际成本，不新增固定顺序硬限制。
- **部分完成：** 证据缺失、当前授权失效或累计预算耗尽时，给出有来源的缺口，不宣称目标已完成。

真实 Provider Trace 与确定性替身分开记分。只有真实 Provider 调用、合法 MCP/Knowledge 行动、来源当前性及最终回答能证明 Agent 行为；定向确定性测试仅证明入口、持久化、TaskControl、幂等和副作用边界。
