from __future__ import annotations
import hashlib
import json
import math
import pathlib
import sqlite3
import sys

ROOT = pathlib.Path(__file__).resolve().parent
REPO = ROOT.parents[3]
LOG = ROOT / "runs" / "postrun-evidence-check-green.log"
lines: list[str] = []

def require(ok: bool, name: str) -> None:
    if not ok:
        raise AssertionError(name)
    lines.append("PASS " + name)

def walk_prompts(value):
    if isinstance(value, dict):
        for key, child in value.items():
            if key in {"user_prompt", "prompt", "user_input"} and isinstance(child, str):
                yield child
            yield from walk_prompts(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk_prompts(child)

def main() -> int:
    try:
        cases = json.loads((REPO / "docs/evidence/ar-03-real-llm-01-prep/CASES.json").read_text(encoding="utf-8"))
        prompt = next(iter(walk_prompts(cases)), None)
        require(prompt is not None, "frozen input found")

        requests, responses = {}, {}
        for line in (ROOT / "PROVIDER_HTTP.jsonl").open(encoding="utf-8"):
            row = json.loads(line)
            target = requests if row["record_type"] == "provider_http_request" else responses
            target[row["global_request_number"]] = row
        require(len(requests) == len(responses) == 13 and requests.keys() == responses.keys(), "13 request/response pairs; no missing result")

        totals = {key: 0 for key in ("prompt_tokens", "completion_tokens", "total_tokens", "prompt_cache_hit_tokens", "prompt_cache_miss_tokens")}
        costs_by_scenario = {"A": 0, "B": 0}
        counts = {"A": 0, "B": 0}
        for number, request in requests.items():
            response = responses[number]
            body = request["body"]
            usage = response["body"].get("usage") or {}
            require(response["status_code"] == 200, f"request {number} returned HTTP 200")
            require(request["url"] == "https://api.deepseek.com/v1/chat/completions", f"request {number} used frozen endpoint")
            require(body.get("model") == "deepseek-flash" and response["body"].get("model") == "deepseek-flash", f"request {number} model matched")
            require(body.get("max_tokens") == 2048 and body.get("thinking", {}).get("type") == "disabled" and body.get("parallel_tool_calls") is False and body.get("stream") is False, f"request {number} frozen parameters matched")
            require(not body.get("tools") or body.get("tool_choice") == "auto", f"request {number} tool choice matched")
            require(all(key in usage for key in ("prompt_tokens", "completion_tokens", "total_tokens")), f"request {number} usage complete")
            require(bool(response["body"].get("id")), f"request {number} has Completion ID")
            require(not any("authorization" in key.lower() or "api-key" in key.lower() for key in request.get("headers", {})), f"request {number} headers redacted")
            scenario = request["scenario"]
            counts[scenario] += 1
            for key in totals:
                totals[key] += usage.get(key, 0)
            costs_by_scenario[scenario] += math.ceil(usage["prompt_tokens"] * .30 + usage["completion_tokens"] * 1.20)
        require(counts == {"A": 7, "B": 6}, "paired allocation A=7, B=6")
        require(max(row["body"]["usage"]["prompt_tokens"] for row in responses.values()) <= 12000, "context input remained within 12,000 tokens")

        result = json.loads((ROOT / "RESULTS.json").read_text(encoding="utf-8"))
        ledger = json.loads((ROOT / "BUDGET_LEDGER.json").read_text(encoding="utf-8"))
        require(result["outcome"] == "PARTIAL" and result["provider_requests"] == 13 and result["mcp_total"] == 12, "runner totals and outcome")
        require(result["business_action_writes"] == 0 and result["historical_experiments_modified"] is False and result["provider_inflight_at_stop"] == 0, "zero writes, historical experiments unchanged, no inflight request")
        require(ledger["provider_ledger_dispatches"] == 13 and ledger["mcp_ledger_dispatches"] == 12 and ledger["reserved_usd_micro"] == 0 and ledger["settled_usd_micro"] == 20252, "budget ledger matches captured HTTP and Usage")
        require(sum(costs_by_scenario.values()) == ledger["settled_usd_micro"], "no-cache peak-price estimate matches settlement")

        domain_traces = []
        fixture_states = {}
        for line in (ROOT / "TRACE.jsonl").open(encoding="utf-8"):
            row = json.loads(line)
            if row.get("record_type") == "scenario_domain_trace":
                domain_traces.append(row)
            elif row.get("record_type") == "isolated_fixture_setup":
                fixture_states[row["scenario"]] = row["receiver_status"]
        require(len(domain_traces) == 2 and {row["scenario"] for row in domain_traces} == {"A", "B"}, "two independent Domain traces")
        require(fixture_states == {"A": "QUEUED", "B": "PROCESSED"}, "frozen Receiver contrast in isolated fixture traces")
        sessions, tasks = set(), set()
        for row in domain_traces:
            scenario = row["scenario"]
            sessions.add(row["session_id"])
            tasks.add(row["task_id"])
            require(sum(1 for message in row["messages"] if message.get("role") == "USER" and message.get("body") == prompt) == 1, f"frozen prompt used exactly once in {scenario}")
            require(all(value == 0 for value in row["agent_business_write_counts"].values()), f"protected write counters are zero in {scenario}")
            mcp_ok = [call for call in row["assistant_calls"] if call.get("kind") == "MCP" and call.get("status") == "OK"]
            require(len(mcp_ok) == 6, f"six successful budgeted MCP calls in {scenario}")
            db = ROOT / "runtime" / f"scenario-{scenario}" / "domain.sqlite3"
            with sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True) as connection:
                dispatches = connection.execute("select experiment_id,kind,status,usage_state,count(*) from ar02_live_dispatches group by experiment_id,kind,status,usage_state").fetchall()
                require(all(item[0] == "AR-03-REAL-LLM-01" for item in dispatches), f"fresh AR-03 ledger identity in {scenario}")
                require(connection.execute("pragma quick_check").fetchone()[0] == "ok", f"SQLite quick_check in {scenario}")
        require(len(sessions) == len(tasks) == 2, "Session and Task identities isolated")

        manifest = json.loads((ROOT / "RUNTIME_ARTIFACTS.json").read_text(encoding="utf-8"))
        for item in manifest["runtime_artifacts"]:
            path = ROOT / item["path"]
            require(path.stat().st_size == item["bytes"] and hashlib.sha256(path.read_bytes()).hexdigest() == item["sha256"], "runtime hash " + item["path"])
        lines.append("USAGE_TOTALS " + json.dumps(totals, sort_keys=True))
        lines.append("SCENARIO_ESTIMATES_USD " + json.dumps({key: value / 1_000_000 for key, value in costs_by_scenario.items()}, sort_keys=True))
        lines.append("RESULT PASS")
        LOG.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print("\n".join(lines))
        return 0
    except Exception as error:
        lines.append("FAIL " + type(error).__name__ + ": " + str(error))
        LOG.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print("\n".join(lines))
        return 1

if __name__ == "__main__":
    raise SystemExit(main())