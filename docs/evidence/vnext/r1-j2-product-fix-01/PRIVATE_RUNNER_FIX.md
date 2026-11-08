# Private R1-LIVE-JOURNEY-02 Runner correction

The Campaign is STOPPED and was not resumed. The private Domain DB, Checkpoint, usage ledger, and original traces were not changed.

In the original private `execution.jsonl` J1-01 entry, both protocol Knowledge MCP calls had `status=OK`, no Task, no `evidence_id`, and no `observation_id`. The J1-01 predicate in private `execute_live.py` required both IDs for every MCP result and therefore counted 0 usable calls, despite two successful Knowledge results and the persisted answer.

The private runner now accepts an unbound call only when it is an allowlisted Knowledge/Skill tool, has `status=OK`, has a dictionary result, and is not an explicit refusal. All other calls continue to require persisted Evidence and Observation IDs. The sibling private continuation runner already used successful-result semantics for this unbound Knowledge case.

Offline evidence:

- Original `execute_live.py` SHA-256: `97e01e45d555f3424f377c4908fce7723c7fba38d775592fa16c33d8fb70baac`
- Corrected private `execute_live.py` SHA-256: `d71ffdf6fb11b130bea7c21afde46918b4fb495a954fcb5f5102efc0b1b2bc1`
- Original private execution trace SHA-256: `416149bcc85c749aeef2662d57f329f289bde4cf855084499c7f495e67bc5fa28`
- Original captured J1-01: 2 successful unbound Knowledge calls; old predicate 0, corrected predicate 2.
- Offline positive/negative predicate assertions and Python compilation passed. No Provider dispatch or DB operation was made.

The historical STOPPED Campaign status and original ledger entries remain untouched. This local correction does not define a generic Campaign resume path.
