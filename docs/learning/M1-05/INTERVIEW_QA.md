# M1-05 面试问答卡

## 1. 为什么 LangGraph checkpoint 不能充当业务 Ledger？

**30 秒：** checkpoint 说明图走到哪里，不能证明外部副作用有没有 COMMIT。OpsPilot 用 Domain SQLite 的 ActionIntent 和 ActionLedger 记录 REPAIR/DELIVER 身份及回执；恢复时先查 Ledger，再决定继续验证或交付。

**2 分钟：** REPAIR 的 SQLite 事务可能已经成功，而进程在 LangGraph 保存下一步之前退出。若只看 checkpoint，Worker 可能重复换配置；若只看 Task `COMPLETED`，也可能误称工单已交付。因此首次写入前先持久化 ActionIntent，D3 动作入口在事务里以 action ID、request digest、计划资格、Approval、TaskControl 和版本 CAS 裁决。重启后复用同一 Intent，已 COMMITTED 的 Ledger 只回放原回执。M1-05 的真实故障实验在 REPAIR COMMIT 后退出，恢复后仍只有一条 REPAIR Ledger。

**追问 / 源码 / 证据：** `opspilot/domain/d3.py::execute_repair`、`execute_deliver`；[`runs/20261018T100615Z/RESULTS.json`](../../evidence/vnext/m1-05/runs/20261018T100615Z/RESULTS.json)，退出码 87、最终 REPAIR/DELIVER 各一条。

## 2. Web 审批怎样与 TaskControl 和动作授权共同裁决？

**30 秒：** HTTP 身份只确认“谁在请求”。Domain 仍要在同一事务核验 APPROVER 角色、不可自批、Task owner/tenant、当前控制 revision、没有待处理更正、Plan 有效和资源版本匹配。批准和新恢复 Run 一起提交。

**2 分钟：** Origin、CSRF、Cookie 是入口防线，不是最终业务授权。`submit_web_plan_approval()` 使用 `BEGIN IMMEDIATE`，复用原 D3 审批校验，再原子写 Command 幂等记录、新 `APPROVAL_RESUME` Run、checkpoint 映射及 Outbox。关键纠错或 abort 若先提交，就使控制版本/终止状态失效，旧 Plan 不能获批；REPAIR/DELIVER 还会在自己的 Domain 事务中再次验证动作权限。审批者只是批准人，可信 Worker/executor 才推进动作。

**追问 / 源码 / 证据：** `opspilot/domain/task_control.py::submit_web_plan_approval`、`opspilot/domain/d3.py::_submit_plan_approval_in_transaction`；APR-02 的 Trigger rollback、APR-05 的 abort/纠错/过期版本测试见 [`pytest-approval-directed.txt`](../../evidence/vnext/m1-05/pytest-approval-directed.txt)。

## 3. 为什么批准后另建 Run，还能恢复原 Graph？

**30 秒：** 旧 INVESTIGATE Run 已释放 Worker 执行占用并保持 `WAITING_APPROVAL`。新 Run 有新的调度身份；Domain 持久映射把它绑定到原 checkpoint thread。恢复前核验映射和 Plan hash，再继续原 interrupt。

**2 分钟：** 如果用新 Run ID 直接作为 checkpoint key，原 Graph 不存在；如果把旧 Run 重新标为 RUNNING，又会混淆历史和调度状态。`approval_resume_links` 绑定 source Run、checkpoint thread、resume Run、plan hash、approval ID 和 revision。Worker 以新 Run 认领并通过 fence，`run_investigation()` 在任何 checkpoint 读取前校验 Domain 身份，再检查原 Graph 的 Plan hash、stage 与 interrupt。原调查模型/MCP 证据和不可变 Plan继续使用，不重新生成 Plan。

**追问 / 源码 / 证据：** `get_approval_resume_link()`、`_validate_approval_resume_in_transaction()`、`run_investigation()`；APR-03 和 APR-07 的 source/resume/checkpoint 映射在 [`RESULTS.json`](../../evidence/vnext/m1-05/RESULTS.json)。

## 4. Domain Outbox 解决了什么？

**30 秒：** 它让业务事实和“需要投影的事件”在同一 SQLite 事务中落地。进程退出后，重连可以补发已提交事件；补发不会执行 REPAIR 或 DELIVER。

**2 分钟：** 如果先写 Domain、再单独发 SSE，进程可能在两者之间退出，页面永远看不到已提交事实。若先发 SSE 再写 Domain，页面会看到未提交的批准或动作。M1-05 把 Approval、Run、link 和 Outbox 同事务提交；Repair、Verification、Report、Delivery 继续沿用已有 Domain Outbox。SSE 按持久 `event_seq` 回放，浏览器重新读取 history 并去重。真实 smoke 的审批响应丢失后，HTTP History 和 Stream 均返回 200，历史和新事件顺序无重复。

**追问 / 源码 / 证据：** `opspilot/domain/events.py`、`_insert_outbox()`、`project_outbox()`；APR-07 原始轨迹和事件序列见 [`runs/20261018T100615Z/RESULTS.json`](../../evidence/vnext/m1-05/runs/20261018T100615Z/RESULTS.json)。

## 5. 什么才算业务恢复与最终交付？

**30 秒：** 恢复不是模型说成功，也不是配置写入成功。相同客户端身份和固定业务 route 必须实际收到 HTTP 200，并校验订单字段；随后冻结报告，并通过独立 DELIVER Intent 写入一个工单回执。

**2 分钟：** S1 从真实的 401 Endpoint Probe 和可信当前配置证据出发。审批后 REPAIR 以版本 CAS 将 credential ref 从 `cred-v1` 改为 `cred-v2`，配置版本 v7→v8。Verifier 使用绑定的 service/integration/principal/route 在线请求，检查 HTTP 200、`order_id=demo-order`、`status=CONFIRMED`。Domain 冻结含该验证引用的报告后，独立 DELIVER 追加工单。UI 只从 Domain outcome 投影 `RECOVERED_NOT_DELIVERED` 或 `DELIVERED`，不会以 Task `COMPLETED` 或 SSE 消息冒充交付。

**追问 / 源码 / 证据：** `verify_repair_online()`、`get_or_create_report()`、`execute_deliver()`、`get_task_outcome()`；真实 provider/MCP/HTTP 和唯一回执见 [`REPORT.md`](../../evidence/vnext/m1-05/REPORT.md) 及 [`RESULTS.json`](../../evidence/vnext/m1-05/RESULTS.json)。
