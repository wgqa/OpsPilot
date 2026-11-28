# R1-LIVE-JOURNEY-02 Cost Ledger

Application estimates from persisted Usage; not the provider invoice.

- Campaign R1-LIVE-JOURNEY-02; model deepseek-flash.
- Provider sends 7/12; HTTP 200 7; MCP calls 5.
- Reserve/send USD 0.645600; outstanding UNKNOWN reserve USD 0.000000.
- Settled estimate USD 0.014765; remaining of USD 8.00 USD 7.985235.

| # | Run | Completion ID | HTTP | Input | Output | Total | Cache hit | Cache miss | Reserve USD | Settled USD | State |
|---:|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| 1 | `run-06101179-1123-4adf-bad6-49f601264724` | `6e67a52f-9133-474f-bc8a-a7eb9c4f1102` | 200 | 1648 | 67 | 1715 | 256 | 1392 | 0.645600 | 0.000575 | DELIVERED |
| 2 | `run-06101179-1123-4adf-bad6-49f601264724` | `ddddec06-4597-47ee-a029-47e26edfb226` | 200 | 3314 | 126 | 3440 | 256 | 3058 | 0.645600 | 0.001146 | DELIVERED |
| 3 | `run-06101179-1123-4adf-bad6-49f601264724` | `5c136c7f-d8f9-45a6-8a2d-1e9d38652841` | 200 | 4671 | 1001 | 5672 | 256 | 4415 | 0.645600 | 0.002603 | DELIVERED |
| 4 | `run-619d4f78-eb53-4fc9-8a9d-c98351485a5c` | `2ff9d088-2fba-4f69-8c59-a1ea00894d8e` | 200 | 4931 | 806 | 5737 | 256 | 4675 | 0.645600 | 0.002447 | DELIVERED |
| 5 | `run-1c5476c2-822f-4199-a185-e29cf9c2455b` | `8fb329f7-eacd-435e-82d6-4936366a2b90` | 200 | 4756 | 721 | 5477 | 256 | 4500 | 0.645600 | 0.002292 | DELIVERED |
| 6 | `run-da63984e-2030-405f-81f4-383e91c4a205` | `9c3b36dc-e1d1-41e9-ac7b-b0bfc133210b` | 200 | 5780 | 162 | 5942 | 256 | 5524 | 0.645600 | 0.001929 | DELIVERED |
| 7 | `run-da63984e-2030-405f-81f4-383e91c4a205` | `191309d8-ea5c-4fd9-91be-349fcea5828a` | 200 | 8980 | 899 | 9879 | 256 | 8724 | 0.645600 | 0.003773 | DELIVERED |

Totals: 34080 input / 3782 output / 37862 total tokens; cache hit 1792, miss 32288; settlement USD 0.014765.

Price checked before execution: DeepSeek official deepseek-flash pricing listed cache-miss input USD 0.30/M and output USD 1.20/M. The frozen public-capacity reserve remained USD 0.645600 per send. See [official pricing](https://api-docs.deepseek.com/quick_start/pricing/) and [Chat Completions API](https://api-docs.deepseek.com/api/create-chat-completion/).

All seven dispatches are DELIVERED with HTTP 200, Completion ID and Usage. No UNKNOWN, missing Usage or retries. First three settlements were preserved during the audited runner correction. Remaining budget is not authorization for another Campaign.
