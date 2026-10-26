# Stage B RED record

The frozen plan is commit `5a33f3e`. These tests were added before product-source changes and reproduce the missing exact source projection.

## Fresh runs

- `runs/red-01/api-pytest.log`, exit 1: test collection was blocked because the pytest console entry point did not include the repository on `PYTHONPATH`. This is a test invocation setup failure, not a product RED.
- `runs/red-01/projection-node-test.log`, exit 1: expected pre-implementation `ERR_MODULE_NOT_FOUND` for `frontend/src/conversation.ts`.
- `runs/red-02/api-pytest.log`, exit 1: pytest's default temp discovery hit an inaccessible user temp directory. This is an environment setup failure, not a product RED.
- `runs/red-03/api-pytest.log`, exit 1: both API cases reached assertions and failed because the message read API does not expose `answer_run_id`, `answer_source_message_id`, or `answer_kind`. The fixture persisted a real Chat answer and a durable program limit notice; an S3 authorization-revocation case also confirmed the association is currently absent. This is the effective API RED.

The RED fixtures preserve the exact association contract: only a persisted Chat answer or a durable `budget-notice:<run_id>` record with a matching `chat_message_sources` source digest may be linked. The S3 case also requires association metadata to be redacted together with its answer body after current scope authorization is revoked.

No production source was modified before these runs. Browser evidence remains `NOT_RUN / BLOCKED_BY_TOOL_ENVIRONMENT`; these API tests do not claim browser acceptance.
