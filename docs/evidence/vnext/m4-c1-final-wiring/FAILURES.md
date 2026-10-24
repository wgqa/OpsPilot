# RED、失败与中断记录

所有记录均保留；测试准备失败不计作业务复现。未筛选的全量首跑也保留，旧 C1 预实现 RED 没有改写或删除。

| 运行 | 结果 | 归类 |
|---|---:|---|
| `red-01` | collection exit 2 | 测试准备错误：测试模块未能按工作树导入。 |
| `red-02` | collection exit 2 | 测试准备错误：导入了旧主工作区 `task_control.py`，缺少候选分支函数。 |
| `red-03` | collection exit 2 | 测试准备错误：使用了缺少 `langchain_core` 的 Python 环境；PowerShell 路径变量也未设置成功。 |
| `red-04` | 4 errors | 测试准备错误：pytest 默认临时目录无权限。 |
| `red-05` | 3 failed, 1 passed | 有效业务 RED：真实 S3 `model_call()` 的出站正文没有 `prior_readonly_followups`；失效 Knowledge 改变后，调用前校验未察觉来源变化并触发 Provider。空历史正例通过。 |
| `red-wire05` | 1 failed, 343 deselected | 有效预算 RED：用提交中的原版 S3 源码运行 WIRE-05，带历史与移除历史的 Token 估算未体现差异（旧 Prompt 未装入历史）；断言证明历史没有进入预算计算。 |
| `green-01` | 4 passed | 初次接线 GREEN；之后增加了 Token 预算分项断言。 |
| `green-02` | 4 passed | 接线及历史块 Token 估算 GREEN。 |
| `green-03` | 4 passed | 正常调查与解释 Prompt 均包含合法历史结果。 |
| `green-04` | 5 passed | 增加历史上下文超预算时调用前阻断的负例。 |
| `green-05` | 5 passed | 在保留原始 RED 后复跑冻结接线测试。 |
| `green-06` | 5 passed | 最终测试版本；含普通 S3 Prompt 当前性约束与真实 `model_call()` 捕获。 |
| `regression-01` | 120 passed | C1/HF-01/S3/HF 与 Context 定向回归。 |
| `full-01` | 341 passed, 2 failed | 未筛选基线运行：一项是冻结的 C1 预实现 RED；另一项 M2-02 跨进程用例子进程缺少模型初始化配置，返回 73，未调用 Provider。 |
| `full-02` | 342 passed, 1 deselected | 加入本地确定性 no-provider 启动配置，并按旧验收约定排除冻结 C1 预实现 RED。 |
| `full-03` | 中断，exit 1 | 实施方在 63% 左右按 Ctrl-C 终止：发现冻结 WIRE-05 还缺少超预算负例。不是测试断言结果；最终运行改在 `full-04`。 |
| `full-04` | 343 passed, 1 deselected, exit 0 | 最终全量门禁；只排除冻结的 C1 实现前 RED。耗时 308.22 秒。 |

原始日志、命令和退出状态位于同名 `runs/` 子目录。未在任何失败上改写 Gold、弱化预期或隐藏旧失败。
