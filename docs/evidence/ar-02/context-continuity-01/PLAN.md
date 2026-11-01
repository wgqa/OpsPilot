# AR-02-CONTEXT-CONTINUITY-01 Acceptance Plan

## Frozen baseline

- Repository: `wgqa/OpsPilot`
- Base: `codex/ar02-real-journey-02@e090e994ff29685249dc8a76f1ddf6d8f0e7508a`
- Remote candidate verified read-only: same SHA
- Remote main verified read-only: `ec8c3582f6d145eec9979c43607302731411ead8`
- Work branch: `codex/ar02-context-continuity-01`
- Working tree was clean before the branch was created.
- North Star blob: `1f737712c7a36ceb34433ac09c3fbba3c3305542`
- AGENTS blob: `32c45506cceeaa8c76a5c56bf8360ff476b58856`
- Project Skill blob: `d405c8d413d633824b279202cc1503dab4cf0b03`

## Prior failure preserved

`docs/evidence/ar-02/real-journey-02/REPORT.md` records the real S02-4 failure as `12029 > 12000` before any Provider or MCP dispatch. S02-5 was not run. The historical report, trace, ledger, Gold, and prior UNKNOWN records are read-only inputs and will not be edited.

## Frozen acceptance checks

1. Run a deterministic formal API/Worker/ASSISTANT_V1 five-turn S02 journey with a deliberately accumulated but bounded history. S02-4 must reach the offline model and complete; S02-5 must also complete. No real Provider client or external request is permitted.
2. Inspect the actual pre-dispatch `assistant_calls.request_json` and model-visible messages. The exact assembled message/tool estimate must remain within the existing 12,000-token input budget.
3. Preserve current user text, trusted TaskBinding, and current Run MCP ToolMessages in full. Preserve historical answer/source IDs, versions, timestamps, and digests as bounded historical references/summaries.
4. Historical business facts are explicitly marked historical and cannot appear as current observations. The S02-4 current result must come from its own Run's successful MCP observations.
5. Revalidation must happen before projection. Revoked, expired, mismatched, cross-Task, and cross-Session source material must not be restored through a summary/reference. Existing source-validity tests remain in scope.
6. A normal short request still reaches the offline model. A deliberately over-budget current request still fails closed before model/Provider dispatch.

## Hard limits

- No real DeepSeek or other Provider calls.
- No resume/retry of `AR-02-REAL-JOURNEY-02`.
- No changes to Gold, historical evidence/ledger, TaskControl, Gate, MCP business API, or model tool-selection policy.
- Keep the existing 12,000-token input budget.
