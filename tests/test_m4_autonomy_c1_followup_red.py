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


def test_follow_up_investigation_uses_real_mcp_and_persists_a_readonly_result(
    tmp_path: Path, monkeypatch,
) -> None:
    import asyncio

    from langchain_core.messages import AIMessage

    from opspilot.config import MODEL_API_KEY, MODEL_NAME
    from opspilot.domain.task_control import trusted_identity
    from opspilot.investigator import run_investigation

    db = tmp_path / "m4-autonomy-c1-followup-mcp.sqlite3"
    reset_fixture(db, "S1_POS")
    session_id, task_id, diagnosis_run_id, diagnosis_id = _diagnosed_task(db)
    with connect(db) as connection:
        original_task = dict(connection.execute(
            "SELECT status FROM task_bindings WHERE task_id=?", (task_id,),
        ).fetchone())
        original_diagnosis = dict(connection.execute(
            "SELECT digest,outcome,body_json FROM s3_diagnoses WHERE receipt_id=?", (diagnosis_id,),
        ).fetchone())
        diagnosis_count = int(connection.execute(
            "SELECT COUNT(*) FROM s3_diagnoses WHERE task_id=?", (task_id,),
        ).fetchone()[0])

    app = create_app(
        db_path=db,
        start_worker=False,
        credentials={"support-a": PASSWORD},
        expected_origin=ORIGIN,
        heartbeat_seconds=0.05,
    )
    monkeypatch.setenv(MODEL_API_KEY, "local-test-key")
    monkeypatch.setenv(MODEL_NAME, "c1-fake-integration-model")
    monkeypatch.setattr(
        "opspilot.domain.investigation_updates.classify_input",
        lambda **_kwargs: {
            "intent": "FOLLOW_UP", "change_summary": "",
            "readonly_action": "INVESTIGATE",
        },
    )

    class ScriptedModel:
        def __init__(self, **_kwargs):
            self.calls: list[str] = []

        def bind_tools(self, *_args, **_kwargs):
            return self

        async def ainvoke(self, messages):
            body = str(messages[-1].content)
            self.calls.append(body)
            if len(self.calls) == 1:
                assert "Treat that latest request as the active goal" in str(messages[0].content)
                assert "Query live business facts only when the latest request depends on current business state" in str(messages[0].content)
                assert "HTTP 202" in body
                return AIMessage(content="", tool_calls=[{
                    "id": "c1-knowledge-call",
                    "name": "search_callback_knowledge",
                    "args": {"query": "HTTP 202 acknowledgement", "reason": "Read the bound protocol meaning requested by the user."},
                }])
            if len(self.calls) == 2:
                assert "retrieved_knowledge_method_only" in body
                assert "document_id" in body
                return AIMessage(content="The bound protocol material answers the HTTP acknowledgement question.")
            assert "READONLY_FOLLOWUP" in body
            assert "retrieved_knowledge_method_only" in body
            return AIMessage(content=(
                "RESULT: ANSWERED\n"
                "当前绑定协议中的 HTTP 202 表示接收端已接受请求，不证明回调处理完成。"
                "依据当前契约知识条目；如需确认当前接收进度，应继续查询该 Task 绑定的接收状态。"
            ), id="c1-fake-explanation")

    monkeypatch.setattr("opspilot.investigator.ChatOpenAI", ScriptedModel)
    with TestClient(app, raise_server_exceptions=False) as client:
        login = client.post(
            "/api/auth/login", headers={"Origin": ORIGIN},
            json={"actor_id": "support-a", "password": PASSWORD},
        )
        assert login.status_code == 200, login.text
        headers = {"Origin": ORIGIN, "X-CSRF-Token": login.json()["csrf_token"]}
        message = client.post(
            f"/api/sessions/{session_id}/messages",
            headers={**headers, "Idempotency-Key": "m4-c1-followup-mcp-message"},
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
        assert assessment.status_code == 200, assessment.text
        assessed = assessment.json()
        assert assessed["follow_up_action"] == "INVESTIGATE"
        run_id = str(assessed["investigation_run_id"])
        replay_assessment = client.post(
            f"/api/tasks/{task_id}/investigation-updates/proposals",
            headers={**headers, "Idempotency-Key": source_message_id},
            json={"source_message_id": source_message_id},
        )
        assert replay_assessment.status_code == 200, replay_assessment.text
        assert replay_assessment.json()["investigation_run_id"] == run_id
        result = asyncio.run(run_investigation(
            task_id,
            "support-a",
            db_path=db,
            checkpoint_db_path=tmp_path / "followup-checkpoints.sqlite3",
            run_id=run_id,
        ))

        assert result["graph_state"]["stage"] == "complete", result
        final_run = client.get(f"/api/runs/{run_id}")
        assert final_run.status_code == 200, final_run.text
        assert final_run.json()["status"] == "SUCCEEDED"
        inspector = client.get(f"/api/tasks/{task_id}/inspector")
        assert inspector.status_code == 200, inspector.text
        visible_result = next(
            item for item in inspector.json()["readonly_followups"] if item["run_id"] == run_id
        )

    with connect(db) as connection:
        observations = [dict(row) for row in connection.execute(
            """SELECT o.observation_id,o.tool_name,o.status,o.evidence_id,a.run_id
               FROM d2_tool_observations o JOIN d2_attempts a ON a.attempt_id=o.attempt_id
               WHERE o.task_id=? AND a.run_id=? ORDER BY o.created_at""",
            (task_id, run_id),
        ).fetchall()]
        model_contexts = [json.loads(str(row[0])) for row in connection.execute(
            "SELECT messages_json FROM s3_model_contexts WHERE task_id=? AND run_id=? ORDER BY rowid",
            (task_id, run_id),
        ).fetchall()]
        after_task = dict(connection.execute(
            "SELECT status FROM task_bindings WHERE task_id=?", (task_id,),
        ).fetchone())
        after_diagnosis = dict(connection.execute(
            "SELECT digest,outcome,body_json FROM s3_diagnoses WHERE receipt_id=?", (diagnosis_id,),
        ).fetchone())
        assert int(connection.execute(
            "SELECT COUNT(*) FROM s3_diagnoses WHERE task_id=?", (task_id,),
        ).fetchone()[0]) == diagnosis_count
        assert int(connection.execute(
            "SELECT control_revision FROM task_controls WHERE task_id=?", (task_id,),
        ).fetchone()[0]) == 0
        assert int(connection.execute(
            "SELECT COUNT(*) FROM messages WHERE task_id=? AND input_kind='CORRECT_TASK_INPUT'", (task_id,),
        ).fetchone()[0]) == 0
        for table in ("d3_action_intents", "d3_action_ledgers", "s3_handoff_queue_entries", "s3_handoff_receipts"):
            assert int(connection.execute(f"SELECT COUNT(*) FROM {table} WHERE task_id=?", (task_id,)).fetchone()[0]) == 0

    assert after_task == original_task
    assert after_diagnosis == original_diagnosis
    assert any(item["tool_name"] == "search_callback_knowledge" and item["status"] == "OK" for item in observations)
    assert all(item["run_id"] == run_id for item in observations)
    context_text = json.dumps(model_contexts, ensure_ascii=False)
    assert source_message_id in context_text
    assert "retrieved_knowledge_method_only" in context_text
    assert visible_result["result_state"] == "ANSWERED"
    assert visible_result["source_refs"]
    assert any(item.get("kind") == "KNOWLEDGE" for item in visible_result["source_refs"])
    assert visible_result["result"]["diagnosis_persisted"] is False
    from opspilot.domain.task_control import persist_readonly_followup_result
    replay_result = persist_readonly_followup_result(
        db,
        trusted_identity(db, "support-a"),
        run_id,
        result_state=str(visible_result["result_state"]),
        answer_text=str(visible_result["answer_text"]),
        source_refs=list(visible_result["source_refs"]),
        result=dict(visible_result["result"]),
        reason_code=visible_result["reason_code"],
    )
    assert replay_result["replayed"] is True

    # A fresh app instance reads the frozen answer and sources from the same Domain DB.
    restarted_app = create_app(
        db_path=db,
        start_worker=False,
        credentials={"support-a": PASSWORD},
        expected_origin=ORIGIN,
        heartbeat_seconds=0.05,
    )
    with TestClient(restarted_app, raise_server_exceptions=False) as client:
        login = client.post(
            "/api/auth/login", headers={"Origin": ORIGIN},
            json={"actor_id": "support-a", "password": PASSWORD},
        )
        assert login.status_code == 200, login.text
        history = client.get(
            f"/api/tasks/{task_id}/inspector",
            headers={"Origin": ORIGIN, "X-CSRF-Token": login.json()["csrf_token"]},
        )
        assert history.status_code == 200, history.text
        stored = next(item for item in history.json()["readonly_followups"] if item["run_id"] == run_id)
        assert stored["result_digest"] == visible_result["result_digest"]
        assert stored["answer_text"] == visible_result["answer_text"]


def test_readonly_followup_completion_label_fails_closed_to_partial() -> None:
    from opspilot.s3_investigation import _parse_readonly_followup_answer

    assert _parse_readonly_followup_answer("RESULT: ANSWERED\nBound source supports this.") == (
        "ANSWERED", "Bound source supports this."
    )
    assert _parse_readonly_followup_answer("RESULT: PARTIAL\nThe requested clause is absent.") == (
        "PARTIAL", "The requested clause is absent."
    )
    assert _parse_readonly_followup_answer("A response without the required label.") == (
        "PARTIAL", "A response without the required label."
    )
