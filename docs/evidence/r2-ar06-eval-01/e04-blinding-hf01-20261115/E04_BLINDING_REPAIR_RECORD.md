# E04-H blinding repair record

**Status:** `POST_FREEZE_FIXTURE_BLINDED_V2`
**Base:** `4e23e229cea3e42d61ebb2bc49f25a0e37bf5f1c`
**Candidate branch:** `codex/r2-ar06-e04-eval-blinding-hf01`

## What changed

The first E04 fixture exposed `orders-e04-absence` as the project ID in MCP discovery results. The original Trace contains 12 occurrences of that identifier in the model-visible messages across its four model requests. That name disclosed the selected fixture condition before the first real model run.

The revised fixture uses the neutral model-visible project ID `orders-protocol-review`. The E04 runtime registry is generated from the existing scoped document references and no longer contains evaluation-only fixture metadata. E03 remains `orders-async-demo`; shared `knowledge/assistant-access.json`, document contents, document IDs, versions, source labels, and digests are unchanged.

The original frozen E04-H question is loaded from `CASES.json` without edits. The test-created manifest records a post-freeze revision and the fixture boundary outside model context. It does not add a hint to the question or tool results. The model still has the ordinary legal choices: compare the authorized v1/v2 documents, read a bounded source excerpt, ask for missing materials, or stop.

## Evidence lineage

| Artifact | SHA256 |
| --- | --- |
| Original Manifest | `5ea356cc2928d335aa5030bae083ffd899aa121843454a028532fb53b124b83f` |
| Original Trace | `7354e0ba526e18515c829f31a659640a064584f98689a4d57602f8366b23c432` |
| Original Result | `3fb707e218150284d185672c2846381b731d83f3ade5688bb3eebf9de7d15ebb` |
| Revised Manifest v2 | `a9c5787ce504eaf44d87746445a1ca3d039ad55d98b43225eeb12b70e20a5507` |
| Revised fixture Trace | `8d144f5c06cc4d59f9e9e0c9d7bc455854276100ea5550717725869127c6a7bc` |
| Revised fixture Result | `cbb5d23407b5597470f73a44b755c0012849d9eb2be0acb0d68cc6477447a7a2` |

The original Manifest, Trace, and Result remain in `e04-h-absence-20261115/` unchanged. Manifest v2 links the original Manifest by path and SHA and records that document contents and the frozen question are unchanged.

## Actual model-input audit

The new run used a fresh isolated Runtime, a formal Assistant API Session, and the local Fixture Model. Audit source is each persisted model call's `request_json.messages` and `request_json.tools`, not just the test model's intended prompt.

- Four actual model request inputs were inspected.
- `orders-protocol-review` is the only registered project ID and appears in scoped discovery results after the first request.
- No occurrence was found for `orders-e04-absence`, `absence`, `expected_answer`, `gold_status`, either fixture-status label, `fixture_manifest`, `E04-H`, or `evaluation_only` in any model-visible messages or tool schemas.
- `deployment_version_verified=false` remains in the normal business result and is visible as a boundary that static protocol documents do not establish deployment state.
- Gold, Rubric, manifest metadata, and evaluation-only status remain outside the model request.

See `E04_MODEL_INPUT_AUDIT.json` and the full sanitized `E04_FIXTURE_TRACE.json`.

## Execution boundary

This is an offline Fixture result, not a real-model score. The run created no Runtime Grant, sent no Provider request, received no Provider response, created no TaskBinding, and performed no business write. `assessment_status` remains `UNVERIFIED`; independent Rubric scoring is still pending.
