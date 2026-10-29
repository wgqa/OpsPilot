# 原始失败与范围限制

- red-01：新 worktree 没有 basetemp 的父目录，3 errors；测试准备失败，不是有效业务 RED。
- red-02：3 failed；真实认证 Session 请求新入口/资料范围均 404，有效接口 RED。
- green-api-01：沙箱不允许 native shell 写新 worktree 日志，测试未启动；工具返回的 shell exit 0
  不是 pytest 成功。后以限定 worktree/免费测试的自动权限复核执行，未绕过安全限制。
- green-api-02：13 passed，接口及资料模块 GREEN。
- loop-01：3 failed / 1 passed；真实配置读取不匹配 Runtime 接口。
- loop-02：3 failed / 1 passed；本地替身缺少 run_manager 参数，测试适配问题。
- loop-03、04：2 failed / 2 passed；两个 Run 来源关联入口都拒绝新只读核心，修复后继续保留
  普通 Chat 的拒绝测试。未删除授权/版本/TTL/作用域验证。
- loop-05：1 failed / 3 passed；MCP dict 的 JSON 内容未被装入工具结果，Knowledge 来源丢失。
- loop-06：21 passed，含 OS 退出 86 → 新进程同 Run 恢复。
- final-core-01：1 failed / 23 passed；新增撤权测试用了不存在的 version 列，未真正撤权。
  改为 principal_version 并断言更新一行，不修改 403 预期。
- final-core-02：24 passed；后续又加入并发预留与成对真实事实测试，最终数量见 RESULTS。
- frontend-node-final：Node strip-only 不支持原有 TS parameter property，准备错误；改用
  --experimental-transform-types，不改业务代码避开解析。
- frontend-build-final：2 项类型错误；修正新字段的可空值和事件 value 的安全收窄。
- 前端子任务另有 ESLint HTMLSelectElement 全局缺失与测试夹具字段名问题；其原始日志一并保留。
  最终 23 项 Node、TypeScript/构建、变更文件 ESLint 均有独立日志。
- full-01：420 passed / 7 failed。七处旧迁移测试仍断言最新 Schema=17；新版本为18。
  原有保留行、Plan hash、权限和幂等断言未放宽，只更新目标版本断言。原失败留存。
- 历史 C1 Follow-up 测试默认向旧 behavior-red-trace.jsonl 追加新产物；每轮新产物另存本目录，
  原文件按原 Git Blob 恢复并核对。没有把新产物提交成历史证据。已废弃 Intent 的旧 C1 RED
  文件单列 NOT_RUN，不增生产兼容分支，不改变旧 Gold。

- correction-01：原 Worker 更正链执行后，导出脚本使用了错误的答案表名，导出失败。
- correction-02：导出成功，脚本错误地把控制修订只算一次；原协议受理与应用各提升一次。
  核对 task_control.py 后保留原协议，测试加强检查受理版本、应用版本和 Message seq。
- correction-03：新 Run 已 SUCCEEDED、E1交付正确，但脚本错误要求用户交付 JSON 中含英文
  UNKNOWN；原交付保存自然语言“E1当前处理未知”。未改模型或生产输出。
- correction-04：同一冻结更正目标在新的独立副本复验，exit0；新Run两条真实MCP观察、
  一条PARTIAL用户答案，正确区分 E1/E2，无修复或交接写入。全部为免费模型替身。

真实 Provider=NOT_RUN、浏览器=B-11 HOLD/NOT_RUN。没有用确定性模型结果充当真实智能效果。

提交前证据扫描第一次将 task-UUID 中的 sk- 子串误识别为密钥，停止审计（exit1）；
加入完整前缀边界后复核，537处 Task ID 子串被正确排除，真实前缀和可用环境密钥均0匹配。
这是扫描准备问题，不是 Provider 调用或产品失败；业务源码和原始运行日志未改变。
内部两个子任务触发平台用量限制；主实施者接手修复/回归，内部审查不是主 Agent 独立验收。
所有本地 HTTP 业务数据仅隔离测试库，故障/初态由测试准备；没有模型发起修复、重发或交接。
