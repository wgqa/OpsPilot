# E09-D readiness report

## Decision

`ACCEPTANCE_CANDIDATE` for independent review. Offline API/Worker wiring and evidence are available in this versioned directory. This is **not** an E09-D quality PASS and is not authorization to run a paid Provider. No E10 work is included.

## Base and review inputs

- Branch: `codex/r2-ar06-e09-d-readiness-01`.
- Base / pre-change HEAD: `9c5a22f393b0852605cb603b81b350af915ce98b`.
- `PROJECT_NORTH_STAR.md` Blob: `43dabda468506717c6956e676dfad4304c4f38e6`.
- `AGENTS.md` Blob: `807b928686a4dd2cac7b15b3c354b9943c93c910`.
- `.agents/skills/opspilot-slice-review/SKILL.md` Blob: `d405c8d413d633824b279202cc1503dab4cf0b03`.
- Frozen input SHA256: `c1acd3fa789befa733aa96bf3a49b08357ff071f3b627b4c40319882e2805cf8`.
- The applicable frozen Gold/Rubric/protocol files were not edited. The new turn script and manifest are explicitly post-freeze.

## Offline evidence

Final persistent Fixture run:

- Runtime: `user-demo-r2-e09-artifact` under the unique pytest basetemp `.runtime/.pytest-e09-d-20261115-finalmanifest`.
- Session: `session-9e52ca2b-c151-4c24-bf4a-dffe9a2dd497`.
- Task: `task-1fb75377-48d6-457f-a03b-b9ca1bdc24b4`.
- 11/11 Runs SUCCEEDED: ten Taskless turns and one trusted order-binding/current-query Run.
- 16 Fixture dispatches; three successful persisted Summary-compression attempts; 13 Summary dependencies.
- Three Taskless Summary versions were persisted; versions 1 and 2 were superseded, version 3 remained CURRENT. The later Taskless Run saw the already persisted Summary in its actual request.
- The Task-bound Run excluded all Taskless Summary IDs. It retained the original HTTP 202 goal and key user assertion via the normal session-history path; the final model input showed the TaskBinding.
- The final Run used `get_callback_delivery` and `get_receiver_processing`. Both current Fixture results shared an Event ID, and the Observation rows referenced the final Task and Run. The Fixture answer was `HTTP 202 / ACKNOWLEDGED` with `Receiver=QUEUED`; this is not a real business observation.
- The Session contains 22 messages, 11 Run answers, and two final-Run Observation rows. `assistant_calls.request_json`, context manifests, the Summary rows, and their dependencies are included in the versioned audit files.
- Summary compression input estimates were 320, 5,237, and 1,363 tokens, each within the recorded 6,000-token compression input limit. These are application estimates, not Provider Usage.
- Provider sends: 0. Runtime Grants: 0. UNKNOWN: 0. External business writes: 0.

The Fixture model verifies call wiring and projection behavior, not natural-language model quality. The exact output/manifest hashes are recorded in the files themselves and in `E09_EVIDENCE_SHA256.txt`.

## Observed call path

`POST /api/sessions/{id}/assistant/messages` admits each Taskless turn; the Worker calls the existing Context Builder and its compression lifecycle. Successful compression attempts create versioned `context_summaries` and `context_summary_dependencies`. A later Taskless model request shows the current Summary in `assistant_calls.request_json`. The trusted order endpoint then creates the TaskBinding and submits the current-state question in the same Run. The Task-bound Context Builder does not reuse the Taskless Summary; current Delivery/Receiver MCP results and their Observations are linked to that final Run and Task.

## Tests

The final full-suite command and result are in `E09_FINAL_GREEN_LOG.txt`; iteration RED and focused GREEN logs are also retained.

- E09 readiness, AR04A journey, compression budget/cancel, M302 Context, and M4 currentness: **33 passed in 187.82s**.
- Coverage includes persisted Summary use, Taskless-to-Task separation, cross-tenant Summary isolation and foreign-session denial, invalidated Summary exclusion, compression budget/failure behavior, and historical evidence marked historical-only.
- The E09-specific assertions additionally verify that the initial HTTP 202 goal and source-qualified `max_attempts=5` / claimed v1 survive compression, all Taskless summaries stay out of the Task-bound model input, the current Tool Observations belong to the final Run/Task, and evaluation labels do not leak into model input.
- Full repository suite: `NOT_RUN`.

Iteration record: the first cross-tenant fixture attempt used a runtime alias outside the required `user-demo-*` allowlist and failed closed with `USER_DEMO_RUNTIME_NAME_INVALID`; the alias was corrected and both focused and full regressions passed. An earlier fixture design used a separate TaskBinding acknowledgement Run and then another current-query Run. It reached `CHAT_ATTEMPTS_EXHAUSTED` under the existing three-attempt total (which includes compression). The fixture was changed to place the final question in the trusted binding request's `initial_message`; no production code or attempt limit was changed. The original console capture for that iteration was not persisted, so this is recorded as an implementation observation, not counted in the 32-test result.

## Changed scope and limits

- Production code, Schema, Gold, Rubric, permissions, Context budgets, and runtime limits: unchanged.
- Added one offline Fixture/API test and versioned evaluation evidence/docs only.
- The 10-turn script is post-freeze and cannot be called an untouched frozen per-turn sample.
- Synthetic configuration and logs remain untrusted. The current Fixture is queued, not processed.
- Fixture output cannot show that DeepSeek will preserve the goal, use Summary well, distinguish current/historical sources, or choose efficient tools.
- The Task-bound Run correctly excludes Taskless Summary. The regression evidence supports that boundary; it does not establish lossless availability of every original attachment after binding.
- Live Usage, vendor invoice, current endpoint credentials, and user-facing browser behavior: `NOT_RUN`.

See `E09_LIVE_RUNBOOK.md` for the 11-Run plan and USD 0.22 proposed upper pool estimate; a separate explicit authorization is still required.


## Versioned evidence provenance

This directory is the final version for the corrected manifest. Its manifest SHA256 is `4de0ce03bc958b318ec5c981abf1550cd52503ca6abaf5f3b0371a9584efcf0a`; the final trace records the same SHA. The earlier manifest with the placeholder midnight timestamp was preserved as ../e09-d-readiness-20261115/E09_FIXTURE_MANIFEST.initial.json with SHA256 `b8aa52a00c52b20dfc289ac0b2287a072c8d9a8550b661990cad014a977f4480`; earlier trace artifacts remain in the prior versioned directories and are not the final run.
