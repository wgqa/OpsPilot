# M3-CLOSEOUT-01 失败与尝试记录

- 开工环境枚举首次读取opspilot分发版本报PackageNotFoundError；本项目从checkout导入，依赖可用。随后按实际已安装依赖枚举成功。此为检查脚本问题，原始错误仅见工具输出，不冒充已保存原始日志。

- journey-01 首次API启动失败，api.log保留原始异常；运行时观测入口在临时目录执行时未将仓库根目录加入Python导入路径。只修正测试入口sys.path，复用同一已初始化Domain，没有重建环境或改业务数据。

- Task B只读预检：A修复后的200不会通过当前问题类型选择器，不能用该条件证明Episodic实际使用。未降低检索门禁；按任务卡允许的已有fixture路径，另行先记录CASE-B-SETUP，再显式准备版本单调的新合成事故。原冻结Scope的fixture描述S1_MISMATCH是文字标签；真实现有枚举为S1_POS，初始化日志已记录。
- 候选快照检查首次错误读取不存在的created_by列；仅查询失败，无数据修改，改为按实际d5_memories schema只读导出，候选v1原始快照已保存。

- 浏览器原生confirm：Plan批准、Episodic确认、Episodic撤销、正式关键更正四次操作触发后，自动化click等待超时，getJsDialog未返回可操作对象。没有绕过弹窗或改成后台写入；分别请用户在5174点击确认，收到“已确认”后，实际Web POST与Domain事件落库。截图03、07、12、15及api.log保留流程；工具超时的原始返回仅在对话工具记录中，不伪称已另存原始文件。

- 受控崩溃（预期故障，不是一次业务成功）：Task B同Run已有当前MCP与Checkpoint后强制终止本轮自有API树。原始crash-trigger.json、process-events.jsonl、crash-monitor.log保留。一个模型尝试停在RESERVED/PREPARED，是否传到Provider、Token和费用UNKNOWN。重启后同Run回到WAITING_APPROVAL，没有将它称为业务恢复，也未重置预算。

- **GAP-01（未补齐）**：额外Provider请求体观测器只包装了httpx，最终检查发现provider-wire.jsonl仅3条APPLICATION_BOOT。当前本机OpenAI SDK实际用httpx2：本地`.venv/Lib/site-packages/openai/_base_client.py`导入httpx2，`langchain_openai/_compat.py`对OpenAI>=3选择httpx2。已有真实响应ID、Usage及Domain Provenance，但实际传输的经验内容／撤销后请求体没有被捕获。没有补造离线请求当原始调用，没有声称捕获成功，没有修改历史日志；本轮因此PARTIAL，停止等待主Agent。完整Provider请求体不具备独立证据，不能以本报告其余成功项目抵消。

- 报告只读对账脚本首次将初始化快照中的JSON字符串与导出后的解码列表直接比较，报`AssertionError: {'no_scope_writes_in_journey': False}`。只读核对确认Scope、版本、updated_at均相同，差别仅`'["orders.read"]'`与`['orders.read']`。修正证据脚本为两端统一JSON解码后16项对账通过；未修改Domain或测试断言，未修改原快照。首次错误见对话工具输出，成功重算原始stdout保存在runs/evidence-analysis.log。

- 一次日志阅读误用`Get-Content -LiteralPath .../*.log`导致通配符不展开，随后改用`-Path`正常读取。这是只读检查命令错误，不是产品失败；原返回仅见对话工具记录。

- 真实Summary依赖撤销：两次Chat没有自然生成Summary，计0，NOT_COVERED。新鲜24项定向中有消息→摘要→后续回答失效及独立Memory撤销回归，不能替代真实Episodic撤销摘要旅程或任意多层DAG证明。

- 历史原库两次WORKER_RETRY_EXHAUSTED本次没有复现。根因仍未知，不修改旧失败记录，不因新的隔离库正常就关闭该问题。本轮初始化仅一次，首次启动导入错误后复用原隔离库，未通过反复换库躲避Worker问题。

- 所有货币费用NOT_REPORTED，已知49092 Token之外还有一次中断UNKNOWN。MCP tools/list没有独立原始计数，不虚报；tools/call的10次尝试与10项实际Observation均保留。

没有产品代码RED→GREEN：本轮没有定位到需修改生产代码的直接阻塞缺陷，也没有修改225个用例。新鲜完整225/225、定向24/24、前端3/3通过，不能据此将GAP-01标为通过。
