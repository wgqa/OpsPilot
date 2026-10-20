# M3-CLOSEOUT-01 冻结补证范围

基线：main@95b235f29af2df40b1608c23e3bf15acbaf25c26，本地与远端一致。原M3矩阵/Gold保持不变。起始225项pytest。只补齐E2E-03的真实Episodic业务案例链；不做M4/S3、新工具、新Memory/Context机制或收益调参。

## 开工保护

AGENTS.md有用户未提交修改，PROJECT_NORTH_STAR.md和开发目录及历史pytest目录未跟踪，均不覆盖、不暂存。原API8000/前端5173保持运行，不读取其口令、不重置其数据库。测试资料和临时库只放本项目内。

## 六段式验收卡

1. 用户旅程：独立合成loopback测试环境，support-a在Web建立新的S1 Task A；真实401调查、独立approver-a Web审批、受控REPAIR、同身份固定路由HTTP200、冻结报告与DELIVER。来源可信后在Web创建Episodic Candidate，独立approver确认，support创建不同Task B。Web撤销后同Task B Session追问，再由合法Investigator Run完成同Run跨进程恢复。
2. 模型/工具：真实deepseek-flash Provider、TaskBinding限定MCP stdio、现有Chat/Investigator/预算/Checkpoint，不打桩。保存实际选用Memory内容摘要、Prompt digest/上下文来源与usage。只读观测工具可以额外保存安全的真实入参/返回引用，不能改变Provider或MCP执行。
3. 受信状态：复用TaskControl、Approval、Plan、Intent/Ledger、Verification/Report/Delivery、Memory Domain及来源版本。审批角色独立authenticated identity，所有业务操作走Web/Domain。
4. 禁止动作：不得把Semantic当Episodic，不得用旧Trace冒充新运行，不直接SQL批准、伪造Evidence/Receipt，不在Task A后重置凭证或业务状态制造401。Task B可合法复查A修复后仍为200的状态，以当前Probe优先证明不照搬历史结论。不得提高预算/重试上限。
5. 判定：A业务回执完整后才创建Candidate；B不同Task且同租户项目、实际Provider/MCP使用历史方法，当前Evidence独立；撤销后新Chat排除Memory及依赖助手历史；摘要若未自然出现，真实摘要失效链标NOT_COVERED并独立引用现有DAG测试；同Run恢复预算不重置、无重复副作用；全量/定向/前端通过。十项条件齐备才PASS_CANDIDATE，正式PASS归主Agent。关键证据不足PARTIAL/UNVERIFIED，安全违规BLOCKED。
6. 轨迹：源码SHA/hash、环境来源、Task/Session/Run/Thread、Memory ID/version/digest/source refs、Provider/MCP、审批与动作账本、HTTP/订单字段、撤销事件、PID/Checkpoint/Attempts、失败/UNKNOWN usage脱敏保存。

## 固定阶段与补充执行细节

- A：新的S1_MISMATCH fixture只在全新测试库初始化一次，配置v7，真实业务操作把它修到v8。记录初始化快照；不复制旧业务完成结果作为新Task A。
- B：由A可信结果创建EPISODIC Candidate→独立确认ACTIVE。只记录合法来源及审计，不注入模板或手工长期Memory。
- C：创建新Task B，用户表述为核实之前401的当前状态；保留A修复后的真实200，不人为复发。模型可以安全NO_ACTION或适当停止，不强迫再生成修复Plan。需要关联当前B的MCP Evidence和选用经验。
- D：先在B进行一次有依赖的只读问答，随后APPROVER Web撤销，再新Chat，核对撤销Memory和旧助手排除；若未产生Summary，明确本次真实Summary DAG未覆盖。
- E：优先用B的合法后续Run；若B正常只读调查已终结，允许同Session用Web建立另一个明确标识的Task C进行撤销后调查。恢复证明必须是这个新Run本身在旧/新进程保持同一ID，不得把重启后新建的Run当恢复。注入点必须已有真实持久Checkpoint/Attempt；进程树限本次自有服务。
- 回归：新鲜完整pytest、Episodic/Semantic/Context定向、frontend typecheck/build/lint。保持225原有用例；新增仅直接阻塞的复现与必要回归。

## 当前环境检查

Python3.14.0，SQLite3.50.4；FastAPI0.137.1、LangGraph1.2.16、MCP2.3.0、tiktoken0.14.0、langchain-openai1.7.2、pytest9.1.1；Vue3.5.44、Vite8.3.4、TypeScript5.9.3。已有模型ID deepseek-flash，密钥和自定义端点本地可用（值不记录）。源码直接从当前checkout加载，不依赖opspilot分发元数据；首次版本枚举因未安装opspilot发行metadata失败，修正检查方法，不安装或升级依赖。

完成后提交推送main、记录最终SHA、停止等待整体复盘。不扩大范围，不重跑收益评测。
