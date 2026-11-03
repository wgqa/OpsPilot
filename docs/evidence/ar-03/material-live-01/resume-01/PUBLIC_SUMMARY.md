# Public safety summary

- Candidate is based on accepted safe commit `ff956ea71b90448d40229c57b8f8619c997b5cbd` on `codex/ar03-material-live-01-exec-prep`.
- New identity `AR-03-MATERIAL-LIVE-01-RESUME-01` is separate from the consumed historical claim. Its claim state is pending explicit paid authorization; the paid one-shot is not consumed.
- Frozen caps are unchanged: 16 Provider / 10 MCP / USD 10.50, with USD 0.645600 reservation per Provider request.
- Offline formal API/Worker/MCP preview passed with current same-Event `202/ACKNOWLEDGED` and `QUEUED`; Provider HTTP=0 and business writes=0.
- Preflight returned `PREFLIGHT_READY_AWAITING_PAID_AUTHORIZATION` on implementation HEAD `9cca2504005aeb7bd4e7ad7ad69fb0f3ddfdd26c`.
- Full raw logs, DBs and environment-specific execution data stay in local private evidence storage. No credentials, absolute local paths, or raw database contents are included here.
- Broader regression reproduced the same 4 failures on the accepted base; details and limits are in `FAILURES.md`.
