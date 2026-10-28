# A/B real-model comparison: NOT_RUN

P1 has no paid-call authorization; P2 is NOT_RUN. No real DeepSeek model choices,
Usage, prices actually billed, task quality differences or architecture ranking
have been observed in this release. All HTTP model responses in TRACE are explicitly
labelled LOCAL_PROTOCOL_STUB; original-agent traces use a deterministic model.

The final local five-pair test used equivalent initial fact snapshots, identical
six wire schemas/permissions, 10 Runs, 26 fake-Provider requests and 16 real local
MCP attempts. Each arm used 13 model calls and 8 MCP attempts. Stub Usage (100
input / 20 output per response) tests accounting only. It predicts neither real
cost nor intelligence. Per-case outcome/tool sequence is recorded, not prescribed
as Gold. Protected business snapshots stayed unchanged.

Preserved confounds from original PARITY.md:

- A reconstructs structured current Context and extra method catalog; B uses its
  shorter instruction and native message/tool history. Prompt/context are unequal.
- A executes one candidate then reconsiders; B serializes a native multi-call batch
  if the model violates parallel=false. Same capability/authorization, different
  execution semantics. The local normal cases use single proposals.
- Initial Run 8/6 only; B's cap also limits experimental Task cumulative use. Full
  product multi-Run CONTUX 24/18 allocation is outside this comparison.
- Existing sources are revalidated by both arms, but invalidated retained B history
  stops rather than rebuilding a product Context. Worker/checkpoint recovery,
  formal diagnosis and handoff writers are not included in either trial adapter.

The same Provider adapter and finite global ledger reduce new transport/accounting
confounds. They do not make prompts equal or isolate Agent Loop as a causal factor.
Real scoring, if separately authorized, retains task completion, decisions,
observation-driven change, Event/request identity, clarify/stop, safety, Tokens,
latency/errors and all partials. Report model answer/clarification separately from
deterministic fallback; never use fallback as evidence of model intelligence.

No claim that A or B is better, no production migration, no AR-02 recommendation
based on the deterministic scores. Current next action is independent P0 review
and monetary/authorization resolution, not paid execution.
