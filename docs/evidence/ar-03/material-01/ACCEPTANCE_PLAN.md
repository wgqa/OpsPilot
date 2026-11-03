# AR-03-MATERIAL-01 — 冻结验收计划

**状态：** IMPLEMENTATION_AUTHORIZED / ACCEPTANCE_CANDIDATE_PENDING  
**Base：** `01eb6f9c38d062f7de040e202713a352215014f2` (`codex/ar03-b-reliability-01`)  
**工作分支：** `codex/ar03-material-01`  
**远端状态：** `REMOTE_UNVERIFIED`（本轮开工 GitHub 443 不可达；本地 `origin/main`=`ec8c3582f6d145eec9979c43607302731411ead8`，须在提交/推送前重查）

## 用户目标与边界

用户可以在统一助手对话中查看授权协议的原文条款、贴入自己的配置或日志并让 Agent 解释，再在可信绑定订单后结合本 Run 的 Delivery/Receiver 事实形成未提交说明草稿。用户材料始终是未验证线索；协议、用户材料和当前业务 Observation 是三种不同来源。

只读复用现有 `ASSISTANT_V1`、Session 项目授权、MCP、TaskBinding、Context 与 Skill 机制。本切片不运行真实 Provider 或浏览器，不写业务状态，不改变 TaskBinding、权限、S3 Gate、预算或历史证据，不实现文件上传、任意路径读取或业务动作。

## 冻结 Gold

见同目录 `CASES.json`。Gold 规定可接受的用户结果、必须可核对的来源和禁止结论，不规定唯一工具顺序。

### 必须证明

1. **授权原文**：模型可从其 Session 授权文档集合中发现文档，再通过受限 MCP 读取有界原文；结果含文档 ID、版本、source、Digest、授权版本/摘要、节/行范围和精确文本。无关/未授权/撤权/改 Digest 的材料不可读或不能在后续模型调用中继续作为有效来源。
2. **用户材料**：多行配置、JSON、日志作为原始用户消息进入真实模型输入并持久关联来源 Message；提示与结果明确把它作为未验证材料分析。畸形、局部、互相矛盾的材料可交付部分分析及未知项；文本中的指令、订单/Event ID、状态或授权声明不能改变可信绑定或创建当前 Evidence。
3. **连续会话**：下一轮代词式追问可以利用先前授权原文和答复作为历史线索；历史摘要保留来源 ID/版本/Digest，并标记为历史方法材料，不转成新鲜业务事实。撤权、版本/Digest 变化时应在出站前拒绝失效来源或重新合法读取。
4. **按需 Skill**：提供一个 `protocol-upgrade-impact-analysis` 业务 Skill，沿现有清单/摘要/Digest 加载机制供模型按需调用。简单 HTTP 概念问题允许不加载；适用的协议升级问题允许加载。Skill 只给分析方法，不能授权资源、改写事实或指导业务写入。Skill ON/OFF 成对 Fixture 只证明接线与内容差异，不证明真实模型效果。
5. **可信业务事实**：无绑定时，即使用户材料包含订单/Event/处理状态，也不得执行订单业务 MCP 查询。经正式可信 API 绑定后可读同一订单/Event 的真实当前 Delivery 与 Receiver。`202/ACKNOWLEDGED + QUEUED` 不代表完成；当前 `PROCESSED` 只允许确认该同一 Event 已处理。用户日志、其他 Event 或旧 Run Observation 不能冒充当前事实。
6. **边界和预算**：无 REPAIR、Approval、DELIVER、Handoff、Receipt 或其他业务写入；既有模型/MCP 计数、MCP 每 Run 上限 6 和 Context 12,000 Token 上限不变。真实 Provider 请求为 0。

## RED → GREEN 方案

先提交本文件与 `CASES.json` 作为冻结点，再提交新增失败测试和原始 RED 日志；RED 提交前不修改正式业务源码。实现后新鲜运行同一测试得到 GREEN，并运行 scoped protocol/knowledge、assistant Context、AR-02/AR-03 Assistant 集成及适用安全回归。保留每次失败、原始日志、测试命令和退出码；不改旧 Gold/RED。

## 证据等级与停止

- Fixture/Mock MCP/API/SQLite 证明受信读取和 Assistant 接线，不证明真实模型会选对工具或用户会认为答案有用。
- Skill ON/OFF 只比较实际工具调用、输入内容和可见观察；真实 Provider 效果标记 `REAL_MODEL_NOT_VERIFIED`。
- 不运行浏览器或收费调用，不把确定性 Worker 旅程写成真实模型验收。
- 达成冻结测试、相关回归与报告后提交隔离分支并停止，状态仅为 `ACCEPTANCE_CANDIDATE`，等待主 Agent 独立验收。

## 开工核验记录

目标提交实际 Blob：

| 文件 | Git Blob |
|---|---|
| `PROJECT_NORTH_STAR.md` | `1f737712c7a36ceb34433ac09c3fbba3c3305542` |
| `AGENTS.md` | `32c45506cceeaa8c76a5c56bf8360ff476b58856` |
| `.agents/skills/opspilot-slice-review/SKILL.md` | `d405c8d413d633824b279202cc1503dab4cf0b03` |
| `docs/evidence/ar-03-real-llm-01-prep/CASES.json` | `c29b5cf7630fa838a365634d0df5f9f0f2bfa834` |
| `docs/evidence/ar-03-real-llm-01-prep/GOLD.md` | `88d5e6f40f027ce2622b957d8ab32b8d2b827381` |

North Star、AGENTS、项目 Skill、AR-03 冻结 CASES/Gold 与 B Reliability/REAL-LLM-02 证据已从 Base worktree 实际读取。Base worktree 存有 6 组历史 pytest 临时目录，原样保留；主工作区有既存未跟踪资料，未作修改。基线与 `origin/main` 的本地引用相符；本轮网络不可达，远端实时 HEAD 未核实。
