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
)
from opspilot.domain.task_control import (
    claim_task_run,
    create_session,
    create_task_with_initial_run,
    finish_task_run,
    trusted_identity,
)
from opspilot.web.app import create_app
from tests.s3_observation_support import record_s3_observation


ORIGIN = "http://testserver"
PASSWORD = "support-test-password"


def _diagnosed_task(db: Path) -> tuple[str, str, str, str]:
    prepare_s3_fixture(db, "DELIVERED_PENDING", contract_version=2, queue_age_seconds=60)
    identity = trusted_identity(db, "support-a")
    session = create_session(db, identity)
    created = create_task_with_initial_run(
        db,
        identity,
        session_id=str(session["session_id"]),
        service_id="orders-async-demo",
        integration_id="async-integration-a",
        ticket_id="M4-C1-FOLLOWUP-RED",
        initial_message="订单已完成，HTTP 202 后请核实下游回调状态。",
        idempotency_key="m4-c1-followup-red-create-task",
        s3_order_id="async-order",
    )
    task_id, run_id = str(created["task_id"]), str(created["run_id"])
    claim_task_run(db, identity, run_id)
    server = make_server(db, "tenant-a", "127.0.0.1", 0)
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True)
    thread.start()
    try:
        root = f"http://127.0.0.1:{server.server_port}"
        facts = [
            ("get_order_status", get_order_status_fact(db, task_id, root)),
            ("get_callback_delivery", get_callback_delivery_fact(db, task_id)),
            ("get_receiver_processing", get_receiver_processing_fact(db, task_id)),
        ]
    finally:
        server.shutdown()
        thread.join(timeout=2)
        server.server_close()
    evidence_ids = [
        str(record_s3_observation(
            db, {"task_id": task_id, "run_id": run_id}, tool_name, fact, arguments={},
        )["evidence_id"])
        for tool_name, fact in facts
    ]
    gate = evaluate_s3_gate(db, task_id, evidence_ids, run_id=run_id)
    assert gate["decision"] == "DIAGNOSED", gate
    diagnosis = persist_s3_diagnosis(db, task_id, run_id, evidence_ids)
    finish_task_run(db, identity, run_id, "SUCCEEDED")
    return str(session["session_id"]), task_id, run_id, str(diagnosis["receipt_id"])


def test_follow_up_request_for_bound_protocol_is_routed_to_same_task_readonly_investigation(
    tmp_path: Path, monkeypatch,
) -> None:
    """Behavior RED: legal FOLLOW_UP intent has no investigation route on current baseline."""
    db = tmp_path / "m4-autonomy-c1-followup-red.sqlite3"
    reset_fixture(db, "S1_POS")
    session_id, task_id, diagnosis_run_id, diagnosis_id = _diagnosed_task(db)
    app = create_app(
        db_path=db,
        start_worker=False,
        credentials={"support-a": PASSWORD},
        expected_origin=ORIGIN,
        heartbeat_seconds=0.05,
    )
    monkeypatch.setenv("OPSPILOT_MODEL_NAME", "c1-deterministic-red")
    monkeypatch.setattr(
        "opspilot.domain.investigation_updates.classify_input",
        lambda **_kwargs: {
            "intent": "FOLLOW_UP",
            "change_summary": "",
            "readonly_action": "INVESTIGATE",
        },
    )
    with TestClient(app, raise_server_exceptions=False) as client:
        login = client.post(
            "/api/auth/login",
            headers={"Origin": ORIGIN},
            json={"actor_id": "support-a", "password": PASSWORD},
        )
        assert login.status_code == 200, login.text
        headers = {"Origin": ORIGIN, "X-CSRF-Token": login.json()["csrf_token"]}
        message = client.post(
            f"/api/sessions/{session_id}/messages",
            headers={**headers, "Idempotency-Key": "m4-c1-followup-red-message"},
            json={
                "task_id": task_id,
                "input_kind": "CHAT_READONLY",
                "body": "请按当前绑定的协议版本核对 HTTP 202 的含义，并给出可查证的依据。",
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
        runs = [dict(row) for row in connection.execute(
            "SELECT run_id,kind,status,source_message_id FROM task_runs WHERE task_id=? AND source_message_id=?",
            (task_id, source_message_id),
        ).fetchall()]
        control_revision = int(connection.execute(
            "SELECT control_revision FROM task_controls WHERE task_id=?", (task_id,),
        ).fetchone()[0])
        corrections = int(connection.execute(
            "SELECT COUNT(*) FROM messages WHERE task_id=? AND input_kind='CORRECT_TASK_INPUT'", (task_id,),
        ).fetchone()[0])
        diagnosis = dict(connection.execute(
            "SELECT receipt_id,body_json,digest FROM s3_diagnoses WHERE receipt_id=?", (diagnosis_id,),
        ).fetchone())
        write_counts = {
            table: int(connection.execute(f"SELECT COUNT(*) FROM {table} WHERE task_id=?", (task_id,)).fetchone()[0])
            for table in ("d3_action_intents", "d3_action_ledgers", "s3_handoff_queue_entries", "s3_handoff_receipts")
        }
    followup_runs = [row for row in runs if row["kind"] != "CHAT_READONLY"]
    trace = {
        "schema": "opspilot-m4-autonomy-c1-followup-red-v1",
        "case_id": "C1-FOLLOWUP-BEHAVIOR-RED",
        "diagnosis_run_id": diagnosis_run_id,
        "diagnosis_id": diagnosis_id,
        "task_id": task_id,
        "source_message_id": source_message_id,
        "assessment_status": assessment.status_code,
        "assessment_intent": assessment.json().get("intent") if assessment.status_code == 200 else None,
        "readonly_action_requested_by_test_double": "INVESTIGATE",
        "linked_runs": runs,
        "readonly_investigation_run_count": len(followup_runs),
        "control_revision": control_revision,
        "critical_correction_count": corrections,
        "diagnosis_digest": diagnosis["digest"],
        "write_counts": write_counts,
        "expected": "one persisted same-Task read-only investigation Run linked to the FOLLOW_UP message",
        "observed": "existing service creates only the CHAT_READONLY Run; no Investigator Run is linked",
        "classification_source": "deterministic test double; not a Provider trace",
    }
    trace_path = Path(__file__).resolve().parents[1] / "docs/evidence/vnext/m4-autonomy-c1/runs/rev1/behavior-red-trace.jsonl"
    trace_path.parent.mkdir(parents=True, exist_ok=True)
    with trace_path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(trace, ensure_ascii=False, sort_keys=True) + "\n")

    assert assessment.status_code == 200, assessment.text
    assert assessment.json()["intent"] == "FOLLOW_UP"
    assert len(followup_runs) == 1, "the explicit read-only investigation request was not routed into an Investigator Run"
    assert followup_runs[0]["source_message_id"] == source_message_id
    assert followup_runs[0]["run_id"] != diagnosis_run_id
    assert control_revision == 0
    assert corrections == 0
    assert diagnosis["digest"]
    assert write_counts == {
        "d3_action_intents": 0,
        "d3_action_ledgers": 0,
        "s3_handoff_queue_entries": 0,
        "s3_handoff_receipts": 0,
    }
