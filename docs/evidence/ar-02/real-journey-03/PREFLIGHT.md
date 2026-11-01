# AR-02-REAL-JOURNEY-03 Preflight

## Frozen checkout

- Local base: `bc5484fe721bd2a54bc3a73326ff3c649fa1baa2` on `codex/ar02-context-continuity-01` was verified clean before branch creation.
- New branch: `codex/ar02-real-journey-03`, created at that exact base.
- `PROJECT_NORTH_STAR.md` Blob: `1f737712c7a36ceb34433ac09c3fbba3c3305542`.
- `AGENTS.md` Blob: `32c45506cceeaa8c76a5c56bf8360ff476b58856`.
- `.agents/skills/opspilot-slice-review/SKILL.md` Blob: `d405c8d413d633824b279202cc1503dab4cf0b03`.
- Frozen `CASES.json` Blob: `0b8411942ec99724d9aa10d45faa50a58676836b`.
- Frozen `SMOKE_INPUTS.md` Blob: `ee9b1623a2296905c425449709a2f9ae6563caca`.
- Initial remote read failed with a connection reset, so it was marked `UNVERIFIED` at that point. After the candidate branch push, a fresh `git ls-remote --heads origin main codex/ar02-context-continuity-01 codex/ar02-real-journey-03` succeeded: remote `main=ec8c3582f6d145eec9979c43607302731411ead8`, base branch `bc5484fe721bd2a54bc3a73326ff3c649fa1baa2`, candidate `e051cb555fa5764d565eb4d773fc9e95d3063014`. `main` is unchanged.

## Provider and fee check

DeepSeek's official pricing and Chat Completions documentation were checked on 2026-11-01. The documented peak cache-miss rates are USD 0.30/M input and USD 1.20/M output; `deepseek-flash` currently maps to DeepSeek-V4.1-Flash-1017. Its documented context length is 1M tokens and maximum output is 384K. Using the frozen maximum combined context/output envelope yields USD 0.645600 per dispatch. Sixteen such reservations total USD 10.329600, below USD 10.50. This is a conservative application reservation, not a billing guarantee.

Sources:

- https://api-docs.deepseek.com/quick_start/pricing/
- https://api-docs.deepseek.com/api/create-chat-completion/

## Local environment and wire checks

- Existing local `.env` presence and expected key names were checked without displaying values. The API key is loaded in memory from that existing file only for the live process; no key is written into evidence.
- Real provider remains opt-in by `OPSPILOT_ASSISTANT_PROVIDER_ENABLED=1` and the exact new experiment ID.
- An explicit HTTPX MockTransport test exercises the actual ChatOpenAI serialization. It is required to assert the URL, model, `thinking`, `max_tokens`, tool schema, `tool_choice`, `parallel_tool_calls`, stream mode, no SDK retry, and absence of `max_completion_tokens` before live execution.
- Existing context-continuity tests keep the 12,000-token input limit and prove the frozen S02-4/S02-5 deterministic journey fits. A live over-budget context is fail-closed; this task will not raise the limit.
- The formal runner uses a new ignored runtime directory and new Domain/Checkpoint SQLite files. It refuses to reuse either file.
- No paid request is made by the preparation tests. No standalone provider connectivity probe is authorized or planned.

## Offline execution results

- Focused offline preflight and context continuity: 5 passed, exit code 0. Command: `python -m pytest -q --basetemp=D:\学习\agent新项目\.pytest-temp\ar02-rj03-prep-20261101-01 tests/test_ar02_real_journey_03_prep.py tests/test_ar02_context_continuity_01.py`.
- Related AR-02 regression: 63 passed, exit code 0. Command: `python -m pytest -q --basetemp=D:\学习\agent新项目\.pytest-temp\ar02-rj03-regression-20261101-01 tests/test_ar02_real_journey_03_prep.py tests/test_ar02_real_journey_budget_scope.py tests/test_ar02_live_budget.py tests/test_ar02_context_continuity_01.py tests/test_ar02_journey_p0.py tests/test_ar02_journey_p0_hf02.py tests/test_ar02_knowledge.py tests/test_ar02_assistant.py tests/test_ar02_runtime.py`.
- Python source syntax check passed. Runtime versions are recorded in the final report.

## Execution gate

The real S02 run may begin only after the offline checks pass, the implementation commit SHA is fixed, the exact run branch and output paths are verified, and the formal Worker is launched in the authorized network-capable execution context. If that cannot be demonstrated before the first Provider dispatch, execution stops without changing any historical ledger.
