# AR-02-CONN-01 — 冻结执行计划

- Repo：wgqa/OpsPilot
- Branch：codex/ar02-live-01
- Base：606adea415962f74d53db67cf55493c1bcb59bc9
- GitHub 只读接口核实的远端 main：ec8c3582f6d145eec9979c43607302731411ead8
- GitHub 只读接口核实的远端目标分支：606adea415962f74d53db67cf55493c1bcb59bc9
- 本地 fetch / ls-remote 因沙箱网络连接失败；没有把旧本地跟踪引用冒充为实时远端读取。
- PROJECT_NORTH_STAR.md Blob：1f737712c7a36ceb34433ac09c3fbba3c3305542
- AGENTS.md Blob：32c45506cceeaa8c76a5c56bf8360ff476b58856
- 项目 Skill Blob：d405c8d413d633824b279202cc1503dab4cf0b03，已实际读取并执行 A 节核验。
- 任务卡 SHA-256：2d0b226aa9cf4005edea7a00526119f8f214a18d22f12c2851121d852c24e27a
- 冻结 S01/S02 输入 Blob：ee9b1623a2296905c425449709a2f9ae6563caca
- HF-02 报告 Blob：9b462627f790087b26b77d59cd0cefb9d6a63942；状态仍为实施方 ACCEPTANCE_CANDIDATE。

## 唯一目标与停止线

只验证当前 OpenAI SDK、HTTPX2、网络/TLS、DeepSeek Flash Chat Completions 能否在一次请求内返回可关联的有效 Completion、模型输出和 Usage。不验证 Agent、工具调用、MCP、RAG、连续旅程或业务结果。

真实 Provider Completion 最多 1 次：deepseek-flash、非思考、max_tokens=64、单条静态输入“请只回复：OK”、30 秒、零自动重试、不带 tools / tool_choice。每次发送前先在独立 SQLite 原子持久化唯一 ATTEMPT_RESERVED；账本目录或记录存在就停止。错误、超时、未知或无 Usage 后不再尝试。

应用侧预留上限 USD 0.01；不是供应商账户硬扣费限制。历史 P1 UNKNOWN 的 USD 0.645600 预留和原 P1 数据库、Checkpoint、Trace 均不重用、不结算、不修改。禁止 S01/S02、浏览器、业务写入、main 合并和 AR-03。

## 当前产品事实

AR-02-LIVE-01 P1 的 S01 原始结果为 Run 失败、Provider Dispatch UNKNOWN，费用预留 USD 0.645600 保留；模型 Completion、Usage、MCP 观察都未能核实。原 S01/S02 Gold 保持不变，本轮不重跑。

## 范围

只新增本目录的单次探针脚本、脱敏证据和运行日志；不修改生产源码、冻结 Gold 或旧证据。
