# E10-H Contract Audit

**Task:** R2-AR06-E10-H-READINESS-01
**Base:** `335346c3c96b06e3de65c70c1096eb5ae1961a6b`
**Working branch:** `codex/r2-ar06-e10-h-readiness-01`
**Evidence class:** offline Fixture Model + formal FastAPI/Worker + local Domain MCP

## Baseline read and frozen files

The following files were opened from the base checkout and checked against its Git blobs:

| File | Base blob |
|---|---|
| `PROJECT_NORTH_STAR.md` | `43dabda468506717c6956e676dfad4304c4f38e6` |
| `AGENTS.md` | `807b928686a4dd2cac7b15b3c354b9943c93c910` |
| `.agents/skills/opspilot-slice-review/SKILL.md` | `d405c8d413d633824b279202cc1503dab4cf0b03` |
| `docs/evidence/r2-ar06-eval-01/CASES.json` | `c3f5190fa7193e89d36a3e54f5489577d0c0b033` |
| `docs/evidence/r2-ar06-eval-01/RUBRIC.json` | `71e8f975e50b2883c1ea96c785a66fbd3207606d` |
| `docs/evidence/r2-ar06-eval-01/EVAL_PROTOCOL.md` | `be2969c409b13966cd2c6222445974710e02422f` |

The frozen case input is submitted byte-for-byte as stored in `CASES.json`:

> New Session: use any still-valid cross-session method memory only as guidance, check it against current evidence, and ignore/reject an older conflicting memory after it is revoked.

Its UTF-8 SHA256 is recorded in `E10_MEMORY_FIXTURE_MANIFEST.json`. The case remains in the H split. Gold, Rubric, evaluation protocol, and historical results were not edited.

The frozen E10 constraint is preserved exactly:

> Existing AR04B fixtures cover cross-task use, owner/tenant isolation and revocation boundaries, but do not provide this exact two-memory conflict pair; status cannot exceed PARTIAL.

This work supplies the missing offline pair. It does not lift that ceiling or award a formal score.

## Existing architecture and chosen Memory type

The implementation uses the existing **Semantic Memory** path in `opspilot/domain/semantic_memory.py`:

1. A persisted USER message on a trusted Task is submitted to `POST /api/tasks/{task_id}/semantic-memories/candidates`.
2. A project-authorized APPROVER activates the candidate through `POST /api/semantic-memories/{id}/confirm`.
3. The approver revokes the conflicting record through `POST /api/semantic-memories/{id}/revoke`; the row and `REVOKED` event remain auditable.
4. A fresh target Session gets a trusted TaskBinding from `POST /api/sessions/{session_id}/assistant/order`.
5. The existing Context Builder selects current ACTIVE Semantic Memory by tenant and TaskBinding-derived project. It records the selected reference and exclusions in the Context Manifest and labels the model projection `CONFIRMED_SEMANTIC_PROJECT_CONTEXT_NOT_FACT`.
6. Existing Assistant tools read the current Delivery and Receiver observations. Memory is method guidance, not current business evidence.

Semantic Memory is **project and tenant scoped**, not Owner scoped. Each source Task in this fixture is nevertheless created by trusted `tenant-a / support-a`; confirmation and revocation are done by project-authorized `approver-a`. This is distinct from Personal Memory, which has its own tenant and Owner scope. E10 does not substitute Personal Memory for Semantic Memory.

`opspilot/domain/episodic_memory.py` provides a separate approved case-experience path. It was not used for this E10 pair. No new Memory store, lifecycle, or retrieval layer was added.

## Relevant existing source and regression evidence

| Source at base | Blob | Use |
|---|---|---|
| `tests/test_ar04b_memory_journey_01.py` | `d34bba3217d8ac0adfb9ede63dcab7d6024b95eb` | Formal Assistant wire, ON/OFF, cross-tenant and revoke race precedents |
| `opspilot/domain/semantic_memory.py` | `3f0c56e186e60cb3837d5f7cd15d1dc85c0d9bfb` | Candidate, confirm, revoke, source and scope currentness |
| `opspilot/domain/episodic_memory.py` | `dc761237659e28fd31f5d7453d44be06989db479` | Confirmed the separate episodic responsibility |
| `opspilot/domain/chat.py` | `83234c9b678d6580fbd06f8b4933e40b2810359d` | Existing Memory context and manifest assembly |
| `tests/test_m303_semantic_memory.py` | `a254e3d187f358668dd8c773f951e99a580f38fa` | Candidate, approver, cross-task, revoke, revision and expiry checks |
| `tests/test_c01_b2_a_personal_memory.py` | `8665696ade4fa1fe7fe7c70f4ddacc78090ddaeb` | Personal Memory Owner isolation and lifecycle regression |

The historical `runs/E10_MEMORY_TRACE_SUMMARY.json` is retained. It records AR04B coverage but explicitly did not claim the E10 two-memory pair. Nothing in this submission replaces that historical evidence.

## Fixture semantics and limits

- A is a confirmed method-only Semantic Memory. It says to read the current Receiver, correlate it with the same Event Delivery, and not equate HTTP 202 with business completion.
- B is first created and confirmed as a conflicting method memory, then formally revoked. Its old row, version 1, version 2, source, and lifecycle events are retained.
- A separate active memory variant has its source message digest changed in the isolated Runtime to exercise `SEMANTIC_MEMORY_SOURCE_INVALID`; it is not represented as a formal user correction or revocation.
- The label names `METHOD_MEMORY_VALID`, `METHOD_MEMORY_REVOKED_CONFLICT`, and `METHOD_MEMORY_SOURCE_INVALID_CONFLICT` exist only in the evidence manifest. The test scans actual target model wires to ensure these labels, `expected_answer`, `gold_status`, revoked Memory B, and its content are absent.
- Target current facts come from target-Task MCP Observation rows for one Event: Delivery `ACKNOWLEDGED / HTTP 202`; Receiver `QUEUED`. The response does not claim completed processing.
- The Fixture Model uses a predetermined tool policy. It proves API, Worker, Context, Memory lifecycle and Observation wiring; it does not prove natural-language autonomy or that a real model will use A well.

## No-goal changes

No production Agent, Context, Memory, Schema, MCP, Domain authorization, Gold, Rubric, Provider, or Grant code was changed. No E09 runtime/database/checkpoint/Trace was read or modified. No paid Provider request, Runtime Grant, external business write, merge, or browser Live run occurred.
