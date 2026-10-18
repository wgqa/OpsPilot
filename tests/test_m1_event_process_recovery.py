from __future__ import annotations

import json
import os
import secrets
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx

from opspilot.domain.database import connect


ROOT = Path(__file__).resolve().parents[1]


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _kill_tree(process: subprocess.Popen) -> None:
    if process.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False,
        )
    else:
        process.kill()
    process.wait(timeout=15)


def test_n2_01_committed_repair_event_replays_after_commit_process_death(
    demo_db: Path, tmp_path: Path
) -> None:
    commit_script = Path(__file__).with_name("m1_repair_commit_process.py")
    committed = subprocess.run(
        [sys.executable, "-X", "utf8", str(commit_script), str(demo_db)],
        cwd=ROOT, capture_output=True, text=True, encoding="utf-8", timeout=60,
    )
    assert committed.returncode == 0, committed.stderr
    commit_event = json.loads(committed.stdout.strip().splitlines()[-1])
    assert commit_event["status"] == "COMMITTED"
    assert commit_event["before_version"] == 7 and commit_event["after_version"] == 8
    assert commit_event["config_version"] == 8
    assert commit_event["durable_repair_event_count_before_process_exit"] == 1

    port = _free_port()
    origin = f"http://127.0.0.1:{port}"
    credentials = {
        "OPSPILOT_DB_PATH": str(demo_db),
        "OPSPILOT_CHECKPOINT_DB_PATH": str(tmp_path / "restart-checkpoint.sqlite3"),
        "OPSPILOT_WEB_ORIGIN": origin,
        "OPSPILOT_WEB_SUPPORT_PASSWORD": secrets.token_urlsafe(24),
        "OPSPILOT_WEB_APPROVER_PASSWORD": secrets.token_urlsafe(24),
        "OPSPILOT_WEB_SUPPORT_B_PASSWORD": secrets.token_urlsafe(24),
        "OPSPILOT_WEB_APPROVER_B_PASSWORD": secrets.token_urlsafe(24),
        "PYTHONUTF8": "1",
    }
    environment = os.environ.copy()
    environment.update(credentials)
    server_log = (tmp_path / "event-replay-server.log").open("w", encoding="utf-8")
    server = subprocess.Popen(
        [sys.executable, "-X", "utf8", "-u", "-m", "opspilot.web.server",
         "--host", "127.0.0.1", "--port", str(port)],
        cwd=ROOT, env=environment, stdout=server_log, stderr=subprocess.STDOUT,
    )
    try:
        end = time.monotonic() + 15
        while time.monotonic() < end:
            if server.poll() is not None:
                raise AssertionError(f"replay server exited with code {server.returncode}")
            try:
                ready = httpx.get(f"{origin}/api/health", timeout=0.5)
                if ready.status_code == 200:
                    break
            except httpx.HTTPError:
                time.sleep(0.05)
        else:
            raise AssertionError("replay server readiness timeout")

        with httpx.Client(base_url=origin, timeout=5.0) as client:
            login = client.post(
                "/api/auth/login", headers={"Origin": origin},
                json={"actor_id": "support-a", "password": credentials["OPSPILOT_WEB_SUPPORT_PASSWORD"]},
            )
            assert login.status_code == 200
            history = client.get(
                f"/api/sessions/{commit_event['session_id']}/events/history?after=0",
                headers={"Last-Event-ID": "0"},
            )
            assert history.status_code == 200
            repair_events = [
                item for item in history.json()["items"]
                if item["event_kind"] == "REPAIR_COMMITTED"
                and item["source_id"] == commit_event["action_id"]
            ]
            assert len(repair_events) == 1
            assert repair_events[0]["payload"]["action_id"] == commit_event["action_id"]
            assert "fixture-a-current-secret" not in history.text
            with connect(demo_db) as connection:
                action_counts = {
                    "intent": connection.execute(
                        "SELECT COUNT(*) FROM d3_action_intents WHERE action_id = ?",
                        (commit_event["action_id"],),
                    ).fetchone()[0],
                    "ledger": connection.execute(
                        "SELECT COUNT(*) FROM d3_action_ledgers WHERE action_id = ? AND status='COMMITTED'",
                        (commit_event["action_id"],),
                    ).fetchone()[0],
                    "repair_event": connection.execute(
                        "SELECT COUNT(*) FROM session_events WHERE source_kind='ACTION_LEDGER' AND source_id=? AND event_kind='REPAIR_COMMITTED'",
                        (commit_event["action_id"],),
                    ).fetchone()[0],
                    "config_version": connection.execute(
                        "SELECT config_version FROM integrations WHERE tenant_id='tenant-a' AND integration_id='integration-a'"
                    ).fetchone()[0],
                }
            assert action_counts == {"intent": 1, "ledger": 1, "repair_event": 1, "config_version": 8}
            print("M1_EVIDENCE " + json.dumps({
                "case": "N2-01", "commit_process_pid": commit_event["pid"],
                "new_api_process_pid": server.pid, "repair_action_id": commit_event["action_id"],
                "http_status": history.status_code, "replayed_event_count": len(repair_events),
                "action_counts_after_restart": action_counts,
                "repair_event_payload": repair_events[0]["payload"],
            }, sort_keys=True))
    finally:
        _kill_tree(server)
        server_log.flush()
        server_log.close()
