# AR-02-P0-01 v1.1 — authorized free implementation freeze

Base: main `ec8c3582f6d145eec9979c43607302731411ead8`. Reference only:
AR-01 `b4e130fb22491bc84e69329df2553253a239e024`; never merge that branch wholesale.
Current human reply: `授权代码实施与免费验证` (2026-10-30). This supersedes the
attachment's IMPLEMENTATION_NOT_AUTHORIZED for code/free tests only. Paid Smoke,
browser STOP, main merge and Stage B B-11 HOLD remain unchanged.

Actual North Star / AGENTS / Skill reads, blobs:
`1f737712c7a36ceb34433ac09c3fbba3c3305542` /
`32c45506cceeaa8c76a5c56bf8360ff476b58856` /
`d405c8d413d633824b279202cc1503dab4cf0b03`.
Task attachment SHA256: `0d583d29ed4c0f051f6b322c9d30a6dc6ff02ad21f54dbdc5d968c73fedc4b62`.
M2-01/M2-02 DEFERRED_GATES remain applicable. No historical Gold/RED edits.
Original checkout main@add47ec8, modified AGENTS and untracked materials untouched.

## Minimal interface gaps and reuse

| Area | Verified present | Required change |
| --- | --- | --- |
| Session/Message | nullable Task Chat, owner/tenant, operation id, persisted answers | opt-in professional assistant message admission using same records |
| Worker/SSE | fenced single worker, recovery, outbox, answer source IDs | persist a fixed assistant core per new Run; retain legacy dispatch |
| create_agent | real six-tool loop in isolated AR-01 | product context/admission, persistent execution, normal-language delivery |
| Knowledge | versioned lexical/BM25 assets; S3 tool requires Task | tiny trusted document grant mapping and Session scope selection, no fake Task |
| Business | authorized order catalogue, TaskBinding, MCP/HTTP, current_s3_evidence | user-confirmed binding, same read tools/currentness; no formal diagnosis writer |
| Continuity | Message history/source checks | retain materials/references across no-Task/Task turns, exclude invalid sources |
| Recovery | Domain worker recovery + existing checkpoint library | stable create_agent thread, durable calls/observations, nonduplicate final answer |

No generic Router/Planner/Goal store. Plain questions use the same model core,
not HTTP-status keywords. The model can answer/clarify/query/stop. Program controls
scope, currentness, accounting, final persistence and all privileged actions.

## Critical RED, not predetermined model output for every Gold

1. Existing authenticated Session has no Task: assistant entry is accepted,
   idempotent and creates no business binding; baseline endpoint missing is RED.
2. Trusted no-Task document scopes: single auto-selection, multiple explicit
   selection, current grant/version checks, no grant still permits concept Chat.
3. Same Session material/answer/source continuity, real local MCP when bound;
   revoked/cross-tenant/stale/history facts cannot become current facts.
4. A persistent tool observation before final answer survives process restart;
   retry does not duplicate the final Message, reset counters or resend unknown
   Provider results. Exact durable IDs and traces required.

Retain G01–G10 in GOLD.json without a unique tool sequence. Use deterministic
models only for wiring/free tests, clearly not proof of intelligence. Genuine
model validation remains NOT_RUN until separately authorized.

## Bounded execution and transition

Reuse existing answer attempts and Task auxiliary accounting; new core's actual
Provider calls are durably counted, including failed/reserved/unknown. No increase
to existing Task totals. Per Run at most 8 model / 6 MCP attempts, 30s/model,
12s/tool, 60s execution and bounded context. No-Task access has no business tools.
Knowledge grants are not Semantic Memory approval grants or production IAM.

User-confirmed resource selection uses the existing authorized catalogue and
TaskBinding creation transaction. Core remains read-only: no DiagnosisReceipt,
Plan, Approval, Intent, Ledger, Queue, Handoff or simulated business recovery.
Formal critical correction still uses existing confirmation/TaskControl/new Run;
legacy protected execution remains available. No cross-core checkpoint switching.

Early checkpoint: free S01 concept and S02 Knowledge→authorized investigation
in one Session, then freeze paid preflight NOT_RUN. Existing P1 request reserve
USD .317031 exceeds proposed Smoke total .20; cannot reuse that strategy blindly,
infer hard token bounds from estimates, spend old authorization or raise the cap.
Paid configuration requires separate review and authorization.

## Evidence and stop

Freeze → actual API RED → minimum product wiring → free early smoke → continuity,
OS recovery and relevant legacy safety tests. Preserve all failures, raw commands,
exit codes, MCP/HTTP/SQLite/provenance and final user answers. No browser automation.
Stop with candidate commit on codex/ar02-p0-01, no main merge. Report partial,
not-run and product failures separately; no new planning round or platform work.
