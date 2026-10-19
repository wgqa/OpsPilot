from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sqlite3
from typing import Any

from opspilot.domain.database import connect
from opspilot.domain.d2 import canonical_json, digest_json


PROBLEM_TYPE = "auth_401"
S2_PROBLEM_TYPE = "auth_403_scope"
MEMORY_SUMMARY = (
    "历史案例提示：先核对主体状态、认证策略、集成配置和真实业务 Probe。"
    "只用当前任务的 MCP Evidence 交给确定性门禁判断；历史经验不代表当前事实、根因或授权。"
)
MAX_MEMORY_RESULTS = 1
MEMORY_SCHEMA_VERSION = "opspilot-case-memory-v1"
MEMORY_AUTHORITY = "HISTORICAL_METHOD_HINT_ONLY"


class MemoryError(RuntimeError):
    pass


class MemoryScopeDenied(MemoryError):
    pass


class MemorySourceRejected(MemoryError):
    pass


class ContextAssetInvalidated(MemoryError):
    pass


class SkillCompatibilityError(MemoryError):
    pass


class MemoryIdempotencyConflict(MemoryError):
    pass


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _now_text() -> str:
    return _now().isoformat(timespec="milliseconds")


def _parse_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)


def project_id_for_service(service_id: str) -> str:
    """D5 demo project scope; derived from trusted TaskBinding, never model input."""
    if not service_id or len(service_id) > 64:
        raise ValueError("Invalid trusted service ID.")
    return f"service:{service_id}"


def _row_dict(row: sqlite3.Row) -> dict[str, object]:
    result = dict(row)
    result["source_evidence_ids"] = json.loads(str(result.pop("source_evidence_ids_json")))
    result["applicability_constraints"] = json.loads(str(result.pop("applicability_constraints_json")))
    result["source_refs"] = json.loads(str(result.pop("source_refs_json", "[]")))
    result["experience"] = json.loads(str(result.pop("experience_json", "{}")))
    return result


def _trusted_binding(connection: sqlite3.Connection, task_id: str) -> dict[str, object]:
    row = connection.execute(
        """SELECT b.* FROM task_bindings AS b
           JOIN trusted_operators AS owner ON owner.actor_id = b.actor_id
             AND owner.tenant_id = b.tenant_id AND owner.role = 'SUPPORT'
           WHERE b.task_id = ?""",
        (task_id,),
    ).fetchone()
    if row is None:
        raise MemoryScopeDenied("Trusted TaskBinding is unavailable.")
    return dict(row)


def _require_memory_operator(
    connection: sqlite3.Connection, actor_id: str, tenant_id: str, role: str | None = None
) -> dict[str, object]:
    row = connection.execute(
        "SELECT actor_id, tenant_id, role FROM trusted_operators WHERE actor_id = ?",
        (actor_id,),
    ).fetchone()
    if row is None or str(row["tenant_id"]) != tenant_id:
        raise MemoryScopeDenied("Memory actor is outside the trusted tenant scope.")
    if role is not None and str(row["role"]) != role:
        raise MemoryScopeDenied(f"Memory actor must have {role} role.")
    return dict(row)


def _evidence_digest_matches(row: sqlite3.Row | dict[str, object]) -> bool:
    item = dict(row)
    try:
        observed_versions = json.loads(str(item["observed_versions_json"]))
        facts = json.loads(str(item["facts_json"]))
        payload = {
            "tenant_id": str(item["tenant_id"]), "task_id": str(item["task_id"]),
            "fact_type": str(item["fact_type"]), "resource_id": str(item["resource_id"]),
            "principal_id": str(item["principal_id"]), "data_source": str(item["data_source"]),
            "observed_versions": observed_versions, "facts": facts,
            "trust_class": str(item["trust_class"]),
        }
    except (KeyError, json.JSONDecodeError, TypeError):
        return False
    return digest_json(payload) == str(item.get("digest", ""))


def _source_for_s1_task(connection: sqlite3.Connection, task_id: str) -> dict[str, object]:
    binding = _trusted_binding(connection, task_id)
    rows = connection.execute(
        """SELECT l.ledger_id, l.action_id, l.plan_hash, l.before_version, l.after_version,
                  l.result_digest AS ledger_result_digest, i.tenant_id, v.verification_id,
                  v.service_id, v.integration_id, v.principal_id, v.business_route,
                  v.response_status, v.business_assertions_json, v.recovery_verified,
                  v.result_digest AS verification_result_digest,
                  r.report_ref, r.verification_id AS report_verification_id,
                  r.repair_action_id AS report_repair_action_id, r.report_version,
                  r.content_digest, r.immutable_content_json
           FROM d3_action_ledgers AS l
           JOIN d3_action_intents AS i ON i.action_id = l.action_id
           JOIN d3_verification_receipts AS v ON v.tenant_id = l.tenant_id
             AND v.task_id = l.task_id AND v.plan_hash = l.plan_hash
             AND v.repair_action_id = l.action_id
           JOIN d3_report_artifacts AS r ON r.tenant_id = v.tenant_id
             AND r.task_id = v.task_id AND r.plan_hash = v.plan_hash
             AND r.repair_action_id = v.repair_action_id
             AND r.verification_id = v.verification_id
           WHERE l.tenant_id = ? AND l.task_id = ? AND l.action_kind = 'REPAIR'
             AND l.status = 'COMMITTED' AND v.recovery_verified = 1
             AND v.response_status = 200
           ORDER BY r.created_at DESC, l.committed_at DESC""",
        (binding["tenant_id"], task_id),
    ).fetchall()
    accepted: list[dict[str, object]] = []
    for raw in rows:
        row = dict(raw)
        if row["tenant_id"] != binding["tenant_id"]:
            continue
        if (row["service_id"], row["integration_id"], row["principal_id"]) != (
            binding["service_id"], binding["integration_id"], binding["principal_id"]
        ):
            continue
        route = connection.execute(
            "SELECT route FROM services WHERE tenant_id = ? AND service_id = ?",
            (binding["tenant_id"], binding["service_id"]),
        ).fetchone()
        if route is None or row["business_route"] != route["route"]:
            continue
        try:
            assertions = json.loads(str(row["business_assertions_json"]))
            report = json.loads(str(row["immutable_content_json"]))
        except (json.JSONDecodeError, TypeError):
            continue
        digest = hashlib.sha256(str(row["immutable_content_json"]).encode("utf-8")).hexdigest()
        if digest != row["content_digest"] or row["report_verification_id"] != row["verification_id"]:
            continue
        try:
            ledger_result_json = str(connection.execute(
                "SELECT result_json FROM d3_action_ledgers WHERE ledger_id = ?", (row["ledger_id"],),
            ).fetchone()["result_json"])
            verification_versions = json.loads(str(connection.execute(
                "SELECT probe_observed_versions_json FROM d3_verification_receipts WHERE verification_id = ?",
                (row["verification_id"],),
            ).fetchone()["probe_observed_versions_json"]))
            stored_assertions = json.loads(str(row["business_assertions_json"]))
        except (KeyError, json.JSONDecodeError, TypeError):
            continue
        if hashlib.sha256(ledger_result_json.encode("utf-8")).hexdigest() != str(row["ledger_result_digest"]):
            continue
        if not isinstance(stored_assertions, dict):
            continue
        response_body_for_digest = stored_assertions.get("response_body")
        request_id_for_digest = stored_assertions.get("request_id")
        auth_event_id_for_digest = stored_assertions.get("auth_event_id")
        base_assertions = {
            key: value for key, value in stored_assertions.items()
            if key not in {"response_body", "request_id", "auth_event_id"}
        }
        verification_payload = {
            "tenant_id": str(row["tenant_id"]), "task_id": task_id,
            "plan_hash": str(row["plan_hash"]), "repair_action_id": str(row["action_id"]),
            "service_id": str(row["service_id"]), "integration_id": str(row["integration_id"]),
            "principal_id": str(row["principal_id"]), "business_route": str(row["business_route"]),
            "request_id": request_id_for_digest, "auth_event_id": auth_event_id_for_digest,
            "observed_versions": verification_versions, "response_status": int(row["response_status"]),
            "response_body": response_body_for_digest, "business_assertions": base_assertions,
            "recovery_verified": bool(row["recovery_verified"]),
        }
        if digest_json(verification_payload) != str(row["verification_result_digest"]):
            continue
        if row["report_repair_action_id"] != row["action_id"] or int(row["report_version"]) != 1:
            continue
        if report.get("schema_version") != "opspilot-d3-report-v1" or report.get("business_outcome") != "RECOVERED":
            continue
        if report.get("task_id") != task_id or report.get("tenant_id") != binding["tenant_id"]:
            continue
        report_ledger = report.get("repair_ledger")
        report_receipt = report.get("verification_receipt")
        if not isinstance(report_ledger, dict) or report_ledger.get("status") != "COMMITTED" or report_ledger.get("action_id") != row["action_id"]:
            continue
        if not isinstance(report_receipt, dict) or (
            report_receipt.get("verification_id") != row["verification_id"]
            or report_receipt.get("recovery_verified") not in (True, 1)
            or report_receipt.get("response_status") != 200
        ):
            continue
        if report.get("plan_hash") != row["plan_hash"]:
            continue
        if not all(assertions.get(key) is True for key in (
            "same_tenant", "same_service", "same_integration", "same_principal",
            "same_business_route", "order_id_matches", "order_status_matches",
            "expected_post_repair_versions",
        )):
            continue
        response_body = assertions.get("response_body")
        if not isinstance(response_body, dict) or response_body.get("order_id") != "demo-order" or response_body.get("status") != "CONFIRMED":
            continue
        if int(report.get("verification_receipt", {}).get("response_status", 0)) != 200:
            continue
        evidence = report.get("evidence")
        if not isinstance(evidence, list):
            continue
        evidence_ids = list(dict.fromkeys(
            str(item.get("evidence_id")) for item in evidence
            if isinstance(item, dict) and isinstance(item.get("evidence_id"), str)
        ))
        if not evidence_ids:
            continue
        evidence_rows = connection.execute(
            """SELECT evidence_id, tenant_id, task_id, digest, fact_type, facts_json,
                      observed_versions_json, resource_id, principal_id, data_source, trust_class
               FROM d2_evidence
               WHERE tenant_id = ? AND task_id = ? AND evidence_id IN (%s)"""
            % ",".join("?" for _ in evidence_ids),
            (binding["tenant_id"], task_id, *evidence_ids),
        ).fetchall()
        if len(evidence_rows) != len(evidence_ids):
            continue
        if any(
            str(item["tenant_id"]) != str(binding["tenant_id"])
            or str(item["task_id"]) != task_id
            or str(item["principal_id"]) != str(binding["principal_id"])
            or str(item["trust_class"]) != "untrusted_tool_observation"
            or not _evidence_digest_matches(item)
            for item in evidence_rows
        ):
            continue
        if any(
            str(item["tenant_id"]) != str(binding["tenant_id"])
            or str(item["task_id"]) != task_id
            for item in evidence_rows
        ):
            continue
        evidence_refs = [
            {
                "kind": "EVIDENCE", "id": str(item["evidence_id"]),
                "digest_or_version": str(item["digest"]),
            }
            for item in evidence_rows
        ]
        source_refs = [
            {
                "kind": "REPAIR_LEDGER", "id": str(row["ledger_id"]),
                "digest_or_version": str(row["ledger_result_digest"]),
            },
            {
                "kind": "VERIFICATION_RECEIPT", "id": str(row["verification_id"]),
                "digest_or_version": str(row["verification_result_digest"]),
            },
            {
                "kind": "FROZEN_REPORT", "id": str(row["report_ref"]),
                "digest_or_version": str(row["content_digest"]),
            },
            *evidence_refs,
        ]
        source_refs.sort(key=lambda item: (str(item["kind"]), str(item["id"])))
        valid_initial_probes: list[dict[str, object]] = []
        for evidence_row in evidence_rows:
            try:
                facts = json.loads(str(evidence_row["facts_json"]))
                versions = json.loads(str(evidence_row["observed_versions_json"]))
            except (json.JSONDecodeError, TypeError):
                continue
            if str(evidence_row["fact_type"]) != "endpoint_probe" or not isinstance(facts, dict):
                continue
            before = versions.get("before") if isinstance(versions, dict) else None
            after = versions.get("after") if isinstance(versions, dict) else None
            if (
                facts.get("http_status") == 401
                and facts.get("service_id") == str(binding["service_id"])
                and facts.get("integration_id") == str(binding["integration_id"])
                and facts.get("principal_id") == str(binding["principal_id"])
                and facts.get("route") == str(row["business_route"])
                and facts.get("auth_event_scope_valid") is True
                and facts.get("versions_stable_during_probe") is True
                and isinstance(before, dict) and isinstance(after, dict)
                and before.get("config_version") == int(row["before_version"])
                and after.get("config_version") == int(row["before_version"])
            ):
                valid_initial_probes.append(facts)
        if not valid_initial_probes:
            continue
        initial_probe = valid_initial_probes[0]
        accepted.append({
            "tenant_id": str(binding["tenant_id"]),
            "project_id": project_id_for_service(str(binding["service_id"])),
            "problem_type": PROBLEM_TYPE,
            "source_outcome": "REPAIRED_VERIFIED",
            "source_task_id": task_id,
            "service_id": str(binding["service_id"]),
            "source_evidence_ids": evidence_ids,
            "source_report_ref": str(row["report_ref"]),
            "source_verification_id": str(row["verification_id"]),
            "source_repair_action_id": str(row["action_id"]),
            "source_refs": source_refs,
            "source_facts": {
                "http_status_before": initial_probe["http_status"],
                "route": str(row["business_route"]),
                "config_version_before": int(row["before_version"]),
                "config_version_after": int(row["after_version"]),
                "verified_http_status": int(row["response_status"]),
                "business_order_id": str(response_body["order_id"]),
                "business_order_status": str(response_body["status"]),
            },
        })
    if not accepted:
        raise MemorySourceRejected(
            "Memory requires a committed same-task REPAIR, verified online 200, frozen report, and checkable Evidence."
        )
    return accepted[0]


def _source_for_s2_task(connection: sqlite3.Connection, task_id: str) -> dict[str, object]:
    binding = _trusted_binding(connection, task_id)
    receipt = connection.execute(
        """SELECT * FROM s2_diagnosis_receipts
           WHERE tenant_id = ? AND task_id = ?
           ORDER BY created_at DESC, rowid DESC LIMIT 1""",
        (binding["tenant_id"], task_id),
    ).fetchone()
    if receipt is None:
        raise MemorySourceRejected("S2 Memory requires a trusted DiagnosisReceipt.")
    if (
        str(receipt["tenant_id"]) != str(binding["tenant_id"])
        or str(receipt["task_id"]) != task_id
        or str(receipt["gate_policy_version"]) != "s2-scope-evidence-v1"
    ):
        raise MemorySourceRejected("S2 DiagnosisReceipt is outside the trusted TaskBinding.")
    try:
        predicate = json.loads(str(receipt["predicate_json"]))
        evidence_ids = json.loads(str(receipt["evidence_ids_json"]))
        evidence_digests = json.loads(str(receipt["evidence_digests_json"]))
        observed_versions = json.loads(str(receipt["observed_versions_json"]))
    except (json.JSONDecodeError, TypeError) as error:
        raise MemorySourceRejected("S2 DiagnosisReceipt source fields are malformed.") from error
    if (
        not isinstance(predicate, dict)
        or predicate.get("authenticated") is not True
        or predicate.get("principal_enabled") is not True
        or predicate.get("resource_binding_valid") is not True
        or predicate.get("authz_outcome") != "DENY"
        or predicate.get("reason_code") != "SCOPE_INSUFFICIENT"
        or not isinstance(predicate.get("missing_scopes"), list)
        or not predicate["missing_scopes"]
        or predicate.get("request_id") != str(receipt["request_id"])
        or int(predicate.get("decision_id", -1)) != int(receipt["decision_id"])
        or not isinstance(evidence_ids, list)
        or not evidence_ids
        or not isinstance(evidence_digests, dict)
        or not isinstance(observed_versions, dict)
    ):
        raise MemorySourceRejected("S2 DiagnosisReceipt does not prove a scoped authenticated denial.")
    evidence_rows = connection.execute(
        """SELECT e.*, a.run_id AS attempt_run_id, a.kind AS attempt_kind,
                  o.status AS observation_status
           FROM d2_evidence e
           JOIN d2_tool_observations o ON o.evidence_id = e.evidence_id AND o.task_id = e.task_id
           JOIN d2_attempts a ON a.attempt_id = o.attempt_id AND a.task_id = o.task_id
           WHERE e.tenant_id = ? AND e.task_id = ? AND a.run_id = ?
             AND e.evidence_id IN (%s) ORDER BY o.rowid"""
        % ",".join("?" for _ in evidence_ids),
        (binding["tenant_id"], task_id, str(receipt["run_id"]), *[str(item) for item in evidence_ids]),
    ).fetchall()
    by_id = {str(row["evidence_id"]): row for row in evidence_rows}
    if set(by_id) != set(str(item) for item in evidence_ids):
        raise MemorySourceRejected("S2 DiagnosisReceipt Evidence is missing or outside its source Run.")
    if {
        evidence_id: str(row["digest"]) for evidence_id, row in by_id.items()
    } != {str(key): str(value) for key, value in evidence_digests.items()}:
        raise MemorySourceRejected("S2 DiagnosisReceipt Evidence digest does not match the stored source.")
    for row in by_id.values():
        if (
            str(row["attempt_kind"]) != "MCP"
            or str(row["attempt_run_id"]) != str(receipt["run_id"])
            or str(row["observation_status"]) != "OK"
            or str(row["principal_id"]) != str(binding["principal_id"])
            or str(row["trust_class"]) != "untrusted_tool_observation"
            or not _evidence_digest_matches(row)
        ):
            raise MemorySourceRejected("S2 source Evidence is not a same-Run trusted-scope MCP observation.")
    probe_rows = [row for row in by_id.values() if str(row["fact_type"]) == "endpoint_probe"]
    authz_rows = [row for row in by_id.values() if str(row["fact_type"]) == "scope_authz_decision"]
    if len(probe_rows) != 1 or len(authz_rows) != 1:
        raise MemorySourceRejected("S2 Memory requires one correlated live Probe and Authz Decision.")
    try:
        probe = json.loads(str(probe_rows[0]["facts_json"]))
        authz = json.loads(str(authz_rows[0]["facts_json"]))
        probe_versions = json.loads(str(probe_rows[0]["observed_versions_json"]))
        receipt_versions = observed_versions
    except (json.JSONDecodeError, TypeError) as error:
        raise MemorySourceRejected("S2 source Evidence is malformed.") from error
    request_id = str(receipt["request_id"])
    if (
        not isinstance(probe, dict) or not isinstance(authz, dict)
        or probe.get("http_status") != 403
        or probe.get("service_id") != str(binding["service_id"])
        or probe.get("integration_id") != str(binding["integration_id"])
        or probe.get("principal_id") != str(binding["principal_id"])
        or probe.get("route") != "/api/orders/demo-order"
        or probe.get("request_id") != request_id
        or authz.get("request_id") != request_id
        or authz.get("decision_id") != int(receipt["decision_id"])
        or authz.get("authn_result_code") != "AUTH_ACCEPTED"
        or authz.get("outcome") != "DENY"
        or authz.get("reason_code") != "SCOPE_INSUFFICIENT"
        or authz.get("missing_scopes") != predicate.get("missing_scopes")
        or probe.get("authz_event_id") != int(receipt["decision_id"])
        or probe_versions != receipt_versions.get(str(probe_rows[0]["evidence_id"]))
        or authz_rows[0]["digest"] != evidence_digests.get(str(authz_rows[0]["evidence_id"]))
    ):
        raise MemorySourceRejected("S2 Probe, Authz Decision, request and receipt are not correlated.")
    authz_event = connection.execute(
        """SELECT z.*, a.result_code AS authn_result_code
           FROM authz_events z JOIN auth_events a ON a.event_id = z.authn_event_id
           WHERE z.request_id = ? AND z.decision_id = ?""",
        (request_id, int(receipt["decision_id"])),
    ).fetchone()
    if (
        authz_event is None
        or str(authz_event["tenant_id"]) != str(binding["tenant_id"])
        or str(authz_event["principal_id"]) != str(binding["principal_id"])
        or str(authz_event["service_id"]) != str(binding["service_id"])
        or str(authz_event["integration_id"]) != str(binding["integration_id"])
        or str(authz_event["route"]) != "/api/orders/demo-order"
        or str(authz_event["outcome"]) != "DENY"
        or str(authz_event["reason_code"]) != "SCOPE_INSUFFICIENT"
        or str(authz_event["authn_result_code"]) != "AUTH_ACCEPTED"
        or int(authz_event["credential_policy_version"]) != int(predicate["credential_policy_version"])
        or int(authz_event["scope_policy_version"]) != int(predicate["scope_policy_version"])
        or int(authz_event["grant_version"]) != int(predicate["grant_version"])
    ):
        raise MemorySourceRejected("S2 source does not match the persisted trusted Authz Decision.")
    try:
        event_scopes = {
            "required_scopes": json.loads(str(authz_event["required_scopes_json"])),
            "granted_scopes": json.loads(str(authz_event["granted_scopes_json"])),
            "missing_scopes": json.loads(str(authz_event["missing_scopes_json"])),
        }
    except (json.JSONDecodeError, TypeError) as error:
        raise MemorySourceRejected("Persisted S2 Authz Decision scopes are malformed.") from error
    if any(
        authz.get(key) != value or predicate.get(key) != value
        for key, value in event_scopes.items()
    ):
        raise MemorySourceRejected("S2 Evidence scope facts do not match the trusted Authz Decision.")
    source_refs: list[dict[str, object]] = [{
        "kind": "DIAGNOSIS_RECEIPT",
        "id": str(receipt["receipt_id"]),
        "digest_or_version": digest_json({
            "receipt_id": str(receipt["receipt_id"]),
            "tenant_id": str(receipt["tenant_id"]),
            "task_id": str(receipt["task_id"]),
            "run_id": str(receipt["run_id"]),
            "request_id": request_id,
            "decision_id": int(receipt["decision_id"]),
            "predicate_json": str(receipt["predicate_json"]),
            "evidence_ids_json": str(receipt["evidence_ids_json"]),
            "evidence_digests_json": str(receipt["evidence_digests_json"]),
            "observed_versions_json": str(receipt["observed_versions_json"]),
        }),
    }]
    source_evidence_ids = [str(item) for item in evidence_ids]
    for evidence_id in source_evidence_ids:
        source_refs.append({
            "kind": "EVIDENCE", "id": evidence_id,
            "digest_or_version": str(by_id[evidence_id]["digest"]),
        })
    outcome = "DIAGNOSED"
    handoff = connection.execute(
        """SELECT h.*, q.entry_id AS joined_entry_id, q.draft_id AS queue_draft_id,
                  q.draft_version AS queue_draft_version, q.draft_digest AS queue_draft_digest,
                  q.queue_status, d.content_digest AS stored_draft_digest,
                  d.receipt_id AS draft_receipt_id
           FROM s2_handoff_receipts h
           JOIN s2_handoff_queue_entries q ON q.entry_id = h.entry_id
             AND q.tenant_id = h.tenant_id AND q.task_id = h.task_id
           JOIN s2_handoff_drafts d ON d.draft_id = h.draft_id
             AND d.tenant_id = h.tenant_id AND d.task_id = h.task_id
           WHERE h.tenant_id = ? AND h.task_id = ?""",
        (binding["tenant_id"], task_id),
    ).fetchone()
    if handoff is not None:
        receipt_payload = {
            "schema_version": 1,
            "tenant_id": str(handoff["tenant_id"]),
            "task_id": str(handoff["task_id"]),
            "handoff_kind": str(handoff["handoff_kind"]),
            "entry_id": str(handoff["entry_id"]),
            "draft_id": str(handoff["draft_id"]),
            "draft_version": int(handoff["draft_version"]),
            "draft_digest": str(handoff["draft_digest"]),
            "operation_id": str(handoff["operation_id"]),
            "canonical_request_digest": str(handoff["canonical_request_digest"]),
            "accepted_by_receiver_ref": str(handoff["accepted_by_receiver_ref"]),
            "accepted_by_actor_id": str(handoff["accepted_by_actor_id"]),
            "accepted_at": str(handoff["accepted_at"]),
            "control_revision": int(handoff["control_revision"]),
            "request_id": str(handoff["request_id"]),
            "decision_id": int(handoff["decision_id"]),
            "credential_policy_version": int(handoff["credential_policy_version"]),
            "scope_policy_version": int(handoff["scope_policy_version"]),
            "grant_version": int(handoff["grant_version"]),
        }
        if (
            str(handoff["handoff_kind"]) != "SCOPE_REVIEW"
            or str(handoff["queue_status"]) not in {"PENDING_REVIEW", "REVIEWED"}
            or str(handoff["request_id"]) != request_id
            or int(handoff["decision_id"]) != int(receipt["decision_id"])
            or str(handoff["queue_draft_id"]) != str(handoff["draft_id"])
            or int(handoff["queue_draft_version"]) != int(handoff["draft_version"])
            or str(handoff["queue_draft_digest"]) != str(handoff["draft_digest"])
            or str(handoff["stored_draft_digest"]) != str(handoff["draft_digest"])
            or str(handoff["draft_receipt_id"]) != str(receipt["receipt_id"])
            or hashlib.sha256(canonical_json(receipt_payload).encode("utf-8")).hexdigest()
                != str(handoff["receipt_digest"])
        ):
            raise MemorySourceRejected("S2 HandoffReceipt or queue entry is not bound to this diagnosis.")
        outcome = "SCOPE_ESCALATED"
        source_refs.extend([
            {
                "kind": "HANDOFF_RECEIPT", "id": str(handoff["receipt_id"]),
                "digest_or_version": str(handoff["receipt_digest"]),
            },
            {
                "kind": "HANDOFF_QUEUE_ENTRY", "id": str(handoff["entry_id"]),
                "digest_or_version": str(handoff["draft_digest"]),
            },
        ])
    source_refs.sort(key=lambda item: (str(item["kind"]), str(item["id"])))
    return {
        "tenant_id": str(binding["tenant_id"]),
        "project_id": project_id_for_service(str(binding["service_id"])),
        "problem_type": S2_PROBLEM_TYPE,
        "source_outcome": outcome,
        "source_task_id": task_id,
        "source_evidence_ids": source_evidence_ids,
        "source_report_ref": None,
        "source_verification_id": None,
        "source_refs": source_refs,
        "source_facts": {
            "http_status": 403,
            "route": str(authz_event["route"]),
            "reason_code": str(authz_event["reason_code"]),
            "required_scopes": json.loads(str(authz_event["required_scopes_json"])),
            "granted_scopes": json.loads(str(authz_event["granted_scopes_json"])),
            "missing_scopes": json.loads(str(authz_event["missing_scopes_json"])),
            "credential_policy_version": int(authz_event["credential_policy_version"]),
            "scope_policy_version": int(authz_event["scope_policy_version"]),
            "grant_version": int(authz_event["grant_version"]),
        },
    }


def _source_for_task(
    connection: sqlite3.Connection, task_id: str, problem_type: str | None = None,
) -> dict[str, object]:
    if problem_type in (None, PROBLEM_TYPE):
        try:
            return _source_for_s1_task(connection, task_id)
        except MemorySourceRejected:
            if problem_type == PROBLEM_TYPE:
                raise
    if problem_type in (None, S2_PROBLEM_TYPE):
        return _source_for_s2_task(connection, task_id)
    raise MemorySourceRejected("Unsupported episodic Memory problem type.")


def _memory_content_digest(row: sqlite3.Row | dict[str, object]) -> str:
    memory = dict(row)
    try:
        source_refs_value = memory.get("source_refs_json", memory.get("source_refs", []))
        experience_value = memory.get("experience_json", memory.get("experience", {}))
        source_refs = json.loads(source_refs_value) if isinstance(source_refs_value, str) else source_refs_value
        experience = json.loads(experience_value) if isinstance(experience_value, str) else experience_value
    except (json.JSONDecodeError, TypeError):
        return ""
    payload = {
        "schema_version": str(memory.get("schema_version", "")),
        "problem_type": str(memory.get("problem_type", "")),
        "source_outcome": str(memory.get("source_outcome", "")),
        "summary": str(memory.get("summary", "")),
        "source_refs": source_refs,
        "experience": experience,
    }
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def _memory_source_still_valid(connection: sqlite3.Connection, row: sqlite3.Row | dict[str, object]) -> bool:
    memory = dict(row)
    try:
        source = _source_for_task(
            connection, str(memory["source_task_id"]), str(memory["problem_type"]),
        )
        ids = json.loads(str(memory["source_evidence_ids_json"]))
        stored_refs = json.loads(str(memory["source_refs_json"]))
    except (MemoryError, json.JSONDecodeError, KeyError, TypeError):
        return False
    if not (
        source["tenant_id"] == memory["tenant_id"]
        and source["project_id"] == memory["project_id"]
        and source["source_outcome"] == memory["source_outcome"]
        and source["source_refs"] == stored_refs
        and source["source_evidence_ids"] == ids
        and source["source_report_ref"] == memory["source_report_ref"]
        and source["source_verification_id"] == memory["source_verification_id"]
        and str(memory["content_digest"]) == _memory_content_digest(memory)
    ):
        return False
    return True


def _record_memory_event(
    connection: sqlite3.Connection,
    *,
    memory_id: str,
    tenant_id: str,
    project_id: str,
    event_type: str,
    actor_id: str,
    version: int,
    details: dict[str, object] | None = None,
) -> None:
    connection.execute(
        """INSERT INTO d5_memory_events
           (event_id, memory_id, tenant_id, project_id, event_type, actor_id,
            memory_version, occurred_at, details_json)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (f"memory-event-{uuid.uuid4()}", memory_id, tenant_id, project_id,
         event_type, actor_id, version, _now_text(), canonical_json(details or {})),
    )


def _find_memory_command(
    connection: sqlite3.Connection,
    *,
    tenant_id: str,
    actor_id: str,
    idempotency_key: str,
    command_kind: str,
    target_ref: str,
    request_digest: str,
) -> dict[str, object] | None:
    rows = connection.execute(
        "SELECT * FROM commands WHERE tenant_id = ? AND actor_id = ? AND idempotency_key = ?",
        (tenant_id, actor_id, idempotency_key),
    ).fetchall()
    if not rows:
        return None
    if len(rows) != 1:
        raise MemoryIdempotencyConflict("IDEMPOTENCY_STATE_AMBIGUOUS")
    row = rows[0]
    if (
        str(row["command_kind"]) != command_kind
        or str(row["target_ref"]) != target_ref
        or str(row["request_digest"]) != request_digest
    ):
        raise MemoryIdempotencyConflict("IDEMPOTENCY_CONFLICT")
    return json.loads(str(row["result_json"]))


def _record_memory_command(
    connection: sqlite3.Connection,
    *,
    tenant_id: str,
    actor_id: str,
    idempotency_key: str,
    command_kind: str,
    target_ref: str,
    request_digest: str,
    result: dict[str, object],
) -> None:
    connection.execute(
        """INSERT INTO commands
           (command_id, tenant_id, actor_id, command_kind, target_ref, idempotency_key,
            request_digest, accepted_at, accepted_status, result_json)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'ACCEPTED', ?)""",
        (f"memory-command-{uuid.uuid4()}", tenant_id, actor_id, command_kind,
         target_ref, idempotency_key, request_digest, _now_text(), canonical_json(result)),
    )


def _case_experience(source: dict[str, object]) -> tuple[str, dict[str, object], dict[str, object]]:
    facts = source.get("source_facts")
    if not isinstance(facts, dict):
        raise MemorySourceRejected("Trusted source facts are missing.")
    outcome = str(source["source_outcome"])
    problem_type = str(source["problem_type"])
    service_id = str(source.get("service_id", ""))
    if outcome == "REPAIRED_VERIFIED" and problem_type == PROBLEM_TYPE:
        if (
            facts.get("http_status_before") != 401
            or facts.get("verified_http_status") != 200
            or not isinstance(facts.get("route"), str)
            or int(facts.get("config_version_after", 0)) <= int(facts.get("config_version_before", 0))
        ):
            raise MemorySourceRejected("S1 case does not prove the historical 401 to verified 200 recovery.")
        summary = (
            f"历史恢复案例：绑定业务路由 {facts['route']} 曾返回 HTTP 401；"
            f"经受控配置更新 v{facts['config_version_before']}→v{facts['config_version_after']} 后，"
            f"同身份业务验证返回 HTTP 200。"
        )
        experience: dict[str, object] = {
            "source_authority": MEMORY_AUTHORITY,
            "symptom_pattern": "Historical bound business request returned HTTP 401 before a verified configuration repair.",
            "case_specific_facts": {
                key: facts[key] for key in (
                    "http_status_before", "route", "config_version_before", "config_version_after",
                    "verified_http_status", "business_order_id", "business_order_status",
                )
            },
            "investigation_guidance": [
                "For a new task, read current bound integration configuration, principal status, and authentication policy.",
                "Use the current task's bound business probe to distinguish authentication failure from other outcomes.",
                "Only current task Evidence and the deterministic Gate can establish a cause or action eligibility.",
            ],
            "applicability": {"problem_type": PROBLEM_TYPE, "service_id": service_id},
            "required_current_checks": ["integration_config", "principal_status", "auth_policy", "endpoint_probe"],
            "limitations": [
                "Historical facts do not describe the target task's current state.",
                "This memory does not authorize a repair or prove that the target task is recovered.",
            ],
        }
        constraints = {
            "problem_type": problem_type, "service_id": service_id,
            "source_outcome": outcome, "required_current_checks": experience["required_current_checks"],
        }
    elif problem_type == S2_PROBLEM_TYPE and outcome in {"DIAGNOSED", "SCOPE_ESCALATED"}:
        required = facts.get("required_scopes")
        granted = facts.get("granted_scopes")
        missing = facts.get("missing_scopes")
        if (
            facts.get("http_status") != 403 or facts.get("reason_code") != "SCOPE_INSUFFICIENT"
            or not all(isinstance(value, list) for value in (required, granted, missing))
            or not missing
        ):
            raise MemorySourceRejected("S2 case does not prove an authenticated scope denial.")
        qualifier = "已提交交接" if outcome == "SCOPE_ESCALATED" else "仅完成可信诊断"
        summary = (
            f"历史权限诊断案例：绑定路由 {facts['route']} 返回 HTTP 403，"
            f"可信授权决策为 Scope 不足；{qualifier}，不表示权限已授予或服务已恢复。"
        )
        experience = {
            "source_authority": MEMORY_AUTHORITY,
            "symptom_pattern": "Historical authenticated request was denied because the trusted authorization decision lacked required scopes.",
            "case_specific_facts": {
                key: facts[key] for key in (
                    "http_status", "route", "reason_code", "required_scopes", "granted_scopes",
                    "missing_scopes", "credential_policy_version", "scope_policy_version", "grant_version",
                )
            },
            "investigation_guidance": [
                "Probe the current task's bound route first and use only that live Request ID for authorization facts.",
                "Compare current required, granted, and missing scopes and policy/grant versions from the trusted Domain.",
                "A historical denial or handoff never grants scope; only current Domain Gate and an independent authorized workflow can decide next steps.",
            ],
            "applicability": {"problem_type": S2_PROBLEM_TYPE, "service_id": service_id},
            "required_current_checks": ["endpoint_probe", "scope_authz_decision"],
            "limitations": [
                "A 403 diagnosis is not a permission grant, a repair, or an API recovery.",
                "SCOPE_ESCALATED means only that a real handoff receipt exists; downstream authorization is still pending.",
                "Historical Request IDs and scope versions are not reusable for a new task.",
            ],
        }
        constraints = {
            "problem_type": problem_type, "service_id": service_id,
            "source_outcome": outcome, "required_current_checks": experience["required_current_checks"],
        }
    else:
        raise MemorySourceRejected("Unsupported trusted Memory outcome.")
    return summary, experience, constraints


def create_memory_candidate(
    path: str | Path,
    source_task_id: str,
    trusted_actor: str,
    *,
    ttl_days: int = 30,
    idempotency_key: str | None = None,
) -> dict[str, object]:
    if not 1 <= ttl_days <= 30:
        raise ValueError("D5 memory lifetime must be between 1 and 30 days.")
    idempotency_key = idempotency_key or f"internal-{uuid.uuid4()}"
    if not idempotency_key.strip() or len(idempotency_key) > 200:
        raise MemoryIdempotencyConflict("IDEMPOTENCY_KEY_REQUIRED")
    with connect(path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        binding = _trusted_binding(connection, source_task_id)
        _require_memory_operator(connection, trusted_actor, str(binding["tenant_id"]))
        if str(binding["actor_id"]) != trusted_actor:
            raise MemoryScopeDenied("Only the trusted Task owner can create its Memory candidate.")
        project_id = project_id_for_service(str(binding["service_id"]))
        target_ref = source_task_id
        command_request = {"command_kind": "MEMORY_CANDIDATE_CREATE", "task_id": source_task_id}
        request_digest = digest_json(command_request)
        replay = _find_memory_command(
            connection, tenant_id=str(binding["tenant_id"]), actor_id=trusted_actor,
            idempotency_key=idempotency_key, command_kind="MEMORY_CANDIDATE_CREATE",
            target_ref=target_ref, request_digest=request_digest,
        )
        if replay is not None:
            return replay
        existing = connection.execute(
            """SELECT * FROM d5_memories WHERE tenant_id = ? AND project_id = ?
               AND source_task_id = ?""",
            (binding["tenant_id"], project_id, source_task_id),
        ).fetchone()
        if existing is not None:
            result = _row_dict(existing)
            _record_memory_command(
                connection, tenant_id=str(binding["tenant_id"]), actor_id=trusted_actor,
                idempotency_key=idempotency_key, command_kind="MEMORY_CANDIDATE_CREATE",
                target_ref=target_ref, request_digest=request_digest, result=result,
            )
            return result
        source = _source_for_task(connection, source_task_id)
        if str(source["tenant_id"]) != str(binding["tenant_id"]):
            raise MemoryScopeDenied("Memory source tenant does not match its trusted TaskBinding.")
        summary, experience, constraints = _case_experience({
            **source, "service_id": str(binding["service_id"]),
        })
        memory_id = f"episodic-{uuid.uuid4()}"
        created_at = _now_text()
        expires_at = (_now() + timedelta(days=ttl_days)).isoformat(timespec="milliseconds")
        content_payload = {
            "schema_version": MEMORY_SCHEMA_VERSION,
            "problem_type": str(source["problem_type"]),
            "source_outcome": str(source["source_outcome"]),
            "summary": summary, "source_refs": source["source_refs"], "experience": experience,
        }
        content_digest = digest_json(content_payload)
        connection.execute(
            """INSERT INTO d5_memories
               (memory_id, tenant_id, project_id, type, problem_type, summary,
                applicability_constraints_json, source_task_id, source_evidence_ids_json,
                source_report_ref, source_verification_id, source_outcome, schema_version,
                source_refs_json, experience_json, content_digest, state, version,
                expires_at, created_at)
               VALUES (?, ?, ?, 'EPISODIC', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'CANDIDATE', 1, ?, ?)""",
            (memory_id, source["tenant_id"], source["project_id"], source["problem_type"],
             summary, canonical_json(constraints), source_task_id,
             canonical_json(source["source_evidence_ids"]), source["source_report_ref"],
             source["source_verification_id"], source["source_outcome"], MEMORY_SCHEMA_VERSION,
             canonical_json(source["source_refs"]), canonical_json(experience), content_digest,
             expires_at, created_at),
        )
        _record_memory_event(
            connection, memory_id=memory_id, tenant_id=str(source["tenant_id"]),
            project_id=str(source["project_id"]), event_type="CANDIDATE_CREATED",
            actor_id=trusted_actor, version=1,
            details={"source_task_id": source_task_id, "problem_type": source["problem_type"],
                     "source_outcome": source["source_outcome"], "content_digest": content_digest},
        )
        row = connection.execute("SELECT * FROM d5_memories WHERE memory_id = ?", (memory_id,)).fetchone()
        result = _row_dict(row)
        _record_memory_command(
            connection, tenant_id=str(binding["tenant_id"]), actor_id=trusted_actor,
            idempotency_key=idempotency_key, command_kind="MEMORY_CANDIDATE_CREATE",
            target_ref=target_ref, request_digest=request_digest, result=result,
        )
    return result


def confirm_memory(
    path: str | Path, memory_id: str, actor_id: str, *, idempotency_key: str | None = None,
) -> dict[str, object]:
    idempotency_key = idempotency_key or f"internal-{uuid.uuid4()}"
    with connect(path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute("SELECT * FROM d5_memories WHERE memory_id = ?", (memory_id,)).fetchone()
        if row is None:
            raise MemorySourceRejected("Memory record does not exist.")
        _require_memory_operator(connection, actor_id, str(row["tenant_id"]), "APPROVER")
        request_digest = digest_json({"command_kind": "MEMORY_CONFIRM", "memory_id": memory_id})
        replay = _find_memory_command(
            connection, tenant_id=str(row["tenant_id"]), actor_id=actor_id,
            idempotency_key=idempotency_key, command_kind="MEMORY_CONFIRM",
            target_ref=memory_id, request_digest=request_digest,
        )
        if replay is not None:
            return replay
        if row["state"] == "ACTIVE":
            result = _row_dict(row)
            _record_memory_command(
                connection, tenant_id=str(row["tenant_id"]), actor_id=actor_id,
                idempotency_key=idempotency_key, command_kind="MEMORY_CONFIRM", target_ref=memory_id,
                request_digest=request_digest, result=result,
            )
            return result
        if row["state"] != "CANDIDATE":
            raise MemorySourceRejected("Only a CANDIDATE memory can be activated; revoked versions never revive.")
        if _parse_time(str(row["expires_at"])) <= _now():
            raise MemorySourceRejected("Expired candidates cannot be activated.")
        if not _memory_source_still_valid(connection, row):
            raise MemorySourceRejected("Memory source is no longer checkable.")
        version = int(row["version"]) + 1
        confirmed_at = _now_text()
        connection.execute(
            """UPDATE d5_memories SET state = 'ACTIVE', version = ?, confirmed_by = ?,
               confirmed_at = ? WHERE memory_id = ? AND state = 'CANDIDATE'""",
            (version, actor_id, confirmed_at, memory_id),
        )
        _record_memory_event(
            connection, memory_id=memory_id, tenant_id=str(row["tenant_id"]),
            project_id=str(row["project_id"]), event_type="CONFIRMED",
            actor_id=actor_id, version=version,
        )
        updated = connection.execute("SELECT * FROM d5_memories WHERE memory_id = ?", (memory_id,)).fetchone()
        result = _row_dict(updated)
        _record_memory_command(
            connection, tenant_id=str(row["tenant_id"]), actor_id=actor_id,
            idempotency_key=idempotency_key, command_kind="MEMORY_CONFIRM", target_ref=memory_id,
            request_digest=request_digest, result=result,
        )
    return result


def revoke_memory(
    path: str | Path, memory_id: str, actor_id: str, *, idempotency_key: str | None = None,
) -> dict[str, object]:
    idempotency_key = idempotency_key or f"internal-{uuid.uuid4()}"
    with connect(path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute("SELECT * FROM d5_memories WHERE memory_id = ?", (memory_id,)).fetchone()
        if row is None:
            raise MemorySourceRejected("Memory record does not exist.")
        _require_memory_operator(connection, actor_id, str(row["tenant_id"]), "APPROVER")
        request_digest = digest_json({"command_kind": "MEMORY_REVOKE", "memory_id": memory_id})
        replay = _find_memory_command(
            connection, tenant_id=str(row["tenant_id"]), actor_id=actor_id,
            idempotency_key=idempotency_key, command_kind="MEMORY_REVOKE",
            target_ref=memory_id, request_digest=request_digest,
        )
        if replay is not None:
            return replay
        if row["state"] == "REVOKED":
            result = _row_dict(row)
            _record_memory_command(
                connection, tenant_id=str(row["tenant_id"]), actor_id=actor_id,
                idempotency_key=idempotency_key, command_kind="MEMORY_REVOKE", target_ref=memory_id,
                request_digest=request_digest, result=result,
            )
            return result
        if row["state"] != "ACTIVE":
            raise MemorySourceRejected("Only ACTIVE memory can be revoked.")
        version = int(row["version"]) + 1
        revoked_at = _now_text()
        connection.execute(
            """UPDATE d5_memories SET state = 'REVOKED', version = ?, revoked_by = ?,
               revoked_at = ? WHERE memory_id = ? AND state = 'ACTIVE'""",
            (version, actor_id, revoked_at, memory_id),
        )
        _record_memory_event(
            connection, memory_id=memory_id, tenant_id=str(row["tenant_id"]),
            project_id=str(row["project_id"]), event_type="REVOKED",
            actor_id=actor_id, version=version,
        )
        updated = connection.execute("SELECT * FROM d5_memories WHERE memory_id = ?", (memory_id,)).fetchone()
        result = _row_dict(updated)
        _record_memory_command(
            connection, tenant_id=str(row["tenant_id"]), actor_id=actor_id,
            idempotency_key=idempotency_key, command_kind="MEMORY_REVOKE", target_ref=memory_id,
            request_digest=request_digest, result=result,
        )
    return result


def _memory_is_applicable(
    row: sqlite3.Row, *, problem_type: str, service_id: str, now: datetime,
) -> bool:
    if row["state"] != "ACTIVE" or row["problem_type"] != problem_type:
        return False
    if _parse_time(str(row["expires_at"])) <= now:
        return False
    try:
        constraints = json.loads(str(row["applicability_constraints_json"]))
    except json.JSONDecodeError:
        return False
    return (
        constraints.get("problem_type") == problem_type
        and constraints.get("service_id") == service_id
        and constraints.get("source_outcome") == str(row["source_outcome"])
        and str(row["schema_version"]) in {MEMORY_SCHEMA_VERSION, "d5-legacy-v1"}
        and len(str(row["summary"])) <= 480
        and str(row["content_digest"]) == _memory_content_digest(row)
    )


def list_applicable_memories(
    path: str | Path,
    task_id: str,
    problem_type: str,
    *,
    limit: int = MAX_MEMORY_RESULTS,
) -> list[dict[str, object]]:
    if not 1 <= limit <= 3:
        raise ValueError("D5 memory retrieval is limited to at most three records.")
    with connect(path) as connection:
        binding = _trusted_binding(connection, task_id)
        project_id = project_id_for_service(str(binding["service_id"]))
        rows = connection.execute(
            """SELECT * FROM d5_memories WHERE tenant_id = ? AND project_id = ?
               AND problem_type = ? AND state = 'ACTIVE' ORDER BY confirmed_at, memory_id""",
            (binding["tenant_id"], project_id, problem_type),
        ).fetchall()
        now = _now()
        results = []
        for row in rows:
            if str(row["source_task_id"]) == task_id:
                continue
            if not _memory_is_applicable(
                row, problem_type=problem_type, service_id=str(binding["service_id"]), now=now,
            ):
                continue
            if not _memory_source_still_valid(connection, row):
                continue
            item = _row_dict(row)
            item["summary"] = str(item["summary"])[:480]
            results.append(item)
            if len(results) >= limit:
                break
    return results


def list_memory_records(
    path: str | Path,
    actor_id: str,
    *,
    memory_id: str | None = None,
    state: str | None = None,
) -> list[dict[str, object]]:
    if state not in {None, "CANDIDATE", "ACTIVE", "REVOKED"}:
        raise ValueError("Unsupported Memory lifecycle state.")
    with connect(path) as connection:
        operator = connection.execute(
            "SELECT tenant_id, role FROM trusted_operators WHERE actor_id = ?", (actor_id,),
        ).fetchone()
        if operator is None or str(operator["role"]) != "APPROVER":
            raise MemoryScopeDenied("Memory inventory requires a trusted same-tenant APPROVER.")
        query = "SELECT * FROM d5_memories WHERE tenant_id = ?"
        params: list[object] = [str(operator["tenant_id"])]
        if memory_id is not None:
            query += " AND memory_id = ?"
            params.append(memory_id)
        if state is not None:
            query += " AND state = ?"
            params.append(state)
        query += " ORDER BY created_at DESC, memory_id LIMIT 100"
        rows = connection.execute(query, params).fetchall()
    return [_row_dict(row) for row in rows]


def get_task_memory_context(
    path: str | Path, task_id: str, actor_id: str,
) -> dict[str, object]:
    with connect(path) as connection:
        binding = _trusted_binding(connection, task_id)
        operator = _require_memory_operator(connection, actor_id, str(binding["tenant_id"]))
        if operator["role"] == "SUPPORT" and str(binding["actor_id"]) != actor_id:
            raise MemoryScopeDenied("Only the task owner can inspect Task Memory context.")
        source_rows = connection.execute(
            "SELECT * FROM d5_memories WHERE tenant_id = ? AND source_task_id = ? ORDER BY created_at",
            (binding["tenant_id"], task_id),
        ).fetchall()
    applicable = []
    for problem_type in (PROBLEM_TYPE, S2_PROBLEM_TYPE):
        applicable.extend(list_applicable_memories(path, task_id, problem_type))
    provenance = list_context_provenance(path, task_id, actor_id)
    return {
        "task_id": task_id,
        "source_memories": [_row_dict(row) for row in source_rows],
        "applicable_memories": applicable,
        "context_provenance": provenance,
    }


def insert_context_provenance_in_transaction(
    connection: sqlite3.Connection,
    *,
    task_id: str,
    attempt_id: str,
    model_id: str,
    prompt_version: str,
    prompt_digest: str,
    tool_schema_version: str,
    tool_schema_digest: str,
    selected_skill: dict[str, str] | None,
    selected_memories: list[dict[str, object]],
    evidence_ids: list[str],
    selected_knowledge: list[dict[str, object]] | None = None,
    selected_input_messages: list[dict[str, object]] | None = None,
    task_run_control: dict[str, object] | None = None,
) -> str:
    """Validate current memory rows and register provenance in reserve_attempt's transaction."""
    binding = _trusted_binding(connection, task_id)
    project_id = project_id_for_service(str(binding["service_id"]))
    memory_refs: list[dict[str, object]] = []
    for selected in selected_memories:
        memory_id = str(selected.get("memory_id", ""))
        try:
            version = int(selected.get("version", 0))
        except (TypeError, ValueError):
            raise ContextAssetInvalidated("Selected memory version is invalid.")
        row = connection.execute("SELECT * FROM d5_memories WHERE memory_id = ?", (memory_id,)).fetchone()
        if (
            row is None
            or row["state"] != "ACTIVE"
            or int(row["version"]) != version
            or str(row["source_task_id"]) == task_id
            or row["tenant_id"] != binding["tenant_id"]
            or row["project_id"] != project_id
            or _parse_time(str(row["expires_at"])) <= _now()
            or not _memory_source_still_valid(connection, row)
        ):
            raise ContextAssetInvalidated("Selected memory is no longer active in this TaskBinding scope.")
        if (
            str(selected.get("summary", "")) != str(row["summary"])
            or str(selected.get("content_digest", "")) != str(row["content_digest"])
            or str(selected.get("schema_version", "")) != str(row["schema_version"])
            or str(selected.get("source_task_id", "")) != str(row["source_task_id"])
            or str(selected.get("source_outcome", "")) != str(row["source_outcome"])
        ):
            raise ContextAssetInvalidated("Selected memory content changed after prompt construction.")
        memory_refs.append({
            "memory_id": memory_id, "version": version,
            "digest": str(row["content_digest"]), "source_task_id": str(row["source_task_id"]),
            "source_outcome": str(row["source_outcome"]),
            "source_refs": json.loads(str(row["source_refs_json"])),
            "source_authority": MEMORY_AUTHORITY,
        })
    if selected_skill is not None and not all(selected_skill.get(key) for key in ("name", "version", "digest")):
        raise ContextAssetInvalidated("Selected Skill provenance is incomplete.")
    knowledge_refs: list[dict[str, str]] = []
    if selected_knowledge:
        from opspilot.domain.knowledge_assets import load_scope_knowledge

        valid_assets = load_scope_knowledge(str(binding["service_id"]), include_legacy=True)
        valid_refs = {
            (item["document_id"], item["version"], item["digest"], item["source"], item["valid_from"])
            for item in valid_assets
        }
        for selected in selected_knowledge:
            ref = tuple(str(selected.get(key, "")) for key in (
                "document_id", "version", "digest", "source", "valid_from",
            ))
            if ref not in valid_refs:
                raise ContextAssetInvalidated("Selected Knowledge changed or is not applicable to this TaskBinding.")
            knowledge_refs.append({
                key: str(selected[key]) for key in (
                    "document_id", "version", "digest", "source", "valid_from",
                )
            })
    call_id = str(connection.execute(
        "SELECT call_id FROM d2_attempts WHERE attempt_id = ? AND task_id = ? AND kind = 'MODEL'",
        (attempt_id, task_id),
    ).fetchone()["call_id"])
    connection.execute(
        """INSERT INTO d5_context_provenance
           (call_id, task_id, attempt_id, model_id, prompt_version, prompt_digest,
            tool_schema_version, tool_schema_digest, selected_skill_name,
            selected_skill_version, selected_skill_digest, selected_memories_json,
            selected_knowledge_json, evidence_ids_json, selected_input_messages_json,
            task_run_control_json, built_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (call_id, task_id, attempt_id, model_id, prompt_version, prompt_digest,
         tool_schema_version, tool_schema_digest,
         selected_skill.get("name") if selected_skill else None,
         selected_skill.get("version") if selected_skill else None,
         selected_skill.get("digest") if selected_skill else None,
         canonical_json(memory_refs), canonical_json(knowledge_refs), canonical_json(evidence_ids),
         canonical_json(selected_input_messages or []), canonical_json(task_run_control or {}), _now_text()),
    )
    return call_id


def finish_context_provenance(
    path: str | Path, call_id: str, status: str, error_class: str | None = None
) -> None:
    with connect(path) as connection:
        connection.execute(
            """UPDATE d5_context_provenance SET model_status = ?, completed_at = ?,
               error_class = ? WHERE call_id = ?""",
            (status[:64], _now_text(), error_class[:128] if error_class else None, call_id),
        )


def assert_task_skill_compatible(
    path: str | Path, task_id: str, selected_skill: dict[str, str] | None
) -> None:
    with connect(path) as connection:
        _trusted_binding(connection, task_id)
        rows = connection.execute(
            """SELECT DISTINCT selected_skill_name, selected_skill_version, selected_skill_digest
               FROM d5_context_provenance WHERE task_id = ? AND selected_skill_name IS NOT NULL""",
            (task_id,),
        ).fetchall()
    # M2-02 adds one separately scoped S2 method Skill. A Task may move between
    # the two reviewed methods when current trusted facts show the other path;
    # a selected Skill's own version/digest remains frozen for that Task.
    from opspilot.skill_assets import SCOPE_PROBLEM_TYPE, load_applicable_skill

    approved_names = {"auth-incident-triage", "auth-scope-triage"}
    expected_by_name = {
        "auth-incident-triage": load_applicable_skill("auth_401"),
        "auth-scope-triage": load_applicable_skill(SCOPE_PROBLEM_TYPE),
    }
    if selected_skill is not None:
        name = str(selected_skill.get("name", ""))
        expected = expected_by_name.get(name)
        if (
            expected is None or name not in approved_names
            or any(selected_skill.get(key) != expected.get(key) for key in ("name", "version", "digest"))
        ):
            raise SkillCompatibilityError("The selected Skill is not a currently verified OpsPilot Skill asset.")
    for row in rows:
        name = str(row["selected_skill_name"])
        expected = expected_by_name.get(name)
        if (
            expected is None or name not in approved_names
            or row["selected_skill_version"] != expected.get("version")
            or row["selected_skill_digest"] != expected.get("digest")
        ):
            raise SkillCompatibilityError("A previously selected Skill version or digest changed during this task.")
        if selected_skill is not None and name == str(selected_skill.get("name")) and (
            row["selected_skill_version"] != selected_skill.get("version")
            or row["selected_skill_digest"] != selected_skill.get("digest")
        ):
            raise SkillCompatibilityError("The selected Skill version or digest changed during this task.")


def list_context_provenance(
    path: str | Path, task_id: str, actor_id: str
) -> list[dict[str, object]]:
    with connect(path) as connection:
        binding = _trusted_binding(connection, task_id)
        operator = _require_memory_operator(connection, actor_id, str(binding["tenant_id"]))
        if operator["role"] == "SUPPORT" and binding["actor_id"] != actor_id:
            raise MemoryScopeDenied("Only the task owner or a same-tenant approver can read Context Provenance.")
        rows = connection.execute(
            """SELECT p.*, t.prompt_digest AS model_trace_prompt_digest,
                      t.status AS trace_status, t.provider_response_id
               FROM d5_context_provenance AS p
               LEFT JOIN d2_model_traces AS t ON t.call_id = p.call_id AND t.task_id = p.task_id
               WHERE p.task_id = ? ORDER BY p.built_at, p.call_id""",
            (task_id,),
        ).fetchall()
    results = []
    for raw in rows:
        item = dict(raw)
        item["selected_memories"] = json.loads(str(item.pop("selected_memories_json")))
        item["selected_knowledge"] = json.loads(str(item.pop("selected_knowledge_json", "[]")))
        item["evidence_ids"] = json.loads(str(item.pop("evidence_ids_json")))
        item["selected_input_messages"] = json.loads(str(item.pop("selected_input_messages_json", "[]")))
        item["task_run_control"] = json.loads(str(item.pop("task_run_control_json", "{}")))
        item["prompt_digest_matches_trace"] = item.get("model_trace_prompt_digest") in (None, item["prompt_digest"])
        current_memory_states: list[dict[str, str]] = []
        with connect(path) as connection:
            for selected in item["selected_memories"]:
                memory_id = str(selected.get("memory_id", ""))
                current = connection.execute(
                    "SELECT * FROM d5_memories WHERE memory_id = ? AND tenant_id = ?",
                    (memory_id, item["tenant_id"] if "tenant_id" in item else _trusted_binding(connection, task_id)["tenant_id"]),
                ).fetchone()
                reason = "CURRENT"
                if current is None:
                    reason = "MEMORY_NOT_FOUND_OR_CROSS_TENANT"
                elif current["state"] != "ACTIVE":
                    reason = "MEMORY_REVOKED_OR_NOT_ACTIVE"
                elif int(current["version"]) != int(selected.get("version", 0)):
                    reason = "MEMORY_VERSION_CHANGED"
                elif str(current["content_digest"]) != str(selected.get("digest", "")):
                    reason = "MEMORY_CONTENT_CHANGED"
                elif _parse_time(str(current["expires_at"])) <= _now():
                    reason = "MEMORY_EXPIRED"
                elif not _memory_source_still_valid(connection, current):
                    reason = "MEMORY_SOURCE_INVALID"
                current_memory_states.append({"memory_id": memory_id, "currentness": reason})
        item["selected_memory_currentness"] = current_memory_states
        results.append(item)
    return results
