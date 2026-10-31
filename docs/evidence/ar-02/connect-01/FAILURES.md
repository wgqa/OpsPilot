# 失败与修复记录

所有失败均来自免费本地预检，未建立真实发送许可，未触碰 Completion API。原始日志和退出码均保存在 runs/。

| 日志 | 结果 | 原因与处理 |
|---|---|---|
| preflight-local-01.log | FAIL | SDK 的 chat.completions.create() 不接受 follow_redirects 参数。改由 HTTPX2 Client send 包装器显式关闭重定向。 |
| preflight-local-02.log | FAIL | Windows 临时目录清理时 SQLite 连接仍打开。关闭查询连接，后续临时测试放到 D 盘证据目录。 |
| preflight-local-03.log | FAIL | reserve_once() 内连接未显式关闭，导致 SQLite 文件锁仍在；补充 close()。 |
| preflight-local-04.log | FAIL | Windows 不允许对只读句柄调用 fsync；原子 JSON 写入改用可写句柄。 |
| preflight-local-05.log | PASS | SDK/HTTPX2 本地请求和持久一次性门禁通过；该次仍使用显式注入的 HTTPX2 Client。 |
| preflight-local-06.log | PASS | MockTransport 改为替换 SDK 默认 Client 的底层 transport，保留默认 HTTPX2 Client 包装。 |
| preflight-local-07.log | PASS | 最终单次发送包装器调整后再次通过本地请求检查。 |
| preflight-local-08.log | PASS | 更新脱敏、Body 绑定和费用记录后的本地预检通过。 |
| preflight-local-09.log | PASS | 当前脚本源文件版本的本地预检通过，Provider 请求数为 0。 |
| network-preflight-01.log | PASS | 对 api.deepseek.com:443 做 DNS/TCP/TLS 检查，无 HTTP 请求。 |

第一次失败生成的本地 SQLite 临时目录位于系统 Temp；已验证精确目录是本脚本创建，再删除该目录内的单个 SQLite 文件和空目录。后续临时测试在证据目录运行并自行清理。未触碰用户已有临时目录。

尚无真实 Provider 成功或失败。若唯一请求超时、失败、缺少 Usage 或结果无法归属，不会重试。

## 追加：最终授权命令触发的意外 Provider 401（本节为最终事实）

原有表格只记录当时观察到的免费预检故障；下列失败发生在随后获批的唯一执行命令中，并取代“尚无真实 Provider 成功或失败”的旧结论。旧日志不改写。

- 原始日志：`runs/provider-single-request-01.log`，退出码：`runs/provider-single-request-01.exit`（1）。
- 异常：OpenAI SDK `AuthenticationError`，HTTP 401；Provider request ID：`9fa30b48-920e-48f8-ba86-442971054b2a`。
- 调用栈位置：`send_once()` 里的 `local_mock_success()`；普通执行上下文中 MockTransport 测试通过，但该授权执行上下文中 MockTransport 未截获请求，真实 DeepSeek endpoint 返回 401。
- 该 client 使用脚本本地占位凭据 `LOCAL_MOCK_ONLY`。未使用用户 `.env` API Key。没有有效 Completion、输出、Usage 或 Completion ID；实际费用未知。
- 请求前没有写入单次持久账本，也没有持久化 USD 0.01 预留。这违反本任务预检与持久发送资格要求，故不能认定为一次合规的真实连通性探测；它仍然是本次唯一可观察到的 Provider HTTP 响应。
- 原始 HTTPX2 live hook 尚未安装，故实际 wire request/response、精确 URL、headers 和 SDK 重试计数未捕获。客户端配置为 `max_retries=0`，堆栈仅显示一次 401；对这次 escaped call 的线级重试计数仍标记 UNVERIFIED。
- 根因只可确认到“MockTransport 在该执行上下文未拦截”。更底层的原因 UNKNOWN。没有进行后续诊断或第二次请求。
- 单次授权已消耗；禁止 retry、切换网络、换模型或使用用户凭据再发请求。`TRACE/STOPPED_NO_RETRY.json` 是仓库内停止标志，`probe_once.py` 现已先检查该标志再运行预检。

失败分类：安全控制失败（发送前授权预留没有生效）；协议/连接结果失败（只观察到 401，不是有效 Completion）；根因未确定。原 P1 UNKNOWN dispatch 仍为 UNKNOWN、USD 0.645600 保留，数据库 SHA 前后相同。

## 追加：隔离候选发布受阻

- 第一次 `git push origin codex/ar02-live-01`：`Recv failure: Connection was reset`。
- 第二次相同推送：`Failed to connect to github.com port 443`。
- 已授权的 GitHub 连接器 `github_create_tree` 返回 HTTP 403 `Resource not accessible by integration`；未创建远端 tree、commit 或 ref。
- 远端 `codex/ar02-live-01` 仍为 `606adea415962f74d53db67cf55493c1bcb59bc9`，`main` 仍为 `ec8c3582f6d145eec9979c43607302731411ead8`。本地候选提交保留，未尝试其他上传方式。
