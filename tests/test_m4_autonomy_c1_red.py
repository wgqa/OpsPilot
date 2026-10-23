from __future__ import annotations

import json
import threading
from pathlib import Path

from fastapi.testclient import TestClient

from opspilot.domain.api import make_server
from opspilot.domain.database import connect, reset_fixture
from opspilot.domain.s3 import (
    evaluate_s3_gate,
    get_callback_delivery_fact,
    get_order_status_fact,
    get_receiver_processing_fact,
    persist_s3_diagnosis,
    prepare_s3_fixture,
    get_s3_outcome,
)
from opspilot.domain.task_control import (
    claim_task_run,
    create_session,
    create_task_with_initial_run,
    finish_task_run,
    trusted_identity,
)
from opspilot.domain.d2 import record_tool_observation
from opspilot.web.app import create_app


ORIGIN = "http://testserver"
PASSWORDS = {
    "support-a": "support-test-password",
    "approver-a": "approver-test-password",
    "support-b": "support-b-test-password",
    "approver-b": "approver-b-test-password",
}


def _diagnosed_task(db: Path) -> tuple[str, str, str, str]:
    """Build a fresh, current S3 diagnosis; this RED does not exercise TTL behavior."""
    prepare_s3_fixture(db, "DELIVERED_PENDING", contract_version=2, queue_age_seconds=60)
    identity = trusted_identity(db, "support-a")
    session = create_session(db, identity)
    created = create_task_with_initial_run(
        db,
        identity,
        session_id=str(session["session_id"]),
        service_id="orders-async-demo",
        integration_id="async-integration-a",
        ticket_id="M4-C1-RED",
        initial_message="订单已完成，HTTP 202 后请核实下游回调状态。",
        idempotency_key="m4-c1-red-create-task",
        s3_order_id="async-order",
    )
    task_id, run_id = str(created["task_id"]), str(created["run_id"])
    claim_task_run(db, identity, run_id)

    server = make_server(db, "tenant-a", "127.0.0.1", 0)
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True)
    thread.start()
    try:
        base_url = f"http://127.0.0.1:{server.server_port}"
        facts = [
            ("get_order_status", get_order_status_fact(db, task_id, base_url)),
            ("get_callback_delivery", get_callback_delivery_fact(db, task_id)),
            ("get_receiver_processing", get_receiver_processing_fact(db, task_id)),
        ]
    finally:
        server.shutdown()
        thread.join(timeout=2)
        server.server_close()

    evidence_ids: list[str] = []
    for index, (tool_name, fact) in enumerate(facts):
        observed = record_tool_observation(
            db,
            task_id=task_id,
            call_id=f"m4-c1-red-observation-{index}",
            attempt_id=None,
            tool_call_id=f"m4-c1-red-tool-{index}",
            tool_name=tool_name,
            arguments={},
            status="OK",
            result=fact,
        )
        evidence_ids.append(str(observed["evidence_id"]))
    gate = evaluate_s3_gate(db, task_id, evidence_ids)
    assert gate["decision"] == "DIAGNOSED", gate
    diagnosis = persist_s3_diagnosis(db, task_id, run_id, evidence_ids)
    finish_task_run(db, identity, run_id, "SUCCEEDED")
    return str(session["session_id"]), task_id, run_id, str(diagnosis["receipt_id"])


def test_explicit_protocol_followup_is_accepted_as_same_task_readonly_run_before_ttl_fix(
    tmp_path: Path, monkeypatch,
) -> None:
    """Expected RED: baseline only classifies FOLLOW_UP, with no investigator Run path."""
    db = tmp_path / "m4-autonomy-c1.sqlite3"
    reset_fixture(db, "S1_POS")
    session_id, task_id, diagnosis_run_id, diagnosis_id = _diagnosed_task(db)
    app = create_app(
        db_path=db,
        start_worker=False,
        credentials=PASSWORDS,
        expected_origin=ORIGIN,
        heartbeat_seconds=0.05,
    )
    monkeypatch.setenv("OPSPILOT_MODEL_NAME", "c1-red-test-model")
    monkeypatch.setattr(
        "opspilot.domain.investigation_updates.classify_input",
        lambda **_kwargs: {"intent": "READONLY_FOLLOWUP", "change_summary": ""},
    )

    with TestClient(app, raise_server_exceptions=False) as client:
        login = client.post(
            "/api/auth/login",
            headers={"Origin": ORIGIN},
            json={"actor_id": "support-a", "password": PASSWORDS["support-a"]},
        )
        assert login.status_code == 200, login.text
        headers = {"Origin": ORIGIN, "X-CSRF-Token": login.json()["csrf_token"]}
        message = client.post(
            f"/api/sessions/{session_id}/messages",
            headers={**headers, "Idempotency-Key": "m4-c1-red-followup-message"},
            json={
                "task_id": task_id,
                "input_kind": "CHAT_READONLY",
                "body": "请按这个任务当前绑定的协议版本查明 HTTP 202 的含义，并附可核对的文档依据。",
            },
        )
        assert message.status_code == 202, message.text
        source_message_id = str(message.json()["message_id"])
        assessment = client.post(
            f"/api/tasks/{task_id}/investigation-updates/proposals",
            headers={**headers, "Idempotency-Key": source_message_id},
            json={"source_message_id": source_message_id},
        )

    with connect(db) as connection:
        chat_run = connection.execute(
            "SELECT run_id, kind, status, source_message_id FROM task_runs WHERE run_id = ?",
            (str(message.json()["run_id"]),),
        ).fetchone()
        followup = connection.execute(
            """SELECT run_id, kind, status, source_message_id FROM task_runs
               WHERE task_id = ? AND source_message_id = ? AND kind = 'READONLY_FOLLOWUP'""",
            (task_id, source_message_id),
        ).fetchone()
        control_revision = int(connection.execute(
            "SELECT control_revision FROM task_controls WHERE task_id = ?", (task_id,)
        ).fetchone()[0])
        correction_count = int(connection.execute(
            "SELECT COUNT(*) FROM messages WHERE task_id = ? AND input_kind = 'CORRECT_TASK_INPUT'",
            (task_id,),
        ).fetchone()[0])
        diagnosis = connection.execute(
            "SELECT receipt_id, body_json, digest FROM s3_diagnoses WHERE receipt_id = ?",
            (diagnosis_id,),
        ).fetchone()
        task_status = str(connection.execute(
            "SELECT status FROM task_bindings WHERE task_id = ?", (task_id,)
        ).fetchone()[0])
        http_observations = int(connection.execute(
            "SELECT COUNT(*) FROM s3_http_observations"
        ).fetchone()[0])
        side_effect_counts = {
            table: int(connection.execute(f"SELECT COUNT(*) FROM {table} WHERE task_id = ?", (task_id,)).fetchone()[0])
            for table in ("d3_action_intents", "d3_action_ledgers", "s3_handoff_queue_entries", "s3_handoff_receipts")
        }
    trace = {
        "schema": "opspilot-m4-autonomy-c1-red-v1",
        "case_id": "C1-01",
        "baseline_sha": "add47ec83f31fa76b9b6a5782e013311732bc496",
        "task_id": task_id,
        "diagnosis_id": diagnosis_id,
        "diagnosis_run_id": diagnosis_run_id,
        "diagnosis_digest": str(diagnosis["digest"]) if diagnosis is not None else None,
        "diagnosis_gate": json.loads(str(diagnosis["body_json"])).get("gate") if diagnosis is not None else None,
        "diagnosis_currentness": get_s3_outcome(db, task_id).get("currentness"),
        "task_status": task_status,
        "source_message_id": source_message_id,
        "chat_run": dict(chat_run) if chat_run is not None else None,
        "assessment_http_status": assessment.status_code,
        "assessment_error_code": assessment.json().get("code") if assessment.headers.get("content-type", "").startswith("application/json") else None,
        "followup_run_found": followup is not None,
        "control_revision": control_revision,
        "correction_count": correction_count,
        "side_effect_counts": side_effect_counts,
        "setup_http_observation_count": http_observations,
        "followup_provider_calls": 0,
        "followup_mcp_calls": 0,
        "classification_source": "deterministic test double; not a real Provider trace",
        "expected": "accepted same-Task READONLY_FOLLOWUP Run linked to source_message_id; no TaskControl or business-write change",
        "observed": "baseline classifier rejects READONLY_FOLLOWUP before dispatch",
    }
    trace_path = Path(__file__).resolve().parents[1] / "docs/evidence/vnext/m4-autonomy-c1/TRACE.jsonl"
    trace_path.parent.mkdir(parents=True, exist_ok=True)
    with trace_path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(trace, ensure_ascii=False, sort_keys=True) + "\n")

    assert assessment.status_code == 200, assessment.text
    assert assessment.json()["intent"] == "READONLY_FOLLOWUP"
    assert followup is not None, "a read-only follow-up needs its own persisted Run and source message"
    assert followup["kind"] == "READONLY_FOLLOWUP"
    assert followup["source_message_id"] == source_message_id
    assert followup["run_id"] != diagnosis_run_id
    assert control_revision == 0
    assert correction_count == 0
    assert diagnosis is not None
    assert side_effect_counts == {
        "d3_action_intents": 0,
        "d3_action_ledgers": 0,
        "s3_handoff_queue_entries": 0,
        "s3_handoff_receipts": 0,
    }
