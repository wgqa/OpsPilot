# HF-01 失败与修复记录

## 有效 RED（保留原始记录）

`runs/red-01.log` / `runs/red-01-exit.txt`：退出码 1，3 failed / 3 passed。

1. 对实际空结果 `documents=[]`、`source_refs=[]`，旧 FixtureModel 仍输出“本次检索的版本化协议/引用见工具来源”一类声明。
2. TaskBinding 合同 v2、用户明确请求 v1 时，结果错误地令 `deployment_version_verified=true`。
3. TaskBinding 默认 v2 时，结果错误地令 `requested_contract_version=2`，掩盖用户没有明确请求版本这一事实。

这些断言在修复前执行并保存；未改变历史 Gold 或预期以消除失败。

## 修复后结果

`runs/focused-01.log`、`runs/focused-02.log`：相关 30 项均通过；`runs/full-01.log`：439 项活跃测试通过。旧文件 `tests/test_m4_autonomy_c1_red.py` 仍按既有历史门禁单独排除，不宣称其通过。

## 证据整理尝试

第一次生成 Trace 时，筛选脚本错误地把 Delivery 的 `receiver_http_status=202` 当作通用字段 `http_status=202`，因此拒绝选中本地 HTTP/MCP 业务记录。检查原始 Observation 后只修正了 Trace 选择字段，未更改业务代码、用例或验收期望。最终五条 Trace 均来自已保存的实际测试运行记录。

## 测试副作用

完整测试期间，既有 C1 行为测试向 `docs/evidence/vnext/m4-autonomy-c1/runs/rev1/behavior-red-trace.jsonl` 追加了一条新运行记录。该路径不属于本修复，且测试前已核对为与 HEAD Blob 一致。运行后将其恢复到该原始 Blob；最终差异中不包含此文件，旧记录保留。

## 远端推送阻断

- Git HTTPS `ls-remote` 与 `push` 均无法连接 `github.com:443`。
- 已连接的 GitHub 集成可读取仓库，但 `create_blob` 与 `create_branch` 写操作均返回 `403 Resource not accessible by integration`。
- SSH 推送因主机密钥未验证而失败；没有关闭主机密钥校验。

因此 `codex/ar02-hf-01` 当前只存在于本地 worktree，远端未发布；没有创建 PR、改写远端引用或触碰 `main`。源码与证据提交 SHA 保留，可在网络/权限恢复后安全推送。

## 未解决 / 未执行

- 真实模型是否遵循来源提示：未验证，Provider 调用 0 次。
- 真实收费请求协议与预算上限：未执行，详见 `COST_GAP.md`。
- 浏览器路径：未运行，遵守既有 STOP。
- 真实线上部署版本：没有授权部署观察工具，故始终报告未验证。
