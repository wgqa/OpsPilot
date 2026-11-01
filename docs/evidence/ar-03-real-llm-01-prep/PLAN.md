# AR-03-REAL-LLM-01 — Offline Preparation Plan

**Preparation status:** `IN_PROGRESS_OFFLINE_ONLY`
**Base:** `codex/ar02-ar03-integration-01@11e86b4606074495ab448630b3017f14a3e0f6dd`
**Working branch:** `codex/ar03-real-llm-01`
**Remote state:** `UNVERIFIED`; read-only `git ls-remote` could not connect to GitHub port 443.
**No main update, Provider request, browser action, or business operation is authorized in this prep slice.**

## Checkout and governing records

- Repository: `wgqa/OpsPilot`; current local HEAD at start was the exact requested base, with a clean worktree.
- `PROJECT_NORTH_STAR.md` Blob: `1f737712c7a36ceb34433ac09c3fbba3c3305542`.
- `AGENTS.md` Blob: `32c45506cceeaa8c76a5c56bf8360ff476b58856`.
- `.agents/skills/opspilot-slice-review/SKILL.md` Blob: `d405c8d413d633824b279202cc1503dab4cf0b03`; actually read at start and again during closeout.
- AR-02 × AR-03 integration plan/report: `docs/evidence/ar-02-ar03-integration-01/PLAN.md` and `REPORT.md` at the base commit.
- AR-03-04 source acceptance contract/report: commit `255087bae4dc0e9990a650786f5b9aae26f9f1db`, paths `docs/evidence/ar-03/upgrade-investigation/ACCEPTANCE_PLAN.md` and `REPORT.md`. The source candidate was reported as an acceptance candidate, not treated as independent approval.
- Historical AR-02 real journey: `docs/evidence/ar-02/real-journey-03/REPORT.md` remains `PARTIAL`; S02-4 did not make a fresh Receiver observation. This record and its traces are not modified.
- Frozen source user inputs: `docs/evidence/ar-02/hf-01/SMOKE_INPUTS.md` Blob `ee9b1623a2296905c425449709a2f9ae6563caca`; `docs/evidence/ar-02/real-journey/CASES.json` Blob `0b8411942ec99724d9aa10d45faa50a58676836b`. They are background safety references, not rewritten or substituted for this new prompt.
- Applicable AR-02 experiment budget code and no-write boundaries are reviewed from the base. Historical experiment rows are not opened for mutation or reset.

The preparation serves the North Star user journey: the user can ask about an unfamiliar protocol upgrade, let the model choose among authorized documentation and current read-only business facts, and receive a fact-grounded draft with uncertainty. The code will preserve the existing single Assistant path rather than add another Runtime or fixed tool sequence.

## Frozen live journey candidate

The exact user prompt is in `CASES.json` and is identical in the two cases. Each scenario gets a fresh isolated Domain database, Checkpoint database, Session, and run. A trusted support API operation binds the test order before the model run; chat text cannot create that authorization. Fixture preparation is recorded as setup, not Agent evidence.

The only business fact intentionally varied between the paired cases is the target Event's current Receiver state: `QUEUED` versus `PROCESSED`. Both use a same-Event `HTTP 202 / ACKNOWLEDGED` delivery. The model may discover, compare, query current facts, clarify, or answer in any legal order; no sequence is prescribed.

## Acceptance and offline preparation

`GOLD.md` freezes outcome, evidence, permitted conclusion, and forbidden result. `BUDGET.md` freezes the proposed caps but explicitly does not authorize a paid request. Offline work will:

1. Add the new unique experiment ID to the existing allowlist/schema only if needed for isolated budget preflight; do not change historical limits or rows.
2. Exercise the exact formal API → Worker → `ASSISTANT_V1` → LangChain/HTTPX path using `httpx.MockTransport` and a fresh test DB/checkpoint.
3. Verify the new ID cannot open against an older DB schema, provider opt-in remains off by default, a present API key alone does not enable it, and the new budget is isolated from old IDs.
4. Run the relevant AR-02 and AR-03 offline regression tests. Keep all RED and setup failures.

The offline mock can prove request serialization, API/Worker wiring, local budget accounting, and safe source boundaries. It cannot establish real-model decision quality, actual Provider Usage/cost, or browser experience. Before any live request, the Main Agent and user must separately approve the frozen cases and expense limits, and the official price/configuration must be rechecked.

## Stop line

Stop after frozen preparation, the formal MockTransport preflight, and relevant offline regression. Deliver either `READY_FOR_LIVE_AUTHORIZATION` (only if all preparation gates pass) or `BLOCKED`, then wait. No real DeepSeek request, browser, approval, repair, delivery, ticket write, old ledger use, main merge, or further phase is permitted here.
