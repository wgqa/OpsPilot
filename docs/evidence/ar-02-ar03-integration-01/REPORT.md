# AR-02 × AR-03-INTEGRATION-01 — Offline Integration Report

**State:** `ACCEPTANCE_CANDIDATE`

**Branch:** `codex/ar02-ar03-integration-01`

**Base:** `a6935a0944b27d0f5598242eb5e1deaa756af1f4`

**Frozen plan commit:** `f6690be72cb6d803a562c17f8222d86a2efe36a5`

**AR-03 source:** `255087bae4dc0e9990a650786f5b9aae26f9f1db`

This slice adds authorized protocol discovery and comparison to the existing `ASSISTANT_V1` API/Worker/MCP path. It does not replace the Assistant or create a second graph, worker, agent, or frontend entry.

## What a user can now do in the offline formal path

Without knowing internal document IDs, a user can ask the Assistant to find authorized callback retry protocol versions and compare them. The local stdio MCP server returns the currently permitted documents and section-level differences with line locations, digest, source, and explicit uncertainty. With a trusted order binding, the same Assistant can combine that material with current same-Event order, delivery, and receiver reads to produce an unsubmitted support draft.

### Unbound protocol journey

The deterministic model received a natural-language request to find and compare old/new retry protocols and assess whether customer completion can be confirmed. It selected `list_scoped_protocol_documents`, then `compare_scoped_protocols`. The actual local MCP response contained two authorized versions, their source/digest, and section differences. The final persisted answer reported that protocol changes can guide investigation but do not prove deployment or customer completion. A subsequent Run in the same Session received only the bounded historical summary and provenance; it did not receive the full comparison diff.

### Bound business-fact pair

Two isolated, equivalent local tasks used different current same-Event Receiver facts:

- `QUEUED`: the model read order, delivery, and receiver observations and produced a draft that said receipt/HTTP 202 is not proof of processing completion; the receiver remained queued and further processing was unknown.
- `PROCESSED`: the model read the same classes of current observations and produced a materially different conclusion: processing was confirmed for the observed Event, while avoiding claims about another Event or online protocol deployment.

Both drafts were unsubmitted. The tests confirmed zero Diagnosis, Approval, ActionIntent, Ledger, or Handoff records.

This is evidence of observation-dependent product-path behavior under the deterministic model fixture, not evidence that a real LLM would autonomously choose the same actions or answer equally well.

## Changes and conflict handling

- Selectively ported the comparison engine and scoped comparison module from the frozen AR-03 source commit; no branch merge or wholesale overwrite was used.
- Added the two requested read-only MCP tools to the existing MCP server.
- Added a trusted Session→Project lookup by using the existing Knowledge scope/grant checks.
- Added revalidation of discovery/comparison output against current Session/Tenant/Actor/project grant and current authorized document bytes/digests. Comparison revalidation recomputes the current result and canonical-compares all user-visible fields, covering fields not included in the legacy comparison digest.
- Added bounded historical projections for discovery/comparison. They retain source refs, version/digest and limited difference summaries, mark the material as historical method only, omit complete `diff_evidence`, and are revalidated before later use.
- Preserved AR-02's 12,000-token budget, existing Knowledge/source validation, TaskBinding, current S3 evidence checks, and Assistant/MCP/worker pipeline. Protocol documents remain distinct from current business facts and from deployment verification.

Files changed: `opspilot/assistant_mcp.py`, `opspilot/domain/assistant.py`, `opspilot/domain/assistant_knowledge.py`, new `opspilot/domain/protocol_comparison.py`, new `opspilot/domain/scoped_protocol_comparison.py`, new integration and retained AR-03 protocol tests, plus this evidence folder.

## Evidence and validation

`TRACE.jsonl` contains 74 records from seven persisted local API/Worker Runs, 20 deterministic fixture model dispatches, 13 actual local MCP calls, six actual S3 HTTP/MCP observations, seven persisted answers and their source links. Estimated input contexts were 932–4,776 tokens under the existing 12,000-token input cap. These values are local estimates; there is no Provider Usage in this experiment.

The final fresh command `D:\学习\agent新项目\.venv\Scripts\python.exe -m pytest tests/test_ar03_protocol_comparison.py tests/test_ar03_02_scoped_protocol_comparison.py tests/test_ar02_ar03_integration_01.py -q --basetemp=.pytest-temp/ar02-ar03-final-confirm` passed 50 tests. The preserved AR-02 regression run passed 84; its raw pytest output did not include the command line, so the exact invocation cannot be recovered and is not claimed. The earlier seven-case integration set passed 7, and the explicit unauthorized MCP test passed 1. Changed modules compiled, the trace and results JSON parsed, the sensitive-marker scan found no matches, and `git diff --check` passed. All attempts, including setup/test errors and the safe runtime budget refusal encountered during test setup, are in `FAILURES.md` and `runs/`.

The complete repository pytest suite was **not run**. Real DeepSeek, browser, production, and deployment-version verification were **not run**. No paid Provider request, browser action, repair, approval, delivery, external write, `main` change, or historical ledger mutation occurred.

## Known issue and limits

- The previous AR-02 real model S02-4 failure to actively obtain a fresh receiver observation remains a historical PARTIAL. This integration does not hardcode a tool sequence to mask it.
- `deployment_version_verified` remains false: the protocol catalog/configuration is not proof of what is deployed online.
- Results are from deterministic model control-flow and local real API/Worker/SQLite/MCP/HTTP integration; real model quality is unverified.
- Trace/context token values are local estimates rather than actual Provider Usage.

## Skill six-question closeout

1. **User change:** A natural-language request can discover and compare authorized protocol versions and, once a trusted binding exists, relate them to current order/Delivery/Receiver facts for an unsubmitted draft.
2. **Agent decision:** The FixtureModel selected when to discover, compare, read current business facts, and answer; this proves the path can be used, not real-model autonomy.
3. **Observation-driven:** The current same-Event `QUEUED` and `PROCESSED` observations caused different conclusions, with no unique sequence required by product code.
4. **Constraint:** Session/Tenant/Actor/grant/digest revalidation prevents unauthorized, changed, or revoked sources from becoming trusted facts; positive same-scope journeys and negative scope/tamper paths passed.
5. **Simplification:** Existing Assistant, Knowledge scope, MCP, TaskBinding, evidence, and budget responsibilities were reused; no separate runtime, gate, or state store was added. No unrelated old conditions were removed.
6. **Evidence and stop:** Targeted AR-02/AR-03 tests, local API/Worker/MCP trace, and static checks are recorded. Full pytest, browser, and real Provider are not run. Stop at this isolated candidate for independent review.

The implementation submits only an `ACCEPTANCE_CANDIDATE`; it does not self-sign acceptance or authorize merge to `main`.
