"""Owns only this phase's isolated API/Vite process trees and synthetic fixture."""
import json
import os
import secrets
import sqlite3
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path.cwd()
sys.path.insert(0, str(ROOT))
from opspilot.config import load_local_environment
from opspilot.domain.database import reset_fixture
from opspilot.smokes.m1_03 import _kill, _server_environment, _start, _start_vite, _wait_http

load_local_environment()
EVIDENCE = Path(__file__).resolve().parent
OUT = EVIDENCE / "runs/journey-01"
RUNTIME = ROOT / ".runtime/m3-hf-02/journey-01"
RUNTIME.mkdir(parents=True, exist_ok=True)
OUT.mkdir(parents=True, exist_ok=True)
(OUT / "screenshots").mkdir(exist_ok=True)
DB, CP = RUNTIME / "domain.sqlite3", RUNTIME / "checkpoints.sqlite3"
resume_existing = "--resume" in sys.argv
if DB.exists() and not resume_existing:
    raise SystemExit("This controller requires a fresh directory; existing Domain is protected.")
if resume_existing:
    if not DB.exists() or not CP.exists():
        raise SystemExit("Resume requires both original persistent databases.")
    passwords = json.loads((RUNTIME / "test-passwords.json").read_text(encoding="utf-8"))
else:
    passwords = {actor: secrets.token_urlsafe(22) for actor in ("support-a", "approver-a", "support-b", "approver-b")}
    (RUNTIME / "test-passwords.json").write_text(json.dumps(passwords), encoding="utf-8")
    reset_fixture(DB, "S1_POS")
with sqlite3.connect(DB) as d:
    d.row_factory = sqlite3.Row
    initial = {t: [dict(r) for r in d.execute("SELECT * FROM " + t)] for t in ("integrations", "principals", "auth_policies", "principal_scope_grants", "route_scope_policies", "orders", "trusted_operators")}
if not resume_existing:
    (OUT / "fixture-initial.json").write_text(json.dumps(initial, ensure_ascii=False, indent=2), encoding="utf-8")

env = _server_environment(DB, CP, "http://127.0.0.1:5176", passwords)
env.update({"OPSPILOT_CONTEXT_STRATEGY": "HYBRID", "OPSPILOT_CONTEXT_INPUT_BUDGET_TOKENS": "12000", "OPSPILOT_CONTEXT_OUTPUT_RESERVE_TOKENS": "512", "OPSPILOT_CONTEXT_WINDOW_TOKENS": "16384", "OPSPILOT_CONTEXT_SAFETY_MARGIN_TOKENS": "1024", "OPSPILOT_HF02_PROVIDER_OBSERVATIONS": str(OUT / "provider-observations.jsonl")})
commands = RUNTIME / "commands.jsonl"
if not resume_existing:
    commands.write_text("", encoding="utf-8")


def record(kind, **values):
    row = {"at": datetime.now(timezone.utc).isoformat(), "kind": kind, **values}
    with (OUT / "process-events.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(json.dumps(row, ensure_ascii=False), flush=True)


record("DOMAIN_REUSED_NOT_RESET" if resume_existing else "FIXTURE_INITIALIZED_ONCE", scenario="S1_POS", current_integration_versions=[r["config_version"] for r in initial["integrations"]], note="Existing receipts, memories, control and checkpoint retained" if resume_existing else "Fresh fixture")
api = vite = None


def start_api():
    global api
    api = _start([sys.executable, "-X", "utf8", "-u", str(EVIDENCE / "acceptance_server.py"), "--host", "127.0.0.1", "--port", "8003"], ROOT, env, OUT / "api.log")
    _wait_http(api, "http://127.0.0.1:8003/api/health", OUT / "api.log")
    record("API_STARTED", launcher_pid=api.pid, git_sha=subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(), input_budget=int(env["OPSPILOT_CONTEXT_INPUT_BUDGET_TOKENS"]), database=str(DB.relative_to(ROOT)), checkpoints=str(CP.relative_to(ROOT)))


try:
    start_api()
    vite = _start_vite(5176, "http://127.0.0.1:8003", env, OUT / "vite.log")
    record("VITE_STARTED", launcher_pid=vite.pid, url="http://127.0.0.1:5176/")
    offset = commands.stat().st_size if resume_existing else 0
    while True:
        with commands.open("r", encoding="utf-8") as f:
            f.seek(offset)
            line = f.readline()
            if line and line.endswith("\n"):
                offset = f.tell()
            else:
                line = ""
        if not line:
            time.sleep(.05)
            continue
        command = json.loads(line)
        if command["command"] in {"restart", "begin_B"}:
            if command["command"] == "begin_B":
                env["OPSPILOT_CONTEXT_INPUT_BUDGET_TOKENS"] = "3600"
                record("B_FIXED_BUDGET_SELECTED", input_budget=3600, reason="Frozen SCOPE before experiment")
            record("TERMINATING_OWNED_API", launcher_pid=api.pid, reason=command.get("reason", command["command"]))
            _kill(api)
            record("OWNED_API_TERMINATED", launcher_pid=api.pid, returncode=api.returncode)
            start_api()
        elif command["command"] == "exit":
            break
finally:
    _kill(api)
    _kill(vite)
    record("OWNED_SERVICES_STOPPED")
