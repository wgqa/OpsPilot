"""Trusted S1 setup shared by recovery tests and their child processes."""

from __future__ import annotations

import json
from pathlib import Path

from opspilot.domain.d2 import get_task_binding
from opspilot.domain.d3 import (
    create_plan_from_gate,
    get_task_action_state,
    get_task_outcome,
    revalidate_approved_plan,
)
from opspilot.domain.database import get_integration_info
from opspilot.domain.task_control import (
    claim_task_run,
    create_session,
    create_task_with_initial_run,
    finish_task_run,
    submit_web_plan_approval,
    trusted_identity,
)


class NoRecoveryModel:
    """A resumed D3 checkpoint must never return to model investigation."""

    def __init__(self, **_configuration: object) -> None:
        pass

    def bind_tools(self, *_args: object, **_kwargs: object) -> None:
        raise AssertionError("D3 recovery unexpectedly tried to bind model tools")

    async def ainvoke(self, *_args: object, **_kwargs: object) -> None:
        raise AssertionError("D3 recovery unexpectedly tried to call a model")


def start_s1_investigation(db: Path, case: str) -> tuple[dict[str, object], str]:
    owner = trusted_identity(db, "support-a")
    session = create_session(db, owner)
    created = create_task_with_initial_run(
        db, owner, session_id=str(session["session_id"]),
        service_id="orders-demo", integration_id="integration-a", ticket_id="INC-A-001",
        initial_message="The orders API returns HTTP 401 after credential rotation.",
        idempotency_key=case,
    )
    run_id = str(created["run_id"])
    claim_task_run(db, owner, run_id)
    binding = get_task_binding(db, str(created["task_id"]))
    return {**binding, "session_id": created["session_id"]}, run_id


def plan_s1_repair(
    db: Path, task_id: str, source_run_id: str, gate: dict[str, object],
) -> dict[str, object]:
    plan = create_plan_from_gate(db, task_id, "support-a", gate, run_id=source_run_id)
    finish_task_run(db, trusted_identity(db, "support-a"), source_run_id, "WAITING_APPROVAL")
    return plan


def approve_s1_repair(db: Path, task_id: str, plan_hash: str) -> dict[str, object]:
    return submit_web_plan_approval(
        db, trusted_identity(db, "approver-a"), task_id=task_id, plan_hash=plan_hash,
        decision="APPROVED", idempotency_key=f"recovery-approve-{plan_hash}",
    )


def claim_and_revalidate_s1_repair(
    db: Path, approval: dict[str, object], live_api: str,
) -> dict[str, object]:
    run_id = str(approval["resume_run_id"])
    claim_task_run(db, trusted_identity(db, "support-a"), run_id)
    receipt = revalidate_approved_plan(
        db, str(approval["task_id"]), str(approval["plan_hash"]),
        str(approval["approval_id"]), "executor-a", live_api, run_id=run_id,
    )
    assert receipt["status"] == "VALID", receipt["reason_code"]
    assert receipt["run_id"] == run_id and len(receipt["evidence_ids"]) == 4
    probe = receipt["facts"]["endpoint_probe"]["facts"]
    print(json.dumps({
        "event": "approval_resume_revalidated",
        "task_id": receipt["task_id"], "run_id": run_id,
        "source_run_id": approval["source_run_id"], "approval_id": receipt["approval_id"],
        "plan_hash": receipt["plan_hash"], "receipt_id": receipt["receipt_id"],
        "content_digest": receipt["content_digest"], "evidence_ids": receipt["evidence_ids"],
        "observed_at": receipt["observed_at"],
        "http_status": probe["http_status"], "request_id": probe["request_id"],
        "auth_event_id": probe["auth_event_id"], "route": probe["route"],
    }, sort_keys=True), flush=True)
    return receipt


def recovery_snapshot(db: str | Path, task_id: str) -> dict[str, object]:
    """Capture the real Domain state without serializing credentials or headers."""
    state = get_task_action_state(db, task_id, "support-a")
    outcome = get_task_outcome(db, task_id, "support-a")
    integration = get_integration_info(db, "tenant-a", "integration-a")
    revalidation = None
    if outcome["revalidation"] is not None:
        receipt = state["revalidation_receipts"][-1]
        probe = json.loads(str(receipt["facts_json"])).get("endpoint_probe", {}).get("facts", {})
        revalidation = {
            **outcome["revalidation"],
            "evidence_ids": json.loads(str(receipt["evidence_ids_json"])),
            "probe": {
                key: probe[key] for key in (
                    "http_status", "request_id", "auth_event_id", "route", "principal_id",
                    "integration_id", "service_id", "auth_event_scope_valid",
                ) if key in probe
            },
        }
    return {
        "task_id": task_id,
        "task_status": outcome["task_status"],
        "business_outcome": outcome["business_outcome"],
        "plan": outcome["plan"],
        "resume_run": outcome["resume_run"],
        "revalidation": revalidation,
        "config_version": integration["config_version"],
        "credential_ref": integration["credential_ref"],
        "permissions": {item["action_kind"]: item["state"] for item in state["permissions"]},
        "intents": [
            {key: row[key] for key in ("action_kind", "action_id", "request_digest")}
            for row in state["action_intents"]
        ],
        "ledgers": [
            {key: row[key] for key in ("action_kind", "action_id", "ledger_id", "status")}
            for row in state["action_ledgers"]
        ],
        "verification_id": (outcome["verification"] or {}).get("verification_id"),
        "verification_http_status": (outcome["verification"] or {}).get("response_status"),
        "report_ref": (outcome["frozen_report"] or {}).get("report_ref"),
        "delivery_id": (outcome["delivery"] or {}).get("delivery_id"),
        "ticket_entries": outcome["ticket_entry_count"],
    }
