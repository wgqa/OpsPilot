# AR-03-MATERIAL-REMAINDER-01 — Offline Acceptance Plan

## Freeze and scope

- Base: `305a59c25e4161a5712a1e0127012761e63cf90f`
- Branch: `codex/ar03-material-remainder-01`
- Remote `main` before commit: `ec8c3582f6d145eec9979c43607302731411ead8`; candidate branch was absent remotely.
- Read from this target commit: `PROJECT_NORTH_STAR.md` blob `1f737712c7a36ceb34433ac09c3fbba3c3305542`; `AGENTS.md` blob `32c45506cceeaa8c76a5c56bf8360ff476b58856`; `.agents/skills/opspilot-slice-review/SKILL.md` blob `d405c8d413d633824b279202cc1503dab4cf0b03`.
- Frozen MAT Gold: `docs/evidence/ar-03/material-01/CASES.json`, blob `faf16fbb857278e98f8afbe179fe327855132967`
- This slice changes only the new experiment's call limits and Task budget policy. It does not authorize or send a real Provider request.
- North Star, AGENTS, project Skill, prior MAT contract, deferred gates, and prior traces were read from the Base checkout. The project Skill remains the process guide; North Star §8 remains authoritative.
- The four recorded blobs matched `git rev-parse HEAD:<path>` and `git hash-object --path=<path> <path>`. The final branch diff contains no merge history and does not change North Star, AGENTS, Skill, frozen MAT Gold or historical evidence.

## Test matrix

| Concern | Positive evidence | Negative evidence |
|---|---|---|
| Autonomy capacity | A formal Assistant Worker completes 11 local MCP calls, including repeat reads, through stdio MCP and Domain | Campaign still rejects Provider request 17 and rejects spend beyond the persisted USD cap |
| Business currentness | MockTransport path reads same Event Delivery and Receiver; QUEUED and PROCESSED produce different fixture answers | No cross-run evidence is used; no diagnoses, handoff queue entries, or receipts are created |
| Skill availability | ON exposes the Skill loader while allowing the model fixture to decide whether to call it | OFF does not expose it; ON does not auto-load it |
| Authorization | Trusted API creates the bound Task; no-bound order tools remain hidden under existing regression tests | Provider construction from new experiment ID plus API key alone remains denied; Task policy requires the matching open campaign row and bound demo service |
| Recovery and accounting | Dispatches, MCP calls and attempts remain durable and idempotent | UNKNOWN remains a campaign stop; same-key replay and new logical keys cannot send after UNKNOWN |
| Time protection | New Task retains its existing 300,000 ms active-time deadline; each Assistant Run remains bounded by 60 seconds and MCP handlers by 12 seconds | At the active-time deadline, a would-be MCP reservation is rejected before an Attempt row is inserted |
| Compatibility | Default Runs remain 8/6; old material campaign remains 16/10 | Old campaign ledger schemas that do not contain this experiment ID are rejected without migration |

## Evidence levels

- `RED` was first captured with the project virtual environment after Base-only tests exposed missing experiment registration, scoped limits, and Task policy support.
- GREEN uses a deterministic FixtureModel and HTTPX `MockTransport`; actual FastAPI, Worker, LangChain Agent, local stdio MCP and Domain SQLite paths are exercised.
- No live DeepSeek call, browser test, business write, or paid one-shot claim was used. Mock completions do not establish real model quality or Skill benefit.

## Stop line

After the focused tests, relevant prior MAT/AR-03/S3/D2 security regressions, evidence generation and isolated branch submission, stop. Real Provider execution requires independent review and new explicit paid authorization.
