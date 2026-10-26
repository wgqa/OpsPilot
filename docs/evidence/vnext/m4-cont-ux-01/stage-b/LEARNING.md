# Stage B source learning notes

## Context is not the conversation transcript

- **Principle:** model context is a bounded, filtered input for one execution. A durable workbench history is a user-facing projection of persisted Messages, Runs and Answers. They have different retention, source-validity and display requirements.
- **Business problem:** type-batched results and nearest-message matching made a late answer appear under a newer question.
- **Code:** `frontend/src/conversation.ts::projectConversation` uses persisted IDs to derive question threads; `opspilot/web/app.py::get_messages` returns exact Chat answer associations from the Domain records.
- **Evidence/failure:** Stage B RED demonstrated missing source fields. The green projection tests interleave questions/results, keep late answer formation time, retain same-text operations and orphan unassociated records rather than guessing.
- **Interview answer:** “I keep execution context and conversation history separate. The UI builds a read-only projection from stable Message/Run/Answer identities; the model prompt stays governed by Context provenance and token limits.”

## Message, Run and Task have separate identities

- **Principle:** the user request, its execution attempt and its business task are related but not interchangeable. `source_message_id` expresses origin; `task_id` expresses business scope; `run_id` expresses execution.
- **Business problem:** proximity or identical body text cannot safely tell which request produced which answer.
- **Code:** `opspilot/web/app.py::get_messages`, `frontend/src/api.ts::MessageItem`, and `frontend/src/conversation.ts::attach`.
- **Evidence/failure:** the API test verifies the exact persisted Chat Run/source pair and deliberately mutates the source relation; the latter response has no inferred association. The projection test preserves two same-text requests as separate anchors.
- **Interview answer:** “I model correlation explicitly with IDs and verify tenant/session/task/source consistency at the read boundary. When the association is absent, I surface it as unassociated instead of guessing.”

## At-least-once events and idempotent display

- **Principle:** SSE/replay may deliver an event more than once. The projection must use stable persisted IDs, not content text, to avoid duplicate presentation.
- **Business problem:** duplicate chunks or replayed messages could show an answer twice or collapse two intentional requests.
- **Code:** `frontend/src/conversation.ts::addUnique` and stable `message_id`, `run_id`, `chunk_id` keys.
- **Evidence/failure:** the pure Node test replays the same Message and chunk IDs, expecting one rendered stream; the test also preserves distinct same-text Message IDs.
- **Interview answer:** “Delivery can be at least once, so rendering is idempotent over stable event/entity IDs. I do not deduplicate by answer text because that can erase valid user operations.”

## Run success is not the same as a user answer

- **Principle:** a Run status is operational state; the user needs a durable answer or an honest limit/failure explanation.
- **Business problem:** a successful execution row alone does not prove a consumable answer, while a program limit notice must not be advertised as model success.
- **Code:** `opspilot/web/app.py::get_messages` distinguishes `CHAT_MODEL` from `PROGRAM_LIMIT`; `frontend/src/App.vue` renders the latter as a program limit; the projection omits run status only when a durable answer item is present.
- **Evidence/failure:** the API test joins a successful Chat answer to its exact source and separately links a durable `CHAT_ATTEMPTS_EXHAUSTED` notice to its source with a failed Run.
- **Interview answer:** “I report the user-facing result separately from execution status. A budget stop can be useful and non-empty without being called a model answer or successful task completion.”

## Why a read projection, not a new timeline table

- **Principle:** when relationships already exist in Message, Run, Answer and Assessment records, a deterministic read projection avoids duplicating business state.
- **Business problem:** a new timeline table would create a second lifecycle and reconciliation problem for late answers, corrections and retries.
- **Code:** `frontend/src/conversation.ts` is a pure projection; the only backend addition is a read-only association in the existing messages endpoint.
- **Evidence/failure:** frontend build and unit tests pass; backend tests cover exact IDs and S3 authorization revocation. Browser DOM/screenshot verification remains blocked and is not claimed.
- **Interview answer:** “I chose a derived view because all timeline elements already have durable identities. The Domain remains authoritative; the UI only sorts and groups the existing records.”
