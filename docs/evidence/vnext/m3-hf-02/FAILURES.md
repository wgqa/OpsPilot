# M3-HF-02 尝试与失败记录（持续追加）

- 观测器独立校验首轮成功：真实标记Chat、序列化HTTP请求、Attempt、Provider响应与491 Token均匹配，开始业务前Task数0。旧M3-CLOSEOUT-01观测失败文件保持不变；新观测无完整原始Prompt输出。
- A审批测试脚本首次发送了错误枚举`APPROVE`，API按Schema返回422 INVALID_REQUEST，没有落审批或产生动作。保留A-approval.log和web-commands.jsonl原始失败；检查PlanApprovalRequest后以正确`APPROVED`提交，正常受理。没有放宽Schema或审批守卫。
- A崩溃监视器首次启动时使用了从截断UI标题误补的错误Task UUID。该ID不存在，未触发任何业务Run或进程崩溃。原A-crash-monitor.log保留；终止仅本轮该监视器进程树后，增加测试监视器的存在性检查，并从只读Domain取得完整真实ID。A-crash-monitor-corrected.log记录了真实同Run的5个Checkpoint/1项MCP触发。没有修改生产TaskControl。
- A4受控崩溃保留一项已发出但未取得SDK结果的模型尝试，状态RESERVED；请求体观测存在并不证明已完成或已知费用。实际是否由Provider完成、usage与费用UNKNOWN；恢复新尝试继续消耗原Task预算，总8 MODEL/6 MCP，没有清零。
- B来源案例准备：初次用户输入包含“不自行修复或授予Scope”的否定表达，进入S1_SCOPE_CHANGE_UNSUPPORTED/WAITING_INPUT，0 Provider/MCP。审批前置检查如实失败，保留B-source-approval.log；没有重建Task掩盖失败。通过正常Web CORRECT_TASK_INPUT澄清仅核实当前绑定认证事实，继续同一Task的新Run。此为安全意图守卫的保守误拒现象；尚未进行源码根因裁决，不猜测性改生产代码，也不将其与历史WORKER_RETRY_EXHAUSTED混同。

中断请求和未完成实验不得按0消耗或PASS处理；本文件在最终报告中列出所有新增尝试、摘要失败、未知成本及尚未证明项。

## 后续尝试（追加，不覆盖以上原记录）

- B来源正式澄清仍停在同一Task的WAITING_INPUT，0 Provider/MCP。源码证实`_requires_scope_clarification`扫描旧输入，变更词命中但否定词白名单未覆盖“不自行…授予Scope”。这是P2保守误拒，本轮未改。原失败Task与两Run保留。实验身份冻结前，改为让已有有效Task B获得新的独立审批、真实REPAIR v9→v10/200/报告/DELIVER，再创建E2；不是fixture伪造源成功。
- 第一B第2轮后的浏览器工具曾两次在上一回复尚生成时超过工具等待期限，未产生重复POST。保存当时DOM；为遵守固定输入顺序与轮数，第3–8轮改用正常认证Web API，第1/2/9/10轮为浏览器操作。渠道在web-commands与浏览器证据中区分，不声称全部人工点击。
- 第一B的首个真实Summary仅含seq1–2用户消息，未包含目标Memory/助手，不能算目标DAG。下一压缩`context-compression-2345279c-8da9-40a3-a32d-eda9bc4a1145`确实发送含目标助手/Memory依赖的源材料，但HTTP200后提交抛TaskControlError；当前Probe已跨300秒TTL。未持久化目标Summary、Response ID或Usage；原异常只存class，准确code未捕获。该次Token/费用UNKNOWN。
- 两跳P1 RED01：2项失败中，Semantic为派生回答仍有效的真实断言失败；Episodic是测试准备采用S2路径导致无法选用Memory的准备错误，不拿它当产品缺陷。改用既有S1可信来源测试准备后RED02两项均在撤销后派生回答仍被选用处失败。两份原始pytest日志/exit-code完整保留。独立冻结4ea1657、RED提交ba44a5c后，仅修复35行祖先校验；GREEN26/26、全量227/227。
- 修复后唯一一次真实对照先冻结准确身份与相同输入，再运行8+2轮。准备/控制器/测试脚本耗时使开始Chat时当前Probe已约250秒龄，未达到协议希望在撤销时仍新鲜的条件。第7轮真实压缩`context-compression-4ce7f654-c0d4-4904-b4dd-4352182252b0`在HTTP200后跨TTL再验证抛TaskControlError，0持久Summary；Response ID/Usage未知。ACTIVE仍按8轮停止，没有换预算/延长TTL/第三次运行。
- 修复后第9/10轮真实请求都排除了旧经验/助手，但Evidence先过期、Memory后撤销，不能隔离撤销因果，也不能证明目标Summary跨重启失效。目标Summary实验最终PARTIAL，详见SUMMARY_LINEAGE。
- Worker两个历史重试耗尽仍无原exception/stack。只读核验和两次合成故障注入通过不证明原根因；保持ROOT_CAUSE_NOT_PROVEN，未改生产Worker。
- 汇总脚本首版把初始fixture的JSON字符串与脱敏export已解码list直接比较，误报Scope差异；保留`runs/AGGREGATE-01-projection-mismatch.json`。核对实际grant/policy版本、内容、时间完全相同后，仅规范化测试汇总的JSON列，第二版11/11一致性检查通过。没有改Domain/原始快照/判断标准。

## 未知成本，不计零

实际49次请求/46份完整Usage，已知159690 Token下界；3项UNKNOWN分别是A进程崩溃中的MODEL Attempt及上述两次压缩提交失败。HTTP200不是完整Provider完成元数据；货币价格/账单未采集，费用UNKNOWN。

## 历史材料与停止线

原M3-CLOSEOUT-01 PARTIAL、D6 E10 PARTIAL、原M2/M3 Gold与失败日志均未改。本轮的B失败不会追改旧Gold；所有能力与缺口随新证据一起提交，等待独立验收，不自动进入后续开发。
