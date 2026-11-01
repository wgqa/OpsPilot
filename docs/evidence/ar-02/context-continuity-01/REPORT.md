# AR-02-CONTEXT-CONTINUITY-01

**Status: `ACCEPTANCE_CANDIDATE`** — implementation and offline evidence are ready for independent review. This report does not claim real-model success or final PASS.

- Frozen base: `e090e994ff29685249dc8a76f1ddf6d8f0e7508a`
- Acceptance freeze commit: `5c157ea8290b9900eb70cd925fa37cba149abb18`
- Implementation commit: `da2e8ca85df26f4d887e1b503467aad948051b8c`
- Branch: `codex/ar02-context-continuity-01`

## User-visible result

The formal offline S02 journey now completes the fourth and fifth user turns after accumulated answers and MCP results. At S02-4 the model fixture selected the existing read-only `get_callback_delivery` and `get_receiver_processing` tools. The real local MCP/Domain path returned matching Event observations; the Receiver was `QUEUED`, so the answer reported that processing was not confirmed. S02-5 then produced a source-aware draft that preserved the remaining unknowns.

The tool order was selected by the deterministic fixture used by the existing formal Worker path. This proves the local request/observation/context path and its limits; it does not prove live model autonomy.

## Change summary

- `opspilot/domain/assistant.py::history_sources()` still revalidates every prior Run through `sources_current()` before projection. It now keeps at most 6 history Runs and 12 successful MCP source projections, retains call/Observation/Evidence IDs, request and result digests, timestamps and observed versions, and maps results to bounded allowlisted historical summaries. Knowledge keeps at most 2 versioned documents with bounded excerpts. Historical business facts are marked `HISTORICAL_RUN_ONLY`; they are not inserted into this Run's Observation set. Revoked or otherwise invalid Runs retain an exclusion reason but contribute no source content.
- `opspilot/assistant.py::Loop.context()` no longer duplicates complete prior assistant answer bodies inside `prior_answers`. Answers already selected in `_prepare_context()` are referenced by stable Run/Message/source IDs, digest, sequence and timestamp. A valid answer created before the current Task binding may contribute only a 220-character bounded excerpt. Same-session/tenant, earlier-sequence and Task-scope checks plus source revalidation remain in place.
- The existing pre-dispatch `investigator_context_budget()` remains authoritative at 12,000 estimated input tokens. Current user input, trusted binding and the current Run's actual tool messages remain in the outbound request. No schema, budget, Gate, TaskControl, tool, model-selection, or write contract changed.

## Evidence and token comparison

The prior real S02-4 report recorded `12029 > 12000` and stopped before Provider or MCP dispatch; S02-5 was not run. The frozen deterministic stress case reproduced the same boundary at `12064 > 12000` (`runs/red-boundary.log`). With the bounded projections, the final formal Worker run estimated at most `6553/12000` tokens across its three actual offline model dispatches (`TRACE_ACCEPTANCE.jsonl`). Against the deterministic RED estimate this is a reduction of 5511 estimated tokens (about 45.7%). These values are the project's conservative context estimator, not Provider-reported token usage.

S02-4 and S02-5 completed through FastAPI, Worker, ASSISTANT_V1, local HTTP/MCP, SQLite and deterministic fixture models. The trace records matching Event identity and `QUEUED` Receiver state. A follow-up source revocation caused the old Knowledge-producing Runs to be excluded; no historical source was reintroduced.

## Verification

- Focused: 2 passed, 0 failed — `runs/acceptance-focused.log`.
- Related regression: 71 passed, 0 failed in two fresh executions — `runs/regression-acceptance.log` and final-code repeat `runs/regression-final-final.log`. This includes AR-02 Journey P0/HF02, Knowledge/runtime, Context, TTL-FIX-01 and M4-03-HF-02 targeted regression modules.
- Provider calls: 0.
- Current-run read-only MCP tools in S02-4: `get_callback_delivery`, `get_receiver_processing`.
- Business writes/approvals/repairs/handoffs: 0.
- All pytest basetemp paths in the final runs were under `D:\学习\agent新项目\.pytest-temp\`; earlier failed-attempt provenance and the one initial default C: temp invocation are documented in `FAILURES.md`.
- Historical full pytest suite and browser journey were not run; neither is represented as passed.
- Runtime versions: Python 3.14.0, pytest 9.1.1, LangChain 1.4.1, `langchain-core` 1.6.12, LangGraph 1.2.16, `langchain-openai` 1.7.2, OpenAI SDK 3.33.0, HTTPX 0.28.1, FastAPI 0.137.1.

## Scope and limits

Only offline deterministic tests ran. No real DeepSeek request, browser automation, S01/S02 live journey, business write, approval, repair, or handoff was performed. Historical Run observations remain leads; only the current Run's MCP messages support the present-state answer. The real Provider behavior and user-facing live quality remain unverified.

## Six-question handoff

1. **User change:** a short continuous S02 session can reach the current same-Event delivery/receiver check and produce the requested draft without failing on duplicated history.
2. **Agent decision:** the deterministic fixture chose two legitimate read-only MCP tools; live LLM choice was not tested.
3. **Observation-driven:** same-Event delivery plus current Receiver `QUEUED` yields “processing not confirmed”; historical 202/QUEUED remains labeled historical.
4. **Limits:** bounded history and source revalidation protect token budget and provenance; normal current Run tools and answer continuity remain allowed. Both sides were tested offline.
5. **Simplification:** reused existing history validation, MCP call ledger and token estimator; no new compressor, Runtime, Gate or budget was added.
6. **Evidence/stop line:** frozen RED reproduced, focused and related regression passed; stop here for independent review. Real Provider, browser and full pytest remain unverified.

## Reproduction

From the isolated checkout, using its `.venv` Python:

```powershell
python -m pytest -q --basetemp=<D-drive-temp> tests/test_ar02_context_continuity_01.py
python -m pytest -q --basetemp=<D-drive-temp> tests/test_ar02_context_continuity_01.py tests/test_ar02_journey_p0.py tests/test_ar02_journey_p0_hf02.py tests/test_ar02_knowledge.py tests/test_ar02_runtime.py tests/test_m302_context.py tests/test_m4_ttl_fix_01.py tests/test_m4_03_hf_02.py
```

The frozen acceptance plan is in `PLAN.md`; machine results and exact commands are in `RESULTS.json`; detailed failure history is in `FAILURES.md`; final trace rows are in `TRACE_ACCEPTANCE.jsonl`.
