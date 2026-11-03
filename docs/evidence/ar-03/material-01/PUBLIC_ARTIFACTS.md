# Public artifact handling

The RED logs in this publication branch are sanitized derivatives of the original local run logs. The original byte-for-byte logs remain on the local `codex/ar03-material-01` candidate worktree. Sanitization replaces only the isolated TestClient fixture password echo with `[LOCAL_TEST_PASSWORD_REDACTED]`; test outcomes, traceback structure, commands, and exit codes are otherwise retained. A complete per-file hash inventory will be added with the implementation evidence.
