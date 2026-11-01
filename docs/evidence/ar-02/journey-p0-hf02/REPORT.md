# AR-02-JOURNEY-P0-HF02 收口报告

## 状态

`ACCEPTANCE_CANDIDATE`。本报告提交免费、定向的 HF02 验收证据，不代表主 Agent 最终 PASS。

- 基线：`990d977755854100f1718a5266499859a09dbacd`
- 冻结提交：`2a10306cc4a05ce2915b81cc8232740673afad9f`
- 实现提交：`4ced0dde8e61947ba7840bd4cd7c9a16eef519c5`
- 最终候选 SHA：由证据提交后的 Git HEAD 与交接报告提供。

## 用户结果与真实轨迹

- **HF02-01：** 无 TaskBinding 的 Session 中，FixtureModel 明确提议 `get_order_status`，但该工具未提供给模型。Assistant 将请求记录为 `FAILED`，结果为 `ASSISTANT_TOOL_NOT_EXPOSED / NOT_STARTED`；未启动 ToolNode handler、MCP `tools/call`、D2 Attempt 或业务 HTTP 读取。最终 Session 消息说明未取得可信业务事实。
- **HF02-02 正例：** 正式 API/Worker/`ASSISTANT_V1`/本地 MCP stdio 下，绑定订单同一 Event 的 Receiver 查询返回 `QUEUED`，用户答案为“尚不能确认处理完成”。
- **HF02-02 失败观察：** 同一 Task、Event、订单与问题的新 Run 再次实际调用 Receiver MCP 工具；只在该 MCP 子进程中注入受控查询异常。MCP call 为 `FAILED`，Attempt/Observation 为 `ERROR`，没有新 Receiver Evidence。由于之前的 QUEUED Evidence 仍存在，计数从 1 保持为 1；系统没有将旧 QUEUED 冒充当前成功结果，最终回答为 UNKNOWN/无法确认。

真实运行轨迹见 [TRACE.jsonl](TRACE.jsonl)，同一份机器生成观察也保存在 `runs/TRACE-05-regression.jsonl`。痕迹来源为正式 API、Worker、本地 SQLite、MCP stdio 和确定性 FixtureModel，不是付费模型。

## 修改范围与依据

实现相对冻结基线 `990d977755854100f1718a5266499859a09dbacd` 的最小差异：

- `opspilot/assistant.py`：`Loop.awrap_tool_call` 在 dispatch 前检查模型请求名称是否属于本 Run 实际暴露的工具集。未暴露工具持久记为 `FAILED`，响应显式表示 `NOT_STARTED`，不会调用 ToolNode。实际 handler 结果必须是字典，否则拒绝将其标成成功结果。
- `opspilot/domain/assistant.py`：MCP 缓存重放要求持久结果是 JSON 对象；来源当前性校验同样拒绝 NULL、畸形 JSON 或非对象。
- `tests/test_ar02_journey_p0_hf01.py`：更新旧 HF01 断言，使其验证新的拒绝记录是 `FAILED / NOT_STARTED`。旧报告、Gold、RED、Trace 未改写。
- `tests/test_ar02_journey_p0_hf02.py`：增加两条冻结用例，分别覆盖拒绝/缓存/历史来源和 Receiver 实际 MCP 查询失败。

未新增 Guard、Runtime、Schema、工具权限、业务写入语义或模型平台。

## RED、GREEN 与回归

| 执行 | 结果 | 证据 |
|---|---|---|
| 初次日志目录准备 | pytest 未执行，日志目录不存在 | `runs/00-log-directory-setup-error.txt` |
| RED 初次尝试 | 测试注入的 `sitecustomize` 未进入 MCP 子进程；保留为测试准备失败 | `runs/01-red.log` |
| RED（修正临时注入路径后） | `1 failed, 1 passed`；核心调用状态为 `OK`，复现冻结缺陷；Receiver 错误路径通过并未写新 Evidence | `runs/02-red-after-fixture-fix.log` |
| 定向 GREEN | `2 passed` | `runs/03-targeted-green.log` |
| 首轮相关回归 | `41 passed, 1 failed`；唯一失败为 HF01 旧断言仍要求结果为 NULL，与本次已修复的明确拒绝对象不兼容 | `runs/04-targeted-regression.log` |
| 更新既有断言后的新鲜相关回归 | `42 passed, 0 failed`，44.71 秒 | `runs/05-targeted-regression.log` |

冻结 RED、环境准备失败、旧断言失配及其后成功结果全部保留，没有覆盖旧文件。全量 pytest 未执行；HF01 历史全量 `489 passed / 4 failed` 是历史结果，不是本轮验证。

对源码、测试和文档执行 `git diff --cached --check`（排除原样日志）通过。未过滤的检查只报告原始 pytest 日志中 traceback 格式产生的空白尾随字符；这些原始输出未做格式化或改写。

## 未执行与边界

- 真实 Provider 请求：0。
- 浏览器自动化：未执行。
- 外部系统调用：未执行。
- 主线合并：未执行。
- 本地测试创建了隔离 Task/TaskBinding、读取 Observation 与审计记录；没有 REPAIR、Approval、ActionIntent、Ledger、Queue、Receipt 或其他业务副作用提交。
- 没有重跑全量 pytest，也没有把历史 `489/4` 写成本轮通过。

## North Star 六问摘要

1. **用户变化：** 未暴露的工具请求不会再被当作成功事实；Receiver 查询失败时仍能收到明确未知状态。
2. **Agent 决策：** 只验证 FixtureModel 的选择与安全响应，不宣称真实模型自主性提升。
3. **观察驱动：** 同一 Event 的 QUEUED Observation 支持“排队中”；之后 Receiver 查询失败则回答 UNKNOWN。
4. **新边界及正常路径：** 未暴露工具不 dispatch；已授权的订单与 Receiver 查询、Knowledge 空结果和其他合法调用由相关回归验证未退化。
5. **简化：** 复用现有 Assistant Call、Source Validation、MCP 和测试流程，没有新增治理组件。
6. **证据与停止线：** 2 项定向用例、42 项相关回归通过；全量、浏览器和真实 Provider 未运行。任务交主 Agent复核后停止。

## 验收范围

可供主 Agent 独立验收的范围仅为本报告列出的两个问题和本次新鲜相关回归。最终裁决由主 Agent 作出。
