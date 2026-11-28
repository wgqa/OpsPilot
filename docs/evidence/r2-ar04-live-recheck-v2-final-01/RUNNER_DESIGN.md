# Final live runner design

## Reuse and version binding

`run_live_final.py` delegates source/Trace validation and the full Mock Assistant path to the accepted V2 implementation at `../r2-ar04-live-recheck-v2-prep-01/run_v2.py`. It does not edit that runner or production files. A scoped adapter temporarily binds V2's task and Base to this task and applies a unique non-secret Runtime service identity/config version. It restores the imported V2 module after each call.

Before preparation, preflight, authorization validation and every future send boundary, the adapter verifies:

- task Base ancestry, no merge after Base, no tracked diff outside this evidence directory;
- North Star, AGENTS, Review Skill and baseline Blobs;
- production `chat.py` and `assistant.py` Blobs;
- frozen 29-message history, questions/Gold/rubric hashes, old real traces, corrected per-Case reply source, and prior protected RED/history records;
- request model, non-thinking parameters, token ceiling, answer `tool_choice=none`, tool schema and trusted prompt prefix.

## Preparation path

1. `prepare` installs the offline network guard.
2. Corrected V2 source entries are validated before Mock dispatch.
3. Three independent Assistant → Context Builder → two Mock summary calls → Domain validation/persistence → final answer Prompt → Mock answer paths run through the normal Runtime Grant and Domain APIs.
4. The Mock runner persists its request trace and a shared 9-slot ledger; the ledger is explicitly `MOCK`, and its internal estimated settlement is not a Provider charge.
5. The existing zero-cost preflight reloads the main repository `.env`, reports booleans only, supplements only non-secret Runtime config in an isolated test identity, creates/binds a temporary Grant, and constructs an Assistant model with Mock transport. It performs no Provider authentication or request.
6. The result becomes `READY_FOR_LIVE_AUTHORIZATION` only if all Mock checks and the Grant preflight pass and the worst-case reserve is under USD 0.06.

## Live entry and authorization

The command is `python run_live_final.py live --authorization <fresh-task-authorization.json>`. It rejects missing, malformed, stale, expired or wrong-task manifests before loading the Mock results or creating the output directory. It requires the exact matrix, provider/model, price snapshot, token limits, no retries, no external MCP, `tool_choice=none`, no more than USD 0.06, and a validity window of at most 24 hours. A price snapshot older than 24 hours blocks the run.

After validating the manifest, the live entry repeats a zero-cost Runtime Grant/config preflight against the main `.env`. Only then does it call the existing serial `run_recheck.run_cases` path using V2's current source/answer validator. The V2 adapter configures three cases and the existing `GlobalBudgetLedger` once for all nine request slots. Each case receives its own Domain database, Checkpoint, Session, Run and Grant; the shared ledger reserves the full worst-case request cost before each send. The underlying HTTP transport uses retries=0. An exception after send start is `UNKNOWN`, remains reserved, stops the campaign and is never retried. First Case failure stops later cases. `live_run_01` is single-use and cannot be resumed or overwritten.

The live mode is not used in this preparation. No authorization file or `live_run_01` exists. Do not treat the preserved older authorization strings as authorization for this task. The authorized hard cap is copied into the reused ledger before ledger creation; a lower authorized cap cannot silently inherit the task maximum.

## Evidence boundaries

The live Runner saves redacted request/response trace, Provider IDs and usage, shared cost ledger, per-case persistence/source manifests, final Prompt visibility and prior-run comparison through the existing evidence capture. Gold and rubric are excluded from outbound requests. The current Mock answers are synthetic and are not semantic scores. `L2=NOT_RUN_LIVE`; `L3=NOT_RUN`; implementation scoring remains preliminary until independent review.
