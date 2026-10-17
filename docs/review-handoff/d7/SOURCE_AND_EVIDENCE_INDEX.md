# 源码与脱敏证据索引

运行实现 SHA：`a2517fdbe2b66e4490867cc388aadc32ec5b5197`。审计文档/附件源 SHA 以 `REVIEW_INPUT/PACKAGE.json` / 包内 `MANIFEST.json` 为准，最终 main 交付 SHA 在 Git 和交付消息中核对。附件中每个文件给出精确来源 SHA、路径、完整标记和字节哈希；所有入包文件均为完整文件，没有隐藏节选。

## 最短核心源码路线

| 文件 | 关键函数 / 责任 | 对应验证 |
|---|---|---|
| `opspilot/cli.py` | `main`：可信本地角色入口、调查/批准/恢复、smoke | E01 processes；D1 CLI/业务测试 |
| `opspilot/investigator.py` | `_prompt_messages`、`build_investigation_graph` 内 investigate/execute_read_tools/d3_*、`run_investigation`、`_d3_terminal_is_authoritative` | D2/D3/D4/D5 测试；D7 E01/WORKERS |
| `opspilot/mcp_server.py` / `tools/model_tools.py` | `build_task_server`、严格只读工具参数 | D2 real MCP；D4 注入；D7 真实 MCP Observation |
| `opspilot/domain/d2.py` | TaskBinding、scope、`reserve_attempt`、`record_tool_observation`、`evaluate_evidence_gate` | `tests/test_d2_investigation.py` |
| `opspilot/domain/d3.py` | Plan/批准/取消、Intent、`execute_repair`、`verify_repair_online`、`get_or_create_report`、`execute_deliver` | `tests/test_d3_actions.py`、`tests/test_d4_recovery.py` |
| `opspilot/domain/database.py` / `api.py` / `client.py` | 表唯一约束、事务、fixture、真实 HTTP 与身份固定 | `tests/test_s1_business.py`；D7 BUSINESS_STATE |
| `opspilot/domain/episodic_memory.py` / `skill_assets.py` / `skills/auth-incident-triage/` | 来源核验/确认撤销、固定通用正文、按任务重检、Skill 摘要和 Context 台账 | `tests/test_d5_context.py`；D6 E10 REAL-TRAJECTORIES |
| `opspilot/smokes/d3.py` / `d5.py` / `tests/d4_crash_worker.py` | 真实流程的测试驱动、自动可信批准、真实进程故障窗口 | D7 E01 13 条检查；WORKERS 原始输出 |
| `docs/evidence/d6/CASES.json` / `RESULTS.json` | 离线 Gold、逐 pytest node 映射与独立指标/分母 | D6 冻结历史；D7 不回写 |

更多责任问题、逐步测试命令见 `docs/evidence/d7/CODE_READING_MAP.md`。精确测试名称以完整测试文件和 D6 CASES 的 node 列表为准，不能仅凭表述当作已执行。

## 阶段证据

| 阶段 | 报告 / 最小原始证据 | 真实性与边界 |
|---|---|---|
| D1 | `docs/evidence/d1/REPORT.md`；tool-call-smoke、mcp-smoke、checkpoint-smoke、s1-smoke、pytest-clean 文本 | 历史真实技术 smoke；早期 fixture-only 修改不是正式 REPAIR |
| D2 | `docs/evidence/d2/REPORT.md`；当前负例优先看 D6 E02/E03 | 拆分只读 MCP、模型选择、Gate；没有写入 |
| D3 | `docs/evidence/d3/REPORT.md` / TRACE；最新闭环以 D7 为准 | 真实模型/HTTP，但自动 smoke 的 APPROVED 是程序模拟可信角色 |
| D4 | `docs/evidence/d4/REPORT.md` / `pytest-full.txt`；最新原始子进程以 D7 WORKERS 为准 | crash、lost-response、取消/替换、历史回执和越界 |
| D5 | `docs/evidence/d5/REPORT.md`；D6 E10 `attempt-02/REAL-TRAJECTORIES.json` | 真实跨任务 Prompt 注入、撤销恢复；非新案例学习/收益证明 |
| D6 | `docs/evidence/d6/REPORT.md` / CASES / RESULTS / pytest；e01/e02/e03 TRACE；e10 ATTEMPT-01 与失败 run/投影、attempt-02 REAL-TRAJECTORIES | 9 PASS + E10 PARTIAL；模型 4/5、40/33/102725；64/64 pytest；E07 分类勘误可追溯 |
| D7 初次 | `docs/evidence/d7/clean-environment/PROVENANCE.json`、RUNS、e01 TRACE/DOMAIN_COUNTS、pytest-full、d4-recovery/pytest | 新 venv/新 DB 的真实失败：Skill 摘要；61/64；采集器 import exit 4；两次准备校验失败另外留痕 |
| D7 修正后 | `docs/evidence/d7/clean-environment/attempt-02/`；attempt-02/RUNS、SOURCE_HASHES/VERIFICATION、e01 TRACE/BUSINESS_STATE/CONTEXT_PROVENANCE、d4-recovery WORKERS/RECOVERY_SUMMARY、pytest-full | 第二个新目录/新 venv；E01 13/13、恢复 2/2、全量 64/64；7 模型/6 MCP/19244 Token；实际 scope 工具错误保留 |

离线附件优先完整 Python/测试、合同、上述关键日志和脱敏 TRACE；不复制大规模重复进程日志或无关早期规划，完整 Git 历史不在包内。MANIFEST 是包内实有文件的权威清单；历史报告引用的其他文件如未入包，要标 UNVERIFIABLE 或向主 Agent 明确索取，不能声称附件是全部历史仓库。D7 E01 TRACE 已内嵌两个进程事件，包中另附必要进程原始记录供核对。

## 复验命令与外部依赖

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.lock.txt
.\.venv\Scripts\python.exe -m pip check
New-Item -ItemType Directory -Path .runtime -Force | Out-Null
.\.venv\Scripts\python.exe -m pytest -vv -s --basetemp=.runtime/review-full
.\.venv\Scripts\python.exe -m pytest -vv -s tests/test_d4_recovery.py -k 'langgraph_replays_committed' --basetemp=.runtime/review-recovery
# 配置本地 .env 后使用新的 DB/checkpoint，真实模型有成本，不能复用成功 DB。
.\.venv\Scripts\python.exe -m opspilot.cli d3-smoke --db .runtime/review-e01.sqlite3 --checkpoint-db .runtime/review-e01-checkpoints.sqlite3 --evidence-dir .runtime/review-e01-evidence
```

包源/模型服务需要网络与用户自己的模型 key；pytest 不需要模型 key，使用真实本地 HTTP/MCP/SQLite/OS 子进程。`.env.example` 只有变量名。演示 fixture 中的合成凭证是测试源码的一部分，不是生产秘密；附件不含实际 API key、`.env`、credential 数据表或 SQLite 数据文件。
