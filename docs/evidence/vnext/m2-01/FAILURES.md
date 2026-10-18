# M2-01 运行失败与修复记录

本索引保留全部已知失败尝试及其解释。只有最后的定向/全量日志用作最终通过证据；历史失败没有删除，也没有把 setup error 算成产品 RED。

| 尝试 | 记录 | 观察 | 分类与处置 |
|---|---|---|---|
| 初次旧实现 RED | `logs/pytest-s2fact-red-baseline.txt`、`logs/pytest-s2fact-red-baseline-retry.txt` | 首次调用因 Windows 默认 Temp 权限问题得到 2 个 setup error；retry 使用隔离 temp 后真实复现两项产品失败：有效凭证且缺 Scope 时旧 API 返回 200，旧真实 MCP 目录没有 `get_scope_authz_facts` | 首次尝试是环境错误；retry 是产品行为 RED，保留并由 M2-01 实现修复 |
| Windows Temp 权限重试 | `logs/pytest-m2-01-directed-trace-fields-final.txt` | Windows 默认 `pytest-of-tu me manques` 路径返回 `PermissionError`，7 个 fixture setup error、1 个纯标准测试通过；测试未完整执行 | 环境/命令问题，不计产品失败；后续使用唯一新 `.runtime/m2-01/...` basetemp，定向 8/8 |
| 首次实现定向尝试 | `logs/pytest-m2-01-directed-attempt-01.txt` | 额外 MCP 字段未被 SDK schema 层自动拒绝；合同测试引用了不正确的 trace-schema 必填字段 | 测试发现产品边界；工具通过 MCP Context 校验原始 args，输入使用严格类型；更正测试合同断言，不改冻结标准 |
| 修复后定向尝试 | `logs/pytest-m2-01-directed-attempt-02.txt`、`logs/pytest-m2-01-directed-final.txt`、`logs/pytest-m2-01-directed-final-current.txt`、`logs/pytest-m2-01-directed-strict-attempt.txt` | 逐步重跑后均 8 passed | 已通过；最终源码重跑见 `pytest-m2-01-directed-trace-fields-release.txt` |
| 首次整合全量回归 | `logs/pytest-full-attempt-01.txt` | 19 个既有用例失败，集中于默认 MCP catalog 新增工具破坏 M1 固定工具目录，以及 migration 断言仍假设 user_version=5 | 集成回归阻断；新 Scope 工具改为显式 opt-in，迁移版本断言更新为 6；没有删除 M1 测试 |
| 全量重跑 | `logs/pytest-full-attempt-02.txt`、`logs/pytest-full-final.txt`、`logs/pytest-full-release-final.txt` | 分别为 148 passed，零失败 | 最终源码的命令日志为 `pytest-full-trace-fields-release.txt`，148/148 |
| 早期 HTTP/MCP smoke | `logs/m2-01-real-http-mcp-smoke-attempt-01.txt`、`logs/m2-01-real-http-mcp-smoke-final.txt` | HTTP 401/403/200 成立；早期迭代的 MCP 调用次数为 3，尚未包含错误类型负例 | 不是最终 Trace；最终 smoke 增加额外参数及类型拒绝，调用 4 次 |
| 第一版完整 smoke Trace | `logs/TRACE-before-trace-fields-fix.json`、`logs/m2-01-real-http-mcp-before-trace-fields-fix.txt` | Trace 缺少 Scope/Policy 前后版本与 secret scan 文件清单 | Trace 契约核对发现的证据完整性问题；只补充 smoke 记录器字段并重新运行。冻结 Gold/Rubric/Trace schema 未改 |
| 最终真实 HTTP/MCP smoke | `logs/m2-01-real-http-mcp-trace-fields-final.txt` | PASS；3 个 HTTP 请求为 401/403/200；1 次 tools/list、4 次 tools/call；写入 0；记录 Grant/Policy 前后版本和 Trace 扫描文件 | 最终事实层 smoke |

最终结果是 148 passed；没有遗留失败用例。S2 Provider/浏览器未运行是范围内 `NOT_RUN`，不是隐藏的通过项。
