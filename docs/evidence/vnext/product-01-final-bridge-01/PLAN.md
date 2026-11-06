# PRODUCT-01-FINAL-BRIDGE-01

## Frozen scope

- Repository: `wgqa/OpsPilot`
- Base: `codex/product-01-slice-02-live@0d29422b5e4b291926c5a2f44bde7f87a5263960`
- Implementation branch: `codex/product-01-final-bridge-01`
- Main remains unchanged; no merge is authorized.
- Authorized: isolated code changes and free local tests.
- Not authorized: paid Provider calls, browser automation, production writes, or main merge.

## User journey

1. A user asks the ordinary Assistant to investigate an access problem.
2. The Assistant may make an advisory proposal tied to the original user message. The proposal itself creates no Task, binding, approval, permission, or business write.
3. The user reviews the original question and explicitly confirms through the existing Session Task API.
4. The existing S2 Investigator and Domain produce the diagnosis and handoff draft. The existing handoff submit path creates the local receipt and queue entry.
5. In the same Session, the ordinary Assistant may read authorized persisted S1/S2 outcomes and explain their actual state.

## Acceptance boundaries

- The model may answer, clarify, propose, or read same-Session results; no fixed tool order is required.
- Task/tenant/actor authority comes from trusted server context and Domain bindings, never model-supplied IDs.
- Persisted historical outcomes must not be described as a fresh probe.
- A handoff awaiting review is not a permission grant or a recovery result.
- Existing S1 and S2 Domain workflows remain authoritative.
- Browser and real Provider acceptance remain unrun under the current authorization.
