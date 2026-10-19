# HF-01 运行证据索引

- `ACCEPTANCE_PLAN.md`、`HF_GOLD.json`、`RUBRIC.json`、`EVAL_PROTOCOL.md`：实施前冻结标准，提交 `313dbe7`。
- `runs/development-logs/red-*`：冻结标准下的原始 RED、退出码和故障注入/恢复日志。
- `runs/green-dev-*.txt`：定向补充与逐次 GREEN；包括失败运行，不只包含最后 PASS。
- `runs/full-pytest-*.txt`：各源码修订的全量 pytest 记录；`full-pytest-20624cf.txt` 是最终 171 passed。
- `runs/release-4ad7465/`、`release-8b3f3e5/`：Release 运行器数据/Trace schema 故障及其原始失败记录。
- `runs/release-ee94eac/`：固定真实 48 试次；`RELEASE.json` 锁定依赖和代码摘要，`RESULTS.json` 是原始评分，`traces/` 与 `failures/` 含每条完整记录。
- `runs/release-ee94eac-rescored-20624cf/`：使用最终评分器对原始 48 条结果透明重评；`RESCORE.json` 指明源结果哈希、评分器提交和未重跑 Provider/MCP。
- `runs/release-ee94eac-rescored-752173a/`：保留中间重评，其中 H2 “不足以证明”尚未识别，之后再修 scorer。
- `runs/browser-e2e-01/` 至 `browser-e2e-04/`：原始浏览器验收失败。
- `runs/browser-e2e-final-ce9b790/`、`browser-e2e-final-6299ff2/`：后续浏览器补跑及测试器误判。
- `runs/browser-e2e-final-752173a/`：真实 Microsoft Edge 最终 PASS，含四张截图、浏览器网络 Trace、`RESULTS.json` 内 Provider/MCP/Domain Trace 和结果快照。
- `runs/mcp-stdio-s2-final.txt`、`s1-smoke-final.txt`、`frontend-build-final.txt`：MCP、S1 和前端构建原始控制台输出。
- `LEGACY_SHA256.json`：旧 M2-02 六个冻结产物校验清单。
- `RESULTS.json`：本目录最终机器可读 48 条对照结果，含每行原/复评分、四轴、Trace 引用及模型/MCP/Token/耗时字段。
- `TRACE.json`：Provider、MCP、Web、Domain、安全计数、失败记录和旧 10,003 Gate 证据索引。
- `FAILURES.md`：失败原因、修复顺序和不确定性边界。
