# P1修复后唯一一次真实GREEN旅程

代码修复提交：`00d054aeba196b972255dafd0e7faa03fcd0ce41`，26项定向已通过，完整227项正在新鲜运行。RED协议4ea1657、RED测试ba44a5c保留。原B八轮、TaskControlError失败及原摘要不重写。

准确来源Task `task-b1f6c544-8733-42ad-b88e-d69d58a151b9` 在新的APPROVER认证Web批准后，经既有REPAIR v11→v12、同身份200验证、冻结报告和独立DELIVER成为第三个真实业务案例。新Episodic `episodic-bf9f8893-5c13-4879-9a35-7ba0bda732c0` v2 ACTIVE，digest `cc5ec7bc52e9d6e2591ffa82aec14770dfbc30309fe44102cf5bb2541299588d`。旧E1/E2保持REVOKED。

目标Task `task-0d3394ba-3b79-4a5a-8412-a3a4db3989c7`，Session `session-698a7270-45ad-4e35-a2cd-c3ae7de6bba9`，准备Run `run-ef3a2423-572e-4cc5-a37e-ff086a68878a`。现有fixture单独审计v12→v13，Scope/主体/策略/既有账本不变。准备Investigator使用原12000默认预算，完成后才恢复冻结Chat输入3600；未提高第一次B的预算或轮数。

这是4ea1657预先允许的唯一修复后真实对照。使用原B_INPUTS.json（SHA256 `d13d180ff9b586bc6c07c53651a8c23fac768fdffd2c104d8efa07e00642d40a`），ACTIVE恰好最多8轮，SDK0重试，每Run摘要与回答原上限3；未满8轮若Run失败则停止ACTIVE。新证据单独使用P1前缀。为保持操作时效，8轮正常认证Web API顺序提交并等待前轮终态，浏览器查看真实同Session内容。所有渠道如实记录，不称API调用为人工点击。

八轮内必须有真实Memory→助手→持久Summary→实际Provider请求；观察直接Memory块被裁剪后的派生助手。立即通过独立APPROVER Web撤销，然后第9轮核对祖先和摘要失效，保持当前MCP尚未超过300秒，避免以TTL代替撤销证明。再同库重启Worker，第10轮核对不复活。未实现/失败保留，不继续第三次摘要旅程，不修改原Gold。

服务控制器--resume只复用既有库、Checkpoint和合成口令，明确不再次reset_fixture；实际新启动源码hash、PID和预算保留在process-events/provider-observations。测试入口的重启支持不属于生产Worker改造。
