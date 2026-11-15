# E08-H Readiness Report

## Decision

**`ACCEPTANCE_CANDIDATE` — technically ready for first Live evaluation after independent acceptance and separate user cost authorization.** This task did not create a Grant, start Live services, send a real Provider request, run browser automation, or perform a business write.

## Evidence

- Frozen question and CASES/Rubric/Evaluation Protocol hashes are unchanged; see `E08_FIXTURE_MANIFEST.json`.
- `E08_OFFLINE_TRACE.json` records a new isolated Session, official Assistant API TaskBinding, a sourced history Run, a separate evaluated Run, two `get_receiver_processing` MCP calls, two Observation/Evidence pairs, and the final Fixture Model answer.
- The historical Run read target Event `...0101` as `QUEUED`, version 2. The local synthetic transition changed only that new Runtime's Receiver row to `PROCESSED`, version 3. The evaluated Run then read the same Event as `PROCESSED`.
- The distinct decoy Event `...0102` remained `QUEUED`. A user-supplied prior log says it was `PROCESSED` at `2026-11-14T12:00:00Z`; it is marked `USER_PROVIDED_UNVERIFIED`, and the current Run contains no decoy Observation.
- The persisted old answer remains in Session History, but its source now returns `BUSINESS_SOURCE_INVALIDATED`. Its text is not injected as a current fact. The final request includes the previous untrusted user turn and exact frozen question; the prior Assistant answer itself is absent from the current model input. The frozen question restates that history claim.
- Cross-Event transport history access under the target TaskBinding is denied. Old Evidence after the target version transition and tampered Evidence Digest are both rejected as current sources.
- Actual model-visible schemas and messages, including the current target ToolMessage, are in `E08_MODEL_INPUT_AUDIT.json`; no Gold/Rubric labels or post-freeze fixture label were found in the model requests.

## Limits

The offline assistant uses a scripted Fixture Model. Its 4 dispatches and synthetic 124-token metadata prove the route and evidence wiring only; they are not model-quality evidence. The runner records the offline attempt as `UNVERIFIED`, not PASS. The historical answer is a Fixture Model setup answer. The real model has not seen or evaluated an E08 prompt in this task.

The follow-up Live Runtime is preprimed and has no Grant. Current official peak rates and local rate configuration were inspected for the runbook; values and provider prices must be rechecked before a future authorization. Suggested application cap is USD 0.06 for one Run, with at most 8 model dispatches; no amount was authorized or spent here.

## Execution totals

- New Runtime directories created: 3 named E08 runtimes (two offline fixture runs and one Live-readiness prime), plus pytest's fresh isolated basetemp directories; none were reset or deleted.
- Candidate Trace's evaluated run: SUCCEEDED as a Fixture execution; 2 MCP calls, 2 Observations, 2 Evidence records; Runner `assessment_status=UNVERIFIED`.
- Real Provider requests: 0; UNKNOWN: 0; Runtime Grants created: 0; business writes: 0.
- Final combined E08/E07/E03/E04/source-currentness regression run: 52 passed in 115.56s.

See `E08_LIVE_RUNBOOK.md` for the bounded one-run procedure and stop conditions. Independent main-Agent review and explicit spending approval remain required before Live.
