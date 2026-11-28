# R1-LIVE-JOURNEY-02：历史捕获审计

审计对象是 `R1-LIVE-JOURNEY-01` 的私有归档，只读读取，不复制原始私有内容到仓库。

## 私有文件 SHA-256

| 文件 | 本次读取 SHA-256 | 上轮清单一致 |
|---|---|---|
| `execution.jsonl` | `3d72adf25b179e2d6afc0d3483e789d81f2c3997300d6e027bcab4c0f922e8a2` | 是 |
| `provider_http.jsonl` | `80d910bf7b191de6dcc6d5206794295bb535a9122fc7983a2934d46246b4aac6` | 是 |
| `domain.sqlite3` | `ef5bdc6907ae156c431ff4478e7cfd850e7761b736c719fd3ff3f2777b692197` | 是 |
| `checkpoint.sqlite3` | `883e1e31848e77ac426e100872e398dedd0d919d292b82b2cc275a3c6ae37015` | 是 |
| `runner_console.log` | `1a59fe7590f0ac6ad77db295903f13a6081a45e448d87466171e433ab2a0a789` | 是 |

## 四组请求与响应

以下是私有 HTTP 记录与已提交脱敏 Trace 中对应 Completion 的 canonical JSON SHA-256 比较。四条请求都对应 HTTP 200、`tool_calls` 和有效 Usage；每条真实工具提议均与 Trace 的调用 ID、工具名和解码参数一致。

| Step | Completion ID | Request SHA-256 | Response SHA-256 | Tool Calls |
|---|---|---|---|---:|
| J1-01 | `ab262ab0-b2f6-4071-b6e6-f65b19b73677` | `ade9331b86e2995a94d4c30b3dbab33c1222b10b6682c7cd8513e512d6ca604c` | `0b328d41c83afe4c1801b91771e5926fa6f9ba076e131cb63a3127fa8b6415bf` | 1 |
| J1-02 | `946d179b-cff5-4817-90ed-7365b8057889` | `6e603cea3c75d80006a470e8e74b185130c281a990877818915773d56f684e94` | `abf309aab9f950fff26f8fb2e35ab316d07d8d3ca79d17d7160c3c062e921868` | 1 |
| J2-01 | `4df2dbd1-6798-477e-99ea-b26fb793db9e` | `bdb778e049c1e46ef1444f43c41621b7d615ee734c8f68fbbda4eff83d7e4c80` | `0ccd5a927cb42161789542b93dc6f1ff0b32cfe722ff390cad2ab3caec0dd219` | 3 |
| J2-02 | `23d7fa13-90cb-4ed8-8266-f6f6f6e2987e` | `a0cf0cea7b060dd39705eb73906682bc82b843479fb303c14ccc6421f7b4ba24` | `84edabe45fa977e6aa2c1dde31f3a76b598af4379cec3d4837c7cbb5f9d4cc3c` | 4 |

本次正式 Assistant 离线回放了 J1-01 的单工具提议及 J2-01 的三工具提议；J1-02/J2-02 只完成原始捕获与脱敏 Trace 的审计，没有重放。J2-01 的三个调用是协议文档发现、Delivery 读取、Receiver 读取；隔离 Demo 返回了同一 `event-current` 的 `202/ACKNOWLEDGED` 与 `PROCESSED` 事实。

旧捕获未保存 `Content-Encoding`，因此不能确认真实 HTTP 响应是否使用 gzip。回放中的 gzip 是围绕已验证响应 JSON 构造的本地传输夹具。历史 Run 的 Assistant 解析原因链也没有被记录；本轮不能据此断言旧失败的唯一根因。

原始文件保留在既有受控私有执行目录，不复制到公开仓库。目录的本机绝对路径不在本报告中披露。
