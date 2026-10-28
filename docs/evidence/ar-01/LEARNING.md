# AR-01 learning notes

**Principle → business question.** A tool-calling Agent repeatedly receives actual
observations and chooses its next action. LangGraph supplies execution edges;
the existence of graph nodes does not decide whether a system is autonomous.
The relevant question is who chooses the next evidence and whether different
facts lead to different justified behavior.

**Code.** `agent.py::Candidate.run` calls `create_agent`; no callback-failure route
table is installed there. Tool schemas come from the existing MCP server;
`awrap_model_call` and `awrap_tool_call` account attempts and audit, and the
existing Domain decides current authorization/currentness. `simulation.py` is
explicitly a deterministic test policy. `harness.py::run_a` invokes existing S3
strategy A without its formal Diagnosis writer.

**Experiment and failure.** Identical descriptions with 202 vs 503 led the local
test policy to receiver vs delivery-skill queries. E2 PROCESSED did not establish
E1 completion. These prove mechanics with real MCP/HTTP, not real LLM intelligence.
Schema-title stripping initially broke byte equality; retaining original specs at
the actual model boundary fixed comparison without changing legal parameters.
The first complete run contained a test-model parameter-name error and must not
be counted as passing evidence.

**Context tradeoff.** A reconstructs a compact current structured context; B keeps
native message/tool history and stops when retained sources invalidate. Native
history is convenient but not a substitute for provenance and fresh authorized
facts. The same-instance history digest is a narrow experimental boundary, not a
production Context/Memory design or cross-Run goal manager.

**Interview answer.** “I built a standard create_agent candidate beside the
existing S3 investigation policy, kept the same six task-bound tools and fresh
equivalent SQLite states, and compared actual outbound schemas and call ledgers.
Deterministic tests showed source-aware iteration, limits and Scope rejection.
They did not show a smarter model: no real Provider ran, Prompts/Context differed,
and official business outcomes were deliberately outside the comparison. A paid
paired trial is still required before any architecture recommendation.”

Levels: understood/reproduced = locally evidenced; integrated = isolated
experiment only, not production; improved real-model effect = NOT_VERIFIED.
