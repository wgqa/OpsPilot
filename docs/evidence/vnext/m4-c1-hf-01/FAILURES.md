# M4-C1-HF-01 失败与补充运行记录

本文件保留失败，不用后续通过结果覆盖早期日志。

| 运行 | 观察 | 分类与处理 | 原始记录 |
|---|---|---|---|
| 冻结 RED 01–03 | 基线缺少跨轮补查结果装配，分类器/回答上下文不含持久答案和来源，task-bound Chat 可在路由前被领取 | 预期 RED，保留为实现前缺口证据；对应冻结标准和测试在提交 `8135ab6` | `runs/red-01.log`、`red-02.log`、`red-03.log` |
| HF-02-CHAT-LINEAGE RED | 已持久化的助手回答在其 Knowledge 依赖变更后仍进入下一轮上下文 | 预期 RED；在实现前冻结并重现，之后加入来源再验证 | `runs/red-lineage-01.log` |
| 首批 GREEN 01 | pytest 默认临时目录在 Windows 拒绝访问，5 项在 fixture setup 阶段报 `PermissionError` | 环境/测试启动问题；后续固定每轮独立 `--basetemp` | `runs/green-initial-01.log` |
| 首批 GREEN 02 | 4 passed、1 failed；Investigator 测试中的旧 Evidence 来源没有完整 Observation/Attempt 关联，得到 `INVALID_SOURCE_RUN_ASSOCIATION` | 测试 fixture 的来源链不完整；补齐真实持久来源关联后，后续定向通过 | `runs/green-initial-02.log` |
| 初期集成 GREEN | `green-initial-03` 为 5 passed；`green-debug-01` / `green-expanded-01` 使用了未安装项目依赖的系统 Python，出现 `ModuleNotFoundError`；同时暴露分类器/Chat 测试没有经过有效分类路由装配历史上下文 | 切换仓库 `.venv` 并通过实际路由准备输入；对应来源装配与测试经后续运行验证 | `runs/green-initial-03.log`、`green-debug-01.log`、`green-expanded-01.log` |
| 路由测试迭代 | `green-debug-02` 中 `next_worker_run()` 选中了另一条可领取 Run，测试错误假设目标 Run 一定排第一；之后扩大集成集为 11、再 12 项通过 | 隔离与 Run 选择测试预期调整；最终专项测试 13 项全过 | `runs/green-debug-02.log`、`green-expanded-02.log`、`green-expanded-03.log`、`green-expanded-04.log`、`runs/hf01-target-green-02.log` |
| `hf01-target-green-01` | 新增迟到分类测试误把超时后已结束的 Assessment 当作仍可完成；实际 Domain 正确返回 `UPDATE_ASSESSMENT_NOT_ACTIVE` | 测试预期修正为超时 Assessment 保持 FAILED、同一 Chat 仅一条已启动链；不是产品源码缺陷 | `runs/hf01-target-green-01.log` |
| 首次完整 pytest | 336 passed、2 failed：一项为保留的旧 C1 预实现 RED；另一项为 M2 恢复测试的子进程缺少 `OPSPILOT_MODEL_API_KEY` / `OPSPILOT_MODEL_NAME` | 旧 RED 按冻结要求保留。M2 Worker 明确替换为 `NoToolModel`，对隔离测试进程注入非密钥占位配置后定向通过；随后完整回归 338 passed、仅 deselect 旧 RED | `runs/full-pytest-01.log`、`runs/m2-hf-stale-noop-target-01.log`、`runs/full-pytest-green-01.log` |
| Web harness `backend-start-01/02` | 从子目录启动时未把工作树根加入 Python import path，服务未启动 | 修复启动器的 `PYTHONPATH`，不涉及产品运行逻辑 | `runs/backend-start-01.log`、`backend-start-02.log` |
| Browser attempt 01 | 脚本期待资源下拉框仅一个选项，实际有占位项和两个订单项 | 测试准备错误；修正为按准确订单 ID 选择 | `runs/browser-01.log` |
| Browser attempt 02 | 流程完成，但脚本默认选中 `async-order-2`（v1 / PROCESSING），不符合冻结的协议 v2 场景 | 保留为无效场景尝试，不计验收；最终 run03 精确选择 `async-order` | `runs/web-e2e-hf01-02/journey.json`、`runs/browser-02.log` |
| Browser run03 | 完成全旅程；浏览器记录登录前 `GET /api/auth/me` 401 和一个非 API 404。最后一次当前状态补查取得新 `QUEUED` Observation，但结果是 `PARTIAL / FOLLOWUP_BUDGET_OR_PROVIDER_EXHAUSTED`，answer_text 为空 | 如实作为非致命浏览器资源错误和产品信息缺口保留；不标记最后一问为 ANSWERED。页面显示未形成可展示回答和原因码 | `runs/web-e2e-hf01-03/journey.json`、`TRACE.jsonl`、`browser-03.log`、截图 `04-current-state-followup.png` |

新鲜通过记录：13 项 HF-01 定向测试、M2 stale no-op 进程恢复回归、338 项全量回归（旧 C1 RED 单独 deselected）、前端 typecheck/build、Python compileall 和 diff whitespace 检查。具体命令、退出码及原始输出见 `RESULTS.json` 和 `runs/`。
