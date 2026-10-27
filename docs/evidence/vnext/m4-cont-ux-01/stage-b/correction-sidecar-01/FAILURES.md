# 补差 RED 与失败记录

## 本轮有效 RED

`runs/red-01/node-test.log`：针对批准基线上的真实 Inspector API 响应与确定性正反 fixture，两个断言均失败（0 通过、2 失败）。

1. 保存的 API 快照存在真实 `CHAT_READONLY / BLOCKED / CORRECTION_CONFIRMED` sidecar；修复前 `projectConversation()` 把它作为独立 `RUN_STATUS` 项加入原问题线程，测试得到 `true !== false`。
2. 在新的 Investigator Run 已接管纠错时，同样产生独立 sidecar 状态卡；修复前无法从纠错卡展开查看该 Run。

这不是 API 或 Domain 运行失败，而是前端投影将控制流阻断状态误当成用户未完成业务工作的产品展示缺陷。

## 修复后的证据

- `runs/green-01/node-test.log`：两项通过。
- `runs/frontend-projection-01/node-test.log`：17 项通过，包括已有真实失败、Task 隔离、撤权缓存和来源映射用例。
- `runs/api-regression-01/pytest.log`：20 项通过。
- `runs/typecheck-01/typecheck.log`、`runs/build-01/build.log`、`runs/eslint-01/eslint.log`：退出码均为 0。

所有原始输出按原样保存。更早 Stage B 的 RED、失败记录、Gold 与 Trace 未修改。
