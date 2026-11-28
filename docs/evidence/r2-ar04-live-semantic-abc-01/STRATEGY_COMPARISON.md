# A/B/C Strategy Comparison

## Live semantic results

This candidate has **no live A/B/C comparison**. The run stopped at zero-cost preflight because the local approved DeepSeek credential and Runtime configuration were absent. All nine answer slots are `BLOCKED_BEFORE_PROVIDER_SEND`; live Summary requests, live answers, live Token Usage, L2 and L3 are all **not observed**. No ranking or recall-accuracy claim is made.

| Group | Strategy | Planned answers | Live answers | Live summaries | Live L2/L3 |
|---|---|---:|---:|---:|---|
| A | HYBRID | 3 | 0 | 0 | BLOCKED / BLOCKED |
| B | ROLLING_SUMMARY | 3 | 0 | 0 | BLOCKED / BLOCKED |
| C | RECENT_WINDOW | 3 | 0 | 0 | BLOCKED / BLOCKED |

## Existing offline harness evidence (Fixture + Mock only)

The prior Setup-HF01 harness ran the same questions through the real Assistant context-preparation path with `httpx.MockTransport`. Its deterministic fixture summaries and answers prove wiring and context selection only. They are not real model memory evidence and are not pooled with this live attempt.

For the three selected questions, the stored mock manifests report these context estimates and calls:

| Group | Strategy | Q02 / Q03 / Q06 estimated answer input tokens | Mock summary calls per case | Current schema / trusted prompt parity |
|---|---|---|---:|---|
| A | HYBRID | 4,937 / 4,941 / 4,939 | 2 | same as B/C |
| B | ROLLING_SUMMARY | 4,938 / 4,941 / 4,942 | 2 | same as A/C |
| C | RECENT_WINDOW | 4,840 / 4,842 / 4,841 | 0 | same as A/B |

In those Mock runs the effective history budgets varied by strategy and question (8,175–8,188 tokens) because the Runtime reserves system, context, schema, and tool-result overhead from the configured 12,000-token input cap. A/B each persisted two fixture summaries for these questions; C selected a recent window without a summary. The precise manifests and payloads remain in Setup-HF01 `TEST_RESULTS.json` and `MOCK_TRACE.jsonl.gz`.

## Fairness and schema note

For Q02, Q03, and Q06, the Setup-HF01 Mock records show identical frozen history/question digests, one current tool-schema digest (`555cd385…`), one trusted system-prompt-prefix digest (`46267d78…`), model alias, `tool_choice=none`, and configured input limit across A/B/C. Phase A's tool-schema digest is `f6c75eaa…`; inspection shows actual schema field differences, including omitted annotation titles and the `memory_remember` `additionalProperties:false` constraint. This historical schema drift is documented, not repaired here. The current A/B/C inputs were internally matched in the offline harness, but no live run was made against either schema.

**Evidence labels:** live status = environment/configuration inspection; historical rows = `FIXTURE_AND_MOCK_PROVIDER_TRANSPORT`; no result has `REAL_PROVIDER` evidence.
