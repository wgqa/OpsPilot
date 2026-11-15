# E03-D 首次真实模型运行记录

- 状态：真实首次运行已完成；Rubric 评分仍为 `UNVERIFIED`，交主 Agent 独立评分。
- 基线：`codex/r2-ar06-e03-eval-exec-01@20fa1f9f3767ee75022a53cdcc23d611d5e6457a`
- Runtime：`user-demo-r2-e03-live01`（运行前不存在，独立 Domain / Checkpoint / Spend）。
- Session：`session-874029ef-cedb-4416-933a-c940f952d0e0`
- Run：`run-80e84d08-7f37-4a3b-bfb1-a98fbff91802` — `SUCCEEDED`, terminal timeout `false`, TaskBinding `null`。
- 冻结 Gold SHA256：`c1acd3fa789befa733aa96bf3a49b08357ff071f3b627b4c40319882e2805cf8`
- 冻结输入 SHA256：`19a206256ff387f20552527cfd05899e89bf171c5e500ab9a298f9c5051dcfc6`

## Provider 与费用

- 模型：`deepseek-flash`，本机配置版本 `deepseek-v4.1-flash-1017`，Endpoint host `api.deepseek.com`。
- 本机费率版本 `DEEPSEEK_FLASH_PEAK_2026-11-14`：输入 `300000`、输出 `1200000` micro-USD / 百万 Token，与[DeepSeek 官方价格页](https://api-docs.deepseek.com/quick_start/pricing/)列出的峰时费率一致。运行发生在周日 UTC；官方页面将非峰时费率定为峰时一半，因此本地应用账本使用了较保守的峰时费率。供应商账单未单独查询。
- 本次是 1 个 Agent Run、3 次 Provider send，3 个响应均收到；总 Usage 11,501 input / 1,732 output / 13,233 total Token。
- 应用账本结算 USD `0.005530`；授权 Grant USD `0.060000`，剩余 USD `0.054470`，无未结/UNKNOWN 预留。每次最大预留 USD `0.006058`，单 Run 最坏预留 USD `0.048464`（最多 8 次派发）。
- `chat_attempts.provider_response_id`：`lc_run--01a1ddcc-f321-7432-a211-9187a6b7f6b0-0`。Runtime Spend `completion_id` values: `1a0ea726-b75a-4e88-8949-11bb4f9aaa9a`, `3fe830f0-1000-424e-9cc1-b1ac67652cf2`, `c0d04dd4-a7c5-4a14-903b-bb7429b05a4f`。
- Run 耗时：14,333 ms。没有重试或重提交。Live 服务已优雅停止，保留数据库、Checkpoint、日志及证据。
- Grant 在该 Runtime 中仍为 `ACTIVE`，到 `2026-11-15T07:00:00Z` 自动过期；API/Worker/前端已停止，端口 8000/5173 无监听。本轮没有再发送请求，继续使用须另行授权。

## 模型选择与材料来源

- Runtime 隔离授权：tenant `tenant-a`、actor `support-a`、project `orders-async-demo`，grant version 1；仅有两份文档权限：
  - `callback-retry-contract` v1.0.0，digest `a5974f46bf50e2bfcd63ed1e6528d473560854204d12a50dfb3f82b9e61bc0c3`，source `local:orders-async-demo/contract-v1`。
  - `callback-retry-contract-v2` v2.0.0，digest `9ad3f5a67a5f40da986769c66a78317027d3e57803371a0674d3b14fe412e238`，source `local:orders-async-demo/contract-v2`。
- Agent 实际调用 3 次只读 MCP：`list_scoped_protocol_documents`、`search_project_knowledge`、`compare_scoped_protocols`；模型未加载可选 Skill。协议比较返回一个差异 `DIFF-001` / `EVID-001`，含 v1/v2 摘录和位置 `Lines 1-1`。业务 Observation=0、正式 Domain Evidence=0（E03 无 Task；工具比较内的 EVID 标识不是业务 Evidence 表记录）。
- 比较与最终回答均标记 `deployment_version_verified=false`；没有正式业务写入、审批或交接。

## 评分边界

Runner `SUCCEEDED` 只表示执行完成。本记录保持 Runner `assessment_status=UNVERIFIED`；由主 Agent 按冻结 M1–M6 Rubric 独立评分。正式分母和前五例成绩未改写。

## 文件完整性

- 脱敏 Trace：SHA256 `6575dd64a4a5294719123cd805043d64396029a353bf6331c906ae867525aad4`。
- Runner Result SHA256 `75c61049381fa4a48cbbe6f2f204ad65f013c1e8299ae29258b707619737ceaf`。
- 导出器标记：API Key、Cookie、Authorization、配置密码及通用 Bearer / `sk-` 凭据模式已脱敏；导出不含秘密值。
