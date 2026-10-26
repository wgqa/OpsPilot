from __future__ import annotations

import json
import os
import threading
from pathlib import Path

from fastapi.testclient import TestClient

from opspilot.domain.api import make_server
from opspilot.domain.chat import get_task_inspector
from opspilot.domain.database import connect, reset_fixture
from opspilot.domain.investigation_context import load_investigation_context
from opspilot.domain.s3 import (
    evaluate_s3_gate,
    get_callback_delivery_fact,
    get_order_status_fact,
    get_receiver_processing_fact,
    persist_s3_diagnosis,
    prepare_s3_fixture,
)
from opspilot.domain.s3_answers import persist_run_answer
from opspilot.domain.task_control import (
    claim_task_run,
    create_session,
    create_task_with_initial_run,
    finish_task_run,
    trusted_identity,
)
from opspilot.web.app import create_app
from tests.s3_observation_support import record_s3_observation
from tests.test_m4_c1_hf_01 import _persist_previous_followup


ORIGIN = "http://testserver"
PASSWORD = "support-test-password"


def _task_with_persisted_initial_answer(db: Path) -> tuple[str, str, str, str]:
    """Create a real bound S3 Task, locally query HTTP/MCP facts, and persist its answer."""
    prepare_s3_fixture(db, "DELIVERED_PENDING", contract_version=2, queue_age_seconds=60)
    identity = trusted_identity(db, "support-a")
    session = create_session(db, identity)
    created = create_task_with_initial_run(
        db, identity, session_id=str(session["session_id"]), service_id="orders-async-demo",
        integration_id="async-integration-a", ticket_id="M4-CONT-UX-01-SUPPLEMENT",
        initial_message="订单已完成；请核实同一事件的回调与接收状态。",
        idempotency_key=f"m4-cont-ux-supplement-create-{db.stem}", s3_order_id="async-order",
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
    observations = [
        record_s3_observation(db, {"task_id": task_id, "run_id": run_id}, tool_name, fact, arguments={})
        for tool_name, fact in facts
    ]
    evidence_ids = [str(item["evidence_id"]) for item in observations]
    gate = evaluate_s3_gate(db, task_id, evidence_ids, run_id=run_id)
    assert gate["decision"] == "DIAGNOSED", gate
    diagnosis = persist_s3_diagnosis(db, task_id, run_id, evidence_ids)
    context = load_investigation_context(db, task_id, run_id)["task_run_control"]
    initial_answer = persist_run_answer(
        db, task_id, run_id, context=context,
        answer="INITIAL_RESTRICTED_BODY: 订单已完成，当前回调投递与接收状态已记录。",
        result_state="ANSWERED",
        source_refs=[
            {"kind": "EVIDENCE", "evidence_id": str(item["evidence_id"]),
             "observation_id": str(item["observation_id"]), "fact_type": fact[1]["fact_type"]}
            for item, fact in zip(observations, facts, strict=True)
        ],
        result={"delivery_mode": "DETERMINISTIC_FIXTURE", "s3_diagnosis": True},
        report_ref=str(diagnosis["receipt_id"]),
    )
    finish_task_run(db, identity, run_id, "SUCCEEDED")
    return str(session["session_id"]), task_id, run_id, str(initial_answer["answer_text"])


def _inspector_client(db: Path) -> TestClient:
    app = create_app(db_path=db, start_worker=False, credentials={"support-a": PASSWORD}, expected_origin=ORIGIN)
    return TestClient(app, raise_server_exceptions=True)


def _login(client: TestClient) -> dict[str, str]:
    response = client.post(
        "/api/auth/login", headers={"Origin": ORIGIN},
        json={"actor_id": "support-a", "password": PASSWORD},
    )
    assert response.status_code == 200, response.text
    return {"Origin": ORIGIN, "X-CSRF-Token": response.json()["csrf_token"]}


def _business_answer_snapshot(db: Path, task_id: str) -> dict[str, list[tuple[str, ...]]]:
    with connect(db) as connection:
        return {
            "initial": [tuple(row) for row in connection.execute(
                "SELECT run_id,digest,body_json FROM s3_run_answers WHERE task_id=? ORDER BY run_id", (task_id,),
            )],
            "followup": [tuple(row) for row in connection.execute(
                "SELECT run_id,result_digest,result_json,source_refs_json FROM c1_readonly_followup_runs "
                "WHERE task_id=? ORDER BY run_id", (task_id,),
            )],
            "diagnosis": [tuple(row) for row in connection.execute(
                "SELECT receipt_id,digest,body_json FROM s3_diagnoses WHERE task_id=? ORDER BY rowid", (task_id,),
            )],
        }


def test_inspector_redacts_initial_and_persisted_followup_after_scope_revocation(tmp_path: Path) -> None:
    db = tmp_path / "stage-b-supplement-inspector.sqlite3"
    reset_fixture(db, "S1_POS")
    session_id, task_id, _, initial_body = _task_with_persisted_initial_answer(db)
    followup = _persist_previous_followup(db, session_id, task_id, suffix="stage-b-supplement")
    identity = trusted_identity(db, "support-a")
    before = get_task_inspector(db, identity, task_id)
    assert any(item["answer_text"] == initial_body for item in before["investigation_answers"])
    prior_followup = next(item for item in before["readonly_followups"] if item["run_id"] == followup["run_id"])
    assert prior_followup["result_state"] == "ANSWERED"
    assert prior_followup["source_refs"] and prior_followup["result"]
    before_business = _business_answer_snapshot(db, task_id)

    with connect(db) as connection:
        connection.execute(
            "UPDATE route_scope_policies SET required_scopes_json='[\"revoked-scope\"]', "
            "scope_policy_version=scope_policy_version+1 WHERE tenant_id='tenant-a' AND service_id='orders-async-demo'"
        )
    after_response = _inspector_client(db)
    try:
        headers = _login(after_response)
        response = after_response.get(f"/api/tasks/{task_id}/inspector", headers=headers)
        assert response.status_code == 200, response.text
        after = response.json()
    finally:
        after_response.close()

    evidence_path = os.environ.get("OPSPILOT_SUPPLEMENT_RESPONSE_PATH")
    if evidence_path:
        target = Path(evidence_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps({"authorized": before, "scope_revoked": after}, ensure_ascii=False, indent=2), encoding="utf-8")

    encoded_after = json.dumps(after, ensure_ascii=False)
    violations: list[str] = []
    if after["investigation_answers"]:
        violations.append("initial S3 answer remains visible")
    if after["readonly_followups"]:
        violations.append("persisted C1 Follow-up remains visible")
    for restricted in (initial_body, str(prior_followup["answer_text"]), str(followup["source_message_id"])):
        if restricted in encoded_after:
            violations.append(f"restricted body/source leaked: {restricted[:80]}")
    if after["trusted_state"].get("s3_handoff"):
        violations.append("S3 handoff result remains visible")
    assert _business_answer_snapshot(db, task_id) == before_business, "read authorization must not rewrite immutable answer/diagnosis rows"
    assert not violations, "INSPECTOR_SCOPE_REVOCATION_LEAK: " + "; ".join(violations)
