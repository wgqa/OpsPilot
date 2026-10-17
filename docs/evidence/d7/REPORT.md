# OpsPilot D7 最终交付复现报告

**复现结论：PASS（最小导出修正后的独立环境）；主 Agent 验收、第三方实现审计、用户最终审阅均待进行。** 原始失败仍在独立分母中。D7 没有增加 Agent 功能或改动 Agent/Domain Python 执行逻辑。

实现起点 `28c3e1a65e46ca7992ccf6b783d96f00c0ce2e4d`；最终运行的实现 SHA 为 **`a2517fdbe2b66e4490867cc388aadc32ec5b5197`**。差异仅为 `.gitattributes` 把有字节摘要契约的 Skill 正文固定为 LF，修复 Windows `core.autocrlf=true` 导出后 manifest 校验失败。审计包的文档/证据快照 SHA 见 `docs/review-handoff/d7/REVIEW_INPUT/PACKAGE.json`；最终含附件的 main SHA 在交付消息和 `git rev-parse HEAD` 中给出。提交不能在自身文件里写入自身 SHA，故实现、审计快照与外层附件提交明确区分。

## 环境与隔离

Windows 11 `10.0.26200`；CPython **3.14.0**；SQLite **3.50.4**。两次都从指定 Git 提交导出到新目录，不包含 `.git`、旧 `.runtime`、旧 `.venv`、旧 `.env`，然后分别建立新 venv。模型配置只复制本地忽略的 `.env` 到独立演示目录，内容未进入证据或审计附件。

| 尝试 | 源码 / 独立目录 | 安装与来源 |
|---|---|---|
| 01 | `28c3e1a` / `D:\学习\OpsPilot-D7-repro-20261017T101609Z` | [PROVENANCE](clean-environment/PROVENANCE.json)、[install](clean-environment/install.txt)、[pip freeze](clean-environment/pip-freeze.txt) |
| 02 | `a2517fd` / `D:\学习\OpsPilot-D7-repro-20261017T102036Z` | [PROVENANCE](clean-environment/attempt-02/PROVENANCE.json)、[install](clean-environment/attempt-02/install.txt)、[pip freeze](clean-environment/attempt-02/pip-freeze.txt) |

锁文件 SHA-256 为 `590c6ac5f0829aa73d667698954b60b72f7532f94bdc7b4d25d563baf94bcfaa`。锁定版本包括 langchain 1.4.1、langchain-openai 1.7.2、langgraph 1.2.16、langgraph-checkpoint-sqlite 3.1.2、mcp 2.3.0、pydantic 2.14.1、pytest 9.1.1。模型为实际配置的 `deepseek-flash`，OpenAI-compatible Chat Completions；其他 Python/模型/操作系统组合未验证。安装需要 Python 包源；真实模型调用需要外网及用户自己的凭证。离线附件支持完整核心源码阅读，未包含 wheel 或模型服务。

导出文本受 Git 换行属性影响；源码对照按 CRLF→LF 规范化与 `git show SHA:path` 比较，实际导出字节哈希另存 [SOURCE_HASHES](attempt-02/SOURCE_HASHES.json) 和 [校验说明](attempt-02/SOURCE_VERIFICATION.json)。字节摘要 Skill 不做运行时宽松归一化，固定 LF 后原 manifest 原样有效。无 `.git` 的导出中 helper 的 `TRACE.git_head` 为空，helper 的 `smoke_command` 是旧的通用示例字符串；**实际命令/来源以 RUNS.json、PROVENANCE 和 SOURCE_HASHES 为准**，原始 TRACE 未改写。

## 命令、退出码和分母

从原仓库执行 `git archive --format=zip --output=<新zip路径> <实现SHA>`，解压到上述新目录。进入新目录后执行：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.lock.txt
# 本地准备 .env；模型 API key 只保存在该文件，不能复制进审计附件。
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m pip freeze --all
.\.venv\Scripts\python.exe -m opspilot.cli d3-smoke --db .runtime/d7-e01.sqlite3 --checkpoint-db .runtime/d7-e01-checkpoints.sqlite3 --evidence-dir docs/evidence/d7/e01
.\.venv\Scripts\python.exe -m pytest -vv -s --basetemp=.runtime/pytest-d7-full
.\.venv\Scripts\python.exe -m compileall -q opspilot tests
```

恢复用例使用 `d4-recovery/CAPTURE.py` 观察既有测试，把文件复制到干净目录 `.runtime/d7-capture.py` 后执行 `.\.venv\Scripts\python.exe .runtime/d7-capture.py`。它内部调用两个既有 `test_d4_langgraph_replays_committed_*`，用 `sys.setprofile` 保存 `_worker_event` 取得的真实子进程输出，未替代 Domain、模型或动作。直接无采集器复跑的命令见 DEMO。两次运行每条命令的完整 argv、工作目录、PID、开始/结束 UTC、退出码在 [首次 RUNS](RUNS.json)、[修正后 RUNS](attempt-02/RUNS.json)；安装记录在各 PROVENANCE。

| 项目 | 尝试 01（保留） | 尝试 02（修正后） |
|---|---|---|
| 安装 / pip check / compileall | exit 0 / 0 / 0 | exit 0 / 0 / 0 |
| E01 smoke | FAIL，exit 1；1/13 检查为真（仅未审批无写入） | **13/13，exit 0** |
| D4 采集入口 | exit 4；导入失败，0 个测试执行 | **2/2，exit 0** |
| 全量 pytest | **61/64，3 failed，exit 1** | **64/64，exit 0，60.11s** |

最终全量日志：[pytest-full.txt](attempt-02/pytest-full.txt)。64 项是原有同一组 D1–D6 回归，定向恢复 2 项是重复执行的子集，不能相加宣传成 66 项独立测试。D7 E01 命令共 **2 次尝试，1 PASS / 1 FAIL**；首轮没有任何模型请求，修正后的新鲜模型端到端运行只有 1 次。未反复筛选模型成功样本。

## 新鲜业务事实

第二次 smoke 总进程 PID **36440**，exit 0；调查进程 **27704** 与批准/恢复进程 **9112** 分别 exit 0。可信身份为 support-a / approver-a / executor-a。**自动 smoke 由测试程序选择 approver-a 并发送 APPROVED，它证明审批路径而非真实人亲手做决定**；人工两进程 CLI 说明在根 README，本轮没有伪称人工手动审批已执行。

- 初始真实 `GET /api/orders/demo-order` 返回 401，Evidence 含 request/auth-event 关联；批准前配置仍 `cred-v1 / v7`，工单条目 0。
- Plan `a50d0de299d38ca04774fc6f66f5eb8980457ecb7fbcfdf16bf9137c2c6d8c81`，两个 ActionIntent 在各自动作之前持久化。REPAIR `action-829acbaa-f8bf-4e27-b623-b44ae8b45bfb` / Ledger `ledger-1452d727-ce5c-45cc-a1c6-1d32e651c1cd`，配置仅 **v7→v8**，ref 变为 `cred-v2`。
- 同一 `tenant-a/orders-demo/integration-a/principal-a`、同一路由真实返回 **HTTP 200**，`order_id=demo-order`、`status=CONFIRMED`。Verification `verification-16d97f92-45a9-4db7-94ca-ca732498f547`。
- 冻结报告 `report-dad6c81f-2da3-4a1f-bdaf-905c3211bba8`，digest `d598f377628a70ac39bcc22ad4ce51f561612531f88d88d88e3b17ab81dfb1c9`；独立 DELIVER `action-6dcc1200-3457-4188-83a4-f0bc747752f2` / Ledger `ledger-a807829b-e634-4d94-b54c-e07355d10fbb`。REPAIR/DELIVER 各 1 笔 Ledger、各自许可消费；DeliveryRecord 1、INC-A-001 工单条目 **1**。

完整来源见 [TRACE](attempt-02/e01/TRACE.json)、[两个进程](attempt-02/e01/process_logs.json)、[非秘密业务表投影](attempt-02/e01/BUSINESS_STATE.json)、[Context Provenance](attempt-02/e01/CONTEXT_PROVENANCE.json)。Intent request digest、Ledger result digest、冻结报告 content digest 已独立对实际字符串重算相等，见 [DIGEST_CHECKS](attempt-02/e01/DIGEST_CHECKS.json)。没有把 SQLite 文件或 credentials 表导出。

本轮真实 **7 次模型响应 / 6 次 MCP tools/call attempt**，全部模型响应有 Provider ID；Provider 用量 **16,627 input + 2,617 output = 19,244 tokens**。其中一个真实 MCP 调用被拒为 `RESOURCE_OUTSIDE_TASK_SCOPE`（模型第一次查询的主体 ID 不在绑定范围），无 Evidence、无读取越界，之后补查当前正确事实并通过门禁；该错误保留在 Observation 中，未称全部工具调用成功。模型/MCP 计数不包含 D4 确定性控制测试。阶段内 MODEL≤8、MCP≤6 的持久预算仍生效。

## 真进程崩溃恢复

| 已有测试 / failpoint | crash → retry PID / exit | 原 action / Ledger 与恢复对照 | 最终副作用 |
|---|---|---|---|
| `test_d4_langgraph_replays_committed_repair_after_os_process_crash` / `repair_after_commit_before_response` | 27692 / **75** → 32936 / **0** | `action-e8c35145-f3a9-49a0-827f-1cc6f7223687`；`ledger-b608af03-b8c7-465d-9769-f43e6272191d`，重放完全相同 | 配置 8；REPAIR/DELIVER 各 1 Ledger；工单 1 |
| `test_d4_langgraph_replays_committed_delivery_after_lost_response` / `deliver_after_commit_before_response` | 28092 / **75** → 17436 / **0** | `action-04533c05-b7f8-455f-82c8-41b1d1c1b6bf`；`ledger-07a02792-d8ab-48fc-87dd-feba896fb10f`，重放完全相同 | 配置 8；REPAIR/DELIVER 各 1 Ledger；工单仍 1 |

原始 stdout/stderr/argv/exit code 见 [WORKERS.json](attempt-02/d4-recovery/WORKERS.json)；恢复后数据库的非秘密计数与逐 ID 比较见 [RECOVERY_SUMMARY](attempt-02/d4-recovery/RECOVERY_SUMMARY.json)，测试日志见 [pytest](attempt-02/d4-recovery/pytest.txt)。这些测试直接准备已批准状态后验证故障窗口，不调用真实模型；模型调查闭环由 E01 单独证明。本地 SQLite COMMIT/幂等结果不等同于远端分布式 exactly-once。

## 历史评测与本轮复用

D6 原样保持：**9 PASS + E10 PARTIAL；5 次真实模型 smoke 4 PASS/1 FAIL；64/64 pytest；40 Provider 调用 / 33 MCP attempt / 102,725 tokens**。D7 没有重写 Gold、补填 E10 或重新定义 Actual Recovery。

D7 的 E02/E03 真实模型负例直接复用 D6 冻结轨迹，**本轮未新跑**：源码 `151a1cea2ea23fa7413abbbd89d5ed6fd173da9c`，E02 UTC `09:51:13.0421782–09:51:24.2271570`、E03 UTC `09:51:32.2472234–09:51:51.9763788`（均 2026-10-17）。路径为 `docs/evidence/d6/e02/TRACE.json` 与 `e03/TRACE.json`；E02 NO_ACTION、E03 INCONCLUSIVE，Actual Recovery 均 false。D7 全量另外新跑了对应确定性安全回归。E10 跨任务真实模型轨迹同样复用 D6，本轮仅复跑其控制测试。

## 失败、差异与停止

1. 两次准备脚本按原始字节比较源码时受 CRLF 影响，分别见 `preparation-attempt-01.txt/02.txt`；尚未运行模型或测试。比较方式修正及实际哈希已公开。
2. 真正首轮干净环境暴露 SkillIntegrityError。E01 FAIL 在 [e01](e01/)；Domain 投影证明模型/工具 attempt、Plan、Intent、Ledger、交付全为 0，配置仍 v7。全量三项 D5 Context 测试因同一摘要错误失败，完整 [原始 pytest](pytest-full.txt) 保留。仅 `.gitattributes` 固定 Skill 字节，不放宽 loader 的完整性校验。
3. 首轮新增采集器缺少 cwd 的 sys.path，pytest exit 4，非业务安全失败；原始 [日志](d4-recovery/pytest.txt) 保留。只修观察脚本的 import 路径，第二次使用同一组已有测试。
4. D6 E10 首次失败仍存于 `docs/evidence/d6/e10/ATTEMPT-01.json`、原始 run 和可恢复 Domain 投影；旧 wrapper 的更深层原始输出缺失，根因未完全还原。固定通用 Memory 与 Skill 重叠，没有公平 ON/OFF 消融，没有案例自学习或效率提升证据。
5. 本地可信角色/SQLite/loopback 业务 API 是 Demo 边界；只验证单一 S1、一个模型端点，未实现公网 IAM、分布式幂等、通用诊断、多 Agent 或其他 P1。调查有持久次数预算和单调用超时，尚无独立的整个活跃调查阶段 wall-clock 截止检查；该差异明确交主 Agent/第三方裁决，不在 D7 扩建 Runtime。未知动作终态仍需 ACTION_OUTCOME_UNKNOWN 人工对账，安全停止不能计恢复。
6. 离线附件的辅助校验曾错误假设每个 CASES 子项都有 Gold，改为按 JSON path 递归比较后证明新旧 Gold 相同，未改 CASES。随后首次解压的 Skill 子集测试因 `.runtime` 父目录不存在出现 2 个 setup error，暴露无模型直接 pytest 的说明缺步骤；只在说明/校验准备中增加建目录命令，未改测试。初包的来源 SHA/哈希、辅助校验错误和原始 pytest 输出保存在 `docs/review-handoff/d7/REVIEW_INPUT/attempt-01/`；最终包重新从修订后的文档快照生成。该附件检查独立于上面的两轮全量回归和 E01 分母，最终检查见外层 `REVIEW_INPUT/VERIFICATION.json`。

未发现未经批准写入、重复业务副作用或成功越界读取的 P0 红线失败；不以此代替独立审查结论。设计条款、实际实现与未实现项见 [漂移表](../../review-handoff/d7/RISKS_AND_DEVIATIONS.md)。交付入口为 [DEMO](DEMO.md)、[源码地图](CODE_READING_MAP.md)、[面试材料](INTERVIEW.md)、[第三方交接](../../review-handoff/d7/REVIEW_BRIEF.md)、[机器结果](RESULTS.json)。D7 到此停止，等待主 Agent 验收；不启动新开发阶段。
