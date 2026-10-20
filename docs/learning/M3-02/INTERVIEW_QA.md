# M3-02 面试问答

## 1. 你如何避免长对话无限增长？

**30 秒回答：** 每次调用前先按模型预算拆分 Context 块，再保留近期交互。对话较长时可生成带来源引用的摘要，但摘要只作派生上下文，使用前要验证它依赖的来源仍有效。

**2 分钟展开：** `context_engineering.py` 负责 Token 估算、预算和块优先级，`chat.py` 将这些策略应用于持久聊天。Recent Window、Rolling Summary、Hybrid 都保留了实际运行记录。摘要本身不能提升为当前事实，也不能覆盖 Domain Evidence。真实策略对照中 Recent Window 成功并消耗 2,799 Provider Token；Rolling Summary 和 Hybrid 都因 `CHAT_ATTEMPTS_EXHAUSTED` 失败，所以现有证据不足以宣称摘要策略更优。

**可能追问：** Token 估算会不会与模型账单不同？会。估算服务于预算和裁剪；Provider 返回的 usage 才是可用的实际 token 记录，缺失时应标为不可得。

**证据：** `docs/evidence/vnext/m3-02-03/runs/strategy-comparison-03/TRACE.json`、`RESULTS.json`。

## 2. 为什么摘要需要来源依赖？

**30 秒回答：** 摘要是从历史消息和证据派生的。如果源消息或引用 Evidence 被撤销、过期或失效，旧摘要可能继续传播过时内容，因此每次使用前都要复核依赖。

**2 分钟展开：** `chat.py` 维护摘要的依赖引用并检查摘要文档完整性。准备压缩和发起后续调用时分别核验来源，保持摘要与原始持久记录之间可追踪。撤销后的来源不应通过摘要重新进入上下文。该设计让摘要成为可重建的缓存，而不是第二份事实库。

**可能追问：** 如果某个来源失效怎么办？排除依赖它的摘要或重建摘要，再用当前有效来源准备 Context。

**证据：** `tests/test_m1_dynamic_investigation.py` 中的来源有效性和撤销回归；`ctx` 相关测试与 `RESULTS.json`。

## 3. 如何评估压缩策略？

**30 秒回答：** 冻结相同对话输入和判分标准，记录最终回答是否完成、Provider token、延迟、错误和摘要调用。失败也保留，不能只挑成功样本。

**2 分钟展开：** M3-02 使用真实 DeepSeek 对同一场景比较 Recent Window、Rolling Summary 与 Hybrid。Recent Window 用 2,799 token 完成；Rolling Summary 与 Hybrid 分别消耗 6,020 和 4,640 token 后预算耗尽，没有最终回答。结果说明特定运行有效，不足以证明总体策略效用；报告因此保留 `NOT_PROVEN`。

**可能追问：** 会不会动态策略优于规则策略？当前证据没有证明这一点，不能据此作性能承诺。

**证据：** `runs/strategy-comparison-03/TRACE.json`、`FAILURES.md`。

## 4. 为什么 CHAT_READONLY 不应改变业务 Graph？

**30 秒回答：** 持久聊天和业务调查是不同执行路径。只读回答可以帮助用户理解，但不能改变业务 Task、Gate、Plan、审批或动作授权。

**2 分钟展开：** Context 允许模型看到用户消息和经过验证的上下文，但可执行工具及状态写入仍受业务 Domain 控制。只读聊天不会把普通对话转成正式纠错或授权。业务输入必须通过专用 TaskControl 协议进入 Investigator，再经 Evidence Gate 和审批链。

**可能追问：** 模型说“已经修复”怎么办？以同身份在线 HTTP 结果和 Domain 回执为准，模型文字不构成恢复证据。

**证据：** `chat.py` 的只读路径与 `tests/test_m1_task_control.py`、M1 回归。
