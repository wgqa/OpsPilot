# M3-01 Memory ON/OFF paired evaluation recovery

- Frozen Gold: `opspilot-m301-memory-pairs-v1`; 8 pairs / 16 planned and `16` included arms.
- Model: DeepSeek `deepseek-flash`; MCP stdio and loopback HTTP; isolated retry arms: `5`.
- Source of preserved original arms: `D:\学习\agent新项目\docs\evidence\vnext\m3-01\runs\paired-eval-03`. First failures remain unchanged there and are summarized in `FAILED_ATTEMPTS.json`.
- Runtime dependencies: `{"langchain": "1.4.1", "langchain-openai": "1.7.2", "langgraph": "1.2.16", "langgraph-checkpoint-sqlite": "3.1.2", "mcp": "2.3.0", "pydantic": "2.14.1"}`.
- Every retry used a separate Worker process to create a fresh event loop. Other arms reused successful persisted real traces without repeating external calls.
- Per-case tokens, model/MCP calls, tool order, outcomes and safety counters are in `RESULTS.json` and `TRACE.json`.
- Utility remains `UTILITY_NOT_PROVEN`; this report does not claim statistical or causal generalization.
- No REPAIR, DELIVER, Scope grant, or handoff submission is allowed or performed by these trials.
