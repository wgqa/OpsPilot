from __future__ import annotations

import asyncio
import json
from pathlib import Path

from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage

from opspilot.config import MODEL_API_KEY, MODEL_NAME
from opspilot.domain.d2 import MAX_MODEL_CALLS, attempt_counts, reserve_attempt
from opspilot.domain.database import connect, reset_fixture
from opspilot.domain.s3_assets import load_knowledge
from opspilot.domain.task_control import claim_task_run, trusted_identity
from opspilot.s3_investigation import S3Nodes
from opspilot.web.app import create_app
from tests.test_m4_autonomy_c1_followup_red import _diagnosed_task


ORIGIN = "http://testserver"
PASSWORD = "support-test-password"


def _readonly_run(tmp_path: Path, monkeypatch) -> tuple[Path, str, str, str, str]:
    db = tmp_path / "c1-acceptance-fix.sqlite3"
    reset_fixture(db, "S1_POS")
    session_id, task_id, diagnosis_run_id, diagnosis_id = _diagnosed_task(db)
    from tests.legacy_budget_support import use_legacy_s3_budget_fixture
    use_legacy_s3_budget_fixture(db, task_id)  # Original FIX-01 targets an existing 8/6 Task.
    app = create_app(
        db_path=db,
        start_worker=False,
        credentials={"support-a": PASSWORD},
        expected_origin=ORIGIN,
        heartbeat_seconds=0.05,
    )
    monkeypatch.setenv(MODEL_API_KEY, "local-test-key")
    monkeypatch.setenv(MODEL_NAME, "c1-acceptance-fix-deterministic")
    monkeypatch.setattr(
        "opspilot.domain.investigation_updates.classify_input",
        lambda **_kwargs: {
            "intent": "FOLLOW_UP", "change_summary": "",
            "readonly_action": "INVESTIGATE",
        },
    )
    with TestClient(app, raise_server_exceptions=False) as client:
        login = client.post(
            "/api/auth/login", headers={"Origin": ORIGIN},
            json={"actor_id": "support-a", "password": PASSWORD},
        )
        assert login.status_code == 200, login.text
        headers = {"Origin": ORIGIN, "X-CSRF-Token": login.json()["csrf_token"]}
        message = client.post(
            f"/api/sessions/{session_id}/messages",
            headers={**headers, "Idempotency-Key": "c1-fix-follow-up-message"},
            json={
                "task_id": task_id,
                "input_kind": "CHAT_READONLY",
                "body": "请解释当前绑定协议的接收确认含义。",
            },
        )
        assert message.status_code == 202, message.text
        source_message_id = str(message.json()["message_id"])
        proposal = client.post(
            f"/api/tasks/{task_id}/investigation-updates/proposals",
            headers={**headers, "Idempotency-Key": source_message_id},
            json={"source_message_id": source_message_id},
        )
        assert proposal.status_code == 200, proposal.text
        assert proposal.json()["follow_up_action"] == "INVESTIGATE"
        run_id = str(proposal.json()["investigation_run_id"])

    claim_task_run(db, trusted_identity(db, "support-a"), run_id)
    return db, task_id, diagnosis_run_id, diagnosis_id, run_id


def _business_snapshot(db: Path, task_id: str, diagnosis_id: str) -> dict[str, object]:
    with connect(db) as connection:
        diagnoses = [dict(row) for row in connection.execute(
            "SELECT receipt_id,outcome,body_json,digest FROM s3_diagnoses WHERE task_id=? ORDER BY rowid",
            (task_id,),
        ).fetchall()]
        task_status = str(connection.execute(
            "SELECT status FROM task_bindings WHERE task_id=?", (task_id,),
        ).fetchone()[0])
        control_revision = int(connection.execute(
            "SELECT control_revision FROM task_controls WHERE task_id=?", (task_id,),
        ).fetchone()[0])
        writes = {
            table: int(connection.execute(
                f"SELECT COUNT(*) FROM {table} WHERE task_id=?", (task_id,),
            ).fetchone()[0])
            for table in (
                "d3_plans", "d3_approvals", "d3_action_intents", "d3_action_ledgers",
                "s3_handoff_queue_entries", "s3_handoff_receipts",
            )
        }
        outbox_count = int(connection.execute(
            "SELECT COUNT(*) FROM domain_outbox WHERE task_id=?", (task_id,),
        ).fetchone()[0])
    return {
        "diagnoses": diagnoses,
        "original_diagnosis": next(row for row in diagnoses if row["receipt_id"] == diagnosis_id),
        "task_status": task_status,
        "control_revision": control_revision,
        "writes": writes,
        "outbox_count": outbox_count,
    }


def _trace_snapshot(snapshot: dict[str, object]) -> dict[str, object]:
    diagnoses = snapshot["diagnoses"]
    return {
        "diagnosis_count": len(diagnoses),
        "diagnosis_ids": [row["receipt_id"] for row in diagnoses],
        "diagnosis_digests": [row["digest"] for row in diagnoses],
        "task_status": snapshot["task_status"],
        "control_revision": snapshot["control_revision"],
        "writes": snapshot["writes"],
        "outbox_count": snapshot["outbox_count"],
    }


def test_readonly_followup_budget_exhaustion_never_persists_business_diagnosis(
    tmp_path: Path, monkeypatch,
) -> None:
    db, task_id, _diagnosis_run_id, diagnosis_id, run_id = _readonly_run(tmp_path, monkeypatch)
    before = _business_snapshot(db, task_id, diagnosis_id)
    for index in range(MAX_MODEL_CALLS):
        reserve_attempt(
            db, task_id, "MODEL", MAX_MODEL_CALLS,
            call_id=f"c1-fix-exhausted-budget-{index}", run_id=run_id,
        )
    assert attempt_counts(db, task_id)["MODEL"] == MAX_MODEL_CALLS

    class ProviderMustNotBeCalled:
        async def ainvoke(self, _messages):
            raise AssertionError("provider called after Task MODEL budget exhaustion")

    node = S3Nodes(
        db, task_id, run_id, ProviderMustNotBeCalled(), "c1-test-model", None, [],
        readonly_followup=True,
    )
    result = asyncio.run(node.report({"evidence_ids": [], "diagnosis_draft": {}}))
    after = _business_snapshot(db, task_id, diagnosis_id)
    with connect(db) as connection:
        readonly_row = connection.execute(
            "SELECT run_id,result_state,answer_text,source_refs_json,result_json,result_digest,reason_code "
            "FROM c1_readonly_followup_runs WHERE run_id=?", (run_id,),
        ).fetchone()
        readonly_result = dict(readonly_row) if readonly_row is not None else None
    trace = {
        "case_id": "C1-FIX-01-BUDGET-EXHAUSTED",
        "task_id": task_id,
        "run_id": run_id,
        "existing_diagnosis_id": diagnosis_id,
        "model_attempts": attempt_counts(db, task_id)["MODEL"],
        "model_limit": MAX_MODEL_CALLS,
        "report_ref": result.get("report_ref"),
        "readonly_result_state": result.get("readonly_result_state"),
        "readonly_result_reason": readonly_result["reason_code"] if readonly_result else None,
        "before": _trace_snapshot(before),
        "after": _trace_snapshot(after),
    }
    print("C1_ACCEPTANCE_FIX_TRACE " + json.dumps(trace, ensure_ascii=False, sort_keys=True))

    assert result.get("readonly_result_state") in {"PARTIAL", "NOT_COMPLETED"}
    assert result.get("report_ref") is None
    assert after["diagnoses"] == before["diagnoses"]
    assert after["task_status"] == before["task_status"]
    assert after["control_revision"] == before["control_revision"]
    assert after["writes"] == before["writes"]
    assert after["outbox_count"] == before["outbox_count"]
    assert readonly_result is not None, "exhausted readonly Run did not persist a readonly result"
    assert readonly_result["result_state"] in {"PARTIAL", "NOT_COMPLETED"}
    assert readonly_result["reason_code"] == "FOLLOWUP_BUDGET_OR_PROVIDER_EXHAUSTED"
    assert json.loads(str(readonly_result["result_json"]))["diagnosis_persisted"] is False


def test_readonly_followup_can_explain_from_current_knowledge_without_more_tools(
    tmp_path: Path, monkeypatch,
) -> None:
    db, task_id, _diagnosis_run_id, diagnosis_id, run_id = _readonly_run(tmp_path, monkeypatch)
    before = _business_snapshot(db, task_id, diagnosis_id)
    knowledge = next(
        item for item in load_knowledge(contract_version=2)
        if item["document_id"] == "receiver-ack-contract-v2"
    )
    knowledge_ref = {
        key: knowledge[key]
        for key in ("document_id", "version", "digest", "source", "valid_from")
    }

    class ExplanationOnlyModel:
        async def ainvoke(self, messages):
            assert "retrieved_knowledge_method_only" in str(messages[-1].content)
            assert "receiver-ack-contract-v2" in str(messages[-1].content)
            return AIMessage(content=(
                "RESULT: ANSWERED\n"
                "当前绑定协议说明 HTTP 202 是接收确认，不代表下游业务处理完成。"
            ), id="c1-fix-direct-explanation")

    node = S3Nodes(
        db, task_id, run_id, ExplanationOnlyModel(), "c1-test-model", None, [],
        readonly_followup=True,
    )
    result = asyncio.run(node.report({
        "evidence_ids": [],
        "diagnosis_draft": {"s3_knowledge_refs": [knowledge_ref]},
    }))
    after = _business_snapshot(db, task_id, diagnosis_id)
    with connect(db) as connection:
        readonly_row = connection.execute(
            "SELECT run_id,result_state,answer_text,source_refs_json,result_json,result_digest,reason_code "
            "FROM c1_readonly_followup_runs WHERE run_id=?", (run_id,),
        ).fetchone()
        readonly_result = dict(readonly_row) if readonly_row is not None else None
        model_attempts = int(connection.execute(
            "SELECT COUNT(*) FROM d2_attempts WHERE task_id=? AND kind='MODEL'", (task_id,),
        ).fetchone()[0])
        mcp_attempts = int(connection.execute(
            "SELECT COUNT(*) FROM d2_attempts WHERE task_id=? AND kind='MCP'", (task_id,),
        ).fetchone()[0])
    trace = {
        "case_id": "C1-FIX-02-CURRENT-SOURCE-DIRECT-EXPLANATION",
        "task_id": task_id,
        "run_id": run_id,
        "existing_diagnosis_id": diagnosis_id,
        "knowledge_document_id": knowledge_ref["document_id"],
        "knowledge_version": knowledge_ref["version"],
        "knowledge_digest": knowledge_ref["digest"],
        "model_attempts": model_attempts,
        "mcp_attempts": mcp_attempts,
        "readonly_result_state": result.get("readonly_result_state"),
        "readonly_result_reason": readonly_result["reason_code"] if readonly_result else None,
        "source_refs": json.loads(str(readonly_result["source_refs_json"])) if readonly_result else [],
        "before": _trace_snapshot(before),
        "after": _trace_snapshot(after),
    }
    print("C1_ACCEPTANCE_FIX_TRACE " + json.dumps(trace, ensure_ascii=False, sort_keys=True))

    assert readonly_result is not None, "readonly Run did not persist its result"
    assert result["readonly_result_state"] == "ANSWERED"
    assert readonly_result["reason_code"] is None
    assert any(
        item.get("kind") == "KNOWLEDGE"
        and item.get("document_id") == "receiver-ack-contract-v2"
        for item in json.loads(str(readonly_result["source_refs_json"]))
    )
    assert model_attempts == 1
    assert mcp_attempts == 3
    assert after["diagnoses"] == before["diagnoses"]
    assert after["task_status"] == before["task_status"]
    assert after["control_revision"] == before["control_revision"]
    assert after["writes"] == before["writes"]
    assert after["outbox_count"] == before["outbox_count"]

