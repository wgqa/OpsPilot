# 失败与未运行项

1. 首次 pytest 因 Windows 默认临时目录权限失败；原始本地日志 `red-backend.log` 保留。换用本次隔离工作树中的唯一 basetemp 后，获得与产品缺口有关的 `red-backend-targeted.log`（2 项预期失败）。
2. 首次 Node 以 strip-only 运行 TypeScript 时不支持参数属性；`red-frontend.log` 保留。改用 Node 的 `--experimental-transform-types` 后得到真正的稳定操作 ID RED（原始字节压缩为 `red-frontend-targeted.log.gz`，未修改本地原始日志），修复后通过。
3. 第一次完整本地旅程沿用了面向 HTTP 202 的通用确定性替身，答复不贴合 401 问题；保留 `TRACE-initial-fixture.json` 及 `worker-journey-initial.log`。后续使用明确的 401 确定性替身；不以替身答案推断真实模型效果。
4. 浏览器、真实 Provider 和新增同 Session 旅程中的审批/修复写入均未运行。既有 D3 定向回归包含隔离 Demo 的模拟审批和写入；没有生产或外部业务写入。历史浏览器 STOP 和 S1 写入延期门禁保持有效。未进行全量 pytest；报告中的 106 项为指定相关套件。
5. 尝试清理本次工作树中新建的 `.pytest-ar05-*` 临时目录时，执行环境自动审查返回 `blocked by policy`，未给出更具体原因。目录原样保留，未尝试绕过；不属于提交内容。
