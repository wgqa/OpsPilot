from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest

from opspilot.domain.database import connect, reset_fixture


ROOT = Path(__file__).resolve().parents[1]
CHILD = ROOT / "tests" / "r1_user_demo_sse_child.py"
PASSWORD = "sse-test-support-password"
ORIGIN = "http://testserver"


def _start_api(
    tmp_path: Path, *, start_worker: bool = True,
) -> tuple[subprocess.Popen[str], Path, Path, Path, int]:
    db_path = tmp_path / "domain.sqlite3"
    checkpoint_path = tmp_path / "checkpoint.sqlite3"
    ready_path = tmp_path / "ready.json"
    stop_path = tmp_path / "shutdown.request"
    reset_fixture(db_path, "S1_POS")
    command = [sys.executable, str(CHILD), "--db", str(db_path), "--checkpoint", str(checkpoint_path),
               "--ready", str(ready_path), "--stop-request", str(stop_path)]
    if not start_worker:
        command.append("--no-worker")
    process = subprocess.Popen(
        command,
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    deadline = time.monotonic() + 15
    while not ready_path.exists() and process.poll() is None and time.monotonic() < deadline:
        time.sleep(0.05)
    assert ready_path.exists(), f"isolated API did not bind; rc={process.poll()}"
    port = int(json.loads(ready_path.read_text(encoding="utf-8"))["port"])
    return process, db_path, checkpoint_path, stop_path, port


def _client(port: int) -> tuple[httpx.Client, str, dict[str, str]]:
    client = httpx.Client(base_url=f"http://127.0.0.1:{port}", timeout=5)
    login = client.post(
        "/api/auth/login", headers={"Origin": ORIGIN},
        json={"actor_id": "support-a", "password": PASSWORD},
    )
    assert login.status_code == 200, login.text
    headers = {"Origin": ORIGIN, "X-CSRF-Token": login.json()["csrf_token"]}
    created = client.post("/api/sessions", headers=headers)
    assert created.status_code == 201, created.text
    return client, str(created.json()["session_id"]), headers


def _request_stop(process: subprocess.Popen[str], stop_path: Path, *, timeout: float = 6) -> tuple[float, str | None]:
    started = time.monotonic()
    stop_path.write_text("graceful-shutdown", encoding="ascii")
    elapsed = time.monotonic() - started
    try:
        process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        return time.monotonic() - started, None
    elapsed = time.monotonic() - started
    output = process.communicate(timeout=1)[0]
    assert process.returncode == 0, output
    return elapsed, output


def test_open_sse_streams_end_when_isolated_windows_api_shuts_down(tmp_path: Path) -> None:
    process, db_path, _checkpoint, stop_path, port_value = _start_api(tmp_path)
    port = port_value
    clients: list[httpx.Client] = []
    responses: list[httpx.Response] = []
    try:
        client, session_id, _headers = _client(port)
        clients.append(client)
        probe = client.send(client.build_request(
            "GET", f"/api/sessions/{session_id}/events?after=0", headers={"Origin": ORIGIN},
        ), stream=True)
        assert probe.status_code == 200 and b"id: 1" in next(probe.iter_bytes())
        probe.close()
        for _ in range(2):
            response = client.send(client.build_request(
                "GET", f"/api/sessions/{session_id}/events?after=0", headers={"Origin": ORIGIN},
            ), stream=True)
            responses.append(response)
            assert response.status_code == 200
            iterator = response.iter_bytes()
            first = next(iterator)
            assert b"id: 1" in first and b"SESSION_CREATED" in first
            heartbeat = next(iterator)
            assert b": heartbeat" in heartbeat
            setattr(response, "_sse_iterator", iterator)

        time.sleep(0.25)
        elapsed, output = _request_stop(process, stop_path)
        print(f"open_sse_shutdown_elapsed_seconds={elapsed:.3f}")
        if output is None:
            raise AssertionError(f"API remained alive {elapsed:.3f}s after shutdown while SSE clients stayed connected")
        print(output)
        assert elapsed < 5, f"SSE-held shutdown took {elapsed:.3f}s; expected prompt graceful close"
        for response in responses:
            assert list(response._sse_iterator) is not None
            assert response.is_closed
    finally:
        for response in responses:
            response.close()
        for client in clients:
            client.close()
        if process.poll() is None:
            # Test-only cleanup after an assertion/timeout: a normal client close
            # is expected to release the baseline stream before any termination fallback.
            stop_path.write_text("graceful-shutdown", encoding="ascii")
            try:
                process.wait(timeout=8)
            except subprocess.TimeoutExpired:
                process.terminate()
                process.wait(timeout=5)


def test_shutdown_without_sse_and_restart_preserve_session_event_cursor(tmp_path: Path) -> None:
    process, db_path, checkpoint_path, stop_path, port_value = _start_api(tmp_path, start_worker=False)
    port = port_value
    client, session_id, write_headers = _client(port)
    try:
        accepted = client.post(
            f"/api/sessions/{session_id}/messages",
            headers={**write_headers, "Idempotency-Key": "hf02-persisted-chat"},
            json={"body": "persist this committed offline message", "input_kind": "CHAT_READONLY"},
        )
        assert accepted.status_code == 202
        message_id = accepted.json()["message_id"]
        run_id = accepted.json()["run_id"]
        before = client.get(f"/api/sessions/{session_id}/events/history?after=0")
        assert before.status_code == 200
        original_ids = [int(item["event_seq"]) for item in before.json()["items"]]
        assert original_ids == [1, 2]
        elapsed, output = _request_stop(process, stop_path)
        print(f"idle_shutdown_elapsed_seconds={elapsed:.3f}")
        print(output)
        assert elapsed < 5
    finally:
        client.close()

    # Restart the same isolated DB and checkpoint without resetting either.
    ready_path = tmp_path / "ready-second.json"
    second_stop = tmp_path / "shutdown-second.request"
    process2 = subprocess.Popen(
        [sys.executable, str(CHILD), "--db", str(db_path), "--checkpoint", str(checkpoint_path),
         "--ready", str(ready_path), "--stop-request", str(second_stop), "--no-worker"],
        cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    try:
        deadline = time.monotonic() + 15
        while not ready_path.exists() and process2.poll() is None and time.monotonic() < deadline:
            time.sleep(0.05)
        assert ready_path.exists(), f"restart failed; rc={process2.poll()}"
        port2 = int(json.loads(ready_path.read_text(encoding="utf-8"))["port"])
        resumed = httpx.Client(base_url=f"http://127.0.0.1:{port2}", timeout=5)
        try:
            # The existing persisted auth session survives process restart.
            resumed.cookies.update(client.cookies)
            me = resumed.get("/api/auth/me")
            assert me.status_code == 200 and me.json()["actor_id"] == "support-a"
            session = resumed.get(f"/api/sessions/{session_id}")
            assert session.status_code == 200
            messages = resumed.get(f"/api/sessions/{session_id}/messages")
            assert messages.status_code == 200
            assert any(item["message_id"] == message_id for item in messages.json()["items"])
            run = resumed.get(f"/api/runs/{run_id}")
            assert run.status_code == 200 and run.json()["status"] == "QUEUED"
            replay = resumed.get(
                f"/api/sessions/{session_id}/events/history?after=999",
                headers={"Last-Event-ID": "0"},
            )
            assert replay.status_code == 200
            assert replay.json()["cursor_source"] == "Last-Event-ID"
            assert [int(item["event_seq"]) for item in replay.json()["items"]] == original_ids

            owner_b = httpx.Client(base_url=f"http://127.0.0.1:{port2}", timeout=5)
            try:
                other_login = owner_b.post(
                    "/api/auth/login", headers={"Origin": ORIGIN},
                    json={"actor_id": "support-b", "password": "sse-test-support-b-password"},
                )
                assert other_login.status_code == 200
                denied = owner_b.get(f"/api/sessions/{session_id}/events", headers={"Origin": ORIGIN})
                assert denied.status_code == 404
            finally:
                owner_b.close()

            stream = resumed.send(resumed.build_request(
                "GET", f"/api/sessions/{session_id}/events?after=999",
                headers={"Origin": ORIGIN, "Last-Event-ID": "0"},
            ), stream=True)
            try:
                assert stream.status_code == 200
                assert b"id: 1" in next(stream.iter_bytes())
            finally:
                stream.close()
        finally:
            resumed.close()
    finally:
        if process2.poll() is None:
            second_stop.write_text("graceful-shutdown", encoding="ascii")
            try:
                process2.wait(timeout=35)
            except subprocess.TimeoutExpired:
                process2.terminate()
                process2.wait(timeout=5)

    with connect(db_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM sessions WHERE session_id=?", (session_id,)).fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM session_events WHERE session_id=?", (session_id,)).fetchone()[0] == 2
        assert connection.execute("SELECT COUNT(*) FROM messages WHERE session_id=?", (session_id,)).fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM task_runs WHERE session_id=?", (session_id,)).fetchone()[0] == 1
