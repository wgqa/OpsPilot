# PRODUCT-01-RUNTIME-GRANT-01

## Frozen scope

- Base: `38ab276cfdcb3b4b6d70232884080aa518827db2`
- Branch: `codex/product-01-runtime-grant-01`
- Main baseline: `60eee87bfe3cca522011316cb4cd2c0064ad291b`
- User task-card SHA-256: `B4D5E149694759227FE3BCD8BB2860F40FDA282FAA462429E7D100799096AAB6`
- North Star blob: `43dabda468506717c6956e676dfad4304c4f38e6`
- AGENTS blob: `807b928686a4dd2cac7b15b3c354b9943c93c910`
- Review Skill blob: `d405c8d413d633824b279202cc1503dab4cf0b03`

Implement one explicit deployment-level Assistant Runtime Grant and persistent spend pool. Ordinary `ASSISTANT_V1` runs must not require historical experiment identities or one-shot claims. The grant is opt-in and has no default authorization or amount. Existing experiment ledgers and semantics remain unchanged.

## Validation boundary

Use isolated SQLite databases, deterministic models, and explicit HTTPX `MockTransport`. Validate the real FastAPI/Worker/Assistant/ChatOpenAI path, persistence and recovery, shared spend across sessions, and refusal paths. No real Provider, browser, external MCP service, production resource, or external business write is authorized.

The implementation retains the existing per-Run MODEL/MCP limits, TaskBinding, source revalidation, and business-write boundaries. This slice does not create a management API or select a production budget.
