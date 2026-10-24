# M4-TTL-FIX-01 冻结验收计划

**冻结基线：** `bd58c66003c4e7fea660967c7a6a30aebcd63cd7`  
**任务范围：** S3 Run-scoped Observation 新鲜度；不修改 S1/S2 业务 Gate，不修改旧 Gold、HF-01/HF-02 报告或原始证据。  
**候选分支：** `codex/m4-ttl-fix-01`  
**状态规则：** 最终只能报告 `ACCEPTANCE_CANDIDATE`，等待主 Agent 独立验收。

## 冻结依据与 RED 来源

本计划在实现修改之前冻结。M4-PREFLIGHT-01 原始证据来自提交
`a34ddc5ec75a935d15a7caef6544f67452f0bc63`，其父提交即本轮固定基线。
本轮将原材料按字节复制到本目录的 `runs/preflight/`，不改写旧证据目录：

- 有效 RED：`runs/preflight/test_evidence_ttl_repeated_mcp_fetch.py`、
  `runs/preflight/red-02-pytest.log` 和 `runs/preflight/TRACE-red-02.jsonl`。
  它通过真实本地 HTTP 与 in-process MCP，在 301 秒后新建 Run 并重取相同事实；
  新 MCP Observation 成功，但 Gate 仍因被复用 Evidence 的旧 `fetched_at`
  返回 `NEED_MORE / S3_EVIDENCE_EXPIRED`。
- 原始失败保留：`runs/preflight/red-01-pytest.log` 与
  `runs/preflight/TRACE-red-01.jsonl`。首轮快照读取未限定 tenant/service，
  命中另一条同名 fixture；只作为测试准备错误记录，不作为业务复现证据。
- Preflight 报告与机器结果仍保存在原目录，未覆盖或修改：
  `docs/evidence/vnext/m4-preflight-01/`。

## 冻结语义

1. Evidence 是不可变、按事实 digest 去重的业务事实行；同事实可以复用同一个
   Evidence ID。`d2_evidence.fetched_at` 永不被后续观察覆盖。
2. Observation 是一次持久的工具返回记录。只有状态成功、工具和 Evidence 类型
   匹配、Task/Run/Attempt/Call/ToolCall 关联一致、返回摘要与 Evidence 内容一致、
   时间戳合法且在 TTL 内的观察，才可证明该 Run 的取证新鲜度。
3. 评估 Run B 只能选 Run B 自己的 Observation；不得拿 Run A 或其他 Run 的观察
   更新 B 的新鲜度。未绑定 Run 的 Gate 不得把跨 Run 的“最新 Observation”当作凭据。
4. 当前授权、TaskBinding、Tenant、Principal、Scope/Grant、HTTP Authz、资源版本、
   事实 digest、事件与请求关联核验继续 fail-closed。新 Observation 不覆盖这些检查。
5. Diagnosis 冻结创建时实际使用的 Evidence 与 Observation 来源。历史 Diagnosis A
   只按 A 的原始 Run/Observation 复核；B 的重查不能令 A 过期的 WAIT 重新成为
   `CURRENT`，也不能改变 A 的正文或 digest。
6. “事实内容未增加”与“本 Run 已成功新取证”分开记录：刷新观察可以使本 Run
   有效前进，但不得令所有重复调用都增加内容进展或绕过既有循环预算。

## 冻结验收用例

| 编号 | 用例与判定 | 必需关联/负例 |
|---|---|---|
| TTL-01 | 同一 Run 正常取证；Gate 与现有业务结论一致 | MCP Observation→Attempt→Run；当前 HTTP Authz 与资源版本有效 |
| TTL-02 | 原 Evidence 超 300 秒后，Run B 真实重查相同事实；Run B Gate 为 `DIAGNOSED` | 保留 Evidence ID，使用 Run B 新 Observation；不能退回旧 `fetched_at` |
| TTL-03 | 对比 A/B 两次记录 | 旧 Evidence 行字段与 digest 不变；Observation/Attempt/Run 不同且归属正确 |
| TTL-04 | Run B 刷新后复核 Run A 的旧 WAIT Diagnosis | A 仍 `INVALIDATED`；旧摘要/digest 不变；不得因 B 的观察被复活或用于旧交接 |
| TTL-05 | 撤销 Scope/Principal 后在 B 查询 | MCP/Domain 读取拒绝或被排除；旧/新观察均不能通过；fail-closed |
| TTL-06 | 资源版本或事实变化 | 旧 Evidence 不得被新的时间戳掩盖；新版本只有在当前绑定和 Authz 重新验证后有效 |
| TTL-07 | 伪造、失败、畸形时间或跨 Run Observation | 错 Task/Run/Attempt/Call/Tool/Evidence、失败尝试、摘要不符、无效/负年龄均不能通过 |
| TTL-08 | SLA WAIT 到期后创建新业务 Run 并真实走 HTTP/MCP | 旧 WAIT 不可交接；新事实经 Gate 为 `CONTACT_RECEIVER_OPERATOR`，owner 确认后可交接 |
| TTL-09 | 新 Diagnosis 的重复交接 | Queue/Receipt/Outbox 各恰一份；旧 Receipt 内容不可变；重试只回放 |
| TTL-10 | Evidence 尚在 TTL 内的既有路径 | 旧 S3/HF-01/HF-02 路径保持；299、300 秒有效，301 秒的旧观察失效 |

### 确定性时间边界

测试注入同一个确定性 UTC 时钟到 D2 的工具事实/持久观察时间和 S3 Gate。对同一个
Observation，年龄 299 秒、300 秒应有效，301 秒应过期；不存在时钟分歧或整数秒
截断。新 Run 的成功观察从本次持久记录时间重新计龄，但不得改变原 Evidence 的
`fetched_at`。

### 实施前 RED / 回归命令

原始 RED 命令见 `docs/evidence/vnext/m4-preflight-01/RESULTS.json`。本轮新增
定向测试应先在此冻结合同下运行并保留失败，再修改源码。随后依次运行：

1. 新增 TTL-01～TTL-10 定向测试及确定性边界测试；
2. M4-03 HF-01、HF-02、M4-02/S3 回归；
3. S1/S2 授权与证据安全回归；
4. 完整 `pytest`。

每个 pytest 命令使用本轮唯一 `--basetemp` 并保存 stdout/stderr、退出码与真实
Trace。无模型调用；MCP/HTTP 集成必须来自真实本地服务路径。未执行的项标为
未验证，不得从历史日志继承 PASS。

## S1/S2 影响边界

本轮先分析 D2 的共享去重/Observation 写入；只运行必要窄回归。默认不修改 S1/S2
Gate。若发现 S1/S2 同样需要业务 Gate 改动，先保存复现与影响路径，停止超范围
修改并向主 Agent 报告。
