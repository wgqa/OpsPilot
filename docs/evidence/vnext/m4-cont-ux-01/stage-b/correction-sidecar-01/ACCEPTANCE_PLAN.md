# Stage B Correction Sidecar — Frozen Acceptance Plan

Status: `FROZEN_BEFORE_RED` (supplemental implementation evidence, not a Stage B verdict).

## Baseline

- Repository: `wgqa/OpsPilot`
- Approved base: `main@54329a6f11f909167ca6b64de6a905d5fe9e36fc`
- Worktree: reused isolated worktree at the approved commit; the primary checkout has unrelated local changes and remains untouched.
- Target Skill: `.agents/skills/opspilot-slice-review/SKILL.md`, blob `d405c8d413d633824b279202cc1503dab4cf0b03`.
- North Star blob: `1f737712c7a36ceb34433ac09c3fbba3c3305542`.
- AGENTS blob: `32c45506cceeaa8c76a5c56bf8360ff476b58856`.
- Frozen CONT-UX Gold remains unchanged: blob `1290ef276690f00b6e9683f0251302f376a70098`.
- Existing closeout API response `runs/green-api-05/responses/correction-answered.json` contains the real persisted `CHAT_READONLY` Run with `status=BLOCKED`, `blocked_reason=CORRECTION_CONFIRMED`, the original question as its source, and a separately completed correction Investigator Run. This response is historical evidence and will not be modified.

## Frozen assertion

When a confirmed, applied correction has an associated new investigation Run, a `CHAT_READONLY` sidecar blocked specifically with `CORRECTION_CONFIRMED` must not appear as a separate unfinished/failure card in the user-facing question thread. Keep the original Run in Domain/API data and retain an expandable audit detail associated with the correction assessment. A genuine failed business investigation must remain visible with its failure reason. Other blocked reasons retain their current behavior.

## RED/GREEN procedure

1. Add a projection regression using the saved real API payload and a deterministic positive/negative frontend fixture.
2. Run the new test before source changes and preserve the raw output as RED.
3. Make the smallest change in the existing conversation projection and its existing expanded correction details.
4. Run the same tests GREEN, then the existing frontend projection tests, typecheck, production build, changed-file ESLint, and the applicable Stage B API/S3 authorization regression.
5. Do not run Computer Use, browser automation, Provider/MCP calls, or paid experiments. Browser acceptance stays `NOT_RUN / BLOCKED_BY_TOOL_ENVIRONMENT`.

No Gold, old RED, API snapshots, historical failures, Gate, TaskControl, or business Run data may be changed.
