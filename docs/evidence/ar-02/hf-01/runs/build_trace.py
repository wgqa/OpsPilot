"""Select auditable observations from saved free, real-MCP test runs only."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNS = ROOT / "runs" / "mcp-runtime-traces"
EMPTY_QUERY = "HTTP 202 acceptance processing"


def details(path: Path) -> dict:
    run = json.loads(path.read_text(encoding="utf-8"))
    events = run.get("events", [])
    calls, payloads, observations = [], [], []
    messages = []
    for event in events:
        if event.get("event") == "model_request":
            messages.append({"phase": "request", "model_id": event.get("model_id"),
                             "messages": event.get("messages", [])})
            for message in event.get("messages", []):
                data = message.get("data", {})
                if message.get("type") == "human":
                    pass
                if message.get("type") == "tool":
                    try:
                        value = json.loads(data.get("content", "{}"))
                    except (TypeError, ValueError):
                        continue
                    if isinstance(value, dict) and "documents" in value:
                        payloads.append(value)
        elif event.get("event") == "model_response":
            messages.append({"phase": "response", "messages": event.get("messages", [])})
            for message in event.get("messages", []):
                for call in message.get("data", {}).get("tool_calls", []):
                    calls.append({"name": call.get("name"), "args": call.get("args")})
        elif event.get("event") == "tool_observation":
            observations.append({
                "tool": event.get("name"), "arguments": event.get("arguments"),
                "result": event.get("result"), "observation": event.get("observation"),
            })
    answer_event = next((event for event in events if event.get("event") == "answer_committed"), {})
    human = next((
        message.get("data", {}).get("content")
        for item in messages if item["phase"] == "request"
        for message in item["messages"] if message.get("type") == "human"
    ), None)
    return {
        "run": run.get("created", {}).get("run_id"),
        "message": run.get("created", {}).get("message_id"),
        "task": run.get("created", {}).get("task_id"),
        "user_input": human,
        "model_messages": messages,
        "model_tool_calls": calls,
        "knowledge_tool_results": payloads,
        "business_observations": observations,
        "answer": answer_event.get("answer"),
        "status": run.get("result", {}).get("status"),
    }


records = [details(path) for path in sorted(RUNS.glob("*.json"))]
hit = next((row for row in records if any(
    p.get("documents") and p.get("source_refs") and p.get("requested_contract_version") is None
    and not row.get("task") for p in row["knowledge_tool_results"]
)), None)
empty = next((row for row in records if any(
    not p.get("documents") and not p.get("source_refs")
    and any(c.get("name") == "search_project_knowledge" and c.get("args", {}).get("query") == EMPTY_QUERY
            for c in row["model_tool_calls"])
    for p in row["knowledge_tool_results"]
)), None)
old_binding = next((row for row in records if any(
    p.get("trusted_binding_contract_version") == 2 and p.get("user_requested_contract_version") == 1
    and p.get("retrieved_contract_version") == 1 and p.get("deployment_version_verified") is False
    for p in row["knowledge_tool_results"]
)), None)
binding_default = next((row for row in records if any(
    p.get("trusted_binding_contract_version") == 2 and p.get("user_requested_contract_version") is None
    and p.get("retrieved_contract_version") == 2 and p.get("deployment_version_verified") is False
    for p in row["knowledge_tool_results"]
)), None)
http = next((row for row in records if row.get("task") and any(
    observation["tool"] == "get_order_status"
    and observation.get("result", {}).get("facts", {}).get("http_status") == 200
    for observation in row["business_observations"]
) and any(
    observation["tool"] == "get_callback_delivery"
    and observation.get("result", {}).get("facts", {}).get("receiver_http_status") == 202
    for observation in row["business_observations"]
) and any(
    observation["tool"] == "get_receiver_processing"
    for observation in row["business_observations"]
)), None)
selected = [
    ("HF01-K1-KNOWLEDGE-HIT", hit), ("HF01-K2-EMPTY-RESULT", empty),
    ("HF01-V3-OLD-PREFERENCE-WITH-BINDING", old_binding),
    ("HF01-V2-BINDING-DEFAULT", binding_default), ("P0-01-LOCAL-HTTP-200-202-RECEIVER", http),
]
assert all(row is not None for _, row in selected), [name for name, row in selected if row is None]
out = ROOT / "TRACE.jsonl"
out.write_text("".join(json.dumps({
    "evidence_level": "DETERMINISTIC_MODEL_REAL_LOCAL_MCP_STDIO_HTTP_SQLITE",
    "case": name, **row,
}, ensure_ascii=False, separators=(",", ":")) + "\n" for name, row in selected), encoding="utf-8")
trace_hash = hashlib.sha256(out.read_bytes().replace(b"\r\n", b"\n")).hexdigest()
files = sorted(
    path for path in (ROOT / "runs").rglob("*")
    if path.is_file() and path.name not in {"TRACE_INDEX.json", "TRACE_INDEX_BUILD.log"}
)
index = {
    "kind": "INDEX_OF_ACTUAL_RUN_ARTIFACTS_NOT_SYNTHETIC_CALLS",
    "trace_sha256_lf": trace_hash,
    "files": [{
        "path": path.relative_to(ROOT).as_posix(),
        "sha256_lf": hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest(),
    } for path in files],
}
(ROOT / "TRACE_INDEX.json").write_text(
    json.dumps(index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
)
print(json.dumps({"selected_cases": len(selected), "trace_lines": len(selected),
                  "trace_sha256_lf": trace_hash, "raw_run_files_indexed": len(files),
                  "cases": [name for name, _ in selected]}))
