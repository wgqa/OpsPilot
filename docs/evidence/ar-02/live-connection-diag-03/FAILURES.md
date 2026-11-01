# 失败记录

1. 首次离线预检命令的 stdout 日志捕获因 `runs/` 目录尚不存在而失败；预检本身已写出 `PREFLIGHT_PROOF.json`，外部请求数为 0。已补建目录并只读校验证明，留存 `runs/01-preflight-proof-validation.log`。没有重复执行预检。
2. 发送前独立账本检查通过：新授权 `AR-02-LIVE-CONNECTION-DIAG-03-20261101-01`、scope `AR-02-LIVE-CONNECTION-DIAG-03-ONE-URLLIB-POST`、USD 0.01 预留、request_count=0。
3. `runs/04-send-once.log`：唯一一次原始 `urllib` 请求尝试失败，没有 HTTP 响应。捕获的异常链为 `URLError` → `PermissionError [WinError 10013]`。依据 Microsoft 的 Winsock 错误表，10013 表示 socket 访问被权限拒绝；这指向本机/运行环境 socket 权限层，但不能区分是沙箱策略、主机安全策略还是其他本地配置。[Microsoft Winsock error codes](https://learn.microsoft.com/en-us/windows/win32/winsock/windows-sockets-error-codes-2?redirectedfrom=MSDN)
4. 因无 HTTP 响应/Usage，Completion、模型版本、输出和实际费用均未知；USD 0.01 预留保持未结算。严格停止，未重试、未换代理或网络。

前一次 OpenAI SDK/HTTPX 请求的底层链仍未保存，因此 WinError 10013 是本次独立标准库调用的直接证据，也是前次连接错误的强关联解释；不能把它追溯写成前次异常已确证的 cause。
