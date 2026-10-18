# M1-06 验收计划修订记录

## Amendment 01 — 更新 M1-04 浏览器角色页面就绪断言

- **发现时间 / Run：** `2026-10-18T11:56Z` / `runs/20261018T115200Z/m1-04/runs/20261018T115410Z`。
- **原样失败证据：** `logs/m1-04-runner.txt`、`m1-04/runs/20261018T115410Z/RESULTS.json`、`m1-04/runs/20261018T115410Z/logs/browser-full.attempt-01.txt`、`m1-04/runs/20261018T115410Z/logs/api-server-first-process.log` 及同一 Run 的 screenshots。
- **触发事实：** Edge M1-04 `full` 在 support-a/suppport-b 登录、跨租户 404 检查及双角色流程末段运行。approver-a 登录 API 返回 HTTP 200，`GET /api/approvals/pending` 返回 HTTP 200；Playwright 随后因为始终等待 `.rail-footer` 而超时。当前 `frontend/src/App.vue` 的 APPROVER 界面明确使用 `.approval-center`，`.rail-footer` 只在 SUPPORT workspace 中。故此为浏览器 helper 的过时 selector，现有证据未显示身份验证/权限缺陷。
- **受影响验收项：** M1FIN-02 的 M1-04 browser 入口未完整结束；M1FIN-06 的浏览器审批者只读 UI / 未列出 Origin 尾部断言未在该次入口完成。该次 Run 标记 FAIL，不能从部分成功宣称整项通过。
- **最小变更：** 仅修改 `frontend/e2e/m1-04-browser.mjs::login()`：SUPPORT 仍等待 `.rail-footer`；`approver-*` 等待 `.approval-center`。不改 UI、API、权限、输入、Gold、超时、测试范围或业务代码。
- **独立重跑：** Amendment 后使用全新 Domain SQLite、Checkpoint SQLite、随机口令与监听端口，完整执行 M1-04 Edge smoke；原失败目录只读保留，修复后结果另开时间戳目录。随后必须新鲜复跑定向回归与完整 pytest。
- **Gold 影响：** 无。仅修正页面就绪探针，使其指向当前角色页面；所有冻结的 M1FIN 判据、输入与安全断言不变。
- **修复与复跑结果：** selector 修正提交 `d74517d925cebb6e99c38dbbc01919c8064a44ed`；fresh Run `20261018T115753Z` 为 `BROWSER_PASS_FULL_PYTEST_PENDING`，9 项 browser checks 中 8 项为 `true`，`NL-05` 明确留给 N1-09/10/11 定向测试。Fresh 完整 pytest 116/116、关键定向 pytest 9/9。原失败 Run 保持 `FAIL`，没有重写或从尝试分母中移除。
