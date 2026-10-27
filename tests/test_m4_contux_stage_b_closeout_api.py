from __future__ import annotations

import json
import os
import shutil
import subprocess
import threading
from pathlib import Path

import pytest

from opspilot.domain.api import make_server
from opspilot.domain.chat import complete_chat_attempt, prepare_chat_attempt
from opspilot.domain.database import connect, reset_fixture
from opspilot.domain.investigation_context import load_investigation_context
from opspilot.domain.s3 import get_callback_delivery_fact, get_order_status_fact, get_receiver_processing_fact, persist_s3_diagnosis
from opspilot.domain.s3_answers import persist_run_answer
from opspilot.domain.task_control import (
    apply_pending_critical_inputs, claim_task_run, create_task_with_initial_run, finish_task_run,
    next_worker_run, register_worker_owner, trusted_identity,
)
from tests.s3_observation_support import record_s3_observation
from tests.test_m4_c1_hf_01 import _persist_previous_followup
from tests.test_m4_contux_stage_b_supplement_api import _inspector_client, _login, _task_with_persisted_initial_answer


ROOT = Path(__file__).resolve().parents[1]


def _snapshot(client, headers: dict[str, str], session_id: str, task_id: str) -> dict[str, object]:
    inspector = client.get(f"/api/tasks/{task_id}/inspector", headers=headers)
    messages = client.get(f"/api/sessions/{session_id}/messages", headers=headers)
    assessments = client.get(f"/api/tasks/{task_id}/investigation-updates", headers=headers)
    assert inspector.status_code == messages.status_code == assessments.status_code == 200
    return {"inspector": inspector.json(), "messages": messages.json(), "assessments": assessments.json()}


def _project_real_api_json(tmp_path: Path, name: str, mode: str, payload: dict[str, object]) -> None:
    node = shutil.which("node")
    assert node, "Node is required for the real API JSON to frontend projection integration test"
    serialized = json.dumps(payload, ensure_ascii=False, indent=2)
    source = tmp_path / f"{name}.json"
    source.write_text(serialized, encoding="utf-8")
    capture_dir = os.environ.get("OPSPILOT_STAGEB_CLOSEOUT_RESPONSE_DIR")
    if capture_dir:
        target = Path(capture_dir)
        target.mkdir(parents=True, exist_ok=True)
        (target / f"{name}.json").write_text(serialized, encoding="utf-8")
    result = subprocess.run(
        [node, "--experimental-strip-types", str(ROOT / "frontend/test/stage-b-api-projection.ts"), str(source), mode],
        cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace", check=False,
    )
    print(result.stdout, end="")
    print(result.stderr, end="")
    assert result.returncode == 0, f"frontend projection of actual API JSON failed with exit {result.returncode}"


def test_real_inspector_and_messages_project_initial_followup_and_revocation(tmp_path: Path) -> None:
    db = tmp_path / "api-projection.sqlite3"
    reset_fixture(db, "S1_POS")
    session_id, task_id, initial_run, _ = _task_with_persisted_initial_answer(db)
    followup = _persist_previous_followup(db, session_id, task_id, suffix="closeout-api")
    identity = trusted_identity(db, "support-a")
    other = create_task_with_initial_run(
        db, identity, session_id=session_id, service_id="orders-demo", integration_id="integration-a",
        ticket_id="STAGE-B-CLOSEOUT-OTHER", initial_message="另一个 Task 的独立问题。",
        idempotency_key="stage-b-closeout-other-task",
    )
    with _inspector_client(db) as client:
        headers = _login(client)
        authorized = _snapshot(client, headers, session_id, task_id)
        initial = next(item for item in authorized["inspector"]["investigation_answers"] if item["run_id"] == initial_run)
        old_followup = next(item for item in authorized["inspector"]["readonly_followups"] if item["run_id"] == followup["run_id"])
        other_source = next(item["message_id"] for item in authorized["messages"]["items"]
                            if item["role"] == "USER" and item["task_id"] == other["task_id"])
        restricted = [initial["answer_text"], initial["report_ref"], old_followup["answer_text"]]
        restricted.extend(str(item["evidence_id"]) for item in authorized["inspector"]["evidence"])
        with connect(db) as connection:
            connection.execute(
                "UPDATE route_scope_policies SET required_scopes_json='[\"revoked-scope\"]', "
                "scope_policy_version=scope_policy_version+1 WHERE tenant_id='tenant-a' AND service_id='orders-async-demo'"
            )
        revoked = _snapshot(client, headers, session_id, task_id)
    payload = {
        "authorized": authorized, "revoked": revoked, "restricted": restricted,
        "ids": {"task_id": task_id, "initial_run": initial_run, "initial_source": initial["source_message_id"],
                "followup_run": followup["run_id"], "followup_source": followup["source_message_id"],
                "other_source": other_source},
    }
    _project_real_api_json(tmp_path, "initial-followup-revoked", "initial", payload)


def test_real_api_chat_answer_projects_once_under_exact_user_question(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = tmp_path / "api-chat-projection.sqlite3"
    reset_fixture(db, "S1_POS")
    session_id, task_id, _, _ = _task_with_persisted_initial_answer(db)
    with _inspector_client(db) as client:
        headers = _login(client)
        accepted = client.post(
            f"/api/sessions/{session_id}/messages", headers={**headers, "Idempotency-Key": "closeout-chat-answer"},
            json={"task_id": task_id, "input_kind": "CHAT_READONLY", "body": "请解释刚才的调查结果。"},
        )
        assert accepted.status_code == 202, accepted.text
        run_id, question_id = str(accepted.json()["run_id"]), str(accepted.json()["message_id"])
        monkeypatch.setattr(
            "opspilot.domain.investigation_updates.classify_input",
            lambda **_kwargs: {"intent": "FOLLOW_UP", "change_summary": "", "readonly_action": "EXPLAIN"},
        )
        assessed = client.post(
            f"/api/tasks/{task_id}/investigation-updates/proposals",
            headers={**headers, "Idempotency-Key": question_id}, json={"source_message_id": question_id},
        )
        assert assessed.status_code == 200, assessed.text
        assert assessed.json()["follow_up_action"] == "EXPLAIN"
        assert str(next_worker_run(db)["run_id"]) == run_id
        identity = trusted_identity(db, "support-a")
        worker_id = "closeout-chat-worker"
        register_worker_owner(db, worker_id, os.getpid())
        claim_task_run(db, identity, run_id)
        attempt = prepare_chat_attempt(db, run_id, worker_id, "deterministic-closeout")
        answer_text = "依据刚才核实的事实，回调已被接收；接收方处理状态仍需确认。"
        completed = complete_chat_attempt(
            db, worker_id, str(attempt["attempt_id"]), answer_text,
            provider_response_id="deterministic-closeout-answer", input_tokens=3, output_tokens=9, total_tokens=12,
        )
        snapshot = _snapshot(client, headers, session_id, task_id)
    payload = {"chat": snapshot, "ids": {"task_id": task_id, "question": question_id,
               "run": run_id, "answer": str(completed["message_id"]), "answer_text": answer_text}}
    _project_real_api_json(tmp_path, "chat-answer", "chat", payload)


def _complete_correction_run(db: Path, task_id: str, run_id: str, state: str) -> str:
    identity = trusted_identity(db, "support-a")
    claim_task_run(db, identity, run_id)
    apply_pending_critical_inputs(db, identity, run_id)
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
    observations = [record_s3_observation(db, {"task_id": task_id, "run_id": run_id}, name, fact, arguments={})
                    for name, fact in facts]
    evidence_ids = [str(item["evidence_id"]) for item in observations]
    diagnosis = persist_s3_diagnosis(db, task_id, run_id, evidence_ids)
    context = load_investigation_context(db, task_id, run_id)["task_run_control"]
    persist_run_answer(
        db, task_id, run_id, context=context, answer=f"CORRECTION_RESULT_{state}: 已重新核实当前回调。",
        result_state=state,
        source_refs=[{"kind": "EVIDENCE", "evidence_id": str(item["evidence_id"]),
                      "observation_id": str(item["observation_id"]), "fact_type": fact[1]["fact_type"]}
                     for item, fact in zip(observations, facts, strict=True)],
        result={"delivery_mode": "DETERMINISTIC_FIXTURE"}, report_ref=str(diagnosis["receipt_id"]),
    )
    finish_task_run(db, identity, run_id, "SUCCEEDED")
    return str(diagnosis["receipt_id"])


@pytest.mark.parametrize("state", ["ANSWERED", "PARTIAL"])
def test_confirmed_correction_api_json_projects_persisted_answer_and_diagnosis(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, state: str,
) -> None:
    db = tmp_path / "correction-projection.sqlite3"
    reset_fixture(db, "S1_POS")
    session_id, task_id, _, _ = _task_with_persisted_initial_answer(db)
    _persist_previous_followup(db, session_id, task_id, suffix=f"closeout-correction-{state}")
    monkeypatch.setattr(
        "opspilot.domain.investigation_updates.classify_input",
        lambda **_kwargs: {"intent": "CRITICAL_CORRECTION", "change_summary": "更正当前回调描述", "readonly_action": "EXPLAIN"},
    )
    with _inspector_client(db) as client:
        headers = _login(client)
        submitted = client.post(
            f"/api/sessions/{session_id}/messages", headers={**headers, "Idempotency-Key": f"closeout-question-{state}"},
            json={"task_id": task_id, "input_kind": "CHAT_READONLY", "body": "之前描述有误，请重新核实这个回调。"},
        )
        assert submitted.status_code == 202, submitted.text
        question_id = str(submitted.json()["message_id"])
        assessed = client.post(
            f"/api/tasks/{task_id}/investigation-updates/proposals",
            headers={**headers, "Idempotency-Key": question_id}, json={"source_message_id": question_id},
        )
        assert assessed.status_code == 200, assessed.text
        proposal = assessed.json()["proposal"]
        confirmed = client.post(
            f"/api/tasks/{task_id}/investigation-updates/{proposal['proposal_id']}/confirm",
            headers={**headers, "Idempotency-Key": str(proposal["operation_id"])},
            json={"operation_id": proposal["operation_id"], "expected_control_revision": proposal["expected_control_revision"]},
        )
        assert confirmed.status_code == 200, confirmed.text
        run_id = str(confirmed.json()["run_id"])
        receipt_id = _complete_correction_run(db, task_id, run_id, state)
        snapshot = _snapshot(client, headers, session_id, task_id)
    assessment = next(item for item in snapshot["assessments"]["items"] if item["source_message_id"] == question_id)
    assert assessment["status"] == "CONFIRMED" and assessment["investigation_run_id"] == run_id
    correction_id = str(assessment["correction_message_id"])
    correction = next(item for item in snapshot["messages"]["items"] if item["message_id"] == correction_id)
    assert correction["application_state"] == "APPLIED_TO_RUN" and correction["applied_run_id"] == run_id
    payload = {"confirmed": snapshot, "ids": {"task_id": task_id, "question": question_id,
               "correction": correction_id, "run": run_id, "receipt": receipt_id, "result_state": state}}
    _project_real_api_json(tmp_path, f"correction-{state.lower()}", "correction", payload)
