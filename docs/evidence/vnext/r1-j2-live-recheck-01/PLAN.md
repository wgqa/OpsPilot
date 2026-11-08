# R1-J2-LIVE-RECHECK-01

**Execution state:** PAID EXECUTION AUTHORIZED; execution not yet started at this revision.

## Frozen journey

Run J1-01, J1-02, J2-01, and J2-02 in one formal Assistant Session using the exact inputs in `CASES.json`. J2-01 creates the trusted binding for `r1-readiness-order` through the existing Assistant order API. J2-02 reuses that binding after the user's Event correction.

The isolated local HTTP fixture prepares two transport records before the Session starts. The current `event-current` Delivery/Receiver projection is HTTP 202 / ACKNOWLEDGED and PROCESSED. `event-previous` has only its historical HTTP 202 transport entry and no current Receiver observation. The fixture is test data, not Agent-obtained evidence.

## Provider and budget contract

- Provider/model: official DeepSeek API, `deepseek-flash` (official page currently identifies DeepSeek-V4.1-Flash-1017).
- Thinking: disabled; `max_tokens=2048`; stream false; tools use `auto`, parallel calls false.
- HTTP timeout 30 seconds; SDK/HTTP retries 0; one Provider request at a time.
- Provider send limit: 12; application pool: USD 8.00.
- Per-send persistent conservative reservation: USD 0.645600; total maximum reservation USD 7.747200, leaving USD 0.252800 under the authorized pool.
- Product request bounds remain 12,000 input and 2,048 output tokens. A 12,000/2,048 peak-price request would price at approximately USD 0.006058; the campaign continues to reserve the larger frozen USD 0.645600 bound before transport.
- The new exact Campaign identity, Runtime Grant, Domain DB, Checkpoint, and private evidence directory are separate from all prior Campaigns. An UNKNOWN or Campaign STOPPED state ends the entire new Campaign; it is never resumed or retried.

Official pricing and capability references checked 2026-11-08:

- [DeepSeek Models & Pricing](https://api-docs.deepseek.com/quick_start/pricing/): peak cache-miss input USD 0.30/M, output USD 1.20/M; 1M context and 384K maximum output for `deepseek-flash`.
- [DeepSeek Chat Completions API](https://api-docs.deepseek.com/api/create-chat-completion/): `thinking.type=disabled`, `max_tokens`, `stream`, function tools, and `tool_choice=auto` parameters.
- [DeepSeek model listing](https://api-docs.deepseek.com/api/list-models/): model identifier and declared context/output limits.

The application reservation is a local safety bound, not a provider invoice. The official page says prices may change; a price/model/config mismatch stops the run before send.

## Evidence boundaries

- Real Provider answers and tool choices must come from actual HTTP responses.
- Task-bound MCP facts count only when returned in the current Run and associated with the active Task/Event.
- Local fixture HTTP posts prepare only the isolated Demo DB; external business writes are prohibited.
- No S1/S2 readback is planned unless the new isolated DB itself contains a trusted persisted outcome; otherwise it remains NOT_RUN.
- No browser automation or main merge is authorized.
