# 失败记录

1. `runs/01-offline-preflight.log`：离线 MockTransport 预检通过；对真实 DeepSeek 请求数为 0。
2. `runs/02-reservation.log` 与 `runs/03-reservation-readonly-check.log`：新授权已持久预留并经只读复核，出站前 request_count 为 0。
3. `runs/04-send-once.log`：唯一真实请求在 request Hook 后进入 `OUTBOUND_STARTED`；response Hook 未触发，SDK 报 `OpenAIConnectionError: Connection error.`。未获得 HTTP 状态、Completion ID、模型版本或 Usage，实际计费未知；USD 0.01 预留保持未结算。

原始异常链没有在这个 one-shot runner 中保存；本次也未能恢复更深层的异常 cause。不能据此判断 DNS、TCP、TLS、代理或服务端根因。

账本的 `scope` 标签由复用的旧 sender 硬编码为 `AR-02-CONN-02-ONE-COMPLETION`，attempt ID 也带旧 `conn02-` 前缀；与本次任务标签不符。实际使用的是新授权 ID、随机 attempt UUID 和独立账本。该元数据问题已如实记录，发送后没有修改账本。

严格停止：没有重试，没有切换网络/模型，没有修改或释放旧实验 UNKNOWN 账本。后续 Provider 请求须另行明确授权。
