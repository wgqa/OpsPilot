# Failures and corrections

All records below are retained as observed. No historical AR-02 live evidence, Gold, or UNKNOWN budget record was edited.

## Valid pre-fix RED

- `runs/red-boundary.log`: the frozen offline formal S02 journey reached S02-4, then failed closed before model/MCP dispatch with `INVESTIGATOR_CONTEXT_EXCEEDS_BUDGET (12064 > 12000)`. S02-5 was not run. This is the primary deterministic reproduction; no Provider call occurred.
- `runs/red-context-overflow-confirmed.log`: a more heavily inflated intermediate history reproduced the same cause at `15512 > 12000`. Kept as supporting evidence, not used for the primary before/after comparison.
- `runs/red-context-overflow.log`: earlier attempt reached FAILED but did not print the precise notice. Kept; the later confirmed RED supersedes it for diagnosis.
- `runs/red-initial.log`: the baseline implementation did not provide the frozen source result digest metadata. This is a separate provenance RED; the exact digest assertion was retained in the test.

## Test preparation and assertion corrections

- `runs/green-first.log`: the S02-4 journey completed, but a test assertion looked for `fact_type` at the top level although the MCP response stores it under `facts`. The assertion was corrected to inspect the persisted calls by tool name and validate their returned facts. No production response shape or business semantics changed.
- During final implementation, a stricter excerpt-length assertion failed because the truncation marker was appended after the requested character limit. The helper was corrected so the marker is included inside the total limit. The captured failure was visible in the execution output but its temporary log path was reused by the successful rerun; therefore it is not represented as an original raw log. Final `runs/acceptance-focused.log` and `TRACE_ACCEPTANCE.jsonl` are the authoritative post-fix evidence.
- One early pytest invocation used the default system temporary directory on C: because the D: pytest parent directory did not yet exist; a later invocation first created the D: parent and all final test runs used explicit D: `--basetemp` paths. No broad C: temp cleanup was performed.

## Final outcome

- `runs/acceptance-focused.log`: 2 passed.
- `runs/regression-acceptance.log`: 71 passed.
- No real Provider request, production write, approval, repair, or handoff occurred.
