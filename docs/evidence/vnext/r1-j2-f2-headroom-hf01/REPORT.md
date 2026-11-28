# R1-J2-F2-HEADROOM-HF01

Status: `ACCEPTANCE_CANDIDATE`\
Base: `0150aaa6eb20ce091b3f99e24124d6b177969e7a`\
Branch: `codex/r1-j2-f2-headroom-hf01`\
Remote `main` checked at start: `60eee87bfe3cca522011316cb4cd2c0064ad291b`

## Result

The saved J2-02 request and its three actual MCP observations were replayed offline. Two historical protocol summaries were exact duplicates across prior Runs and shared the same `session_id`, `project_id`, `grant_version`, and `scope_digest`. The model input previously carried each full summary body twice.

The Assistant now includes an identical historical summary body once and points later exact matches to the earlier historical Run/call. Each occurrence retains its own Run, call, Observation, Evidence, result Digest, observed time, and completion time. Summaries without all four explicit scope fields are not deduplicated. Different summary content or scope remains separate. Invalid/revoked history remains excluded. The full uncompressed source ledger in persisted audit metadata is unchanged.

| Replay measurement | Before | After | Change |
|---|---:|---:|---:|
| Historical source projection | 5,119 | 3,632 | 1,487 tokens saved |
| Same reconstructed request after 3 actual MCP results | 11,960 | 10,594 | 1,366 tokens saved |
| Headroom under the unchanged 12,000-token limit | 40 | 1,406 | target of 600 exceeded by 806 |

The prior F2 evidence recorded 11,900 for its post-F2 replay; the independent reconstruction here differs by 60 tokens. Both show that the pre-headroom margin was inadequate. The original 12,199-token rejected request remains unchanged. The compared before/after replay uses the same saved request, tool-call response, three saved MCP results, tokenizer, and estimator; see `HEADROOM_REPLAY.json` for source hashes and counts.

## Implementation

- `opspilot/domain/assistant.py`: exact summary reuse only when the summary is a mapping with explicit matching Session/project/grant/scope metadata. The duplicate snapshot keeps its independent reference and a pointer to the earlier copy.
- `tests/test_r1_j2_closeout_fix_02.py`: verifies reuse plus per-source lineage, scope/content mismatch preservation, revoked-source exclusion, one normal fourth ToolMessage reaching the offline model handler, and the existing oversized result stopping before reservation/handler.

No current ToolMessage, latest user target, TaskBinding, trusted Observation, call ID, source-time rule, or 12K budget was removed or relaxed. No additional investigation step or fixed tool route was introduced. The change affects only the model-facing projection; `Loop.context()` continues to run normal source freshness/revocation checks, and persisted `wire_source_refs` retains full source records.

## Verification

- Targeted F2 tests: **4/4 passed**. Log: `TEST_LOG_TARGETED.txt`.
- Selected Context/Assistant/continuity/runtime regression: **59/60 passed**. One stale assertion is preserved and documented in `FAILURES.md`; it expects `completed_tools` in the current model projection, but the Base projection already omits that field. Log: `TEST_LOG_RETRY.txt`.
- `python -m compileall -q opspilot/domain/assistant.py tests/test_r1_j2_closeout_fix_02.py`: exit 0.
- `git diff --check`: exit 0 (Git reports the repository's normal LF-to-CRLF working-copy warning for the edited test file).
- Initial pytest attempts also exposed Windows temp-root permission and missing `PYTHONPATH` issues; retained logs and resolution are in `FAILURES.md`.
- The committed environment-failure log replaces the local Windows profile path with `<USER_PROFILE>`; byte-original log remains private with SHA-256 `FC08557DAA10B484AD4158765CCAD6D08996B9D8258D5F551B4EA68D8D6706C3`.

## Six-dimension review

1. **User result:** after three actual tool observations, the reconstructed next request has 1,406 tokens of headroom without raising the input cap.
2. **Agent choice:** tool choice, order, clarification, and stopping behavior are unchanged; no fixed route was added.
3. **Observation-driven behavior:** all three current ToolMessages and their call IDs remain; historical summaries stay explicitly historical and cannot become current observations.
4. **Two-way constraints:** exact same-scope duplicates compact; different scope/content remains; invalid history stays excluded; a normal fourth result proceeds while an oversized result is rejected before reservation.
5. **Responsibility/simplification:** reuses the existing source projection and persistent audit path; no new state machine, compression service, or budget limit.
6. **Evidence/stop line:** all evidence is offline; Provider HTTP, browser automation, and external writes are zero. The STOPPED Campaign and its ledger were not modified.

One existing currentness test assertion remains inconsistent with the Base projection and is not folded into this headroom repair. All original F1 evidence, Gold, traces, and campaign records remain unchanged.
