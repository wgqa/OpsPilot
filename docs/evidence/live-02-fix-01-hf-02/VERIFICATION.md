# LIVE-02-FIX-01-HF-02 验证记录

状态：`ACCEPTANCE_CANDIDATE`。本记录只覆盖画像提示 Token 开销和 PINNED 子预算，不代表真实 Provider 的记忆使用质量已经通过。

## 基线与合同

| 项目 | 值 |
| --- | --- |
| Repo / 工作树 | `wgqa/OpsPilot` / `D:\OpsPilot-LIVE-02-FIX-01-HF02` |
| Branch / Base | `codex/live-02-fix-01-hf02` / `e28630fd3e603e9504535300c6a9511f6826656f` |
| 开工 HEAD | `e28630fd3e603e9504535300c6a9511f6826656f`，与远端 HF-01 相同 |
| North Star Blob | `43dabda468506717c6956e676dfad4304c4f38e6` |
| AGENTS Blob | `807b928686a4dd2cac7b15b3c354b9943c93c910` |
| `opspilot-slice-review` Skill Blob | `d405c8d413d633824b279202cc1503dab4cf0b03` |
| Open Source Agent References Blob | `890ddf8918f976401c4df849eda6394770ed1997` |
| C01-B2-A ADR Blob | `5cc27f62d2dee8bed816d562e68f6b66e8142fc2` |
| C01-B2-B ADR Blob | `a7a0639ef3ff466bd2b1cffd6c7fb158d49a258e` |
| LIVE-02-FIX-01 review Blob | `7bf3bfbc7f974399a7bd921fbea4f4713f769954` |
| HF-01 verification Blob | `d30685935a799a6e08a1686b18bca5e637f60553` |

The North Star's Context/Memory and authority boundaries remain in force. The HF-01 user-profile behavior is preserved: query wording does not gate stable personal profile selection; the model judges usefulness. No S1/S2/S3 history, SLA, UX, MCP, schema, dependencies, Grant policy, learning algorithm, or persistent memory lifecycle was changed.

## Change and token calculation

`estimate_messages_tokens()` uses `tiktoken:cl100k_base:0.14.0`. It counts the system role and message framing (2 base tokens, 4 per message, role tokens, and encoded content). These are deterministic local estimates, not Provider-reported usage.

Before this HF, one B07 auto preference estimated at 270 tokens and its project-background memory at 275, for 545 total. In the three-memory RED fixture, an explicit PINNED preference estimated at 238 and the auto preference at 262; those two were selected, and the auto-learned technical background was excluded by the 600-token total cap.

The prompt projection now sends only the existing source-kind heading, low-authority note, Memory ID, version, kind, and complete content. The full content Digest, source-message Digest/chain, creation metadata, and selection reason stay in the existing persisted `chat_context_manifests.memory_refs_json` and `truncation_json`/Context Manifest. The answer commit path still requires the exact compact guidance and Memory ID in the recorded model messages, validates current Memory sources, and compares model-call Memory ID/version/Digest metadata against the persisted manifest. It no longer requires the Digest itself to be repeated inside the model message body.

HF-01's six-record and 600-token profile ceilings remain unchanged. The PINNED sub-budget is restored to `250` tokens, matching C01-B2-A's original approximately 250-token allowance; the maximum remains three PINNED entries. Both budgets count the complete message estimate and skip whole records.

| Fixture | Base / candidate evidence | Result |
| --- | --- | --- |
| Three records: explicit PINNED preference, auto-learned PINNED preference, auto-learned project background | [`three-memory-red.txt`](logs/three-memory-red.txt), [`profile-green.txt`](logs/profile-green.txt) | Base selects two (238 + 262 = 500), omits B07 background. Candidate puts all three in the actual Fixture Provider input: 93 + 105 + 107 = 305; PINNED subtotal 198/250. Manifest retains all three Digests, source refs, and selection reasons; their full provenance values do not appear in provider messages. |
| Original B07, two AUTO_LEARNED memories, fresh Session | [`b07-green.txt`](logs/b07-green.txt), [`profile-green.txt`](logs/profile-green.txt) | Candidate passes. Latest run estimates 106 + 104 = 210 tokens versus HF-01's recorded 270 + 275 = 545; both records remain present. |
| Total profile cap and token-pressure selection | [`profile-green.txt`](logs/profile-green.txt) | Ten stored records: six complete items selected at 584/600; remaining records are excluded with explicit reasons. A separate pressure fixture selects three complete long preferences at 587/600 and excludes the rest, including the long-term background, as `PERSONAL_PROFILE_TOKEN_BUDGET`. |
| Source invalidation and revocation before send | [`profile-green.txt`](logs/profile-green.txt) | Revoked/expired/revised/source-invalid records stay excluded. Revocation between context preparation and Provider send yields zero transport sends and `NOT_DISPATCHED` spend. |
| Owner/Tenant separation and memory lifecycle | [`profile-green.txt`](logs/profile-green.txt), [`live02-memory-regression.txt`](logs/live02-memory-regression.txt), [`b2b-regression.txt`](logs/b2b-regression.txt) | Other owner/Tenant, revoked, expired, revised, changed-source and unverified-source records do not enter the selected profile. |
| PINNED compatibility | [`b2a-regression.txt`](logs/b2a-regression.txt) | Three-item cap remains; selected PINNED token estimate is at most 250. |

The C01-B2-A test that formerly expected an unrelated `PROJECT_BACKGROUND` record to be absent was updated to the already-approved HF-01 profile contract. It now checks that the bounded low-authority record reaches the model input and remains in the manifest; a Fixture Model result is not treated as proof that a real model will use it appropriately.

## Commands and results

Tests used the locked Python environment at `D:\OpsPilot-C01-B2-LIVE-01-HF02\.venv\Scripts\python.exe`, disabled Provider feature flags, and temporary fixture databases/checkpoints. `offline-only` was a dummy key value; no real Provider send occurred.

```powershell
$py = 'D:\OpsPilot-C01-B2-LIVE-01-HF02\.venv\Scripts\python.exe'
$env:PYTHONUTF8 = '1'
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:OPSPILOT_ASSISTANT_PROVIDER_ENABLED = '0'
$env:OPSPILOT_LEGACY_PROVIDER_ENABLED = '0'
$env:OPSPILOT_ASSISTANT_RUNTIME_ENABLED = '0'
$env:OPSPILOT_MODEL_API_KEY = 'offline-only'
$env:OPENAI_API_KEY = 'offline-only'
$env:LANGSMITH_TRACING = 'false'
$env:LANGCHAIN_TRACING_V2 = 'false'
$env:OPSPILOT_ASSISTANT_EXPERIMENT_ID = ''

& $py -m py_compile opspilot/domain/semantic_memory.py opspilot/domain/chat.py tests/test_live_02_fix_01_hf01_profile.py tests/test_c01_b2_a_personal_memory.py
& $py -m pytest -q -rA -s -p no:cacheprovider --basetemp=.pytest-hf02-profile-final-green --tb=short tests/test_live_02_fix_01_hf01_profile.py
& $py -m pytest -q -rA -s -p no:cacheprovider --basetemp=.pytest-hf02-b2a-final-green --tb=short tests/test_c01_b2_a_personal_memory.py
& $py -m pytest -q -rA -s -p no:cacheprovider --basetemp=.pytest-hf02-live02-memory-final --tb=short tests/test_live_02_fix_01_memory.py tests/test_c01_b_personal_memory.py tests/test_c01_b2_live_01_hf01.py
& $py -m pytest -q -rA -s -p no:cacheprovider --basetemp=.pytest-hf02-b2b-final --tb=short tests/test_c01_b2_b_personal_memory_auto_consolidation.py
```

| Suite | Result | Log |
| --- | ---: | --- |
| HF-02 profile / B07 / budget / lifecycle / revoke fence | 10/10 | [`profile-green.txt`](logs/profile-green.txt) |
| C01-B2-A personal memory | 14/14 | [`b2a-regression.txt`](logs/b2a-regression.txt) |
| LIVE-02 memory + C01-B recall + HF01 stream | 13/13 | [`live02-memory-regression.txt`](logs/live02-memory-regression.txt) |
| C01-B2-B automatic consolidation | 27/27 | [`b2b-regression.txt`](logs/b2b-regression.txt) |

Focused total: `64/64` across these suites. Full repository pytest: `NOT_RUN`. Browser/live Provider quality: `NOT_RUN`. Real Provider requests: `0`; external business writes: `0`.

## Scope and remaining limits

- Production files changed: `opspilot/domain/semantic_memory.py` and `opspilot/domain/chat.py` only.
- No new model calls, storage, schema, dependencies, Memory category, cache, Agent, or summary state.
- Candidate Fixture inputs prove selection/provenance and the existing out-send checks under mocked execution. They do not prove a paid model will select or ignore background appropriately.
- The full repository suite and live user evaluation remain for independent acceptance; no main merge is performed.
