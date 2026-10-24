from __future__ import annotations

import asyncio
import json
from pathlib import Path

from langchain_core.messages import AIMessage

from opspilot.domain.context_engineering import ContextBudgetExceeded, estimate_messages_tokens
from opspilot.domain.database import connect, reset_fixture
from opspilot.domain.d2 import canonical_json
from opspilot.domain.investigation_updates import complete_assessment, reserve_assessment
from opspilot.domain.task_control import claim_task_run, trusted_identity
from opspilot.s3_investigation import S3Nodes
from test_m4_c1_hf_01 import (
    _diagnosed_task,
    _new_user_message,
    _persist_previous_followup,
)


class CapturingModel:
    def __init__(self) -> None:
        self.messages = []

    def bind_tools(self, *_args, **_kwargs):
        return self

    async def ainvoke(self, messages):
        self.messages.append(messages)
        return AIMessage(content="RESULT: ANSWERED\n依据当前上下文作出只读解释。")


def _start_investigation_run(
    db: Path, session_id: str, task_id: str, *, suffix: str,
) -> tuple[str, str]:
    identity = trusted_identity(db, "support-a")
    source = _new_user_message(
        db, session_id, task_id,
        body="你刚才引用的协议为什么不能证明接收方已经处理完成？",
        suffix=suffix,
    )
    message_id = str(source["message_id"])
    assessment = reserve_assessment(
        db, identity, task_id=task_id, source_message_id=message_id,
        idempotency_key=message_id, model_id="c1-s3-wire-deterministic",
    )["prepared"]
    routed = complete_assessment(
        db, identity=identity, assessment_id=str(assessment["assessment_id"]),
        attempt_id=str(assessment["attempt_id"]),
        classification={"intent": "FOLLOW_UP", "change_summary": "", "readonly_action": "INVESTIGATE"},
    )
    run_id = str(routed["investigation_run_id"])
    claim_task_run(db, identity, run_id)
    return message_id, run_id


def _business_snapshot(db: Path, task_id: str) -> dict[str, object]:
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
        "diagnoses": diagnoses, "task_status": task_status,
        "control_revision": control_revision, "writes": writes,
        "outbox_count": outbox_count,
    }


def _call_provenance(db: Path, call_id: str) -> dict[str, object]:
    with connect(db) as connection:
        row = connection.execute(
            """SELECT summary_refs_json,excluded_sources_json,selected_knowledge_json,
                      context_blocks_json,context_budget_json,model_status
               FROM d5_context_provenance WHERE call_id=?""",
            (call_id,),
        ).fetchone()
    assert row is not None
    value = dict(row)
    for key in (
        "summary_refs_json", "excluded_sources_json", "selected_knowledge_json",
        "context_blocks_json", "context_budget_json",
    ):
        value[key.removesuffix("_json")] = json.loads(str(value.pop(key)))
    return value


def _node(db: Path, task_id: str, run_id: str, model: CapturingModel) -> S3Nodes:
    return S3Nodes(
        db, task_id, run_id, model, "c1-s3-wire-deterministic", None, [],
        readonly_followup=True, memory_enabled=False,
    )


def test_c1_wire_01_s3_model_call_sends_prior_followup_and_records_provenance(tmp_path: Path) -> None:
    db = tmp_path / "c1-wire-valid.sqlite3"
    reset_fixture(db, "S1_POS")
    session_id, task_id, _, diagnosis_id = _diagnosed_task(db)
    prior = _persist_previous_followup(db, session_id, task_id, suffix="wire-valid")
    _message_id, run_id = _start_investigation_run(
        db, session_id, task_id, suffix="wire-valid-current",
    )
    before = _business_snapshot(db, task_id)
    model = CapturingModel()
    node = _node(db, task_id, run_id, model)

    state = {"evidence_ids": [], "diagnosis_draft": {}}
    call_id, _calls, _text = asyncio.run(node.model_call(state))
    explain_call_id, _explain_calls, _explain_text = asyncio.run(
        node.model_call(state, explain=True),
    )

    assert len(model.messages) == 2
    body = json.loads(str(model.messages[0][-1].content))
    explain_body = json.loads(str(model.messages[1][-1].content))
    history = body["prior_readonly_followups"]
    explain_history = explain_body["prior_readonly_followups"]
    assert len(history) == 1
    assert explain_history == history
    assert history[0]["run_id"] == prior["run_id"]
    assert history[0]["result_digest"] == prior["result_digest"]
    assert "receiver-ack-contract-v2" in history[0]["answer_text"]
    assert history[0]["source_authority"] == "HISTORICAL_RESULT_ONLY"
    knowledge_ref = next(ref for ref in history[0]["source_refs"] if ref["kind"] == "KNOWLEDGE")
    assert knowledge_ref["document_id"] == prior["document_id"]
    assert knowledge_ref["version"] == prior["document_version"]
    assert knowledge_ref["digest"] == prior["document_digest"]
    assert knowledge_ref["currentness"] == "CURRENT_APPLICABLE"
    old_evidence = next(ref for ref in history[0]["source_refs"] if ref["kind"] == "EVIDENCE")
    assert old_evidence["currentness"] == "HISTORICAL_RUN_ONLY"
    assert all(item.get("evidence_id") != old_evidence["evidence_id"]
               for item in body["current_mcp_evidence"])
    assert all(item.get("evidence_id") != old_evidence["evidence_id"]
               for item in explain_body["current_mcp_evidence"])

    provenance = _call_provenance(db, call_id)
    summary = next(item for item in provenance["summary_refs"]
                   if item.get("kind") == "PRIOR_READONLY_FOLLOWUP")
    assert summary["run_id"] == prior["run_id"]
    assert summary["result_digest"] == prior["result_digest"]
    assert summary["source_refs"]
    assert any(ref.get("currentness") == "CURRENT_APPLICABLE" for ref in summary["source_refs"])
    assert any(ref.get("currentness") == "HISTORICAL_RUN_ONLY" for ref in summary["source_refs"])
    assert summary["currentness"] == "HISTORICAL_RESULT_ONLY"
    assert summary["exclusion_reason"] is None
    block = next(item for item in provenance["context_blocks"]
                 if item["category"] == "PRIOR_READONLY_FOLLOWUP")
    assert prior["run_id"] in block["source_refs"]
    assert prior["result_digest"] in block["source_refs"]
    assert block["estimated_tokens"] > 0
    assert provenance["context_budget"]["estimated_input_tokens"] >= 1
    assert provenance["context_budget"]["estimated_input_tokens"] <= provenance["context_budget"]["input_budget_tokens"]
    assert provenance["model_status"] == "OK"
    explain_provenance = _call_provenance(db, explain_call_id)
    assert any(item.get("kind") == "PRIOR_READONLY_FOLLOWUP"
               for item in explain_provenance["summary_refs"])
    assert explain_provenance["context_budget"]["estimated_input_tokens"] <= explain_provenance["context_budget"]["input_budget_tokens"]
    assert explain_provenance["model_status"] == "OK"
    after = _business_snapshot(db, task_id)
    assert after == before
    assert diagnosis_id in {item["receipt_id"] for item in after["diagnoses"]}


def test_c1_wire_02_stale_knowledge_is_historical_and_exclusion_is_recorded(
    tmp_path: Path, monkeypatch,
) -> None:
    import opspilot.domain.s3_assets as assets

    db = tmp_path / "c1-wire-stale.sqlite3"
    reset_fixture(db, "S1_POS")
    session_id, task_id, _, _ = _diagnosed_task(db)
    prior = _persist_previous_followup(db, session_id, task_id, suffix="wire-stale")
    _message_id, run_id = _start_investigation_run(
        db, session_id, task_id, suffix="wire-stale-current",
    )
    before = _business_snapshot(db, task_id)
    original = assets.load_knowledge(contract_version=2)
    replaced = [dict(item) for item in original]
    target = next(item for item in replaced if item["document_id"] == prior["document_id"])
    target.update({"version": "wire-replacement-v3", "digest": "a" * 64})
    monkeypatch.setattr(assets, "load_knowledge", lambda *, contract_version=None: replaced)
    model = CapturingModel()

    call_id, _calls, _text = asyncio.run(_node(db, task_id, run_id, model).model_call(
        {"evidence_ids": [], "diagnosis_draft": {}},
    ))

    body = json.loads(str(model.messages[0][-1].content))
    history = body["prior_readonly_followups"][0]
    assert history["run_id"] == prior["run_id"]
    assert "receiver-ack-contract-v2" in history["answer_text"]
    knowledge_ref = next(ref for ref in history["source_refs"] if ref["kind"] == "KNOWLEDGE")
    assert knowledge_ref["currentness"] == "HISTORICAL_SOURCE_STALE"
    assert knowledge_ref["reason"] == "KNOWLEDGE_REMOVED_EXPIRED_OR_CHANGED"
    assert body["retrieved_knowledge_method_only"] == []
    evidence_ref = next(ref for ref in history["source_refs"] if ref["kind"] == "EVIDENCE")
    assert evidence_ref["currentness"] == "HISTORICAL_RUN_ONLY"
    assert all(item.get("evidence_id") != evidence_ref["evidence_id"]
               for item in body["current_mcp_evidence"])

    provenance = _call_provenance(db, call_id)
    assert provenance["selected_knowledge"] == []
    summary = next(item for item in provenance["summary_refs"]
                   if item.get("kind") == "PRIOR_READONLY_FOLLOWUP")
    assert summary["currentness"] == "HISTORICAL_RESULT_ONLY"
    assert summary["exclusion_reason"] == "KNOWLEDGE_REMOVED_EXPIRED_OR_CHANGED"
    assert any(ref.get("currentness") == "HISTORICAL_SOURCE_STALE"
               and ref.get("reason") == "KNOWLEDGE_REMOVED_EXPIRED_OR_CHANGED"
               for ref in summary["source_refs"])
    assert any(item.get("reason") == "KNOWLEDGE_REMOVED_EXPIRED_OR_CHANGED"
               for item in provenance["excluded_sources"])
    assert _business_snapshot(db, task_id) == before


def test_c1_wire_03_no_history_keeps_s3_model_call_available(tmp_path: Path) -> None:
    db = tmp_path / "c1-wire-empty.sqlite3"
    reset_fixture(db, "S1_POS")
    session_id, task_id, _, _ = _diagnosed_task(db)
    _message_id, run_id = _start_investigation_run(
        db, session_id, task_id, suffix="wire-empty-current",
    )
    model = CapturingModel()

    call_id, _calls, _text = asyncio.run(_node(db, task_id, run_id, model).model_call(
        {"evidence_ids": [], "diagnosis_draft": {}}, explain=True,
    ))

    assert len(model.messages) == 1
    body = json.loads(str(model.messages[0][-1].content))
    assert body.get("prior_readonly_followups", []) == []
    provenance = _call_provenance(db, call_id)
    assert not any(item.get("kind") == "PRIOR_READONLY_FOLLOWUP"
                   for item in provenance["summary_refs"])
    assert provenance["context_budget"]["estimated_input_tokens"] > 0
    assert provenance["model_status"] == "OK"


def test_c1_wire_04_knowledge_change_after_prompt_blocks_provider_call(tmp_path: Path, monkeypatch) -> None:
    import opspilot.domain.s3_assets as assets

    db = tmp_path / "c1-wire-preflight.sqlite3"
    reset_fixture(db, "S1_POS")
    session_id, task_id, _, _ = _diagnosed_task(db)
    prior = _persist_previous_followup(db, session_id, task_id, suffix="wire-preflight")
    _message_id, run_id = _start_investigation_run(
        db, session_id, task_id, suffix="wire-preflight-current",
    )
    original_docs = assets.load_knowledge(contract_version=2)
    replacement = [dict(item) for item in original_docs]
    target = next(item for item in replacement if item["document_id"] == prior["document_id"])
    target.update({"version": "wire-preflight-v3", "digest": "b" * 64})
    model = CapturingModel()
    node = _node(db, task_id, run_id, model)
    original_prompt = node.prompt
    calls = 0

    def invalidate_after_first_prompt(state, *, normalize=False, explain=False):
        nonlocal calls
        result = original_prompt(state, normalize=normalize, explain=explain)
        calls += 1
        if calls == 1:
            monkeypatch.setattr(assets, "load_knowledge", lambda *, contract_version=None: replacement)
        return result

    monkeypatch.setattr(node, "prompt", invalidate_after_first_prompt)
    try:
        asyncio.run(node.model_call({"evidence_ids": [], "diagnosis_draft": {}}))
    except RuntimeError as error:
        assert str(error) == "S3_CONTEXT_INVALIDATED_BEFORE_PROVIDER"
    else:
        raise AssertionError("stale prior Knowledge was sent to the S3 model")

    assert calls >= 2
    assert model.messages == []


def test_c1_wire_05_prior_followup_growth_stays_inside_context_budget(tmp_path: Path, monkeypatch) -> None:
    import opspilot.investigator as investigator

    db = tmp_path / "c1-wire-budget.sqlite3"
    reset_fixture(db, "S1_POS")
    session_id, task_id, _, _ = _diagnosed_task(db)
    _persist_previous_followup(db, session_id, task_id, suffix="wire-budget")
    _message_id, run_id = _start_investigation_run(
        db, session_id, task_id, suffix="wire-budget-current",
    )
    model = CapturingModel()
    node = _node(db, task_id, run_id, model)
    messages, _metadata = node.prompt({"evidence_ids": [], "diagnosis_draft": {}})
    serialized = [{"role": message.type, "content": str(message.content)} for message in messages]
    full_required = estimate_messages_tokens(serialized) + 8
    body_without_history = json.loads(str(messages[-1].content))
    body_without_history["prior_readonly_followups"] = []
    body_without_history["prior_readonly_followup_exclusions"] = []
    body_without_history["prior_followup_authority"] = ""
    without_history = [
        serialized[0],
        {"role": messages[-1].type, "content": canonical_json(body_without_history)},
    ]
    baseline_required = estimate_messages_tokens(without_history) + 8
    assert full_required > baseline_required
    input_budget = (full_required + baseline_required) // 2
    assert baseline_required <= input_budget < full_required
    monkeypatch.setattr(
        investigator,
        "context_budget_for_model",
        lambda model_id: {"model_id": model_id, "input_budget_tokens": input_budget},
    )

    try:
        asyncio.run(node.model_call({"evidence_ids": [], "diagnosis_draft": {}}))
    except ContextBudgetExceeded as error:
        assert error.code == "INVESTIGATOR_CONTEXT_EXCEEDS_BUDGET"
        assert error.required_tokens == full_required
        assert error.input_budget_tokens == input_budget
    else:
        raise AssertionError("prior follow-up context bypassed the input budget")

    assert model.messages == []
    with connect(db) as connection:
        model_attempts = int(connection.execute(
            "SELECT COUNT(*) FROM d2_attempts WHERE task_id=? AND run_id=? AND kind='MODEL'",
            (task_id, run_id),
        ).fetchone()[0])
    assert model_attempts == 0

