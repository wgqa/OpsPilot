# R1-SHUTDOWN-HF-01 — Diagnostic Plan

## Frozen scope

- Base: `codex/r1-main-integration-gate-01@759d0af9ff09c8995bc6fcfa01870264f201d258`
- Remote `main` at opening: `ec8c3582f6d145eec9979c43607302731411ead8`
- Candidate branch at opening: `codex/r1-main-integration-gate-01`
- North Star Blob: `1f737712c7a36ceb34433ac09c3fbba3c3305542`
- AGENTS Blob: `32c45506cceeaa8c76a5c56bf8360ff476b58856`
- Project Skill Blob: `d405c8d413d633824b279202cc1503dab4cf0b03`
- Prior closeout report Blob: `68284f00cbd730f54caf8081543457be5f439be2`

The project Skill, North Star, AGENTS, prior closeout report, Stage B acceptance plan, and applicable deferred gate were actually read from this checkout. Working tree was clean at opening. This is a test-lifecycle correction only; production Worker and ASGI shutdown behavior remain untouched.

## Diagnostic question

Does the MCP-backed Worker finish dispatch cleanup before the test closes `TestClient`, or does the test treat a terminal Domain Run as proof that the Worker has finished unwinding?

## Frozen invariants

- Keep `TestClient` shutdown cancellation and Worker lock release semantics unchanged.
- Do not swallow `CancelledError`, detach threads, or alter business transactions.
- Keep the 11 MCP / 12 model deterministic capacity assertions and zero business-write assertions.
- Do not edit frozen C1 traces or Gold; retain the historical C1 RED.
- No real Provider, browser automation, external business write, or `main` merge.

## Run order

1. Reuse the recorded full-suite shutdown stack and run the target test under test-only lifecycle instrumentation.
2. Run the same ordered adjacent composition to check for test-order sensitivity.
3. Add a test-only wait for dispatch completion and the Worker idle poll; rerun the target with instrumentation and without instrumentation.
4. Run one complete pytest suite with a 60-second faulthandler timeout. Stop after this run; do not repeat a full suite.

Raw logs stay in the private evidence directory. The repository contains a sanitized lifecycle event extract and test summaries.
