# Failure History — Stage B Supplement 02

保留本轮所有有效 RED、测试准备错误和中间失败。修正后运行另存为新文件，没有覆盖旧日志。

## 有效 RED

- `runs/red-race-02/node-test.log`：9 项测试中 7 passed、2 failed，exit 1。受控 Promise 证明：同 Task 的旧授权 Inspector 响应在撤权响应后仍被接纳；撤权前启动的消息读取在缓存清理后仍恢复旧助手正文。这两项为本轮产品缺陷复现。

## 测试准备失败

- `runs/red-race-01/output-path-error.log`：运行器从 `frontend/` 工作目录写入相对路径失败，完整 Node 输出未能保存，未取得可用 pytest/Node 结果，因此不计为 RED。
- `runs/green-race-02/node-test.log`：一项新增正向断言先恢复授权再验证撤权过滤，测试排列错误；10 passed、1 failed，exit 1。后调整顺序为先验证失权过滤，再验证新授权恢复。

## 中间 lint 失败

- `runs/frontend-checks-01/eslint.log`：测试代码 `prefer-const` 与无用赋值两项 lint 错误。
- `runs/frontend-checks-02/eslint.log`：去掉 `prefer-const` 后仍有一个无用初始赋值错误。
- `runs/frontend-checks-03/`：测试与 scoped ESLint 通过；后续补充了撤权响应中 Receipt/Evidence 字段断言，因此再执行最终 `green-race-04/`。
- `runs/green-race-03/`：当时的 11 项测试及静态检查通过；随后又加强 RED 对受限 answer/source/receipt/evidence 内容的断言，最终结果以更新后的 `green-race-04/` 为准。

## 未重跑的历史问题

- Supplement 01 中的 API 402 项短路径全量通过、深层 Windows basetemp 的 20 项 checkpoint 创建失败，以及旧 C1 废弃 Intent RED，均保持原文件与原结论。本轮没有修改或覆盖这些历史记录，也没有重跑后将其合并为本轮结果。
- 浏览器/DOM/SSE 与 Provider：按当前明确边界 `NOT_RUN`。
