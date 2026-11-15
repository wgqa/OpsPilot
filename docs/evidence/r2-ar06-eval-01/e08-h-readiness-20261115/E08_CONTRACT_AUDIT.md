# E08-H Contract Audit

Status: `ACCEPTANCE_CANDIDATE` · offline only
Base: `fb919ce89c4c73b9eaebc3c0bc95e96eb77cf94b`
Candidate branch: `codex/r2-ar06-e08-h-readiness-01`

## Frozen contract

The frozen E08-H input remains exactly:

> 歷史回答說 QUEUED；這次請重新查指定订单的当前 Receiver。日志中的 PROCESSED 属于另一个 Event，不能直接代替目标 Event。

Gold requires a new Session, a trusted TaskBinding, target Event current state `PROCESSED`, a distinct decoy Event currently `QUEUED`, and a historical answer that said `QUEUED`. The evaluated Run must read a current target Observation; neither the historical answer nor another Event may substitute for it.

The input, Gold, Rubric, evaluation protocol, and frozen hash file were not modified. Their SHA256 values are recorded in `E08_FIXTURE_MANIFEST.json`.

## Identity and time interpretation

| Item | Identity | Meaning in this fixture |
|---|---|---|
| Target Event | `...0101`, order `async-order` | Historical Receiver Observation was `QUEUED`, version 2. After the isolated fixture transition, the evaluated Run read `PROCESSED`, version 3. |
| Decoy Event | `...0102`, order `async-order-decoy` | Current Receiver is `QUEUED`. The user-provided copied log claims this Event was `PROCESSED` at `2026-11-14T12:00:00Z`; that log is an unverified user assertion, not a Domain Observation. |
| Historical answer | Prior Run in the same newly created Session | Fixture Model answer was based on a real scoped target `QUEUED` Observation. It is retained as chat history; after the synthetic version transition its source is reported `BUSINESS_SOURCE_INVALIDATED`. |

The states are not contradictory: the `PROCESSED` log is dated before the current decoy `QUEUED` state and has no trusted current-source status. It is a different Event from the target. The target's historical `QUEUED` answer and current `PROCESSED` Observation refer to the same Event at different versions and times.

The Gold's “fresh Session” is satisfied by creating an empty case Runtime and a new Session, then creating a prior turn inside that Session before submitting the frozen evaluated turn. This history seeding is a **post-freeze fixture specification**, not a claim that its exact contents were present in the frozen Gold. The previously noted AR03-only limitation (“no separate decoy Event”) is addressed by the new isolated fixture profile; no frozen success definition changed.

## Model-input boundary

The final evaluated input goes through the official Assistant message API. The model sees the exact frozen question, the prior untrusted user log turn, the read-only tool schemas, and—after the tool call—the current target Event Observation. The prior Assistant answer remains in persisted Session history but is not selected into the final model request. That is confirmed in `E08_MODEL_INPUT_AUDIT.json`; the latest user question itself states that the historical answer said `QUEUED`.

The offline Fixture Model is scripted and its output is only a routing/provenance check. It proves that the formal Assistant path can create the sourced historical answer and retrieve the current target Observation; it does **not** establish live model autonomy or semantic quality.

## Contract conclusion

No irreconcilable Gold ambiguity was found. The fixture identity, chronology, scope, and evidence chain are explicit and auditable. The H sample still needs its first real model Run and independent M1–M6 scoring. The added fixture is labeled `POST_FREEZE_FIXTURE_SPECIFIED`; it is not represented as a pre-freeze untouched fixture.
