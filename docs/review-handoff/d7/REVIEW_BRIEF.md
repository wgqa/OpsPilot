# OpsPilot v1.0 最终实现与防漂移审计委托

**状态：交接材料准备就绪；第三方审查尚未执行。** 主 Agent 先验收 D7，再提交一次独立实现审计，最后由用户亲自阅读。这里不预填 ACCEPT 或 APPROVED。

审查对象是实际源码、测试和运行证据。冻结合同为 `docs/baseline/v1.0-implementation-baseline.md`，不是重新进行架构选型。范围仍是一个 Agent、一个 Demo Domain、一个只读 MCP Server 的唯一 S1 401 处置链；不以审查为由开启新平台或下一阶段。

代码执行截止点：**`a2517fdbe2b66e4490867cc388aadc32ec5b5197`**（D6 `28c3e1a` 加 Skill LF 导出属性，Agent/Domain Python 不变）。审计文档和附件源快照的精确 SHA 见 [`REVIEW_INPUT/PACKAGE.json`](REVIEW_INPUT/PACKAGE.json) 及 ZIP 内 `MANIFEST.json`；包含附件的最终 main SHA 由交付消息/Git 给出。每个附件文件都有来源 SHA、原路径、完整/节选标记及 SHA-256，不把包内快照与外层包装提交混为一谈。

## 无 GitHub 权限也可以审查

先解压 [`REVIEW_INPUT/opspilot-d7-review.zip`](REVIEW_INPUT/opspilot-d7-review.zip)，从包内根 `README.md`、本文件、`DESIGN_TO_CODE_MATRIX.md` 和 `docs/evidence/d7/CODE_READING_MAP.md` 开始。包内保留原目录结构，包含**完整 `opspilot/**/*.py`、全部现有测试、Skill、锁定依赖、冻结合同、根工程规则、D1–D7 报告、关键 D6/D7 脱敏轨迹和失败证据**。`HISTORICAL_INPUT/CASES-frozen-151a1ce.json` 另附 E07 分类勘误前的原始冻结清单及其独立来源 SHA。这是精选审计附件，不是完整 Git 仓库镜像；不含 Git 历史、所有历史重复日志、原始数据库、`.env`、API key、wheel 或模型服务。缺失文件的边界在 MANIFEST 和索引中说明，不能用自述填补未提供的证据。

离线核验文件完整性：

```powershell
python -c "import json,hashlib,pathlib; r=pathlib.Path('.'); m=json.loads((r/'MANIFEST.json').read_text(encoding='utf-8')); bad=[e['path'] for e in m['files'] if hashlib.sha256((r/e['path']).read_bytes()).hexdigest()!=e['sha256']]; print({'checked':len(m['files']),'mismatches':bad}); raise SystemExit(bool(bad))"
```

若可执行项目，使用 Windows / CPython 3.14.0 建立新 venv，`python -m pip install -r requirements.lock.txt`；全部 pytest 和 D4 恢复不需要模型 key，真实 E01 需要本地 `.env` 的 `OPSPILOT_MODEL_API_KEY` / `OPSPILOT_MODEL_NAME`，自定义端点才填 BASE_URL。网络只用于安装/真实模型；业务 HTTP 是 loopback。新 DB/checkpoint 命令见根 README 与 D7 DEMO。无法执行时区分缺凭证/依赖环境与实际代码缺陷；纯离线阅读不等于重新运行通过。

## 必须回答的八项问题

1. 实现是否仍是唯一 S1 401 凭证引用故障 Agent？是否引入无收益且未在冻结范围内的设施？历史归档规划不作为已实现代码。
2. 调查 → Gate → Plan → Approval → Intent → Domain CAS → 同身份 HTTP Verification → Frozen Report → DELIVER 是否真的贯通？区分实际 HTTP/MCP/事务与 fixture、测试 helper、自动模拟批准。
3. F1 首次执行前的持久 Intent 和相同摘要重放、F2 计划失效竞态、F3 两种独立许可/回执与工单幂等，是否有源码和真实失败注入支持？
4. 作用域、工具参数、双租户边界、Memory/Skill 不扩权、Gold 隔离与撤销后恢复检查，是否在实际代码路径生效而非只写 Prompt？
5. D6 的 9 PASS + E10 PARTIAL、模型 smoke 4/5、pytest 64/64、40 模型 / 33 MCP / 102725 Token，以及 D7 独立分母是否诚实？是否把控制测试冒充模型、把安全停止计恢复或丢掉失败？
6. 哪些仅在本地 Demo 成立，哪些尚未实现？是否有能造成未经批准写入、重复业务副作用、越权读取或伪造回执的具体可复现缺陷？
7. 是否能按 D7 在干净目录和锁定环境复现？无法复现时是代码阻断还是凭证/环境限制？D7 首轮导出失败及最小修复是否足够解释？
8. 是否有可向校招 Agent Engineering 讲清楚的工程主线？指出最多 3 个真正改变结论的缺陷，不生成未来通用平台愿望清单。

## 指定输出

```text
最终结论：ACCEPT / ACCEPT_WITH_LIMITS / BLOCKED
审查对象：<MANIFEST source_snapshot_sha>；材料完整性：COMPLETE / PARTIAL（缺项）
1. 原始目标与实际实现是否漂移（代码/证据）：
2. 各层已实现/未实现及复现结果：
3. F1/F2/F3 与 Control Safety：
4. D6/D7 真实结果、失败与分母：
5. 用户应亲读的最多 8 个源码入口：
6. 最多 3 个实质问题，每项提供：
   P0 BLOCKER / P1 LIMITATION / UNVERIFIED
   合同条款；文件/函数；复现或证据；影响面；最小处理/明确接受边界
7. 不应继续投资的事项：
8. 可以如实用于简历的工程主线：
```

无证据推测写 UNVERIFIED，缺材料写 UNVERIFIABLE 和具体缺项；冻结范围外特性归 P1 Backlog。只有已证明阻断 P0/复现的问题才要求最小修复与针对该条复核，不重开完整架构评审。最终是否接受差异由真实主 Agent/第三方/用户裁决，本包不替他们作结论。
