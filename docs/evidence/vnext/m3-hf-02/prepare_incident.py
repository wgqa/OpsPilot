"""Explicit pre-frozen fixture action, audited separately from Agent operations."""
import hashlib
import json
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path.cwd()
sys.path.insert(0, str(ROOT))
from opspilot.domain.test_fixtures import prepare_d5_auth_401_for_test

db = ROOT / ".runtime/m3-hf-02/journey-01/domain.sqlite3"
base = Path(__file__).resolve().parent
label = sys.argv[1]
if label not in {"A-target", "B-target", "P1-target"}:
    raise SystemExit("Only the pre-frozen fixture preparations are allowed (P1 target requires confirmed RED).")
output = base / f"runs/journey-01/fixture-{label}.json"
if output.exists():
    raise SystemExit("Existing preparation record protected; this is not a repeatable repair.")
tables = ("integrations", "principals", "auth_policies", "principal_scope_grants", "route_scope_policies", "d3_action_ledgers", "d3_delivery_records", "d5_memories")


def snapshot():
    with sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True) as c:
        c.row_factory = sqlite3.Row
        return {table: [dict(r) for r in c.execute("SELECT * FROM " + table)] for table in tables}


before = snapshot()
version = prepare_d5_auth_401_for_test(db, "tenant-a", "integration-a")
after = snapshot()
unchanged = {table: before[table] == after[table] for table in tables if table != "integrations"}
assert all(unchanged.values())
result = {"at": datetime.now(timezone.utc).isoformat(), "label": label, "not_an_agent_action": True, "source_function": "opspilot.domain.test_fixtures.prepare_d5_auth_401_for_test", "source_sha256": hashlib.sha256((ROOT / "opspilot/domain/test_fixtures.py").read_bytes()).hexdigest(), "git_head": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(), "new_config_version": version, "before": before, "after": after, "unchanged": unchanged}
output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps({"label": label, "new_config_version": version, "not_an_agent_action": True, "unchanged": unchanged}))
