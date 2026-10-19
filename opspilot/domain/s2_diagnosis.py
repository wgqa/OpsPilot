from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
import sqlite3
from typing import Any

from opspilot.domain.database import connect
from opspilot.domain.d2 import (
    EVIDENCE_MAX_AGE_SECONDS,
    MAX_MCP_ATTEMPTS,
    MAX_MODEL_CALLS,
    attempt_counts,
    canonical_json,
    digest_json,
    get_scope_authz_facts_fact,
    utc_now,
    ScopeDenied,
)
from opspilot.domain.events import write_outbox_event


GATE_POLICY_VERSION = "s2-scope-evidence-v1"
AUTHZ_SOURCE = "sqlite:authz_events+principal_scope_grants+route_scope_policies"
PROBE_SOURCE = "http:loopback-demo-business-api"
BOUND_ROUTE = "/api/orders/demo-order"


def _parse_time(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)


def _run_evidence(
    connection: sqlite3.Connection, task_id: str, run_id: str,
) -> list[dict[str, object]]:
    rows = connection.execute(
        """SELECT e.*, o.observation_id, o.rowid AS observation_sequence, o.tool_name, o.attempt_id,
                  o.created_at AS observation_at, o.status AS observation_status,
                  a.run_id AS attempt_run_id, a.kind AS attempt_kind
           FROM d2_evidence e
           JOIN d2_tool_observations o ON o.evidence_id = e.evidence_id AND o.task_id = e.task_id
           JOIN d2_attempts a ON a.attempt_id = o.attempt_id AND a.task_id = o.task_id
           WHERE e.task_id = ? AND a.run_id = ? AND o.status = 'OK'
           ORDER BY o.rowid""",
        (task_id, run_id),
    ).fetchall()
    latest: dict[str, dict[str, object]] = {}
    for row in rows:
        item = {key: row[key] for key in row.keys()}
        item["observed_versions"] = json.loads(str(row["observed_versions_json"]))
        item["facts"] = json.loads(str(row["facts_json"]))
        evidence_id = str(row["evidence_id"])
        # A duplicate immutable Evidence row may be re-observed in this Run. Use
        # the newest same-Run MCP Observation as freshness proof.
        latest[evidence_id] = item
    return list(latest.values())


def run_evidence_records(path: str | Path, task_id: str, run_id: str) -> list[dict[str, object]]:
    with connect(path) as connection:
        return _run_evidence(connection, task_id, run_id)


def run_evidence_ids(path: str | Path, task_id: str, run_id: str) -> list[str]:
    return [str(item["evidence_id"]) for item in run_evidence_records(path, task_id, run_id)]


def _current_authz(
    path: str | Path, task_id: str, request_id: str,
    connection: sqlite3.Connection | None = None,
) -> dict[str, object] | None:
    try:
        return get_scope_authz_facts_fact(path, task_id, request_id, connection=connection)
    except (LookupError, ValueError, ScopeDenied):
        return None


def _observation_order(item: dict[str, object]) -> tuple[datetime, int]:
    observed_at = _parse_time(item.get("observation_at")) or datetime.min.replace(tzinfo=timezone.utc)
    return observed_at, int(item.get("observation_sequence", 0))


def _same_authz_facts(stored: dict[str, object], current: dict[str, object]) -> bool:
    fields = (
        "decision_id", "request_id", "authn_event_id", "authn_result_code",
        "tenant_id", "principal_id", "service_id", "integration_id", "route",
        "outcome", "reason_code", "credential_policy_version", "scope_policy_version",
        "grant_version", "required_scopes", "granted_scopes", "missing_scopes",
        "resource_binding_valid",
    )
    a, b = stored.get("facts", {}), current.get("facts", {})
    return isinstance(a, dict) and isinstance(b, dict) and all(a.get(key) == b.get(key) for key in fields)


def _gate(
    decision: str,
    reason: str,
    *,
    evidence: list[dict[str, object]],
    request_id: str | None = None,
    decision_id: int | None = None,
    missing: list[str] | None = None,
    predicate: dict[str, object] | None = None,
) -> dict[str, object]:
    return {
        "decision": decision,
        "reason_code": reason,
        "request_id": request_id,
        "decision_id": decision_id,
        "checked_fact_ids": [str(item["evidence_id"]) for item in evidence],
        "evidence_digests": {str(item["evidence_id"]): str(item["digest"]) for item in evidence},
        "observed_versions": {
            str(item["evidence_id"]): item["observed_versions"] for item in evidence
        },
        "missing_predicates": missing or [],
        "predicate": predicate or {},
        "side_effects": [],
    }


def _need_more_or_budget_exhausted(
    path: str | Path,
    task_id: str,
    *,
    evidence: list[dict[str, object]],
    reason: str,
    missing: list[str],
    request_id: str | None = None,
    decision_id: int | None = None,
    exhausted_reason: str = "S2_EVIDENCE_BUDGET_EXHAUSTED",
    connection: sqlite3.Connection | None = None,
) -> dict[str, object]:
    if connection is None:
        counts = attempt_counts(path, task_id)
    else:
        rows = connection.execute(
            "SELECT kind, COUNT(*) AS n FROM d2_attempts WHERE task_id = ? GROUP BY kind",
            (task_id,),
        ).fetchall()
        counts = {"MODEL": 0, "MCP": 0}
        counts.update({str(row["kind"]): int(row["n"]) for row in rows})
    if counts["MCP"] >= MAX_MCP_ATTEMPTS or counts["MODEL"] >= MAX_MODEL_CALLS:
        return _gate(
            "INCONCLUSIVE", exhausted_reason, evidence=evidence,
            request_id=request_id, decision_id=decision_id, missing=missing,
        )
    return _gate(
        "NEED_MORE", reason, evidence=evidence,
        request_id=request_id, decision_id=decision_id, missing=missing,
    )


def evaluate_s2_evidence_gate(
    path: str | Path,
    task_id: str,
    evidence_ids: list[str] | None = None,
    *,
    run_id: str,
    connection: sqlite3.Connection | None = None,
) -> dict[str, object]:
    """Evaluate only current, same-Run evidence against the trusted S2 predicate."""
    if connection is None:
        with connect(path) as opened:
            return evaluate_s2_evidence_gate(
                path, task_id, evidence_ids, run_id=run_id, connection=opened,
            )
    binding_row = connection.execute(
        "SELECT * FROM task_bindings WHERE task_id = ?", (task_id,),
    ).fetchone()
    if binding_row is None:
        return _gate("INCONCLUSIVE", "TASK_BINDING_MISSING", evidence=[], missing=["trusted_task"])
    binding = {key: binding_row[key] for key in binding_row.keys()}
    run = connection.execute(
        "SELECT tenant_id, task_id, kind, status FROM task_runs WHERE run_id = ?",
        (run_id,),
    ).fetchone()
    if (
        run is None or str(run["tenant_id"]) != str(binding["tenant_id"])
        or str(run["task_id"]) != task_id or str(run["kind"]) == "CHAT_READONLY"
    ):
        return _gate("INCONCLUSIVE", "RUN_TASK_BINDING_INVALID", evidence=[], missing=["trusted_run"])
    all_evidence = _run_evidence(connection, task_id, run_id)

    # The Domain selects every persisted observation from this Run. The caller's
    # candidate list cannot omit contradictory facts or promote prior-Run rows.
    # Current S2 authority consists of the latest live Probe and its matching
    # same-Run authorization facts. Earlier requests stay in history but cannot
    # make the new observation stale or satisfy its Request/Event correlation.
    del evidence_ids
    probes = [item for item in all_evidence if item["fact_type"] == "endpoint_probe"]
    authz_items = [item for item in all_evidence if item["fact_type"] == "scope_authz_decision"]
    if probes:
        latest_probe = max(probes, key=_observation_order)
        latest_probe_facts = latest_probe.get("facts", {})
        latest_request = latest_probe_facts.get("request_id") if isinstance(latest_probe_facts, dict) else None
        authz_items = [
            item for item in authz_items
            if isinstance(item.get("facts"), dict)
            and item["facts"].get("request_id") == latest_request
        ]
        evidence = [latest_probe, *authz_items]
    else:
        evidence = list(authz_items)
        authz_items = [item for item in evidence if item["fact_type"] == "scope_authz_decision"]
    probes = [item for item in evidence if item["fact_type"] == "endpoint_probe"]
    authz_items = [item for item in evidence if item["fact_type"] == "scope_authz_decision"]
    if not probes and not authz_items:
        return _gate("NOT_APPLICABLE", "NO_S2_AUTHORIZATION_EVIDENCE", evidence=evidence)

    allowed_sources = {
        "integration_config": "sqlite:integrations",
        "principal_status": "sqlite:principals",
        "auth_policy": "sqlite:auth_policies",
        "endpoint_probe": PROBE_SOURCE,
        "scope_authz_decision": AUTHZ_SOURCE,
    }
    for item in evidence:
        if item["fact_type"] not in allowed_sources or item["data_source"] != allowed_sources[item["fact_type"]]:
            return _gate("INCONCLUSIVE", "S2_EVIDENCE_SOURCE_INVALID", evidence=evidence)
        if (
            item["tenant_id"] != binding["tenant_id"] or item["task_id"] != task_id
            or item["principal_id"] != binding["principal_id"]
            or item["trust_class"] != "untrusted_tool_observation"
            or item["attempt_kind"] != "MCP" or item["attempt_run_id"] != run_id
        ):
            return _gate("INCONCLUSIVE", "S2_EVIDENCE_SCOPE_INVALID", evidence=evidence)
        facts = item.get("facts", {})
        if not isinstance(facts, dict):
            return _gate("INCONCLUSIVE", "S2_EVIDENCE_FACTS_INVALID", evidence=evidence)
        if item["fact_type"] == "integration_config" and (
            item["resource_id"] != binding["integration_id"]
            or facts.get("integration_id") != binding["integration_id"]
            or facts.get("principal_id") != binding["principal_id"]
        ):
            return _gate("INCONCLUSIVE", "S2_CONFIG_SCOPE_MISMATCH", evidence=evidence)
        if item["fact_type"] == "principal_status" and (
            item["resource_id"] != binding["principal_id"] or facts.get("principal_id") != binding["principal_id"]
        ):
            return _gate("INCONCLUSIVE", "S2_PRINCIPAL_SCOPE_MISMATCH", evidence=evidence)
        if item["fact_type"] == "auth_policy" and (
            item["resource_id"] != binding["service_id"] or facts.get("service_id") != binding["service_id"]
        ):
            return _gate("INCONCLUSIVE", "S2_POLICY_SCOPE_MISMATCH", evidence=evidence)
        age_at = _parse_time(item["observation_at"])
        if item["fact_type"] == "scope_authz_decision":
            age_at = _parse_time(item["fetched_at"])
        if age_at is None:
            return _gate("INCONCLUSIVE", "S2_EVIDENCE_TIME_INVALID", evidence=evidence)
        age = (datetime.now(timezone.utc) - age_at).total_seconds()
        if age < -30:
            return _gate("INCONCLUSIVE", "S2_EVIDENCE_FROM_FUTURE", evidence=evidence)
        if age > EVIDENCE_MAX_AGE_SECONDS:
            return _need_more_or_budget_exhausted(
                path, task_id, evidence=evidence, reason="S2_EVIDENCE_STALE_REQUERY_ALLOWED",
                missing=["current_s2_evidence"], connection=connection,
            )

    if len(probes) > 1:
        # A single Run may inspect multiple live requests, but conflicting outcomes
        # cannot be collapsed into one trusted diagnosis.
        signatures = {
            (item["facts"].get("http_status"), canonical_json(item["observed_versions"]))
            for item in probes if isinstance(item.get("facts"), dict)
        }
        if len(signatures) > 1:
            return _gate("INCONCLUSIVE", "MULTIPLE_PROBE_REQUESTS_REQUIRE_SELECTION", evidence=evidence)
    probe = probes[-1] if probes else None
    probe_facts = probe.get("facts", {}) if probe else {}
    if probe is not None:
        if (
            not isinstance(probe_facts, dict)
            or probe["resource_id"] != f"{binding['service_id']}:{binding['integration_id']}:{BOUND_ROUTE}"
            or probe_facts.get("service_id") != binding["service_id"]
            or probe_facts.get("integration_id") != binding["integration_id"]
            or probe_facts.get("principal_id") != binding["principal_id"]
            or probe_facts.get("route") != BOUND_ROUTE
        ):
            return _gate("INCONCLUSIVE", "S2_PROBE_SCOPE_MISMATCH", evidence=evidence)
        status = probe_facts.get("http_status")
        if status == 401:
            return _gate("NOT_APPLICABLE", "AUTHENTICATION_FAILURE_REMAINS_S1", evidence=evidence)
        if status == 404:
            return _gate("INCONCLUSIVE", "HTTP_404_HAS_NO_SCOPE_ROOT_CAUSE", evidence=evidence,
                         request_id=str(probe_facts.get("request_id") or "") or None)
        if status == 200:
            return _gate("NO_ACTION", "CURRENT_PROBE_DID_NOT_DENY_SCOPE", evidence=evidence,
                         request_id=str(probe_facts.get("request_id") or "") or None)
        if status != 403:
            return _gate("INCONCLUSIVE", "HTTP_STATUS_NOT_A_TRUSTED_SCOPE_PREDICATE", evidence=evidence)
        versions = probe.get("observed_versions", {})
        before = versions.get("before", {}) if isinstance(versions, dict) else {}
        after = versions.get("after", {}) if isinstance(versions, dict) else {}
        if (
            probe_facts.get("versions_stable_during_probe") is not True
            or probe_facts.get("auth_event_scope_valid") is not True
            or not isinstance(before, dict) or before != after
            or not probe_facts.get("request_id")
            or not probe_facts.get("authn_event_id")
            or not probe_facts.get("authz_event_id")
        ):
            return _gate("INCONCLUSIVE", "S2_PROBE_CORRELATION_OR_VERSION_INVALID", evidence=evidence)

    request_id: str | None = None
    matching_authz: dict[str, object] | None = None
    if probe is not None:
        request_id = str(probe_facts["request_id"])
        matching = [
            item for item in authz_items
            if isinstance(item.get("facts"), dict)
            and item["facts"].get("request_id") == request_id
        ]
        if not matching:
            if authz_items:
                return _gate("INCONCLUSIVE", "S2_REQUEST_AUTHZ_CORRELATION_MISMATCH", evidence=evidence,
                             request_id=request_id)
            return _need_more_or_budget_exhausted(
                path, task_id, evidence=evidence, reason="S2_CURRENT_AUTHZ_DECISION_REQUIRED",
                missing=["matching_scope_authz_decision"], request_id=request_id,
                exhausted_reason="S2_AUTHZ_EVIDENCE_MISSING_BUDGET_EXHAUSTED",
                connection=connection,
            )
        matching_authz = matching[-1]
    elif authz_items:
        matching_authz = authz_items[-1]
        facts = matching_authz.get("facts", {})
        request_id = str(facts.get("request_id") or "") if isinstance(facts, dict) else ""
        correction = connection.execute(
            """SELECT m.body FROM task_run_inputs i JOIN messages m ON m.message_id = i.message_id
               WHERE i.run_id = ? AND m.input_kind = 'CORRECT_TASK_INPUT'""",
            (run_id,),
        ).fetchall()
        if not request_id or not any(request_id in str(row["body"]) for row in correction):
            return _gate("INCONCLUSIVE", "REQUEST_ID_NOT_BOUND_TO_CURRENT_PROBE_OR_FORMAL_CORRECTION",
                         evidence=evidence, request_id=request_id or None)

    if matching_authz is None or request_id is None:
        return _need_more_or_budget_exhausted(
            path, task_id, evidence=evidence, reason="S2_CURRENT_AUTHZ_DECISION_REQUIRED",
            missing=["matching_scope_authz_decision"], request_id=request_id,
            connection=connection,
        )
    authz_facts = matching_authz.get("facts", {})
    if not isinstance(authz_facts, dict):
        return _gate("INCONCLUSIVE", "S2_AUTHZ_FACTS_INVALID", evidence=evidence, request_id=request_id)
    current = _current_authz(path, task_id, request_id, connection)
    if current is None or not _same_authz_facts(matching_authz, current):
        return _gate("INCONCLUSIVE", "S2_AUTHZ_FACTS_CHANGED_OR_UNAVAILABLE", evidence=evidence,
                     request_id=request_id)
    current_facts = current.get("facts", {})
    currentness = current_facts.get("currentness") if isinstance(current_facts, dict) else None
    if currentness == "STALE":
        return _need_more_or_budget_exhausted(
            path, task_id, evidence=evidence, reason="S2_POLICY_OR_GRANT_VERSION_STALE",
            missing=["current_policy_grant_evidence"], request_id=request_id,
            decision_id=int(authz_facts["decision_id"]), exhausted_reason="S2_STALE_BUDGET_EXHAUSTED",
            connection=connection,
        )
    if currentness != "CURRENT" or authz_facts.get("currentness") != "CURRENT":
        return _gate("INCONCLUSIVE", "S2_AUTHZ_CORRELATION_CONFLICT", evidence=evidence,
                     request_id=request_id, decision_id=int(authz_facts["decision_id"]))

    expected = (
        binding["tenant_id"], binding["service_id"], binding["integration_id"], binding["principal_id"], BOUND_ROUTE,
    )
    actual = (
        authz_facts.get("tenant_id"), authz_facts.get("service_id"), authz_facts.get("integration_id"),
        authz_facts.get("principal_id"), authz_facts.get("route"),
    )
    if actual != expected or authz_facts.get("request_id") != request_id:
        return _gate("INCONCLUSIVE", "S2_AUTHZ_TASK_BINDING_MISMATCH", evidence=evidence, request_id=request_id)
    if authz_facts.get("authn_result_code") != "AUTH_ACCEPTED" or authz_facts.get("resource_binding_valid") is not True:
        return _gate("NO_ACTION", "S2_AUTHENTICATION_OR_RESOURCE_BINDING_NOT_VALID", evidence=evidence,
                     request_id=request_id, decision_id=int(authz_facts["decision_id"]))

    principal = connection.execute(
        "SELECT status FROM principals WHERE tenant_id = ? AND principal_id = ?",
        (binding["tenant_id"], binding["principal_id"]),
    ).fetchone()
    if principal is None or str(principal["status"]) != "ENABLED":
        return _gate("NO_ACTION", "PRINCIPAL_NOT_CURRENTLY_ENABLED", evidence=evidence,
                     request_id=request_id, decision_id=int(authz_facts["decision_id"]))

    required = authz_facts.get("required_scopes")
    granted = authz_facts.get("granted_scopes")
    missing_scopes = authz_facts.get("missing_scopes")
    if not all(isinstance(item, list) and all(isinstance(value, str) for value in item) for item in (required, granted, missing_scopes)):
        return _gate("INCONCLUSIVE", "S2_SCOPE_SET_INVALID", evidence=evidence, request_id=request_id)
    if missing_scopes != sorted(set(required) - set(granted)):
        return _gate("INCONCLUSIVE", "S2_MISSING_SCOPE_DIFFERENCE_INVALID", evidence=evidence, request_id=request_id)
    if probe is not None:
        versions = probe.get("observed_versions", {})
        before = versions.get("before", {}) if isinstance(versions, dict) else {}
        if (
            probe_facts.get("request_id") != request_id
            or probe_facts.get("authn_event_id") != authz_facts.get("authn_event_id")
            or probe_facts.get("authz_event_id") != authz_facts.get("decision_id")
            or before.get("policy_version") != authz_facts.get("credential_policy_version")
        ):
            return _gate("INCONCLUSIVE", "S2_HTTP_AND_AUTHZ_EVENT_MISMATCH", evidence=evidence, request_id=request_id)

    if authz_facts.get("reason_code") != "SCOPE_INSUFFICIENT" or authz_facts.get("outcome") != "DENY":
        if authz_facts.get("reason_code") == "SCOPE_GRANTED" and not missing_scopes:
            return _gate("NO_ACTION", "CURRENT_DECISION_HAS_NO_MISSING_SCOPE", evidence=evidence,
                         request_id=request_id, decision_id=int(authz_facts["decision_id"]))
        return _gate("INCONCLUSIVE", "CURRENT_403_REASON_IS_NOT_SCOPE_INSUFFICIENT", evidence=evidence,
                     request_id=request_id, decision_id=int(authz_facts["decision_id"]))
    if not missing_scopes:
        return _gate("INCONCLUSIVE", "DENIED_DECISION_HAS_NO_MISSING_SCOPE", evidence=evidence,
                     request_id=request_id, decision_id=int(authz_facts["decision_id"]))

    predicate = {
        "authenticated": True,
        "principal_enabled": True,
        "resource_binding_valid": True,
        "authz_outcome": "DENY",
        "reason_code": "SCOPE_INSUFFICIENT",
        "required_scopes": sorted(set(required)),
        "granted_scopes": sorted(set(granted)),
        "missing_scopes": sorted(set(missing_scopes)),
        "credential_policy_version": int(authz_facts["credential_policy_version"]),
        "scope_policy_version": int(authz_facts["scope_policy_version"]),
        "grant_version": int(authz_facts["grant_version"]),
        "request_id": request_id,
        "decision_id": int(authz_facts["decision_id"]),
    }
    return _gate(
        "DIAGNOSED", "CURRENT_AUTHENTICATED_SCOPE_INSUFFICIENT", evidence=evidence,
        request_id=request_id, decision_id=int(authz_facts["decision_id"]), predicate=predicate,
    )


def record_s2_gate_trace(
    path: str | Path, task_id: str, run_id: str, gate: dict[str, object],
) -> str:
    from opspilot.domain.d2 import get_task_binding

    binding = get_task_binding(path, task_id)
    with connect(path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        run = connection.execute(
            "SELECT tenant_id, task_id FROM task_runs WHERE run_id = ?",
            (run_id,),
        ).fetchone()
        if run is None or run["task_id"] != task_id or run["tenant_id"] != binding["tenant_id"]:
            raise ValueError("S2 Gate trace Run does not match the trusted TaskBinding.")
        count = int(connection.execute(
            "SELECT COUNT(*) AS n FROM s2_gate_traces WHERE task_id = ? AND run_id = ?",
            (task_id, run_id),
        ).fetchone()["n"])
        if count >= 63 and str(gate.get("decision", "")) == "NEED_MORE":
            gate.update({
                "decision": "INCONCLUSIVE",
                "reason_code": "S2_GATE_TRACE_LIMIT_REACHED",
                "predicate": {},
            })
        trace_id = "s2-gate-" + digest_json({
            "tenant_id": str(binding["tenant_id"]), "task_id": task_id, "run_id": run_id,
            "decision": str(gate.get("decision", "INCONCLUSIVE")),
            "reason_code": str(gate.get("reason_code", "UNKNOWN")),
            "request_id": gate.get("request_id"), "decision_id": gate.get("decision_id"),
            "evidence_digests": gate.get("evidence_digests", {}),
            "predicate": gate.get("predicate", {}),
        })[:40]
        if connection.execute(
            "SELECT 1 FROM s2_gate_traces WHERE trace_id = ?", (trace_id,),
        ).fetchone() is not None:
            return trace_id
        if count >= 64:
            latest = connection.execute(
                "SELECT trace_id FROM s2_gate_traces WHERE task_id = ? AND run_id = ? "
                "ORDER BY created_at DESC, rowid DESC LIMIT 1",
                (task_id, run_id),
            ).fetchone()
            if latest is None:
                raise ValueError("S2 Gate trace count is inconsistent with its Run.")
            connection.execute(
                "UPDATE s2_gate_traces SET decision = 'INCONCLUSIVE', "
                "reason_code = 'S2_GATE_TRACE_LIMIT_REACHED', predicate_json = '{}' "
                "WHERE trace_id = ?",
                (str(latest["trace_id"]),),
            )
            gate.update({
                "decision": "INCONCLUSIVE",
                "reason_code": "S2_GATE_TRACE_LIMIT_REACHED",
                "predicate": {},
            })
            return str(latest["trace_id"])
        connection.execute(
            """INSERT OR IGNORE INTO s2_gate_traces
               (trace_id, tenant_id, task_id, run_id, decision, reason_code, request_id,
                decision_id, evidence_ids_json, evidence_digests_json, predicate_json, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (trace_id, binding["tenant_id"], task_id, run_id,
             str(gate.get("decision", "INCONCLUSIVE")), str(gate.get("reason_code", "UNKNOWN")),
             gate.get("request_id"), gate.get("decision_id"),
             canonical_json(gate.get("checked_fact_ids", [])), canonical_json(gate.get("evidence_digests", {})),
             canonical_json(gate.get("predicate", {})), utc_now()),
        )
    return trace_id


def finish_s2_without_draft(
    path: str | Path, task_id: str, run_id: str, gate: dict[str, object],
) -> str:
    """Persist a read-only terminal Task projection when S2 cannot be diagnosed."""
    from opspilot.domain.d2 import get_task_binding

    binding = get_task_binding(path, task_id)
    outcome = str(gate.get("decision", "INCONCLUSIVE"))
    if outcome not in {"NO_ACTION", "INCONCLUSIVE"}:
        raise ValueError("S2 safe stop only accepts NO_ACTION or INCONCLUSIVE.")
    trace_id = record_s2_gate_trace(path, task_id, run_id, gate)
    with connect(path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        _validate_receipt_run(connection, task_id, run_id, str(binding["tenant_id"]))
        projected = "NO_ACTION" if outcome == "NO_ACTION" else "INCONCLUSIVE"
        connection.execute("UPDATE task_bindings SET status = ? WHERE task_id = ?", (projected, task_id))
        write_outbox_event(
            connection, tenant_id=str(binding["tenant_id"]), task_id=task_id,
            source_kind="S2_GATE", source_id=trace_id, event_kind="S2_SAFE_STOP",
            payload={"task_id": task_id, "task_status": projected,
                     "reason_code": str(gate.get("reason_code", "S2_INCONCLUSIVE"))},
            created_at=utc_now(),
        )
    return trace_id


def _validate_receipt_run(connection: sqlite3.Connection, task_id: str, run_id: str, tenant_id: str) -> None:
    run = connection.execute(
        "SELECT * FROM task_runs WHERE run_id = ? AND tenant_id = ? AND task_id = ?",
        (run_id, tenant_id, task_id),
    ).fetchone()
    if run is None or str(run["kind"]) in {"CHAT_READONLY", "APPROVAL_RESUME", "RECONCILE"}:
        raise ValueError("S2 receipt requires the Task's trusted investigation Run.")
    if str(run["status"]) != "RUNNING":
        raise ValueError("S2 receipt Run is not active.")
    from opspilot.domain.task_control import assert_task_control_in_transaction

    assert_task_control_in_transaction(
        connection, tenant_id, task_id, int(run["expected_control_revision"]), run_id=run_id,
    )


def create_diagnosis_receipt(
    path: str | Path,
    *,
    task_id: str,
    run_id: str,
    evidence_ids: list[str] | None = None,
) -> dict[str, object]:
    from opspilot.domain.d2 import get_task_binding

    binding = get_task_binding(path, task_id)
    with connect(path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        _validate_receipt_run(connection, task_id, run_id, str(binding["tenant_id"]))
        gate = evaluate_s2_evidence_gate(path, task_id, evidence_ids, run_id=run_id)
        if gate["decision"] != "DIAGNOSED":
            raise ValueError("A current trusted S2 Gate result is required for DiagnosisReceipt.")
        request_id = str(gate["request_id"])
        decision_id = int(gate["decision_id"])
        ids = list(gate["checked_fact_ids"])
        existing = connection.execute(
            """SELECT * FROM s2_diagnosis_receipts
               WHERE tenant_id = ? AND task_id = ? AND run_id = ? AND request_id = ?""",
            (binding["tenant_id"], task_id, run_id, request_id),
        ).fetchone()
        if existing is not None:
            if (
                str(existing["evidence_ids_json"]) != canonical_json(ids)
                or str(existing["evidence_digests_json"]) != canonical_json(gate["evidence_digests"])
                or int(existing["decision_id"]) != decision_id
            ):
                raise ValueError("An existing DiagnosisReceipt cannot be rewritten with changed Evidence.")
            return _receipt_dict(existing)
        receipt_id = f"s2-receipt-{uuid.uuid4()}"
        now = utc_now()
        connection.execute(
            """INSERT INTO s2_diagnosis_receipts
               (receipt_id, tenant_id, task_id, run_id, request_id, decision_id,
                gate_policy_version, predicate_json, evidence_ids_json,
                evidence_digests_json, observed_versions_json, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (receipt_id, binding["tenant_id"], task_id, run_id, request_id, decision_id,
             GATE_POLICY_VERSION, canonical_json(gate["predicate"]), canonical_json(ids),
             canonical_json(gate["evidence_digests"]), canonical_json(gate["observed_versions"]), now),
        )
        row = connection.execute("SELECT * FROM s2_diagnosis_receipts WHERE receipt_id = ?", (receipt_id,)).fetchone()
        assert row is not None
        return _receipt_dict(row)


def _receipt_dict(row: sqlite3.Row) -> dict[str, object]:
    return {
        "receipt_id": str(row["receipt_id"]), "task_id": str(row["task_id"]),
        "outcome": "DIAGNOSED",
        "run_id": str(row["run_id"]), "request_id": str(row["request_id"]),
        "decision_id": int(row["decision_id"]), "gate_policy_version": str(row["gate_policy_version"]),
        "predicate": json.loads(str(row["predicate_json"])),
        "evidence_ids": json.loads(str(row["evidence_ids_json"])),
        "evidence_digests": json.loads(str(row["evidence_digests_json"])),
        "observed_versions": json.loads(str(row["observed_versions_json"])),
        "created_at": str(row["created_at"]),
    }


def _current_receipt_gate(path: str | Path, receipt: dict[str, object]) -> dict[str, object]:
    return evaluate_s2_evidence_gate(
        path, str(receipt["task_id"]), list(receipt["evidence_ids"]), run_id=str(receipt["run_id"]),
    )


def freeze_handoff_draft(
    path: str | Path, *, task_id: str, receipt_id: str,
) -> dict[str, object]:
    from opspilot.domain.d2 import get_task_binding
    from opspilot.domain.knowledge_assets import load_scope_knowledge

    binding = get_task_binding(path, task_id)
    with connect(path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        receipt_row = connection.execute(
            "SELECT * FROM s2_diagnosis_receipts WHERE receipt_id = ? AND tenant_id = ? AND task_id = ?",
            (receipt_id, binding["tenant_id"], task_id),
        ).fetchone()
        if receipt_row is None:
            raise ValueError("DiagnosisReceipt is not available in this Task scope.")
        receipt = _receipt_dict(receipt_row)
        _validate_receipt_run(connection, task_id, str(receipt["run_id"]), str(binding["tenant_id"]))
        gate = _current_receipt_gate(path, receipt)
        if gate["decision"] != "DIAGNOSED" or gate["request_id"] != receipt["request_id"] or gate["decision_id"] != receipt["decision_id"]:
            raise ValueError("DiagnosisReceipt is stale or no longer current; Draft creation is denied.")
        existing = connection.execute(
            "SELECT * FROM s2_handoff_drafts WHERE tenant_id = ? AND task_id = ? AND receipt_id = ?",
            (binding["tenant_id"], task_id, receipt_id),
        ).fetchone()
        if existing is not None:
            return _draft_dict(existing)
        predicate = dict(gate["predicate"])
        knowledge = load_scope_knowledge(str(binding["service_id"]))
        knowledge_refs = [
            {key: item[key] for key in ("document_id", "version", "digest", "source", "valid_from")}
            for item in knowledge if item.get("document_id") == "api-scope-current"
        ]
        content = {
            "schema_version": 1,
            "task_id": task_id,
            "diagnosis_receipt_id": receipt_id,
            "request_id": str(receipt["request_id"]),
            "decision_id": int(receipt["decision_id"]),
            "service_id": str(binding["service_id"]),
            "integration_id": str(binding["integration_id"]),
            "principal_id": str(binding["principal_id"]),
            "route": BOUND_ROUTE,
            "required_scopes": list(predicate["required_scopes"]),
            "granted_scopes": list(predicate["granted_scopes"]),
            "missing_scopes": list(predicate["missing_scopes"]),
            "versions": {
                "credential_policy_version": int(predicate["credential_policy_version"]),
                "scope_policy_version": int(predicate["scope_policy_version"]),
                "grant_version": int(predicate["grant_version"]),
            },
            "reason": "The current authenticated request was denied because the bound principal lacks the required route scopes.",
            "evidence_ids": list(receipt["evidence_ids"]),
            "evidence_digests": dict(receipt["evidence_digests"]),
            "knowledge_refs": knowledge_refs,
            "state": "FROZEN_DRAFT_NOT_SUBMITTED",
            "authorization_changed": False,
            "handoff_receipt_created": False,
        }
        content_digest = digest_json(content)
        version = int(connection.execute(
            "SELECT COALESCE(MAX(version), 0) + 1 FROM s2_handoff_drafts WHERE tenant_id = ? AND task_id = ?",
            (binding["tenant_id"], task_id),
        ).fetchone()[0])
        draft_id = f"s2-draft-{uuid.uuid4()}"
        now = utc_now()
        connection.execute(
            """INSERT INTO s2_handoff_drafts
               (draft_id, tenant_id, task_id, receipt_id, version, content_json, content_digest, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (draft_id, binding["tenant_id"], task_id, receipt_id, version,
             canonical_json(content), content_digest, now),
        )
        connection.execute("UPDATE task_bindings SET status = 'WAITING_HANDOFF' WHERE task_id = ?", (task_id,))
        write_outbox_event(
            connection, tenant_id=str(binding["tenant_id"]), task_id=task_id,
            source_kind="S2_DRAFT", source_id=draft_id, event_kind="S2_DRAFT_FROZEN",
            payload={"task_id": task_id, "task_status": "WAITING_HANDOFF", "reason_code": "HANDOFF_READY"},
            created_at=now,
        )
        row = connection.execute("SELECT * FROM s2_handoff_drafts WHERE draft_id = ?", (draft_id,)).fetchone()
        assert row is not None
        return _draft_dict(row)


def _draft_dict(row: sqlite3.Row) -> dict[str, object]:
    return {
        "draft_id": str(row["draft_id"]), "task_id": str(row["task_id"]),
        "outcome": "HANDOFF_READY",
        "receipt_id": str(row["receipt_id"]), "version": int(row["version"]),
        "content": json.loads(str(row["content_json"])),
        "content_digest": str(row["content_digest"]), "created_at": str(row["created_at"]),
        "status": "FROZEN",
    }


def get_s2_task_outcome(path: str | Path, task_id: str) -> dict[str, object]:
    from opspilot.domain.d2 import get_task_binding
    from opspilot.domain.s2_handoff import get_s2_handoff_outcome

    binding = get_task_binding(path, task_id)
    accepted = get_s2_handoff_outcome(path, task_id)
    if accepted is not None:
        return accepted
    with connect(path) as connection:
        receipt_row = connection.execute(
            """SELECT * FROM s2_diagnosis_receipts WHERE tenant_id = ? AND task_id = ?
               ORDER BY created_at DESC, receipt_id DESC LIMIT 1""",
            (binding["tenant_id"], task_id),
        ).fetchone()
        if receipt_row is None:
            safe_stop = connection.execute(
                """SELECT decision, reason_code FROM s2_gate_traces
                   WHERE tenant_id = ? AND task_id = ? AND decision IN ('NO_ACTION', 'INCONCLUSIVE')
                   ORDER BY created_at DESC, rowid DESC LIMIT 1""",
                (binding["tenant_id"], task_id),
            ).fetchone()
            if safe_stop is not None:
                return {
                    "task_id": task_id,
                    "task_status": str(binding["status"]),
                    "business_outcome": str(safe_stop["decision"]),
                    "currentness": "CURRENT",
                    "reason_code": str(safe_stop["reason_code"]),
                    "diagnosis_receipt": None,
                    "draft": None,
                    "handoff_receipt": None,
                    "submitted": False,
                    "scope_authorized": False,
                }
            return {"task_id": task_id, "task_status": str(binding["status"]), "business_outcome": "NO_S2_DIAGNOSIS"}
        draft_row = connection.execute(
            """SELECT * FROM s2_handoff_drafts WHERE tenant_id = ? AND task_id = ? AND receipt_id = ?""",
            (binding["tenant_id"], task_id, receipt_row["receipt_id"]),
        ).fetchone()
        receipt = _receipt_dict(receipt_row)
        draft = _draft_dict(draft_row) if draft_row is not None else None
    gate = _current_receipt_gate(path, receipt)
    current = (
        gate.get("decision") == "DIAGNOSED"
        and gate.get("request_id") == receipt["request_id"]
        and gate.get("decision_id") == receipt["decision_id"]
        and gate.get("evidence_digests") == receipt["evidence_digests"]
    )
    return {
        "task_id": task_id,
        "task_status": str(binding["status"]),
        "business_outcome": ("HANDOFF_READY" if draft else "DIAGNOSED") if current else "INCONCLUSIVE",
        "currentness": "CURRENT" if current else "INVALIDATED_BY_CURRENT_FACTS",
        "reason_code": str(gate.get("reason_code") or "S2_RECEIPT_NO_LONGER_CURRENT"),
        "diagnosis_receipt": receipt,
        "draft": draft if current else ({**draft, "current": False} if draft else None),
        "handoff_receipt": None,
        "submitted": False,
        "scope_authorized": False,
    }


def s2_terminal_is_authoritative(
    path: str | Path, task_id: str, run_id: str, state: dict[str, object],
) -> bool:
    if state.get("handoff_draft_id") and state.get("diagnosis_receipt_id"):
        outcome = get_s2_task_outcome(path, task_id)
        draft = outcome.get("draft")
        receipt = outcome.get("diagnosis_receipt")
        return bool(
            outcome.get("business_outcome") == "HANDOFF_READY"
            and isinstance(draft, dict) and draft.get("draft_id") == state.get("handoff_draft_id")
            and isinstance(receipt, dict) and receipt.get("receipt_id") == state.get("diagnosis_receipt_id")
        )
    trace_id = state.get("s2_gate_trace_id")
    if not isinstance(trace_id, str) or not trace_id:
        return False
    with connect(path) as connection:
        row = connection.execute(
            """SELECT decision FROM s2_gate_traces
               WHERE trace_id = ? AND task_id = ? AND run_id = ?""",
            (trace_id, task_id, run_id),
        ).fetchone()
        current = connection.execute(
            "SELECT status FROM task_bindings WHERE task_id = ?",
            (task_id,),
        ).fetchone()
        artifacts = int(connection.execute(
            "SELECT COUNT(*) FROM s2_diagnosis_receipts WHERE task_id = ? AND run_id = ?",
            (task_id, run_id),
        ).fetchone()[0])
    if row is None or current is None or artifacts:
        return False
    expected_status = "NO_ACTION" if str(row["decision"]) == "NO_ACTION" else "INCONCLUSIVE"
    return str(row["decision"]) in {"NO_ACTION", "INCONCLUSIVE"} and str(current["status"]) == expected_status
