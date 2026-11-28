# Captured Provider evidence audit

Original private files were read-only. SHA-256 values at this review:

| Private artifact | SHA-256 |
|---|---|
| `execution.jsonl` | `3d72adf25b179e2d6afc0d3483e789d81f2c3997300d6e027bcab4c0f922e8a2` |
| `provider_http.jsonl` | `80d910bf7b191de6dcc6d5206794295bb535a9122fc7983a2934d46246b4aac6` |
| `domain.sqlite3` | `ef5bdc6907ae156c431ff4478e7cfd850e7761b736c719fd3ff3f2777b692197` |
| `checkpoint.sqlite3` | `883e1e31848e77ac426e100872e398dedd0d919d292b82b2cc275a3c6ae37015` |
| `runner_console.log` | `1a59fe7590f0ac6ad77db295903f13a6081a45e448d87466171e433ab2a0a789` |

The private Provider log contains four `outbound_send_granted` records and four HTTP response records. Their request keys match one-to-one. Each request is POST to `https://api.deepseek.com/v1/chat/completions`, model `deepseek-flash`, `max_tokens=2048`, thinking disabled, `tool_choice=auto`, `parallel_tool_calls=false`, `stream=false`, and a USD `0.645600` pre-send reserve. Each response was HTTP 200, returned a Completion ID, `finish_reason=tool_calls`, and valid Usage.

The actual tool calls below were compared field-for-field (Completion ID, tool-call ID, tool name, and decoded arguments) between the private raw Provider response and `continue-01/TRACE.jsonl`; all four matched. Only the first and third responses were replayed in this closeout. The second and fourth were audited but not executed again.

| Step / Completion ID | Captured proposals |
|---|---|
| J1-01 / `ab262ab0-b2f6-4071-b6e6-f65b19b73677` | `call_00_EJDqHvVzdrvTQ6biGc7M7579` — `list_scoped_protocol_documents(topic="回调重试")` |
| J1-02 / `946d179b-cff5-4817-90ed-7365b8057889` | `call_00_LssiUEIRM1BfffObEXc58389` — `list_scoped_protocol_documents(topic="回调重试")` |
| J2-01 / `4df2dbd1-6798-477e-99ea-b26fb793db9e` | `call_00_TNBghZUJHKran5bTdvJW3270` — `list_scoped_protocol_documents(topic="回调重试 callback retry")`; `call_01_HTeL0q851IuhAtqlKoFQ7045` — `get_callback_delivery(reason="核实绑定订单当前回调事件的实际投递与传输确认状态")`; `call_02_264wCalrAbFQirTp2cgR3537` — `get_receiver_processing(reason="核实当前回调事件在接收方的处理状态")` |
| J2-02 / `23d7fa13-90cb-4ed8-8266-f6f6f6e2987e` | `call_00_M1QbeR0pSFtlf9ddCX4n1880` — `list_scoped_protocol_documents(topic="回调重试协议")`; `call_01_3i7FbAUR6T9DAivYHAdH6928` — `get_callback_delivery`; `call_02_yAEcTPBPqewXIrZF46G92756` — `get_receiver_processing`; `call_03_P5UDzW1uoEvMgHhSIV6D1490` — `get_callback_transport_history` |

| Step | Prompt / completion / total tokens | `system_fingerprint` |
|---|---:|---|
| J1-01 | 1653 / 55 / 1708 | `bc19ba97cbe016479903222bb1578db6` |
| J1-02 | 1759 / 67 / 1826 | `bc19ba97cbe016479903222bb1578db6` |
| J2-01 | 2175 / 142 / 2317 | `bc19ba97cbe016479903222bb1578db6` |
| J2-02 | 2277 / 197 / 2474 | `bc19ba97cbe016479903222bb1578db6` |

SHA-256 of canonical JSON (`sort_keys=true`, compact separators, UTF-8) for the paired request body and response body:

| Completion ID | Request JSON SHA-256 | Response JSON SHA-256 |
|---|---|---|
| `ab262ab0-b2f6-4071-b6e6-f65b19b73677` | `ade9331b86e2995a94d4c30b3dbab33c1222b10b6682c7cd8513e512d6ca604c` | `0b328d41c83afe4c1801b91771e5926fa6f9ba076e131cb63a3127fa8b6415bf` |
| `946d179b-cff5-4817-90ed-7365b8057889` | `6e603cea3c75d80006a470e8e74b185130c281a990877818915773d56f684e94` | `abf309aab9f950fff26f8fb2e35ab316d07d8d3ca79d17d7160c3c062e921868` |
| `4df2dbd1-6798-477e-99ea-b26fb793db9e` | `bdb778e049c1e46ef1444f43c41621b7d615ee734c8f68fbbda4eff83d7e4c80` | `0ccd5a927cb42161789542b93dc6f1ff0b32cfe722ff390cad2ab3caec0dd219` |
| `23d7fa13-90cb-4ed8-8266-f6f6f6e2987e` | `a0cf0cea7b060dd39705eb73906682bc82b843479fb303c14ccc6421f7b4ba24` | `84edabe45fa977e6aa2c1dde31f3a76b598af4379cec3d4837c7cbb5f9d4cc3c` |

For J2-01, the decoded arguments requested protocol discovery for `回调重试 callback retry`, current Delivery/transport confirmation, and current Receiver processing. The replay preserved the exact IDs and arguments from the capture. Tool schemas accepted the arguments and the existing ToolNode invoked MCP.

## Encoding limit

The saved response `safe_headers` include `content-type` and `date`, but do not include `Content-Encoding`. The archived records therefore cannot establish whether the historical live response arrived compressed. J1-01 was replayed through a synthetic gzip wire representation of its captured JSON body; J2-01 used ordinary JSON. This proves both current decoder paths, not the original live encoding or its failure cause.

## Historical billing state

The original four Runtime rows remain `RESPONSE_STORED` with Usage and Completion IDs; the matching four `assistant_calls` remain `UNKNOWN` with no recorded exception cause. The sum of app-ledger settlements is USD `0.002914`; it is an application estimate, not a provider invoice. Each old pre-send reserve remains as recorded. No historical row was updated by this closeout.
