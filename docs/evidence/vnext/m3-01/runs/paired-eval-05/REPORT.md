# M3-01 Memory ON/OFF 真实模型评测

- Gold: `opspilot-m301-memory-pairs-v1`; 冻结 8 对 / 16 次，实际 `16` 次。
- Provider: DeepSeek `deepseek-flash`；MCP: 每次 Run 通过 stdio 子进程连接真实本地 MCP Server，Probe 使用 loopback HTTP。
- Source A S1: Task `task-798b6841-82db-4976-8f41-860d0a33df0c`; Memory `episodic-38fcf19a-7e0c-4944-99cf-0d2c8ea258d6` / `e94ff01876d3f04424cb970ab1a363a2250d8c3ce2235973d948c85169920136`。
- Source A S2: Task `task-0ac3d176-4a5c-4742-b6c9-4d374c4295c7`; DiagnosisReceipt `s2-receipt-e285f502-4f96-45c1-87f3-18b305398fb0`; Memory `episodic-742dadbf-5b49-4f9c-8649-5483d2667f94` / `128cb1193f98b4e1c75c8a273e3b8ee0c5093bab2107817fdb23eac229ee6c9d`。
- Runtime dependencies: `{"langchain": "1.4.1", "langchain-openai": "1.7.2", "langgraph": "1.2.16", "langgraph-checkpoint-sqlite": "3.1.2", "mcp": "2.3.0", "pydantic": "2.14.1"}`.
- Utility: `UTILITY_NOT_PROVEN`. Any observed outcome and token/MCP counts remain in `RESULTS.json`; the 8 pairs are exploratory only.
- No trial authorizes or performs REPAIR, DELIVER, Scope grant, or handoff submission.
- Per-run evidence: `TRACE.json`; raw console log is captured by the invocation wrapper.
