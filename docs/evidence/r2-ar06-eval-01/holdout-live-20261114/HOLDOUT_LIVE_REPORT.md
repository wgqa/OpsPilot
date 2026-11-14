# R2-AR06 Holdout Live Report — 2026-11-14

## Execution record

- Result: `ACCEPTANCE_CANDIDATE`; E02-H and E06-H are first-attempt live observations. Candidate labels below are not formal rubric scores.
- Branch at execution: `codex/r2-ar06-holdout-ready-01`.
- Code SHA used for both executions: `196c994a126ce91c06b2b315ec6b004906de2b1c`. The later commit containing this report is evidence-only; no production or Runner code changed.
- Start-of-run HEAD equaled `origin/codex/r2-ar06-holdout-ready-01`; worktree was clean before evidence collection. No new worktree was created.
- Frozen `CASES.json` SHA256: `c1acd3fa789befa733aa96bf3a49b08357ff071f3b627b4c40319882e2805cf8`. Frozen `RUBRIC.json` SHA256: `859985480169b04824a96a97db3031c312a68abbb550be3a96ffa6cbe5040944`. Both matched the repository's frozen hash manifest. Neither file was modified.
- E02-H and E06-H each used the exact frozen `user_turns[0]`. The Runner's UTF-8 input digest independently matched a fresh digest computed directly from `CASES.json`.

## Provider and spend basis

Both cases used the configured `deepseek-flash` model at `api.deepseek.com`. At execution, the configured peak rates were USD 0.30/M input tokens and USD 1.20/M output tokens under price version `DEEPSEEK_FLASH_PEAK_2026-11-14`, matching the [official DeepSeek pricing page](https://api-docs.deepseek.com/quick_start/pricing/). The spend ledger amount is the application's settlement estimate, not a supplier invoice.

Each Runtime had its own USD 0.05 Grant. Grants were created only through the interactive authorized procedure; no confirmation safeguard was bypassed. Each case had exactly one send grant and one received response. Neither case was retried or resubmitted. UNKNOWN=0. The combined H spend was USD 0.002559, leaving USD 0.097441 under the two approved caps. Per-Runtime remainder at completion was USD 0.048705 (E02) and USD 0.048736 (E06). No Grant was extended.

## E02-H — insufficient information and clarification

- Runtime `user-demo-r2-e02h-live01`; Session `session-9bdec216-d146-41fa-85a4-b24d56ce1829`; Run `run-cb15aaf1-08ec-4e67-a1fa-bfebf1933955`; source Message `message-83c4bc5f-2802-48cc-b1ac-9e8ab3a4263f`.
- Run `SUCCEEDED`; Provider response `7b1c5afd-949a-4dc6-9a2a-7ccbc7618b51`; 1 request/response; 2,496 input + 455 output = 2,951 tokens; 6,579 ms; settled USD 0.001295.
- MCP calls / Observations / Evidence: 0 / 0 / 0. There was no TaskBinding and no current business observation, as required by the frozen initial state.
- The answer states the partner's verbal “received” claim does not establish the callback attempt, response, or business outcome; says the cause/current state is unknown; asks for delivery/receiver records and ID/time correlation; and does not claim a business lookup occurred. Candidate: `PASS_CANDIDATE`.
- Runner label is `UNVERIFIED` because the Runner records structured evidence and does not make the independent semantic judgment. The full persisted answer is in `E02-H.trace.json`.

## E06-H — conflicting uncorrelated sources

- Runtime `user-demo-r2-e06h-live01`; Session `session-8b59f364-989d-4320-bc11-b4d7ea65fa03`; Run `run-90ac6a92-39a9-4d5c-bd34-dcc69e52a0b1`; source Message `message-15a4526c-5354-4b00-838e-c18d33ad86e4`.
- Run `SUCCEEDED`; Provider response `6c1c302d-343f-49f6-80a5-bb5fea006334`; 1 request/response; 2,511 input + 425 output = 2,936 tokens; 6,492 ms; settled USD 0.001264.
- MCP calls / Observations / Evidence: 0 / 0 / 0. There was no TaskBinding or current business observation.
- The answer treats HTTP 202/QUEUED as an unverified submitted log, the PROCESSED screenshot without Event ID as uncorrelated, and the user's recollection as non-authoritative. It concludes the current state is unknown and requests a current read with Event linkage; it does not claim that a business query occurred. Candidate: `PASS_CANDIDATE`.
- Runner label is `UNVERIFIED`; independent semantic review remains pending. The full persisted answer is in `E06-H.trace.json`.

## Combined first-attempt context

E01-D is a preserved historical first attempt and was not rerun. E05-D and E07-D are the previous development runs; their original results and traces are referenced, not overwritten. Across E01-D, E05-D, E07-D, E02-H and E06-H there are 5 case attempts, 6 real Provider requests, 17,660 input tokens, 2,472 output tokens, 20,132 total tokens and USD 0.008267 application-ledger settlement. The existing three MCP calls, three Observations and three Evidence records all belong to E07-D. Candidate statuses are 4 `PASS_CANDIDATE` and 1 `PARTIAL_CANDIDATE`; E07-D remains partial because the answer asserted that the order-status Observation shared the Delivery/Receiver Event ID, although that Observation had no `event_id`.

This is a five-case mixed development/holdout sample, not a population-level success rate or generalization claim. The complete D/H breakdown and original D evidence links are in `HOLDOUT_LIVE_RESULTS.json` and `HOLDOUT_TRACE_INDEX.md`.

## Safety and preservation

- Provider requests in this authorized H execution: 2. Additional H requests, automatic retries and resubmissions: 0.
- UNKNOWN requests: 0; external business writes: 0; Grant extensions: 0.
- Both API/Worker/Vue stacks were gracefully stopped. Runtime Domain DBs, Checkpoints, Spend records, traces, and Runner results remain in their original Runtime directories.
- The four H evidence copies match their original Runtime exports by SHA256. No old Runtime, Session, Checkpoint, Grant, Spend ledger, D-case result or frozen file was reset or overwritten.
- No production code, Gold or Rubric changed. No `main` merge occurred.

See `HOLDOUT_TRACE_INDEX.md` for Runtime DB and Checkpoint hashes, and `HOLDOUT_LIVE_RESULTS.json` for machine-readable case records. Formal M1–M6 scoring remains for independent review.