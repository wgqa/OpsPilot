from __future__ import annotations

import importlib
import json
import os
import sqlite3
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from opspilot.domain.d2 import (
    finish_attempt,
    get_scope_authz_facts_fact,
    probe_endpoint_fact,
    record_tool_observation,
    reserve_attempt,
)
from opspilot.domain.database import connect, reset_fixture
from opspilot.domain.s2_diagnosis import create_diagnosis_receipt, freeze_handoff_draft
from opspilot.domain.task_control import (
    abort_task,
    admit_task_message,
    apply_pending_critical_inputs,
    claim_task_run,
    create_session,
    create_task_with_initial_run,
    finish_task_run,
    trusted_identity,
)


PASSWORDS = {
    "support-a": "support-test-password",
    "approver-a": "approver-test-password",
    "support-b": "support-b-test-password",
    "approver-b": "approver-b-test-password",
}
ORIGIN = "http://testserver"


def test_m203_migration_from_v7_is_additive_and_idempotent(demo_db: Path) -> None:
    from opspilot.domain.database import initialize

    with connect(demo_db) as connection:
        connection.execute("DROP TABLE s2_handoff_receipts")
        connection.execute("DROP TABLE s2_handoff_queue_entries")
        connection.execute("PRAGMA user_version = 7")
    initialize(demo_db)
    initialize(demo_db)
    with connect(demo_db) as connection:
        assert int(connection.execute("PRAGMA user_version").fetchone()[0]) == 8
        tables = {str(row["name"]) for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'",
        ).fetchall()}
    assert {"s2_handoff_queue_entries", "s2_handoff_receipts"} <= tables


def _install_scope_write_audit(db: Path) -> None:
    with connect(db) as connection:
        connection.execute("CREATE TABLE IF NOT EXISTS m203_scope_write_audit (table_name TEXT, operation TEXT)")
        connection.execute("DELETE FROM m203_scope_write_audit")
        for table in ("principal_scope_grants", "route_scope_policies"):
            for operation, suffix in (("INSERT", "ins"), ("UPDATE", "upd"), ("DELETE", "del")):
                connection.execute(
                    f"CREATE TRIGGER IF NOT EXISTS m203_audit_{table}_{suffix} AFTER {operation} ON {table} "
                    f"BEGIN INSERT INTO m203_scope_write_audit VALUES ('{table}', '{operation}'); END"
                )


def _make_ready_draft(db: Path, live_api: str, prefix: str) -> dict[str, object]:
    """Prepare a real same-Run 403 + authz diagnosis and frozen current draft."""
    reset_fixture(db, "S2_SCOPE_DENIED")
    identity = trusted_identity(db, "support-a")
    session_id = str(create_session(db, identity)["session_id"])
    created = create_task_with_initial_run(
        db,
        identity,
        session_id=session_id,
        service_id="orders-demo",
        integration_id="integration-a",
        ticket_id=f"{prefix}-001",
        initial_message="订单查询 API 返回 403，请核实当前授权事实。",
        idempotency_key=f"{prefix}-task",
    )
    task_id, run_id = str(created["task_id"]), str(created["run_id"])
    claim_task_run(db, identity, run_id)
    apply_pending_critical_inputs(db, identity, run_id)

    probe = probe_endpoint_fact(db, task_id, "orders-demo", "integration-a", live_api)
    assert probe["facts"]["http_status"] == 403
    probe_call = f"{prefix}-probe"
    probe_attempt, _ = reserve_attempt(
        db, task_id, "MCP", 6, call_id=probe_call, tool_call_id=f"{prefix}-probe-tool",
        tool_name="probe_endpoint", argument_digest=f"{prefix}-probe-args", run_id=run_id,
    )
    finish_attempt(db, probe_attempt, "OK")
    probe_observation = record_tool_observation(
        db, task_id=task_id, call_id=probe_call, attempt_id=probe_attempt,
        tool_call_id=f"{prefix}-probe-tool", tool_name="probe_endpoint",
        arguments={"service_id": "orders-demo", "integration_id": "integration-a"},
        status="OK", result=probe,
    )

    request_id = str(probe["facts"]["request_id"])
    authz = get_scope_authz_facts_fact(db, task_id, request_id)
    authz_call = f"{prefix}-authz"
    authz_attempt, _ = reserve_attempt(
        db, task_id, "MCP", 6, call_id=authz_call, tool_call_id=f"{prefix}-authz-tool",
        tool_name="get_scope_authz_facts", argument_digest=f"{prefix}-authz-args", run_id=run_id,
    )
    finish_attempt(db, authz_attempt, "OK")
    authz_observation = record_tool_observation(
        db, task_id=task_id, call_id=authz_call, attempt_id=authz_attempt,
        tool_call_id=f"{prefix}-authz-tool", tool_name="get_scope_authz_facts",
        arguments={"request_id": request_id}, status="OK", result=authz,
    )

    receipt = create_diagnosis_receipt(
        db,
        task_id=task_id,
        run_id=run_id,
        evidence_ids=[str(probe_observation["evidence_id"]), str(authz_observation["evidence_id"])],
    )
    draft = freeze_handoff_draft(db, task_id=task_id, receipt_id=str(receipt["receipt_id"]))
    finish_task_run(db, identity, run_id, "SUCCEEDED")
    _install_scope_write_audit(db)
    with connect(db) as connection:
        control_revision = int(connection.execute(
            "SELECT control_revision FROM task_controls WHERE task_id = ?", (task_id,),
        ).fetchone()[0])
    return {
        "identity": identity,
        "session_id": session_id,
        "task_id": task_id,
        "run_id": run_id,
        "receipt": receipt,
        "draft": draft,
        "control_revision": control_revision,
    }


def _domain_module():
    return importlib.import_module("opspilot.domain.s2_handoff")


def _submit(db: Path, ready: dict[str, object], operation_id: str, **overrides: object) -> dict[str, object]:
    module = _domain_module()
    draft = ready["draft"]
    assert isinstance(draft, dict)
    request = {
        "operation_id": operation_id,
        "draft_id": draft["draft_id"],
        "draft_digest": draft["content_digest"],
        "expected_control_revision": ready["control_revision"],
        "handoff_kind": "SCOPE_REVIEW",
    }
    request.update(overrides)
    return module.submit_s2_handoff(
        db,
        ready["identity"],
        task_id=str(ready["task_id"]),
        **request,
    )


def _counts(db: Path, task_id: str) -> dict[str, int]:
    with connect(db) as connection:
        tables = {str(row["name"]) for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'",
        ).fetchall()}
        result = {"queue": 0, "receipts": 0, "submit_outbox": 0, "commands": 0, "scope_writes": 0}
        if "s2_handoff_queue_entries" in tables:
            result["queue"] = int(connection.execute(
                "SELECT COUNT(*) FROM s2_handoff_queue_entries WHERE task_id = ?", (task_id,),
            ).fetchone()[0])
        if "s2_handoff_receipts" in tables:
            result["receipts"] = int(connection.execute(
                "SELECT COUNT(*) FROM s2_handoff_receipts WHERE task_id = ?", (task_id,),
            ).fetchone()[0])
        result["submit_outbox"] = int(connection.execute(
            "SELECT COUNT(*) FROM domain_outbox WHERE task_id = ? AND event_kind = 'S2_HANDOFF_ACCEPTED'",
            (task_id,),
        ).fetchone()[0])
        result["commands"] = int(connection.execute(
            "SELECT COUNT(*) FROM commands WHERE tenant_id = 'tenant-a' AND target_ref = ? AND command_kind = 'S2_HANDOFF_SUBMIT'",
            (f"{task_id}:SCOPE_REVIEW",),
        ).fetchone()[0])
        # These test-only triggers count attempted writes, not just final values.
        if "m203_scope_write_audit" in tables:
            result["scope_writes"] = int(connection.execute(
                "SELECT COUNT(*) FROM m203_scope_write_audit",
            ).fetchone()[0])
        return result


def test_m203_03_explicit_domain_submit_commits_one_queue_receipt_outbox_and_never_grants_scope(
    demo_db: Path, live_api: str,
) -> None:
    ready = _make_ready_draft(demo_db, live_api, "m203-03")
    result = _submit(demo_db, ready, "m203-operation-03")

    assert result["status"] == "ACCEPTED"
    assert result["business_outcome"] == "SCOPE_ESCALATED"
    assert result["scope_authorized"] is False and result["recovered"] is False
    assert result["handoff_status"] == "PENDING_REVIEW"
    assert _counts(demo_db, str(ready["task_id"])) == {
        "queue": 1, "receipts": 1, "submit_outbox": 1, "commands": 1, "scope_writes": 0,
    }
    from opspilot.domain.s2_diagnosis import get_s2_task_outcome

    outcome = get_s2_task_outcome(demo_db, str(ready["task_id"]))
    assert outcome["business_outcome"] == "SCOPE_ESCALATED"
    assert outcome["submitted"] is True and outcome["scope_authorized"] is False
    assert outcome["recovered"] is False and outcome["task_status"] == "COMPLETED"
    with pytest.raises(sqlite3.IntegrityError):
        with connect(demo_db) as connection:
            connection.execute(
                "UPDATE s2_handoff_receipts SET receipt_digest = ? WHERE task_id = ?",
                ("0" * 64, ready["task_id"]),
            )


def test_m203_04_lost_response_replay_returns_same_immutable_receipt(
    demo_db: Path, live_api: str,
) -> None:
    ready = _make_ready_draft(demo_db, live_api, "m203-04")
    first = _submit(demo_db, ready, "m203-operation-04")
    replay = _submit(demo_db, ready, "m203-operation-04")

    assert first["receipt_id"] == replay["receipt_id"]
    assert replay["replayed"] is True
    assert _counts(demo_db, str(ready["task_id"]))["queue"] == 1
    assert _counts(demo_db, str(ready["task_id"]))["receipts"] == 1
    assert _counts(demo_db, str(ready["task_id"]))["submit_outbox"] == 1


def test_m203_06_different_operation_ids_return_same_business_receipt_without_duplicate_entry(
    demo_db: Path, live_api: str,
) -> None:
    ready = _make_ready_draft(demo_db, live_api, "m203-06-sequential")
    first = _submit(demo_db, ready, "m203-operation-06-a")
    second = _submit(demo_db, ready, "m203-operation-06-b")
    assert first["receipt_id"] == second["receipt_id"]
    assert second["replayed"] is True
    assert _counts(demo_db, str(ready["task_id"])) == {
        "queue": 1, "receipts": 1, "submit_outbox": 1, "commands": 2, "scope_writes": 0,
    }


def test_m203_06_two_os_processes_racing_one_business_key_create_one_receipt(
    demo_db: Path, live_api: str, tmp_path: Path,
) -> None:
    ready = _make_ready_draft(demo_db, live_api, "m203-06-process")
    task_id = str(ready["task_id"])
    draft = ready["draft"]
    assert isinstance(draft, dict)
    go = tmp_path / "race.go"
    worker = Path(__file__).with_name("m2_03_handoff_worker.py")
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1])
    commands = []
    processes: list[subprocess.Popen[str]] = []
    for suffix in ("a", "b"):
        operation_id = f"m203-process-{suffix}"
        ready_file = tmp_path / f"race.{suffix}.ready"
        result_file = tmp_path / f"race.{suffix}.json"
        command = [
            sys.executable, str(worker), str(demo_db), task_id,
            str(draft["draft_id"]), str(draft["content_digest"]),
            str(ready["control_revision"]), operation_id, str(go),
            str(ready_file), str(result_file),
        ]
        commands.append((ready_file, result_file))
        processes.append(subprocess.Popen(
            command, cwd=Path(__file__).resolve().parents[1], env=env,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        ))
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline and not all(path.exists() for path, _ in commands):
        time.sleep(0.02)
    assert all(path.exists() for path, _ in commands), "worker processes did not reach the race barrier"
    go.write_text("go", encoding="utf-8")
    outputs = [process.communicate(timeout=20)[0] for process in processes]
    assert all(process.returncode == 0 for process in processes), outputs
    results = [json.loads(result_file.read_text(encoding="utf-8")) for _, result_file in commands]
    assert all(result.get("ok") for result in results), outputs
    assert len({result["receipt_id"] for result in results}) == 1
    assert _counts(demo_db, task_id) == {
        "queue": 1, "receipts": 1, "submit_outbox": 1, "commands": 2, "scope_writes": 0,
    }


def test_m203_05_same_operation_with_changed_payload_is_rejected_without_side_effects(
    demo_db: Path, live_api: str,
) -> None:
    ready = _make_ready_draft(demo_db, live_api, "m203-05")
    _submit(demo_db, ready, "m203-operation-05")
    module = _domain_module()
    draft = ready["draft"]
    assert isinstance(draft, dict)
    with pytest.raises(Exception) as error:
        module.submit_s2_handoff(
            demo_db,
            ready["identity"],
            task_id=str(ready["task_id"]),
            operation_id="m203-operation-05",
            draft_id=str(draft["draft_id"]),
            draft_digest="0" * 64,
            expected_control_revision=int(ready["control_revision"]),
            handoff_kind="SCOPE_REVIEW",
        )
    assert getattr(error.value, "code", None) == "IDEMPOTENCY_CONFLICT"
    assert _counts(demo_db, str(ready["task_id"]))["queue"] == 1
    assert _counts(demo_db, str(ready["task_id"]))["receipts"] == 1
    assert _counts(demo_db, str(ready["task_id"]))["submit_outbox"] == 1


def test_m203_07_current_policy_change_invalidates_frozen_draft_before_handoff(
    demo_db: Path, live_api: str,
) -> None:
    ready = _make_ready_draft(demo_db, live_api, "m203-07")
    with connect(demo_db) as connection:
        connection.execute(
            "UPDATE route_scope_policies SET scope_policy_version = scope_policy_version + 1 "
            "WHERE tenant_id = 'tenant-a' AND service_id = 'orders-demo' AND route = '/api/orders/demo-order'",
        )

    with pytest.raises(Exception) as error:
        _submit(demo_db, ready, "m203-operation-07")
    assert getattr(error.value, "code", None) == "DRAFT_STALE"
    counts = _counts(demo_db, str(ready["task_id"]))
    assert counts["queue"] == counts["receipts"] == counts["submit_outbox"] == 0


@pytest.mark.parametrize("change", ["grant", "principal", "probe_ttl"])
def test_m203_07_grant_principal_or_expired_probe_invalidates_original_draft(
    demo_db: Path, live_api: str, change: str,
) -> None:
    ready = _make_ready_draft(demo_db, live_api, f"m203-07-{change}")
    with connect(demo_db) as connection:
        if change == "grant":
            connection.execute(
                "UPDATE principal_scope_grants SET grant_version = grant_version + 1 "
                "WHERE tenant_id = 'tenant-a' AND principal_id = 'principal-a'",
            )
        elif change == "principal":
            connection.execute(
                "UPDATE principals SET status = 'DISABLED', principal_version = principal_version + 1 "
                "WHERE tenant_id = 'tenant-a' AND principal_id = 'principal-a'",
            )
        else:
            connection.execute(
                "UPDATE d2_tool_observations SET created_at = '2000-01-01T00:00:00+00:00' "
                "WHERE task_id = ? AND tool_name = 'probe_endpoint'",
                (ready["task_id"],),
            )
    with pytest.raises(Exception) as error:
        _submit(demo_db, ready, f"m203-operation-07-{change}")
    assert getattr(error.value, "code", None) == "DRAFT_STALE"
    counts = _counts(demo_db, str(ready["task_id"]))
    assert counts["queue"] == counts["receipts"] == counts["submit_outbox"] == counts["commands"] == 0


def test_m203_08_critical_correction_wins_before_submit_and_invalidates_old_revision(
    demo_db: Path, live_api: str,
) -> None:
    ready = _make_ready_draft(demo_db, live_api, "m203-08-correction-first")
    admit_task_message(
        demo_db, ready["identity"], session_id=str(ready["session_id"]),
        task_id=str(ready["task_id"]), input_kind="CORRECT_TASK_INPUT",
        body="正式更正：以新的受信调查结论重新核对请求关联。",
        idempotency_key="m203-08-correction",
    )
    with pytest.raises(Exception) as error:
        _submit(demo_db, ready, "m203-operation-08-correction")
    assert getattr(error.value, "code", None) in {"TASK_INPUT_PENDING", "TASK_CONTROL_STALE", "TASK_RUN_BUSY"}
    counts = _counts(demo_db, str(ready["task_id"]))
    assert counts["queue"] == counts["receipts"] == counts["submit_outbox"] == 0


def test_m203_08_abort_wins_before_submit_and_post_handoff_abort_cannot_erase_receipt(
    demo_db: Path, live_api: str,
) -> None:
    ready = _make_ready_draft(demo_db, live_api, "m203-08-abort-first")
    abort_task(
        demo_db, ready["identity"], task_id=str(ready["task_id"]),
        reason="stop before handoff", idempotency_key="m203-08-abort",
    )
    with pytest.raises(Exception) as error:
        _submit(demo_db, ready, "m203-operation-08-abort")
    assert getattr(error.value, "code", None) == "TASK_ABORTED"
    assert _counts(demo_db, str(ready["task_id"]))["queue"] == 0

    ready_after = _make_ready_draft(demo_db, live_api, "m203-08-handoff-first")
    committed = _submit(demo_db, ready_after, "m203-operation-08-handoff-first")
    aborted = abort_task(
        demo_db, ready_after["identity"], task_id=str(ready_after["task_id"]),
        reason="abort after receipt", idempotency_key="m203-08-abort-after",
    )
    assert aborted["error_code"] == "TASK_ALREADY_TERMINAL"
    assert _counts(demo_db, str(ready_after["task_id"]))["receipts"] == 1
    outcome = _domain_module().get_s2_handoff_outcome(demo_db, str(ready_after["task_id"]))
    assert outcome is not None and outcome["handoff_receipt"]["receipt_id"] == committed["receipt_id"]


def test_m203_11_precommit_failure_points_roll_back_and_postcommit_loss_replays(
    demo_db: Path, live_api: str, monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _domain_module()
    for point in ("after_command_before_queue", "after_queue_before_receipt", "after_receipt_before_outbox"):
        ready = _make_ready_draft(demo_db, live_api, f"m203-11-{point}")

        def fail_at(actual: str, expected: str = point) -> None:
            if actual == expected:
                raise RuntimeError(f"injected:{actual}")

        monkeypatch.setattr(module, "_M2_03_TEST_FAILPOINT", fail_at)
        with pytest.raises(RuntimeError, match=f"injected:{point}"):
            _submit(demo_db, ready, f"m203-operation-{point}")
        assert _counts(demo_db, str(ready["task_id"])) == {
            "queue": 0, "receipts": 0, "submit_outbox": 0, "commands": 0, "scope_writes": 0,
        }
        monkeypatch.setattr(module, "_M2_03_TEST_FAILPOINT", None)
        replay = _submit(demo_db, ready, f"m203-operation-{point}")
        assert replay["replayed"] is False
        assert _counts(demo_db, str(ready["task_id"]))["receipts"] == 1

    ready = _make_ready_draft(demo_db, live_api, "m203-11-postcommit")

    def lose_response(actual: str) -> None:
        if actual == "after_commit_before_http_response":
            raise RuntimeError("injected:lost-response")

    monkeypatch.setattr(module, "_M2_03_TEST_FAILPOINT", lose_response)
    with pytest.raises(RuntimeError, match="lost-response"):
        _submit(demo_db, ready, "m203-operation-postcommit")
    monkeypatch.setattr(module, "_M2_03_TEST_FAILPOINT", None)
    recovered = _submit(demo_db, ready, "m203-operation-postcommit")
    assert recovered["replayed"] is True
    assert _counts(demo_db, str(ready["task_id"])) == {
        "queue": 1, "receipts": 1, "submit_outbox": 1, "commands": 1, "scope_writes": 0,
    }


def test_m203_13_after_72_hours_is_derived_read_only_and_receipt_digest_is_stable(
    demo_db: Path, live_api: str,
) -> None:
    ready = _make_ready_draft(demo_db, live_api, "m203-13")
    accepted = _submit(demo_db, ready, "m203-operation-13")
    before = _domain_module().get_s2_handoff_outcome(demo_db, str(ready["task_id"]))
    assert before is not None
    accepted_at = datetime.fromisoformat(str(accepted["received_at"]))
    overdue = _domain_module().get_s2_handoff_outcome(
        demo_db, str(ready["task_id"]), now=accepted_at + timedelta(hours=72),
    )
    after = _domain_module().get_s2_handoff_outcome(demo_db, str(ready["task_id"]))
    assert overdue is not None and overdue["handoff_status"] == "OVERDUE"
    assert after is not None
    assert before["handoff_receipt"]["receipt_digest"] == after["handoff_receipt"]["receipt_digest"]
    assert before["queue_entry"]["status"] == after["queue_entry"]["status"] == "PENDING_REVIEW"
    assert _counts(demo_db, str(ready["task_id"]))["queue"] == 1


def test_m203_09_real_web_route_requires_owner_and_exposes_submit_operation(
    demo_db: Path, live_api: str,
) -> None:
    ready = _make_ready_draft(demo_db, live_api, "m203-09")
    module = importlib.import_module("opspilot.web.app")
    app = module.create_app(
        db_path=demo_db,
        start_worker=False,
        credentials=PASSWORDS,
        expected_origin=ORIGIN,
    )
    with TestClient(app, raise_server_exceptions=False) as client:
        login = client.post(
            "/api/auth/login",
            headers={"Origin": ORIGIN},
            json={"actor_id": "support-a", "password": PASSWORDS["support-a"]},
        )
        assert login.status_code == 200
        headers = {
            "Origin": ORIGIN,
            "X-CSRF-Token": login.json()["csrf_token"],
            "Idempotency-Key": "m203-operation-web-09",
        }
        task_id = str(ready["task_id"])
        handoff = client.get(f"/api/tasks/{task_id}/handoff")
        assert handoff.status_code == 200, handoff.text
        draft = ready["draft"]
        assert isinstance(draft, dict)
        response = client.post(
            f"/api/tasks/{task_id}/handoff/submit",
            headers=headers,
            json={
                "operation_id": "m203-operation-web-09",
                "draft_id": draft["draft_id"],
                "draft_digest": draft["content_digest"],
                "expected_control_revision": ready["control_revision"],
                "handoff_kind": "SCOPE_REVIEW",
            },
        )
        assert response.status_code == 202, response.text
        assert response.json()["business_outcome"] == "SCOPE_ESCALATED"
        receipt_id = response.json()["receipt_id"]
        replay = client.post(
            f"/api/tasks/{task_id}/handoff/submit",
            headers=headers,
            json={
                "operation_id": "m203-operation-web-09",
                "draft_id": draft["draft_id"],
                "draft_digest": draft["content_digest"],
                "expected_control_revision": ready["control_revision"],
                "handoff_kind": "SCOPE_REVIEW",
            },
        )
        assert replay.status_code == 200 and replay.json()["replayed"] is True
        assert replay.json()["receipt_id"] == receipt_id

        altered = client.post(
            f"/api/tasks/{task_id}/handoff/submit",
            headers={**headers, "Idempotency-Key": "m203-operation-web-09-other"},
            json={
                "operation_id": "m203-operation-web-09-other",
                "draft_id": draft["draft_id"],
                "draft_digest": "0" * 64,
                "expected_control_revision": ready["control_revision"],
                "handoff_kind": "SCOPE_REVIEW",
            },
        )
        assert altered.status_code == 409 and altered.json() == {"code": "QUEUE_ALREADY_ACCEPTED"}

        extra_field = client.post(
            f"/api/tasks/{task_id}/handoff/submit",
            headers={**headers, "Idempotency-Key": "m203-operation-web-extra"},
            json={
                "operation_id": "m203-operation-web-extra",
                "draft_id": draft["draft_id"],
                "draft_digest": draft["content_digest"],
                "expected_control_revision": ready["control_revision"],
                "handoff_kind": "SCOPE_REVIEW",
                "receiver": "attacker-controlled",
            },
        )
        assert extra_field.status_code == 422 and extra_field.json() == {"code": "INVALID_REQUEST"}
        mismatch = client.post(
            f"/api/tasks/{task_id}/handoff/submit",
            headers={**headers, "Idempotency-Key": "different-key"},
            json={
                "operation_id": "m203-operation-web-mismatch",
                "draft_id": draft["draft_id"],
                "draft_digest": draft["content_digest"],
                "expected_control_revision": ready["control_revision"],
                "handoff_kind": "SCOPE_REVIEW",
            },
        )
        assert mismatch.status_code == 422 and mismatch.json() == {"code": "IDEMPOTENCY_KEY_MISMATCH"}

        forbidden_origin = client.post(
            f"/api/tasks/{task_id}/handoff/submit",
            headers={**headers, "Origin": "http://evil.example"},
            json={
                "operation_id": "m203-operation-web-origin",
                "draft_id": draft["draft_id"],
                "draft_digest": draft["content_digest"],
                "expected_control_revision": ready["control_revision"],
                "handoff_kind": "SCOPE_REVIEW",
            },
        )
        assert forbidden_origin.status_code == 403
        forbidden_csrf = client.post(
            f"/api/tasks/{task_id}/handoff/submit",
            headers={**headers, "X-CSRF-Token": "invalid"},
            json={
                "operation_id": "m203-operation-web-csrf",
                "draft_id": draft["draft_id"],
                "draft_digest": draft["content_digest"],
                "expected_control_revision": ready["control_revision"],
                "handoff_kind": "SCOPE_REVIEW",
            },
        )
        assert forbidden_csrf.status_code == 403

        # A natural-language chat message remains read-only and cannot enqueue work.
        chat = client.post(
            f"/api/sessions/{ready['session_id']}/messages",
            headers={**headers, "Idempotency-Key": "m203-chat-says-submit"},
            json={"body": "好的，提交吧", "task_id": task_id, "input_kind": "CHAT_READONLY"},
        )
        assert chat.status_code == 202, chat.text

        approver = TestClient(app, raise_server_exceptions=False)
        support_b = TestClient(app, raise_server_exceptions=False)
        try:
            approver_headers = {
                **_login_for_test(approver, "approver-a"),
                "Idempotency-Key": "m203-operation-approver",
            }
            denied_approver = approver.post(
                f"/api/tasks/{task_id}/handoff/submit",
                headers=approver_headers,
                json={
                    "operation_id": "m203-operation-approver",
                    "draft_id": draft["draft_id"],
                    "draft_digest": draft["content_digest"],
                    "expected_control_revision": ready["control_revision"],
                    "handoff_kind": "SCOPE_REVIEW",
                },
            )
            assert denied_approver.status_code == 403
            support_b_headers = {
                **_login_for_test(support_b, "support-b"),
                "Idempotency-Key": "m203-operation-cross-tenant",
            }
            denied_cross_tenant = support_b.post(
                f"/api/tasks/{task_id}/handoff/submit",
                headers=support_b_headers,
                json={
                    "operation_id": "m203-operation-cross-tenant",
                    "draft_id": draft["draft_id"],
                    "draft_digest": draft["content_digest"],
                    "expected_control_revision": ready["control_revision"],
                    "handoff_kind": "SCOPE_REVIEW",
                },
            )
            assert denied_cross_tenant.status_code == 403
            assert support_b.get(f"/api/tasks/{task_id}/handoff").status_code == 404
        finally:
            approver.close()
            support_b.close()
        final_handoff = client.get(f"/api/tasks/{task_id}/handoff")
        assert final_handoff.status_code == 200
        assert final_handoff.json()["handoff_receipt"]["receipt_id"] == receipt_id
        assert _counts(demo_db, task_id) == {
            "queue": 1, "receipts": 1, "submit_outbox": 1, "commands": 1, "scope_writes": 0,
        }


def _login_for_test(client: TestClient, actor_id: str) -> dict[str, str]:
    response = client.post(
        "/api/auth/login",
        headers={"Origin": ORIGIN},
        json={"actor_id": actor_id, "password": PASSWORDS[actor_id]},
    )
    assert response.status_code == 200, response.text
    return {"Origin": ORIGIN, "X-CSRF-Token": response.json()["csrf_token"]}
