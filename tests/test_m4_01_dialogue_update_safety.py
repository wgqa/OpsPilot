from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from opspilot.domain.database import connect
from opspilot.web.app import create_app
from tests.test_m4_01_dialogue_updates import (
    ORIGIN,
    PASSWORDS,
    _assess,
    _counts,
    _install_classifier,
    _login,
    _new_task,
    _send_chat,
    m4_client,
)


def _security_snapshot(db: Path, task_id: str) -> dict[str, Any]:
    with connect(db) as connection:
        tables = {
            "binding": "SELECT b.tenant_id, b.task_id, b.service_id, b.integration_id, b.principal_id, s.route FROM task_bindings b JOIN services s ON s.tenant_id = b.tenant_id AND s.service_id = b.service_id WHERE b.task_id = ?",
            "integration": "SELECT tenant_id, integration_id, principal_id, credential_ref, config_version FROM integrations WHERE tenant_id = 'tenant-a' AND integration_id = 'integration-a'",
            "principal": "SELECT tenant_id, principal_id, status, principal_version FROM principals WHERE tenant_id = 'tenant-a' AND principal_id = 'principal-a'",
            "policy": "SELECT tenant_id, service_id, accepted_credential_ref, policy_version FROM auth_policies WHERE tenant_id = 'tenant-a' AND service_id = 'orders-demo'",
            "grant": "SELECT tenant_id, principal_id, granted_scopes_json, grant_version FROM principal_scope_grants WHERE tenant_id = 'tenant-a' AND principal_id = 'principal-a'",
            "route_policy": "SELECT tenant_id, service_id, route, required_scopes_json, scope_policy_version FROM route_scope_policies WHERE tenant_id = 'tenant-a' AND service_id = 'orders-demo'",
        }
        result = {key: tuple(connection.execute(sql, (task_id,)).fetchone()) if "?" in sql else tuple(connection.execute(sql).fetchone())
                  for key, sql in tables.items()}
        result["counts"] = _counts(db, task_id)
        return result


def test_assessment_replay_uses_one_persisted_provider_attempt(m4_client, monkeypatch: pytest.MonkeyPatch) -> None:
    client, db = m4_client
    headers = _login(client)
    session_id, task_id, _ = _new_task(client, headers)
    message_id = _send_chat(client, headers, session_id, task_id, "我刚才说错了，实际请求仍需重新核查。")
    calls = 0

    def classify(**_kwargs):
        nonlocal calls
        calls += 1
        return {"intent": "CRITICAL_CORRECTION", "change_summary": "重新核查实际请求"}

    import opspilot.domain.investigation_updates as module
    monkeypatch.setattr(module, "classify_input", classify)
    first = _assess(client, headers, task_id, message_id)
    replay = _assess(client, headers, task_id, message_id)
    assert first.status_code == replay.status_code == 200
    assert first.json()["assessment_id"] == replay.json()["assessment_id"]
    assert first.json()["proposal"]["proposal_id"] == replay.json()["proposal"]["proposal_id"]
    assert calls == 1
    with connect(db) as connection:
        attempts = int(connection.execute("SELECT COUNT(*) FROM investigation_update_attempts").fetchone()[0])
    assert attempts == 1


def test_cancel_wins_confirmation_replay_and_creates_no_run(m4_client, monkeypatch: pytest.MonkeyPatch) -> None:
    client, db = m4_client
    headers = _login(client)
    session_id, task_id, _ = _new_task(client, headers)
    message_id = _send_chat(client, headers, session_id, task_id, "更正：当前调用路径需要重新核对。")
    _install_classifier(monkeypatch, "CRITICAL_CORRECTION")
    proposal = _assess(client, headers, task_id, message_id).json()["proposal"]
    before = _counts(db, task_id)
    url = f"/api/tasks/{task_id}/investigation-updates/{proposal['proposal_id']}"
    cancel = client.post(
        f"{url}/cancel", headers={**headers, "Idempotency-Key": proposal["operation_id"]},
        json={"operation_id": proposal["operation_id"]},
    )
    assert cancel.status_code in {200, 202}, cancel.text
    confirm = client.post(
        f"{url}/confirm", headers={**headers, "Idempotency-Key": proposal["operation_id"]},
        json={"expected_control_revision": proposal["expected_control_revision"],
              "operation_id": proposal["operation_id"]},
    )
    assert confirm.status_code == 409, confirm.text
    assert confirm.json()["code"] == "UPDATE_PROPOSAL_ALREADY_RESOLVED"
    assert _counts(db, task_id) == before


def test_parallel_confirm_and_cancel_have_one_atomic_winner(m4_client, monkeypatch: pytest.MonkeyPatch) -> None:
    client, db = m4_client
    owner_headers = _login(client)
    session_id, task_id, _ = _new_task(client, owner_headers)
    message_id = _send_chat(client, owner_headers, session_id, task_id, "更正：请重新调查现场请求。")
    _install_classifier(monkeypatch, "CRITICAL_CORRECTION")
    proposal = _assess(client, owner_headers, task_id, message_id).json()["proposal"]
    before = _counts(db, task_id)
    url = f"/api/tasks/{task_id}/investigation-updates/{proposal['proposal_id']}"
    with TestClient(client.app, raise_server_exceptions=False) as confirm_client, \
         TestClient(client.app, raise_server_exceptions=False) as cancel_client:
        confirm_headers = _login(confirm_client)
        cancel_headers = _login(cancel_client)

        def confirm():
            return confirm_client.post(
                f"{url}/confirm", headers={**confirm_headers, "Idempotency-Key": proposal["operation_id"]},
                json={"expected_control_revision": proposal["expected_control_revision"],
                      "operation_id": proposal["operation_id"]},
            )

        def cancel():
            return cancel_client.post(
                f"{url}/cancel", headers={**cancel_headers, "Idempotency-Key": proposal["operation_id"]},
                json={"operation_id": proposal["operation_id"]},
            )

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda action: action(), (confirm, cancel)))
    codes = sorted(response.status_code for response in results)
    assert codes in ([200, 409], [202, 409]), [response.text for response in results]
    after = _counts(db, task_id)
    if after["business_runs"] == before["business_runs"]:
        assert after == before
        with connect(db) as connection:
            status = connection.execute(
                "SELECT status FROM investigation_update_assessments WHERE assessment_id = ?",
                (proposal["proposal_id"],),
            ).fetchone()[0]
        assert status == "CANCELLED"
    else:
        assert after["business_runs"] == before["business_runs"] + 1
        assert after["corrections"] == before["corrections"] + 1
        assert after["revision"] == before["revision"] + 1
        with connect(db) as connection:
            status = connection.execute(
                "SELECT status FROM investigation_update_assessments WHERE assessment_id = ?",
                (proposal["proposal_id"],),
            ).fetchone()[0]
        assert status == "CONFIRMED"


def test_cross_tenant_cannot_read_or_confirm_another_owner_proposal(m4_client, monkeypatch: pytest.MonkeyPatch) -> None:
    client, db = m4_client
    owner_headers = _login(client)
    session_id, task_id, _ = _new_task(client, owner_headers)
    message_id = _send_chat(client, owner_headers, session_id, task_id, "更正：实际请求需要重新检查。")
    _install_classifier(monkeypatch, "CRITICAL_CORRECTION")
    proposal = _assess(client, owner_headers, task_id, message_id).json()["proposal"]
    before = _security_snapshot(db, task_id)
    with TestClient(client.app, raise_server_exceptions=False) as other_tenant:
        other_headers = _login(other_tenant, "support-b")
        listed = other_tenant.get(f"/api/tasks/{task_id}/investigation-updates", headers=other_headers)
        confirmed = other_tenant.post(
            f"/api/tasks/{task_id}/investigation-updates/{proposal['proposal_id']}/confirm",
            headers={**other_headers, "Idempotency-Key": proposal["operation_id"]},
            json={"expected_control_revision": proposal["expected_control_revision"],
                  "operation_id": proposal["operation_id"]},
        )
    assert listed.status_code in {403, 404}, listed.text
    assert confirmed.status_code in {403, 404}, confirmed.text
    assert listed.json().get("code") in {"TASK_OWNER_REQUIRED", "TASK_SCOPE_DENIED"}
    assert confirmed.json().get("code") in {"TASK_OWNER_REQUIRED", "TASK_SCOPE_DENIED"}
    assert _security_snapshot(db, task_id) == before


def test_pending_update_cannot_restart_an_aborted_task(m4_client, monkeypatch: pytest.MonkeyPatch) -> None:
    client, db = m4_client
    headers = _login(client)
    session_id, task_id, _ = _new_task(client, headers)
    message_id = _send_chat(client, headers, session_id, task_id, "更正：请重新核查当前请求。")
    _install_classifier(monkeypatch, "CRITICAL_CORRECTION")
    proposal = _assess(client, headers, task_id, message_id).json()["proposal"]
    stopped = client.post(
        f"/api/tasks/{task_id}/abort", headers={**headers, "Idempotency-Key": "m4-stop-before-confirm"},
        json={"reason": "用户终止后不再接受旧提议"},
    )
    assert stopped.status_code == 202, stopped.text
    before = _counts(db, task_id)
    confirmed = client.post(
        f"/api/tasks/{task_id}/investigation-updates/{proposal['proposal_id']}/confirm",
        headers={**headers, "Idempotency-Key": proposal["operation_id"]},
        json={"expected_control_revision": proposal["expected_control_revision"], "operation_id": proposal["operation_id"]},
    )
    assert confirmed.status_code == 409, confirmed.text
    assert confirmed.json()["code"] == "TASK_ABORTED"
    assert _counts(db, task_id) == before


def test_pending_update_cannot_restart_a_really_delivered_s1_task(
    demo_db: Path, live_api: str, monkeypatch: pytest.MonkeyPatch,
) -> None:
    from opspilot.domain.d3 import (
        execute_deliver, execute_repair, get_or_create_action_intent, get_or_create_report,
        submit_plan_approval, verify_repair_online,
    )
    from tests.test_m1_task_control import _ready_task

    binding, _, plan = _ready_task(demo_db, live_api, "m4-completed-proposal")
    task_id = str(binding["task_id"])
    app = create_app(db_path=demo_db, start_worker=False, credentials=PASSWORDS, expected_origin=ORIGIN)
    with TestClient(app, raise_server_exceptions=False) as client:
        headers = _login(client)
        message_id = _send_chat(client, headers, str(binding["session_id"]), task_id, "更正：请重新调查原来的凭证现象。")
        _install_classifier(monkeypatch, "CRITICAL_CORRECTION")
        proposal = _assess(client, headers, task_id, message_id).json()["proposal"]
        submit_plan_approval(demo_db, str(binding["thread_id"]), "approver-a", str(plan["plan_hash"]), "APPROVED")
        repair_intent = get_or_create_action_intent(demo_db, task_id, str(plan["plan_hash"]), "REPAIR", "executor-a")
        repair = execute_repair(demo_db, str(repair_intent["action_id"]), "executor-a", "m4-actual-repair")
        verified = verify_repair_online(demo_db, task_id, str(plan["plan_hash"]), str(repair_intent["action_id"]), "executor-a", live_api)
        assert verified["recovery_verified"] is True
        get_or_create_report(demo_db, task_id, str(plan["plan_hash"]), str(repair_intent["action_id"]), "executor-a")
        delivery_intent = get_or_create_action_intent(demo_db, task_id, str(plan["plan_hash"]), "DELIVER", "executor-a")
        delivered = execute_deliver(demo_db, str(delivery_intent["action_id"]), "executor-a", "m4-actual-delivery")
        assert repair["status"] == delivered["status"] == "COMMITTED"
        before = _counts(demo_db, task_id)
        confirmed = client.post(
            f"/api/tasks/{task_id}/investigation-updates/{proposal['proposal_id']}/confirm",
            headers={**headers, "Idempotency-Key": proposal["operation_id"]},
            json={"expected_control_revision": proposal["expected_control_revision"], "operation_id": proposal["operation_id"]},
        )
        assert confirmed.status_code == 409, confirmed.text
        assert confirmed.json()["code"] == "TASK_ALREADY_TERMINAL"
        assert _counts(demo_db, task_id) == before
        with connect(demo_db) as connection:
            status = connection.execute("SELECT status FROM task_bindings WHERE task_id = ?", (task_id,)).fetchone()[0]
        assert status == "COMPLETED"
