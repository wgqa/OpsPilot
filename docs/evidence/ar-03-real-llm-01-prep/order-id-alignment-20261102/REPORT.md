# AR-03-REAL-LLM-01-PREP — Order ID Alignment

**Status:** `ACCEPTANCE_CANDIDATE` — limited offline evidence only
**Base:** `codex/ar03-real-llm-01@fe72a12ca4c4d89e4be69ad6842d711d9d3808b7`
**Scope:** Align the paired offline fixture and trusted binding to frozen `ar03-order`; rerun only the QUEUED/PROCESSED comparison.

## Result

The frozen `CASES.json` and `GOLD.md` were not changed. The affected fixture now creates `ar03-order`, the authenticated trusted Assistant order-selection API binds `ar03-order`, and the current Domain binding read confirms that order under `tenant-a` / `support-a`. The principal was `ENABLED`; the current Scope Policy and Grant versions were both 1.

Both cases use the same target Event, `event-00000000-0000-4000-8000-000000000001`. The formal Worker made current same-Task MCP observations for order, Delivery, and Receiver. In both cases the Delivery was `ACKNOWLEDGED` with HTTP 202. Receiver was `QUEUED` in the first case and `PROCESSED` in the second; the persisted answers retain those different conclusions.

The test confirmed zero rows in the S3 diagnosis, D3 plan/authorization/approval/action/verification/report/delivery tables and S3 handoff queue/receipt tables. The Agent-side real Provider request count was 0. The local fixture preparation is test setup, not an Agent business action.

## Execution

Final command:

```powershell
$env:AR02_AR03_TRACE_PATH = 'D:\学习\agent新项目\.worktrees\ar02-real-journey-02\docs\evidence\ar-03-real-llm-01-prep\order-id-alignment-20261102\TRACE-accepted.jsonl'
$env:AR03_ORDER_ALIGNMENT_TRACE_PATH = 'D:\学习\agent新项目\.worktrees\ar02-real-journey-02\docs\evidence\ar-03-real-llm-01-prep\order-id-alignment-20261102\DOMAIN-CHECKS-accepted.jsonl'
& 'D:\学习\agent新项目\.venv\Scripts\python.exe' -m pytest tests/test_ar02_ar03_integration_01.py -k test_formal_worker_protocol_impact_draft_tracks_current_receiver_observation -q --basetemp 'D:\学习\agent新项目\.tmp\ar03-order-alignment-20261102-accepted'
```

Result: **2 passed, 5 deselected, exit 0**. The captured Domain-check trace contains two records and independently validates the order/Event pairing, trusted actor, current authorization versions, HTTP 202/ACKNOWLEDGED, both Receiver states, and zero business-action rows. The complete pytest output is in `runs/queued-processed-pair-accepted.log`; persisted API/Worker/MCP records are in `TRACE-accepted.jsonl`.

The test interpreter was the existing `D:\学习\agent新项目\.venv` environment (`langchain_core 1.6.12`). System `python` lacked `langchain_core`; see `FAILURES.md`. No dependency or lockfile was changed.

## Repository and evidence integrity

- Branch: `codex/ar03-real-llm-01`; local starting HEAD was `fe72a12ca4c4d89e4be69ad6842d711d9d3808b7`.
- At start the worktree was clean and the local upstream tracking ref matched that HEAD.
- Live GitHub remote verification failed because port 443 was unreachable; the remote's current SHA is therefore `UNVERIFIED`. Push status is reported separately after the commit attempt.
- Frozen `CASES.json`, `GOLD.md`, and historical `TRACE.jsonl` / `TRACE-random-id-first-run.jsonl` remain unchanged.
- No Provider request, browser automation, business action, main-branch update, or new feature was performed.
- This is a deterministic offline route/fixture result. Real DeepSeek autonomy remains `NOT_RUN`.

## North Star review summary

1. **User change:** No product behavior changed; the offline paired evidence now uses the frozen order identity.
2. **Agent decision:** Not assessed; the fixture model is deterministic.
3. **Observation-driven:** Same Event HTTP 202 plus QUEUED versus PROCESSED yields the two frozen distinct conclusions.
4. **Constraints:** Trusted binding and current read authorization are asserted; legal bound reads pass, while all action/handoff write tables remain empty.
5. **Simplification:** No production logic or new guard was added; only the existing paired integration test fixture and assertions changed.
6. **Evidence and stop:** Only the affected two pytest cases were rerun. Full pytest, real Provider, browser, and live remote SHA are not verified. Stop pending Main Agent review.
