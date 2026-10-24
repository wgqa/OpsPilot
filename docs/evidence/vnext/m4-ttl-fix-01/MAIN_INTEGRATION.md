# M4-TTL-FIX-01 Main Integration Supplement

**Status:** `ACCEPTANCE_CANDIDATE`
**Repository:** `wgqa/OpsPilot`
**Target:** `main`
**Main before integration:** `add47ec83f31fa76b9b6a5782e013311732bc496`
**TTL candidate:** `codex/m4-ttl-fix-01@bc7fc1633cc2b9e5ed6d652fbb518ea4cd3caafe`
**TTL merge commit:** `8bc6290a09cf3d36f5ca31ed078fc34a54e7e9f8`
**Integration fixes:** `153b3e7` and `6a197f5`
**Freshly tested integration commit:** `6a197f5e9473d838444b6a93b7b2e661c723f9f2`

This supplement records the REV1 integration work. The original `REPORT.md`, `RESULTS.json`, frozen plan, RED materials, and their run logs remain unchanged. The TTL feature code is the reviewed candidate from `00be81c53f090fd8934aa645ac2b16c59c9a7c78`; its evidence bundle is `fb09352b8d62f1179f52e367ba27d750664b3e87`. The merge base with the reviewed main line was `bd58c66003c4e7fea660967c7a6a30aebcd63cd7`.

The merge was performed in a fresh detached worktree based on `origin/main`, keeping the root checkout and its untracked files untouched. `PROJECT_NORTH_STAR.md` and `AGENTS.md` are byte-for-byte unchanged from the pre-merge main commit. The source diff is limited to the TTL candidate and the two `.gitattributes` rules described below; no C1 implementation was mixed into this TTL integration.

## Clean-checkout findings

The first clean Windows checkout exposed a packaging issue hidden by the prior TTL worktree's local file state. `auth-scope-triage/SKILL.md` and `knowledge/api-scope/*.md` are verified against byte-level SHA-256 values, but had no LF checkout rule. With the machine's `core.autocrlf=true`, Git materialized CRLF bytes and the existing checks raised `SkillIntegrityError` or `KnowledgeIntegrityError` before model I/O. The initial run therefore reported 4 S3 failures after 73 passes, and the first S1/S2 run reported 15 scope-knowledge failures after 89 passes.

The two minimal `.gitattributes` additions preserve the exact checked-in bytes for those already hash-verified assets. They do not alter their contents, versions, permissions, Gates, or business behavior. A second fresh checkout confirmed the skill file SHA matched its manifest; the final fresh checkout confirmed both paths use LF. After those corrections, S3/HF, S1/S2, and full-suite regressions passed. The failed logs remain in `runs/rev1/` and are classified in `MAIN_INTEGRATION_RESULTS.json`.

One earlier pytest attempt also failed before collection because the PowerShell invocation passed an empty `--basetemp`; it is retained as a test-preparation failure and was followed by corrected runs.

## Fresh verification

Environment: Windows, Python 3.14.0, pytest 9.1.1, FastAPI 0.137.1, MCP 2.3.0, LangGraph 1.2.16, and `langchain-openai` 1.7.2. The full pytest run used a local dummy model key/name and `http://127.0.0.1:9`; no real Provider call or paid model request occurred. TTL/S3 integration tests use the existing local HTTP and in-process MCP path.

- TTL core and integrity tests: **3 passed**.
- TTL + HF-01/HF-02 + S3/M4-02 regression: **77 passed**.
- S1/S2 security regression: **104 passed**.
- Full pytest: **319 passed**.
- `pip check`, `compileall`, and source/test `.diff --check`: **passed**.

Exact commands, outcomes, exits, and raw log paths are recorded in `MAIN_INTEGRATION_RESULTS.json`. The final tested source commit is `6a197f5e9473d838444b6a93b7b2e661c723f9f2`; this supplement and its logs are documentation-only additions made after that run.

**Acceptance boundary:** this is integration evidence for the conditional merge authorized by REV1, not a self-issued final PASS. C1 remains frozen/RED only at this point; its implementation and final Web/Provider/MCP journey are still outstanding.
