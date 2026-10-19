# M3-01 Memory ON/OFF 真实模型评测

- Gold: `opspilot-m301-memory-pairs-v1`; 冻结 8 对 / 16 次，实际 `16` 次。
- Provider: DeepSeek `deepseek-flash`；MCP: 每次 Run 通过 stdio 子进程连接真实本地 MCP Server，Probe 使用 loopback HTTP。
- Source A S1: Task `task-798b6841-82db-4976-8f41-860d0a33df0c`; Memory `episodic-420647ca-b273-41a2-a524-bb948d570e31` / `e94ff01876d3f04424cb970ab1a363a2250d8c3ce2235973d948c85169920136`。
- Source A S2: Task `task-4c8aa72a-bb1e-4f28-8de2-3c3edaccf6d6`; DiagnosisReceipt `s2-receipt-1ae27285-cd55-476b-a982-baf7cea283b0`; Memory `episodic-e2b59674-6963-43c6-af11-789209b196f6` / `bfc78a31238a0232378b85dc534edba2a51997b0840e652d2c67191d52e501fe`。
- Runtime dependencies: `{"langchain": "1.4.1", "langchain-openai": "1.7.2", "langgraph": "1.2.16", "langgraph-checkpoint-sqlite": "3.1.2", "mcp": "2.3.0", "pydantic": "2.14.1"}`.
- Utility: `UTILITY_NOT_PROVEN`. Any observed outcome and token/MCP counts remain in `RESULTS.json`; the 8 pairs are exploratory only.
- No trial authorizes or performs REPAIR, DELIVER, Scope grant, or handoff submission.
- Per-run evidence: `TRACE.json`; raw console log is captured by the invocation wrapper.
