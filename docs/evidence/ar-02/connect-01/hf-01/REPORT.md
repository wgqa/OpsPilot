# AR-02-CONN-01-HF-01 免费补差报告

## 状态

ACCEPTANCE_CANDIDATE，提交主 Agent 独立验收。OS 级外网阻断仍为 UNVERIFIED / NOT_RUN；本轮没有发送真实 Provider 请求。

## 基线与范围

- Repo：wgqa/OpsPilot
- 工作树：D:\学习\agent新项目\.worktrees\ar02-live-01
- Branch：codex/ar02-live-01
- 本任务开工 Base：a2c4be7270c26b843a35fac13326b0f88f2668d0
- 冻结验收提交：32683bd8f0e182ff187f5f5ea6892adff91f24f7
- 冻结 RED 提交：78c0ff3e24755b948c1278ada91df441cb0b02f7
- 实现提交：47365b613f3df5b156b63ccede79bcd91dcf0e06
- 任务卡 SHA-256：D5AFA4C6304C9A0AFD86C844A06E16A877B2F2DE512DA777EA1A994330C5A282
- main 起始 SHA：ec8c3582f6d145eec9979c43607302731411ead8
- 目标 Skill 已实际读取；当时文件 Blob：d405c8d413d633824b279202cc1503dab4cf0b03
- PROJECT_NORTH_STAR.md Blob：1f737712c7a36ceb34433ac09c3fbba3c3305542
- AGENTS.md Blob：32c45506cceeaa8c76a5c56bf8360ff476b58856

实现范围仅为专用探针模块、其免费离线测试和本任务证据。未修改 main、生产 Agent/Domain、冻结 Gold、旧 401/停止记录或 P1 账本；本轮没有打开或修改 P1 数据库。

## 已核实问题与最小修复

旧 local_mock_success() 和连接失败模拟先创建 OpenAI SDK 默认 HTTP client，再通过修改私有 _transport 替换传输。冻结 RED 在实际 SDK Client 构造前观察到没有传入 http_client；因此旧预检并未证明“不可能使用默认外部传输”。这确认了隔离实现缺陷，但不证明原事故中 Mock 为何失配并得到 HTTP 401；代理、挂载或授权环境原因仍未知。

现实现只允许 create_offline_client() 接受明确的 httpx2.MockTransport，创建 httpx2.AsyncClient(transport=..., trust_env=False, follow_redirects=False) 并将其显式传给已锁定的 OpenAI AsyncOpenAI(http_client=...)。SDK 版本、构造签名、端点与代理变量均在创建 SDK client 前检查。没有默认 transport fallback，也没有 _transport 私有字段修改。

send-once 在函数和 CLI 入口均无条件 BLOCKED，且不读取配置/密钥、不查看 marker 或数据库、不创建客户端、不预留额度、不发网络请求。network-diagnostic 从可执行入口删除。旧单次授权没有恢复；未来新授权的核验和持久预留顺序仅作为合同记录，本轮没有实现或激活发送许可。

## 证据

- 锁定环境：Python 3.14.0、openai==3.33.0、httpx2==2.13.1。
- 最终 HF-01 定向测试：15 passed。
- 提交前最终复跑：15 passed；Python 语法编译通过。
- AR-02 既有本地协议回归：28 passed。
- CLI 离线 Mock 预检：PASS，合成 Completion ID local-mock-completion，Usage 5 input / 1 output / 6 total；真实 Provider 请求 0。
- CLI send-once：BLOCKED，退出码 3，Provider 请求 0。
- 双进程和多线程模拟：相同授权身份最多一条 ATTEMPT_RESERVED；重复及 UNKNOWN 不能再次预留；复制的已消费模拟账本拒绝重放。
- 实际线级 URL：无 /v1 为 /chat/completions；有 /v1 为 /v1/chat/completions。均由真实锁定 SDK 序列化到本地 MockTransport 的请求观察，不是外部 Provider 请求。
- 请求记录保留 POST、DeepSeek Flash、thinking disabled、64 output tokens、无 tools、零 retries；只记录 Authorization 是否存在，并将值脱敏。
- 完整测试命令、退出码和早期失败见 runs/ 与 FAILURES.md；MockTrace 见 TRACE.jsonl 和 TRACE/offline-preflight.json。
- ruff 检查未运行：当前 venv 未安装 ruff，本轮没有为此添加依赖。
- 原始 pytest-green-01.log 保留了 pytest 失败输出中的尾随空白；为不改写原始日志，git diff --check 对日志文件单独排除，其余源文件和证据文件检查通过。

## 网络隔离证据边界

进程代理环境变量在最终 CLI Mock 预检时为空；负例在测试中设置代理变量并验证创建 SDK client 前 fail-closed。显式 MockTransport 的成功和连接失败都观察到外部 Provider 请求数为 0。

本次没有可验证的 OS 级禁网执行环境，且根据冻结合同禁止通过外网探测补证。因此 OS 级外发阻断是 UNVERIFIED / NOT_RUN。不把 Mock hook 计数或测试沙箱限制宣传成 OS 防火墙证明。若主 Agent 要求此项为硬验收，需提供隔离网络测试环境后再单独验证，不能恢复旧授权。

## 历史事故与费用

保留原 HTTP 401、Provider request ID 9fa30b48-920e-48f8-ba86-442971054b2a、实际计费 UNKNOWN、未建立 USD 0.01 预留，以及原 P1 UNKNOWN / USD 0.645600。本轮未补写 reservation、未查询/访问旧数据库、未自动重试。

## 未运行

- 真实 Provider / Completion：NOT_RUN（未授权，且 send-once 硬停止）。
- OS 级外网阻断负例：UNVERIFIED / NOT_RUN。
- 浏览器、S01/S02、业务写入、MCP、旧 P1 数据库：NOT_RUN。
- 全仓 pytest：未执行；本轮只运行本任务和明确相关的 AR-02 本地协议回归。

## Skill 六问简报

- 用户变化：消除了离线预检错误触网的代码路径；没有新增真实模型体验。
- Agent 决策：无新增自主决策能力。
- 观察驱动：旧默认客户端与当前显式 Mock 注入分别由冻结 RED 和本地真实 SDK 序列化观察验证。
- 新增约束：缺少 Mock、端点/SDK/代理条件不符时，阻止客户端创建；合法的双路径本地 Mock 调用仍通过。
- 简化结果：移除了私有 _transport 替换、外网网络诊断和当前候选的真实发送实现；未改生产职责。
- 证据与停止线：免费本地测试通过；OS 级隔离未验证；不恢复 CONN-01 授权，不跑 S01/S02，候选提交后停止。

## 下一步

当前仅为 ACCEPTANCE_CANDIDATE。主 Agent 独立验收后，若认为必要，可要求提供 OS 级断网环境证明；本报告不申请或恢复真实 Provider 授权。
