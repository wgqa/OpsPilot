"""One preregistered real post-fix journey; normal authenticated Web APIs.

Never imports Domain write functions or modifies stored facts. Fixed inputs,
limits and identities are committed before this script executes.
"""
import json
import sqlite3
import time
from datetime import datetime, timezone

from web_commands import BASE, OUT, RUNTIME, WebClient

ids = json.loads((OUT / "P1-identities.json").read_text(encoding="utf-8"))
inputs = json.loads((BASE / "B_INPUTS.json").read_text(encoding="utf-8"))
db_path = RUNTIME / "domain.sqlite3"


def rows(query, args=()):
    with sqlite3.connect(db_path) as db:
        db.row_factory = sqlite3.Row
        return [dict(r) for r in db.execute(query, args)]


def save(name, value):
    (OUT / name).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def record(kind, **values):
    print(json.dumps({"at": datetime.now(timezone.utc).isoformat(), "kind": kind, **values}, ensure_ascii=False), flush=True)


def wait_health():
    import httpx
    for _ in range(160):
        try:
            if httpx.get("http://127.0.0.1:8003/api/health", timeout=1).is_success:
                return
        except httpx.HTTPError:
            pass
        time.sleep(.2)
    raise RuntimeError("API_RESTART_NOT_HEALTHY")


def turn(client, item):
    number = item["number"]
    if (OUT / f"P1-turn-{number:02d}-result.json").exists():
        raise RuntimeError("Refuse duplicate execution")
    accepted = client.request("POST", f"/api/sessions/{ids['target_session_id']}/messages", {
        "body": item["body"], "input_kind": "CHAT_READONLY", "task_id": ids["target_task_id"],
    }, operation_id=f"hf02-p1-{ids['target_task_id']}-turn-{number:02d}")
    record("TURN_ACCEPTED", number=number, run_id=accepted["run_id"])
    result = None
    for _ in range(600):
        result = rows("SELECT * FROM task_runs WHERE run_id=?", (accepted["run_id"],))[0]
        if result["status"] in {"SUCCEEDED", "FAILED", "BLOCKED", "CANCELLED", "ABORTED"}:
            break
        time.sleep(.2)
    save(f"P1-turn-{number:02d}-result.json", {"accepted": accepted, "run": result})
    record("TURN_FINISHED", number=number, run_id=accepted["run_id"], status=result["status"])
    if result["status"] != "SUCCEEDED":
        raise RuntimeError("Bounded experiment stopped on non-successful Run")


wait_health()
support = WebClient("support-a")
for item in inputs["turns"][:8]:
    turn(support, item)
summaries = rows("SELECT * FROM context_summaries WHERE task_id=?", (ids["target_task_id"],))
dependencies = rows("SELECT d.* FROM context_summary_dependencies d JOIN context_summaries s ON s.summary_id=d.summary_id WHERE s.task_id=?", (ids["target_task_id"],))
save("P1-summary-before-revocation.json", {"summaries": summaries, "dependencies": dependencies})
record("ACTIVE_WINDOW_FINISHED", summary_count=len(summaries), dependency_count=len(dependencies))
approver = WebClient("approver-a")
revoked = approver.request("POST", f"/api/memories/{ids['memory_id']}/revoke", {}, operation_id="hf02-p1-revoke-" + ids["memory_id"])
save("P1-revoked.json", revoked)
record("MEMORY_REVOKED", memory_id=revoked["memory_id"], version=revoked["version"])
turn(support, inputs["turns"][8])
events = OUT / "process-events.jsonl"
before = sum(1 for _ in events.open(encoding="utf-8"))
with (RUNTIME / "commands.jsonl").open("a", encoding="utf-8") as f:
    f.write(json.dumps({"command": "restart", "reason": "Pinned post-fix turn 10 no revival after restart"}) + "\n")
for _ in range(160):
    fresh = [json.loads(v) for v in events.read_text(encoding="utf-8").splitlines()[before:]]
    if any(v["kind"] == "API_STARTED" for v in fresh):
        break
    time.sleep(.2)
else:
    raise RuntimeError("Owned restart not observed")
wait_health()
turn(WebClient("support-a"), inputs["turns"][9])
record("BOUNDED_JOURNEY_FINISHED", active_turns=8, revoked_turns=2)
