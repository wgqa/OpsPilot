# AR-03-REAL-LLM-02 Preflight

**Pre-send snapshot:** 0 Provider requests sent. This file records the preflight state before the one-shot live execution.

## Repository and frozen input

- Repo: `wgqa/OpsPilot`
- Worktree: `D:\学习\agent新项目\.worktrees\ar03-real-llm-02`
- Branch: `codex/ar03-real-llm-02`
- Authorized base: `69ffa0d73e6e869c590bc46f36bceda4db62e273`
- Freeze-plan commit: `f2ffcbf032bb4fd646073697bf2a358131d7c0a4`
- Remote SHA checked read-only with `git ls-remote`: source `codex/ar03-live-hf-01` remained at the authorized base; `main` was `ec8c3582f6d145eec9979c43607302731411ead8`; the new target branch did not exist at that check.
- North Star Blob: `1f737712c7a36ceb34433ac09c3fbba3c3305542`.
- AGENTS Blob: `32c45506cceeaa8c76a5c56bf8360ff476b58856`.
- Project Skill Blob: `d405c8d413d633824b279202cc1503dab4cf0b03`.
- Frozen CASES/GOLD/BUDGET Blobs: `c29b5cf7630fa838a365634d0df5f9f0f2bfa834` / `88d5e6f40f027ce2622b957d8ab32b8d2b827381` / `5a71096584b4003b5f30c53fd69ccfd11bbc53d4`.

The project Skill, current North Star, AGENTS, frozen CASES, Gold and budget contract were opened in this checkout. The new runner checks the frozen blobs and exact prompt before execution. No historical experiment evidence or database was changed.

## Provider and budget preflight

On 2026-11-02, the official DeepSeek pricing and Chat Completions pages were rechecked:

- `deepseek-flash` currently resolves to `DeepSeek-V4.1-Flash-1017`.
- Peak cache-miss input is USD 0.30 / million tokens; output is USD 1.20 / million tokens.
- Published context is 1M and maximum output is 384K. The retained USD 0.645600 reservation conservatively accounts for 616K input and 384K output at peak rates. Sixteen reservations total USD 10.329600, below the authorized USD 10.50 by USD 0.170400.
- The exact visible per-request input/output caps (12,000/2,048) would cost USD 0.0060576 at peak rates, but the runner does not reduce the frozen reservation to this smaller estimate.
- Official Chat Completions documentation supports the model alias, `thinking.type=disabled`, `max_tokens`, function tools and `tool_choice=auto`. The current schema page does not document `parallel_tool_calls`; this experiment still sends the frozen `false` field and captures it. Prior acceptance is not treated as a guarantee that the provider honors its semantics.
- Configured endpoint is `https://api.deepseek.com/v1`; the offline formal API/Worker test captured `https://api.deepseek.com/v1/chat/completions`.

The local `.env` contains a configured key, model `deepseek-flash` and the approved DeepSeek base URL. Credential values were not printed or copied into evidence. The opt-in and experiment ID were absent before the runner. This does not establish network connectivity; the actual execution will use the authorized elevated network path. No ping or separate Provider probe is permitted.

## Request-shape and formal-path verification

The deterministic `httpx.MockTransport` test sent the exact frozen goal through the trusted `/assistant/order` API. It verified:

- one USER message, one task Run, and one `ASSISTANT_V1` run;
- the full frozen question is the binding request's `initial_message`;
- no second `/assistant/messages` request is needed;
- actual serialized URL, model, `thinking`, `max_tokens=2048`, `tool_choice=auto`, `parallel_tool_calls=false`, `stream=false`, and absence of `max_completion_tokens`;
- synthetic Usage is recorded only in the offline test and is not live Provider evidence.

The live runner creates fresh per-scenario Domain and Checkpoint SQLite files, uses separate persisted 8 Provider / 6 MCP budgets, shares a process-wide 16 Provider transport cap, and allows only one in-flight Provider request. Combined ledger reservation is bounded by `8 × 0.645600 × 2 = USD 10.329600`. It verifies one user message, one task Run, and one `ASSISTANT_V1` Run per scenario. The existing per-database MCP cap of six composes to twelve across the two isolated databases. Any nonzero protected business-write table count, closed/unknown budget or in-flight response stops the pair. A persistent exclusive execution claim prevents retries.

## Fresh commands and results

1. Initial environment attempt:

   `python -m pytest tests/test_ar03_real_llm_02_live.py -q --basetemp D:\学习\agent新项目\.tmp\ar03-real-llm-02-offline-20261102a`

   Result: collection blocked because `D:\python\python.exe` lacks `langchain`; zero tests ran and zero Provider requests occurred. Preserved at `runs/initial_offline_missing_dependency.log`.

2. Re-ran using the existing project environment:

   `D:\学习\agent新项目\.venv\Scripts\python.exe -m pytest tests/test_ar03_real_llm_02_live.py -q --basetemp D:\学习\agent新项目\.tmp\ar03-real-llm-02-offline-20261102b`

   Result: 2 passed. No packages were installed or modified.

3. Related offline regression:

   `D:\学习\agent新项目\.venv\Scripts\python.exe -m pytest tests/test_ar03_real_llm_02_live.py tests/test_ar03_real_llm_01_live_preflight.py tests/test_ar03_live_budget_allocation.py tests/test_ar03_live_provider_trace_transport.py tests/test_ar02_ar03_integration_01.py::test_full_frozen_goal_in_trusted_order_initial_message_uses_one_assistant_run -q --basetemp D:\学习\agent新项目\.tmp\ar03-real-llm-02-regression-20261102a`

   Result: 8 passed on the first related pass. After adding the pre-send input-token guard and unknown-outcome stop classification, the same command was freshly rerun and 10 tests passed. The final raw console output is `runs/offline_regression_after_unknown_guard.log`; earlier output is retained separately.

4. Runner preflight-only (no network transport construction and no Provider dispatch):

   `D:\学习\agent新项目\.venv\Scripts\python.exe docs/evidence/ar-03/real-llm-02/run_live.py --preflight-only`

   Result before implementation commit: `PREFLIGHT_READY`; 0 Provider requests; correct branch, frozen blobs, 16/12/8/6 caps, USD 10.329600 aggregate reservation and no existing execution claim/runtime. Original output is `runs/preflight_before_commit.log`. It will be repeated after the implementation commit and before any live request.

## Limits

- Deterministic tests prove the formal path and wire contract, not DeepSeek's autonomous decisions or its interpretation of `parallel_tool_calls`.
- The live HTTP transport repeats the existing Context Engineering token estimator at the actual send boundary and refuses if estimated input exceeds the approved 12,000-token ceiling. This is the application's bound/estimate, not a guarantee of provider tokenizer equivalence.
- The real requests have not run; Provider network availability and actual Usage are unverified.
- No browser validation or business write is authorized or performed.
