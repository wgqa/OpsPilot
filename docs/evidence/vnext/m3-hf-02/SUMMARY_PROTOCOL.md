# B 实验开始前冻结的准确来源与判据

本文件与B_INPUTS.json独立提交后才启动3600预算的长对话。A-VALIDATION.json已确认A阶段技术门禁PASS；主Agent最终验收仍待定。生产源码无变更。

- 来源Task：`task-c139d0d1-9e07-4055-9b95-10316384903a`。它先作为A阶段只读目标完成撤销和恢复检查；A验证落盘后，另以approver-a正常Web审批当前Plan，实际执行独立REPAIR v9→v10、同身份HTTP200验证、冻结报告和DELIVER，才成为本实验新可信来源。该新增审批不是来自聊天或Memory。
- 新Episodic：`episodic-6b1aaa89-3267-49f0-85f9-b2f2420a31fb`，ACTIVE v2，digest `1ac68e744d2f329a4c013791b64880edde8a2bab7e17206eea6691e4a2669a53`。由support-a的正常Web候选命令创建、approver-a正常Web确认。旧Episodic E1仍REVOKED v3，没有复活。
- 目标Task：`task-b1f6c544-8733-42ad-b88e-d69d58a151b9`，与来源不同；Session `session-c3380e79-8b86-46a0-8f95-99ae2629297c`。目标准备阶段已用12000默认预算执行独立Investigator `run-4d17cbe0-3d00-48e1-82dc-78740b956fb6`，取得当前v11/401的MCP事实；随后停在待审批，不执行动作。
- Fixture：既有显式test fixture仅把来源修复后的v10递增为v11，Scope/Policy/Principal/账本/回执/Memory不变；不是Agent成果。

## 准备失败及来源选择补充

SCOPE中“另一来源Task C”是准备路径而非Gold业务终态。实际创建的Task `task-98a94a8b-deb8-47c8-90fb-81a2350c3806`因原输入的否定Scope表达进入WAITING_INPUT，正式澄清后同Task仍WAITING_INPUT，均0 Provider/MCP；两次前置检查失败、原输入和Run保留，不称其已修好。没有为此创建新库或放宽意图守卫。最终选择上述已经具备真实独立获批结果的原目标Task作为新来源，保持来源可信、跨Task和全部安全判据不变；本补充在摘要实验执行前固定，非追溯修改旧Gold。

## 固定参数与停止线

HYBRID；输入3600、输出预留512、window16384、安全余量1024；tiktoken cl100k_base。只在独立API进程通过既有环境配置选择该预算，A阶段和目标取证准备记录为12000，二者分别统计。B_INPUTS.json SHA256：`d13d180ff9b586bc6c07c53651a8c23fac768fdffd2c104d8efa07e00642d40a`。

ACTIVE最多8轮，原SDK0次自动重试、每Run回答与压缩总尝试最多3，不增加Run预算；最多24个ACTIVE阶段Provider尝试。固定输入逐项执行，不改措辞追求过关。每轮回答限180字。第6轮是普通只读语义澄清，不是假冒CORRECT_TASK_INPUT，不能改变Graph/Plan。

预期：第1轮助手引用Episodic真实历史v9→v10/200并区分当前v11/401；recent窗口固定12条消息，超过3600预算时，早期该助手成为可压缩历史；真实模型Summary必须持久化并带到该助手和Memory的依赖，且随后至少一次真实Provider请求实际使用该Summary。

8轮内无法形成目标依赖或发生预算安全停止，停止ACTIVE扩展并报告原因，不增加轮数、输入预算或直接插表。成功则撤销新Episodic，执行第9轮，要求旧Summary及派生助手通过结构化依赖校验失效，实际请求与Manifest一致。重启同Domain/Checkpoint Worker后第10轮，旧Summary不能复活。第9/10轮均原3次尝试；允许有界重建或预算安全停止，不能谎称回答或业务恢复成功。

## 内容与来源判据

检查Memory ID/version/digest、正文/Experience摘要、完整资产集合、原始Message digest、Summary ID/version/digest/依赖、实际序列化请求的结构与排除集合。只保存限定片段和hash；完整Prompt仅内存检查。比较实际Token与估算，不用长度或调用次数宣传智能；不重新刷Memory收益对照。
