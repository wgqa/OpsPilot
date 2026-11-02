# AR-03-WEB-01 安全发布清单

## 发布边界

- Repo：`wgqa/OpsPilot`
- 安全发布分支：`codex/ar03-web-01-safe`
- 可信基线：`bf3c4c8e7a98fce06975f0510f3d56c2cdc6d480`
- 原始候选 HEAD（仅本地保留）：`dc38634a8219e8eb1384b8d6631b790a81b4c317`
- 原始候选提交：`42de016ccdca72c14bafea22c60f8e10246fe3e8`（实现与完整原始证据）；`dc38634a8219e8eb1384b8d6631b790a81b4c317`（推送阻断记录）
- 安全分支从可信 Base 新建；没有 cherry-pick 或继承上述原始候选提交历史。原始分支与证据未修改。
- `origin/main` 本地 ref 为 `ec8c3582f6d145eec9979c43607302731411ead8`；在线远端因网络不可达而 `UNVERIFIED`。
- 规则 Blob（从 Base 读取）：North Star `1f737712c7a36ceb34433ac09c3fbba3c3305542`；AGENTS `32c45506cceeaa8c76a5c56bf8360ff476b58856`；项目 Skill `d405c8d413d633824b279202cc1503dab4cf0b03`。冻结 Cases `c29b5cf7630fa838a365634d0df5f9f0f2bfa834`、Gold `88d5e6f40f027ce2622b957d8ab32b8d2b827381`，未改写。

## 拟公开文件逐项检查

| 文件 | 用途 | 脱敏情况 | 敏感内容判断 |
|---|---|---|---|
| `frontend/src/App.vue` | 修复 Session Messages 已安全读取但被并行 Inspector 结果阻塞显示的 UI readiness 竞态；只改变前端读取投影时序 | Diff 仅含 UI 读取/响应代次逻辑；没有新增凭据、URL、业务身份或测试数据 | 不含敏感内容 |
| `frontend/e2e/ar03-web-01.mjs` | 可复核的 Playwright 验收脚本 | 本地登录口令改为必需的 `AR03_WEB_LOCAL_PASSWORD` 环境变量；脚本中无口令。循环地址仅供 localhost 测试。运行生成的原始 ID/DOM 结果不得加入公开提交 | 提交文件不含凭据或个人信息；运行产物需留在本地 |
| `experiments/ar03_web_01/run_server.py` | 只启动隔离 replay/fixture API 与 Worker | 口令来自同一环境变量；Provider 明确禁用；日志输出不含绝对数据库路径或 Fixture 完整内容；只绑定 loopback | 提交文件不含凭据、个人信息或生产地址 |
| `docs/evidence/ar-03/web-01/SAFE_RELEASE_MANIFEST.md` | 记录来源、纳入/排除清单和脱敏依据 | 不含本机用户名、绝对路径、真实会话/运行 UUID | 不含敏感内容 |
| `docs/evidence/ar-03/web-01/REPORT.md` | 说明用户可见结果、实现 Diff、验证级别和限制 | 只用案例别名；不含原始 ID、个人信息或本机路径 | 不含敏感内容 |
| `docs/evidence/ar-03/web-01/RESULTS.json` | 机器可读结果与 source/run 对应摘要 | 真实标识统一映射为 `A-*`、`B-*`、`F-*` 别名；不含路径或凭据 | 不含敏感内容 |
| `docs/evidence/ar-03/web-01/TRACE.jsonl` | 保存来源关联、事实观察和结果状态 | 对 Session/Task/Message/Run/Event/Observation 做稳定别名映射；只保留必要测试事实 | 不含敏感内容 |
| `docs/evidence/ar-03/web-01/runs/STATIC_CHECKS.md` | 汇总本次安全分支静态检查及原候选所跑测试 | 命令路径简化；不附原始环境日志或个人路径 | 不含敏感内容 |
| `screenshots/deterministic-full-flow-safe.png` | 展示一次提交后的用户问题和正式 Assistant 答复 | 从原始浏览器图像裁切聊天区域；不透明遮挡覆盖订单/Event/Delivery 标识行；去除账号、侧栏 Session、Task/Run 标识与 Inspector | 脱敏副本，无凭据/个人信息 |
| `screenshots/real-replay-a-invalidated-safe.png` | 展示历史真实模型答复来源失效后的安全提示 | 裁切聊天区域，去除账号、Session、Run、Message/Observation/Evidence ID 和来源细节；只显示原问题及失效提示 | 脱敏副本，无凭据/个人信息 |
| `screenshots/program-limit-replay-safe.png` | 展示程序限制与模型回答的区分 | 裁切聊天区域，遮挡内部异常码，去除账号、Session、Run、Message/来源标识 | 脱敏副本，无凭据/个人信息 |

## 图片来源与处理

三张公开截图均是已有 Microsoft Edge 截图的确定性像素裁切/遮挡派生物；没有重拍、合成或改写 UI 文本。原截图仍留在原候选分支。原图 SHA-256：deterministic `3B37E55773BEDC0116BE7255CAB7AD315365DF63A95773A516F8576E92FCB118`；real replay A `B40D9D0F6E1B9DD09A1086706999AAF6488E8AB0A4800279BB4C50DE0EA13ABA`；program limit B `4F835B64CB6E33CD2FE60AF004060F4D7C8159ACAF7FF95D1791B7C2C6318963`。

公开派生图 SHA-256：deterministic `00B988DA1ACDB368DF76E23AE113577E57D4A0AB691EA20CE708E6772C1AE1AA`；real replay A `C08077C59D4D2CE31699A0A476981FC1891658C62B5C4555C38E983AEF9F0BBF`；program limit B `562032E0AF1F48B48E826ED82243B345E5D9F23715BFE9BC796AD4D1B600CF43`。

## 原候选资产审查

Base 到原始候选共 `46` 个路径。源码/测试入口中仅上表的 `App.vue`、Playwright runner 和隔离 server 被审核后纳入；原候选全部其它文件均未复制到安全分支，原样保留在本地原始分支：

- `docs/evidence/ar-03/web-01/FAILURES.md` — 原始运行输出/辅助提取文件，含逐条会话、运行、Observation、环境或失败细节；仅保留在本地原候选分支。
- `docs/evidence/ar-03/web-01/PLAN.md` — 原始运行输出/辅助提取文件，含逐条会话、运行、Observation、环境或失败细节；仅保留在本地原候选分支。
- `docs/evidence/ar-03/web-01/PREFLIGHT.md` — 原始运行输出/辅助提取文件，含逐条会话、运行、Observation、环境或失败细节；仅保留在本地原候选分支。
- `docs/evidence/ar-03/web-01/REPORT.md` — 原始运行输出/辅助提取文件，含逐条会话、运行、Observation、环境或失败细节；仅保留在本地原候选分支。
- `docs/evidence/ar-03/web-01/RESULTS.json` — 原始运行输出/辅助提取文件，含逐条会话、运行、Observation、环境或失败细节；仅保留在本地原候选分支。
- `docs/evidence/ar-03/web-01/TRACE.jsonl` — 原始运行输出/辅助提取文件，含逐条会话、运行、Observation、环境或失败细节；仅保留在本地原候选分支。
- `docs/evidence/ar-03/web-01/fixture-failure.json` — 原始运行输出/辅助提取文件，含逐条会话、运行、Observation、环境或失败细节；仅保留在本地原候选分支。
- `docs/evidence/ar-03/web-01/fixture.json` — 原始运行输出/辅助提取文件，含逐条会话、运行、Observation、环境或失败细节；仅保留在本地原候选分支。
- `docs/evidence/ar-03/web-01/replay-a-failure.json` — 原始运行输出/辅助提取文件，含逐条会话、运行、Observation、环境或失败细节；仅保留在本地原候选分支。
- `docs/evidence/ar-03/web-01/replay-a.json` — 原始运行输出/辅助提取文件，含逐条会话、运行、Observation、环境或失败细节；仅保留在本地原候选分支。
- `docs/evidence/ar-03/web-01/replay-b.json` — 原始运行输出/辅助提取文件，含逐条会话、运行、Observation、环境或失败细节；仅保留在本地原候选分支。
- `docs/evidence/ar-03/web-01/revoked-replay.json` — 原始运行输出/辅助提取文件，含逐条会话、运行、Observation、环境或失败细节；仅保留在本地原候选分支。
- `docs/evidence/ar-03/web-01/screenshots/deterministic-after-reload.png` — 原始运行输出/辅助提取文件，含逐条会话、运行、Observation、环境或失败细节；仅保留在本地原候选分支。
- `docs/evidence/ar-03/web-01/screenshots/deterministic-authorized-project-and-order.png` — 原始运行输出/辅助提取文件，含逐条会话、运行、Observation、环境或失败细节；仅保留在本地原候选分支。
- `docs/evidence/ar-03/web-01/screenshots/deterministic-full-flow.png` — 原始运行输出/辅助提取文件，含逐条会话、运行、Observation、环境或失败细节；仅保留在本地原候选分支。
- `docs/evidence/ar-03/web-01/screenshots/fixture-failure.png` — 原始运行输出/辅助提取文件，含逐条会话、运行、Observation、环境或失败细节；仅保留在本地原候选分支。
- `docs/evidence/ar-03/web-01/screenshots/replay-a-after-reload.png` — 原始运行输出/辅助提取文件，含逐条会话、运行、Observation、环境或失败细节；仅保留在本地原候选分支。
- `docs/evidence/ar-03/web-01/screenshots/replay-a-failure.png` — 原始运行输出/辅助提取文件，含逐条会话、运行、Observation、环境或失败细节；仅保留在本地原候选分支。
- `docs/evidence/ar-03/web-01/screenshots/replay-a-sources.png` — 原始运行输出/辅助提取文件，含逐条会话、运行、Observation、环境或失败细节；仅保留在本地原候选分支。
- `docs/evidence/ar-03/web-01/screenshots/replay-b-after-reload.png` — 原始运行输出/辅助提取文件，含逐条会话、运行、Observation、环境或失败细节；仅保留在本地原候选分支。
- `docs/evidence/ar-03/web-01/screenshots/replay-b-sources.png` — 原始运行输出/辅助提取文件，含逐条会话、运行、Observation、环境或失败细节；仅保留在本地原候选分支。
- `docs/evidence/ar-03/web-01/screenshots/revoked-source-hidden-after-reload.png` — 原始运行输出/辅助提取文件，含逐条会话、运行、Observation、环境或失败细节；仅保留在本地原候选分支。
- `docs/evidence/ar-03/web-01/screenshots/revoked-source-hidden.png` — 原始运行输出/辅助提取文件，含逐条会话、运行、Observation、环境或失败细节；仅保留在本地原候选分支。
- `docs/evidence/ar-03/web-01/traces/fixture-green/domain-audit.json` — 原始运行输出/辅助提取文件，含逐条会话、运行、Observation、环境或失败细节；仅保留在本地原候选分支。
- `docs/evidence/ar-03/web-01/traces/fixture-green/server-start.json` — 原始运行输出/辅助提取文件，含逐条会话、运行、Observation、环境或失败细节；仅保留在本地原候选分支。
- `docs/evidence/ar-03/web-01/traces/fixture/api-after-failed.json` — 原始运行输出/辅助提取文件，含逐条会话、运行、Observation、环境或失败细节；仅保留在本地原候选分支。
- `docs/evidence/ar-03/web-01/traces/fixture/server-start.json` — 原始运行输出/辅助提取文件，含逐条会话、运行、Observation、环境或失败细节；仅保留在本地原候选分支。
- `docs/evidence/ar-03/web-01/traces/replay-a-final/domain-audit.json` — 原始运行输出/辅助提取文件，含逐条会话、运行、Observation、环境或失败细节；仅保留在本地原候选分支。
- `docs/evidence/ar-03/web-01/traces/replay-a-final/server-start.json` — 原始运行输出/辅助提取文件，含逐条会话、运行、Observation、环境或失败细节；仅保留在本地原候选分支。
- `docs/evidence/ar-03/web-01/traces/replay-a/domain-audit.json` — 原始运行输出/辅助提取文件，含逐条会话、运行、Observation、环境或失败细节；仅保留在本地原候选分支。
- `docs/evidence/ar-03/web-01/traces/replay-a/server-start.json` — 原始运行输出/辅助提取文件，含逐条会话、运行、Observation、环境或失败细节；仅保留在本地原候选分支。
- `docs/evidence/ar-03/web-01/traces/replay-api-projection-diagnostic.json` — 原始运行输出/辅助提取文件，含逐条会话、运行、Observation、环境或失败细节；仅保留在本地原候选分支。
- `docs/evidence/ar-03/web-01/traces/replay-b-final/domain-audit.json` — 原始运行输出/辅助提取文件，含逐条会话、运行、Observation、环境或失败细节；仅保留在本地原候选分支。
- `docs/evidence/ar-03/web-01/traces/replay-b-final/server-start.json` — 原始运行输出/辅助提取文件，含逐条会话、运行、Observation、环境或失败细节；仅保留在本地原候选分支。
- `docs/evidence/ar-03/web-01/traces/replay-b/api-before.json` — 原始运行输出/辅助提取文件，含逐条会话、运行、Observation、环境或失败细节；仅保留在本地原候选分支。
- `docs/evidence/ar-03/web-01/traces/replay-b/domain-audit.json` — 原始运行输出/辅助提取文件，含逐条会话、运行、Observation、环境或失败细节；仅保留在本地原候选分支。
- `docs/evidence/ar-03/web-01/traces/replay-b/server-start.json` — 原始运行输出/辅助提取文件，含逐条会话、运行、Observation、环境或失败细节；仅保留在本地原候选分支。
- `docs/evidence/ar-03/web-01/traces/revoked-fixture-preparation.json` — 原始运行输出/辅助提取文件，含逐条会话、运行、Observation、环境或失败细节；仅保留在本地原候选分支。
- `docs/evidence/ar-03/web-01/traces/revoked-replay/domain-audit.json` — 原始运行输出/辅助提取文件，含逐条会话、运行、Observation、环境或失败细节；仅保留在本地原候选分支。
- `docs/evidence/ar-03/web-01/traces/revoked-replay/server-start.json` — 原始运行输出/辅助提取文件，含逐条会话、运行、Observation、环境或失败细节；仅保留在本地原候选分支。
- `experiments/ar03_web_01/audit_db.py` — 原始运行输出/辅助提取文件，含逐条会话、运行、Observation、环境或失败细节；仅保留在本地原候选分支。
- `experiments/ar03_web_01/prepare_revoked_replay.py` — 原始运行输出/辅助提取文件，含逐条会话、运行、Observation、环境或失败细节；仅保留在本地原候选分支。
- `frontend/e2e/inspect-replay-api.mjs` — 原始运行输出/辅助提取文件，含逐条会话、运行、Observation、环境或失败细节；仅保留在本地原候选分支。

原候选的失败日志、完整 API/SQLite JSON、完整页面截图及逐项 Trace 都包含会话/任务/运行/观察标识、授权状态、测试环境位置或未筛选失败细节，因此不公开。没有凭“新提交删除”来处理敏感文件；安全发布的 Git 历史直接从可信 Base 起步。

## 扫描结论

本轮检查了原候选两提交历史、46 个差异路径、全部文本文件的凭据/Token/Cookie/密码/密钥模式、代码 Diff、报告、结果 JSON、日志、截图和辅助资产。候选文件中未发现 API Key、Bearer Token、Cookie、有效登录凭据或个人信息。发现并从公开测试代码中移除了本地 demo 密码常量；绝对运行路径、原始会话/运行 ID、授权/Observation 明细只留在本地原始分支。公开代码中的 `127.0.0.1` 仅为本机 loopback 测试配置，不是服务内网地址或生产 Endpoint。

边界：本地 `git ls-remote` 未能连通 GitHub:443，因此在线远端仍为 `UNVERIFIED`；安全分支只会在本清单检查完成后尝试正常 Git 推送，不使用提升权限或其他传输路径。

## 安全工作树中的本地原始日志

本次复核发现，安全工作树的 `runs/` 还存在未跟踪的原始 `.log` 文件。扫描显示其中部分含本机绝对路径、测试身份或原始 UUID。它们没有加入发布暂存区，保留在本地工作树；发布版本只纳入上述脱敏的 `runs/STATIC_CHECKS.md`。这批本地日志包括 `eslint-changed-files.log`、`eslint-final.log`、`fixture-green-final.log`、`fixture-green.log`、`frontend-build-final.log`、`frontend-build.log`、`node-syntax-final.log`、`offline-regression-final.log`、`offline-regression.log`、`playwright-replay-a.log`、`python-syntax-final.log`、`replay-a-after-readiness-fix.log`、`replay-a-green-final.log`、`replay-a-green.log`、`replay-a-red-rerun.log`、`replay-api-diagnostic.log`、`replay-b-api-discovery.log`、`replay-b-green-final.log`、`replay-b-green.log`、`revoked-replay-browser.log`、`server-replay-a.log`。原始候选分支及其中已提交的原始证据保持不变。
