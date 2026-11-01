# HF02 失败与修复记录

本文件逐项保留本轮失败，不覆盖冻结 Gold、旧 HF01 报告或历史日志。

1. **00 — 测试准备未运行。** 第一次写日志时 `runs/` 尚未建立，pytest 没有启动。原始错误在 `runs/00-log-directory-setup-error.txt`。
2. **01 — MCP 子进程注入未命中。** 首次试图用临时 `sitecustomize` 注入 Receiver 查询失败，但导入路径没有包含当前仓库根目录；没有以此结果判定业务行为。日志在 `runs/01-red.log`。
3. **02 — 有效 RED。** 补齐临时 MCP 子进程导入路径后，新增测试得到 `1 failed, 1 passed`。未暴露 `get_order_status` 被旧实现持久记录为 `OK`，其 `result_json` 为 JSON null；冻结核心缺陷得到复现。Receiver 失败测试证明注入确实运行，并通过错误无成功 Evidence 的检查。原始日志及真实 Trace 在 `runs/02-red-after-fixture-fix.log`、`runs/TRACE-02-red-after-fixture-fix.jsonl`。
4. **03 — 定向 GREEN。** 最小源码修复后，两个 HF02 用例 `2 passed`。日志和 Trace 在 `runs/03-targeted-green.log`、`runs/TRACE-03-green.jsonl`。
5. **04 — 既有 HF01 断言与新语义不一致。** 首轮组合回归 `41 passed, 1 failed`。唯一失败要求未暴露工具的 `result_json` 为 null；修复后的安全拒绝明确保存 `FAILED / NOT_STARTED` 对象。没有改 Gold 或历史结果，只把仍在运行的 HF01 源测试断言改为验证明确失败对象、无 Observation/Evidence/HTTP。日志保留于 `runs/04-targeted-regression.log`。
6. **05 — 修正后复跑。** 同一组相关回归新鲜运行 `42 passed, 0 failed`，44.71 秒。日志和 Trace 在 `runs/05-targeted-regression.log`、`runs/TRACE-05-regression.jsonl`。

本轮未运行全量 pytest。历史 HF01 `489 passed / 4 failed` 仍是历史事实，不被记作本轮结果。
