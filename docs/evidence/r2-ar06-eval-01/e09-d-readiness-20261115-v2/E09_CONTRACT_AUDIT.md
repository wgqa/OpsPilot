# E09-D contract audit

## Baseline and freeze

- Case: `E09-D`, split `D`, continuous collaboration.
- Base and current pre-change HEAD: `9c5a22f393b0852605cb603b81b350af915ce98b`.
- Frozen `CASES.json` SHA256: `c1acd3fa789befa733aa96bf3a49b08357ff071f3b627b4c40319882e2805cf8`.
- The frozen Gold, Rubric, evaluation protocol, and their hashes are unchanged.
- The Gold gives one journey-level instruction, not a frozen list of verbatim chat turns. `E09_TURN_SCRIPT.json` is an explicitly post-freeze execution supplement, marked `POST_FREEZE_FIXTURE_SPECIFIED`; it is not represented as pre-freeze holdout material.

## Consistent interpretation

The journey has two authority phases. Ten `CHAT_READONLY` messages first discuss the HTTP 202 goal and synthetic user materials in a Taskless Session. Only after those runs finish is `async-order` bound using the trusted order API. The binding request itself asks for the current Delivery/Receiver status, so current business observations are made within that Task-bound Run.

The distinction in the fixture is:

- The HTTP 202 question, pasted configuration, log excerpts, review matrix, timeline, and draft checklist are user-provided material. They can support discussion of what the user supplied, but do not establish deployed configuration or current business state.
- The stored Taskless Summary is derived conversation context. Its provenance dependencies identify the source messages; it is not a business Observation or a substitute for the later TaskBinding.
- The bounded excerpts of earlier Assistant answers are explicitly marked historical. They do not count as a current Receiver/Delivery read.
- The final Task-bound Run's Delivery and Receiver results are the current business evidence for that Run. The fixture verifies both refer to the same Event and the Observation rows carry that Run and Task ID.

No contract ambiguity was found that blocks this offline fixture. The supplementary script specifies the missing per-turn materials and ordering; it must remain visibly post-freeze. This run is an engineering and wiring check only, not a formal model-quality score.

## Post-freeze fixture identity

`E09_FIXTURE_MANIFEST.json` records the supplement's creation time, source Gold SHA, identity scope, TaskBinding position, material digests, and the explicit `gold_modified=false`, `provider_authorized=false`, and `external_business_writes_authorized=false` boundaries. The manifest points to `E09_TURN_SCRIPT.json` by SHA256. The script contains the exact body, identity, input kind, sequence, and SHA256 for every Taskless turn plus the trusted binding question.

The order profile is the existing isolated `r2-e07-queued` fixture: `async-order` has a Delivery with HTTP 202 / `ACKNOWLEDGED` and a Receiver in `QUEUED`. This is a controlled offline current Observation, not a claim about a live order.

## Scope limitation

The final Task-bound input correctly excludes Taskless Summary IDs. It retains the original goal and the relevant user assertion through the normal bounded session-history path. That path does not make every large raw attachment available in full; the test checks goal and key assertion continuity, not lossless inclusion of every log line. Summary-based context must not be promoted across the Task boundary.
