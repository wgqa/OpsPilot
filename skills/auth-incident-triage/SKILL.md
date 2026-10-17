# auth-incident-triage

Use this method for an authentication-related HTTP 401 investigation:

1. Query the current integration configuration, principal status, and authentication policy through the read-only MCP tools.
2. Run the registered business Probe and compare its current response with the current configuration and policy versions.
3. Distinguish a disabled principal, a credential-reference mismatch, and missing, stale, or conflicting evidence. Do not infer a cause from a historical case.
4. Ask for another read-only fact when evidence is incomplete. Pass only current, task-scoped MCP Evidence to the deterministic Evidence Gate.
5. Stop when the Gate says NO_ACTION or INCONCLUSIVE. A READY result only permits the existing Plan and human-approval workflow to continue.

This Skill describes investigation method only. It does not define tools, permissions, approvals, repairs, current facts, credentials, or authorization.
