from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from opspilot.domain.client import probe_orders
from opspilot.domain.database import connect, get_auth_event, get_integration_info, initialize


AttemptKind = Literal["MODEL", "MCP"]
MAX_MODEL_CALLS = 8
MAX_MCP_ATTEMPTS = 6
EVIDENCE_MAX_AGE_SECONDS = 300


class D2Error(RuntimeError):
    pass


class ScopeDenied(D2Error):
    pass


class BudgetExhausted(D2Error):
    def __init__(self, kind: str, used: int, limit: int):
        super().__init__(f"{kind} attempt budget exhausted ({used}/{limit}).")
        self.kind = kind
        self.used = used
        self.limit = limit


class ToolUnavailable(D2Error):
    def __init__(self, error_code: str):
        super().__init__(error_code)
        self.error_code = error_code


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def digest_json(value: object) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _dict_row(row: Any) -> dict[str, object]:
    return {key: row[key] for key in row.keys()}


def create_task_binding(
    path: str | Path,
    actor_id: str,
    service_id: str,
    integration_id: str,
    ticket_id: str = "INC-A-001",
    *,
    session_id: str | None = None,
) -> dict[str, object]:
    """Create an immutable task binding from the local trusted operator registry."""
    initialize(path)
    with connect(path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        created = _create_task_binding_in_transaction(
            connection, actor_id, service_id, integration_id, ticket_id, session_id=session_id
        )
        result = connection.execute("SELECT * FROM task_bindings WHERE task_id = ?", (created["task_id"],)).fetchone()
    return {**_dict_row(result), "session_id": created["session_id"]}


def _create_task_binding_in_transaction(
    connection,
    actor_id: str,
    service_id: str,
    integration_id: str,
    ticket_id: str,
    *,
    session_id: str | None = None,
) -> dict[str, object]:
    """Shared trusted task-binding creation used by Domain and atomic Web admission."""
    task_id = f"task-{uuid.uuid4()}"
    thread_id = f"opspilot-{uuid.uuid4()}"
    operator = connection.execute(
        "SELECT tenant_id, role FROM trusted_operators WHERE actor_id = ?", (actor_id,)
    ).fetchone()
    if operator is None or operator["role"] != "SUPPORT":
        raise ScopeDenied("The caller is not a trusted support operator.")
    tenant_id = str(operator["tenant_id"])
    resource = connection.execute(
        """SELECT s.service_id, i.integration_id, i.principal_id
           FROM services AS s
           JOIN integrations AS i ON i.tenant_id = s.tenant_id AND i.integration_id = s.integration_id
           JOIN principals AS p ON p.tenant_id = i.tenant_id AND p.principal_id = i.principal_id
           WHERE s.tenant_id = ? AND s.service_id = ? AND i.integration_id = ?""",
        (tenant_id, service_id, integration_id),
    ).fetchone()
    if resource is None:
        raise ScopeDenied("Service and integration are not registered for the caller's tenant.")
    now = utc_now()
    connection.execute(
        """INSERT INTO task_bindings
           (task_id, thread_id, tenant_id, actor_id, service_id, integration_id,
            principal_id, ticket_id, status)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'CREATED')""",
        (task_id, thread_id, tenant_id, actor_id, service_id, integration_id,
         str(resource["principal_id"]), ticket_id),
    )
    connection.execute(
        "INSERT INTO thread_owners (thread_id, tenant_id, owner_id) VALUES (?, ?, ?)",
        (thread_id, tenant_id, actor_id),
    )
    connection.execute(
        """INSERT INTO task_controls
           (task_id, tenant_id, terminal_state, control_revision, pending_critical_message_seq,
            applied_critical_message_seq, changed_at, changed_by, reason)
           VALUES (?, ?, 'ACTIVE', 0, NULL, 0, ?, ?, 'task_created')""",
        (task_id, tenant_id, now, actor_id),
    )
    if session_id is None:
        session_id = f"session-{uuid.uuid4()}"
        connection.execute(
            """INSERT INTO sessions (session_id, tenant_id, owner_id, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?)""",
            (session_id, tenant_id, actor_id, now, now),
        )
    else:
        session = connection.execute(
            "SELECT 1 FROM sessions WHERE session_id = ? AND tenant_id = ? AND owner_id = ?",
            (session_id, tenant_id, actor_id),
        ).fetchone()
        if session is None:
            raise ScopeDenied("The session is not owned by the trusted task submitter.")
    connection.execute(
        """INSERT INTO session_task_links (session_id, task_id, tenant_id, linked_at, is_primary)
           VALUES (?, ?, ?, ?, 1)""",
        (session_id, task_id, tenant_id, now),
    )
    return {
        "task_id": task_id, "thread_id": thread_id, "tenant_id": tenant_id,
        "actor_id": actor_id, "service_id": service_id, "integration_id": integration_id,
        "principal_id": str(resource["principal_id"]), "session_id": session_id,
        "created_at": now,
    }


def get_task_binding(path: str | Path, task_id: str) -> dict[str, object]:
    with connect(path) as connection:
        row = connection.execute(
            """SELECT b.* FROM task_bindings AS b
               JOIN trusted_operators AS o
                 ON o.actor_id = b.actor_id AND o.tenant_id = b.tenant_id
               WHERE b.task_id = ? AND o.role = 'SUPPORT'""",
            (task_id,),
        ).fetchone()
    if row is None:
        raise ScopeDenied("Task binding is not available.")
    return _dict_row(row)


def authorize_thread_resume(
    path: str | Path, thread_id: str, actor_id: str
) -> dict[str, object]:
    """Check ownership before any graph/checkpoint API is called."""
    with connect(path) as connection:
        row = connection.execute(
            """SELECT b.* FROM task_bindings AS b
               JOIN trusted_operators AS o
                 ON o.actor_id = b.actor_id AND o.tenant_id = b.tenant_id
               JOIN thread_owners AS t
                 ON t.thread_id = b.thread_id AND t.tenant_id = b.tenant_id
                    AND t.owner_id = b.actor_id
               WHERE b.thread_id = ? AND b.actor_id = ? AND o.actor_id = ?
                 AND o.role = 'SUPPORT'""",
            (thread_id, actor_id, actor_id),
        ).fetchone()
    if row is None:
        raise ScopeDenied("Thread ownership check failed before checkpoint access.")
    return _dict_row(row)


def _bound_task(path: str | Path, task_id: str) -> dict[str, object]:
    return get_task_binding(path, task_id)


def _fact(
    binding: dict[str, object],
    *,
    fact_type: str,
    resource_id: str,
    data_source: str,
    observed_versions: dict[str, object],
    facts: dict[str, object],
    original_result_ref: str,
    observed_at: str | None = None,
) -> dict[str, object]:
    return {
        "tenant_id": binding["tenant_id"],
        "task_id": binding["task_id"],
        "fact_type": fact_type,
        "resource_id": resource_id,
        "principal_id": binding["principal_id"],
        "data_source": data_source,
        "observed_at": observed_at or utc_now(),
        "observed_versions": observed_versions,
        "facts": facts,
        "original_result_ref": original_result_ref,
        "trust_class": "untrusted_tool_observation",
    }


def get_integration_config_fact(
    path: str | Path, task_id: str, integration_id: str
) -> dict[str, object]:
    binding = _bound_task(path, task_id)
    if integration_id != binding["integration_id"]:
        raise ScopeDenied("Integration is outside the immutable TaskBinding scope.")
    with connect(path) as connection:
        row = connection.execute(
            """SELECT i.integration_id, i.principal_id, i.credential_ref, i.config_version
               FROM integrations AS i
               JOIN task_bindings AS b
                 ON b.tenant_id = i.tenant_id AND b.integration_id = i.integration_id
               WHERE b.task_id = ? AND i.integration_id = ?""",
            (task_id, integration_id),
        ).fetchone()
    if row is None:
        raise ScopeDenied("Integration is outside the immutable TaskBinding scope.")
    facts = _dict_row(row)
    return _fact(
        binding,
        fact_type="integration_config",
        resource_id=integration_id,
        data_source="sqlite:integrations",
        observed_versions={"config_version": int(facts["config_version"])},
        facts=facts,
        original_result_ref=f"domain://integration/{integration_id}/config",
    )


def get_principal_status_fact(
    path: str | Path, task_id: str, principal_id: str
) -> dict[str, object]:
    binding = _bound_task(path, task_id)
    if principal_id != binding["principal_id"]:
        raise ScopeDenied("Principal is outside the immutable TaskBinding scope.")
    with connect(path) as connection:
        row = connection.execute(
            """SELECT p.principal_id, p.status, p.principal_version
               FROM principals AS p
               JOIN task_bindings AS b
                 ON b.tenant_id = p.tenant_id AND b.principal_id = p.principal_id
               WHERE b.task_id = ? AND p.principal_id = ?""",
            (task_id, principal_id),
        ).fetchone()
    if row is None:
        raise ScopeDenied("Principal is outside the immutable TaskBinding scope.")
    facts = _dict_row(row)
    return _fact(
        binding,
        fact_type="principal_status",
        resource_id=principal_id,
        data_source="sqlite:principals",
        observed_versions={"principal_version": int(facts["principal_version"])},
        facts=facts,
        original_result_ref=f"domain://principal/{principal_id}/status",
    )


def consume_tool_fault(path: str | Path, task_id: str, tool_name: str) -> str | None:
    with connect(path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute(
            "SELECT remaining_calls, error_code FROM d2_tool_faults WHERE task_id = ? AND tool_name = ?",
            (task_id, tool_name),
        ).fetchone()
        if row is None or int(row["remaining_calls"]) <= 0:
            return None
        connection.execute(
            "UPDATE d2_tool_faults SET remaining_calls = remaining_calls - 1 WHERE task_id = ? AND tool_name = ?",
            (task_id, tool_name),
        )
        return str(row["error_code"])


def inject_read_tool_failure_for_test(
    path: str | Path, task_id: str, tool_name: str, error_code: str, calls: int = 6
) -> None:
    if tool_name not in {"get_integration_config", "get_principal_status", "get_auth_policy", "probe_endpoint"}:
        raise ValueError("Only a registered D2 read tool can receive a test-only fault.")
    if calls < 1 or calls > MAX_MCP_ATTEMPTS:
        raise ValueError("Fault call count must fit within the D2 MCP attempt budget.")
    with connect(path) as connection:
        connection.execute(
            """INSERT INTO d2_tool_faults (task_id, tool_name, remaining_calls, error_code)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(task_id, tool_name) DO UPDATE SET
                 remaining_calls = excluded.remaining_calls,
                 error_code = excluded.error_code""",
            (task_id, tool_name, calls, error_code),
        )


def get_auth_policy_fact(
    path: str | Path, task_id: str, service_id: str
) -> dict[str, object]:
    binding = _bound_task(path, task_id)
    if service_id != binding["service_id"]:
        raise ScopeDenied("Service is outside the immutable TaskBinding scope.")
    injected_error = consume_tool_fault(path, task_id, "get_auth_policy")
    if injected_error:
        raise ToolUnavailable(injected_error)
    with connect(path) as connection:
        row = connection.execute(
            """SELECT a.service_id, a.accepted_credential_ref, a.policy_version
               FROM auth_policies AS a
               JOIN task_bindings AS b
                 ON b.tenant_id = a.tenant_id AND b.service_id = a.service_id
               WHERE b.task_id = ? AND a.service_id = ?""",
            (task_id, service_id),
        ).fetchone()
    if row is None:
        raise ToolUnavailable("POLICY_SOURCE_UNAVAILABLE")
    facts = _dict_row(row)
    return _fact(
        binding,
        fact_type="auth_policy",
        resource_id=service_id,
        data_source="sqlite:auth_policies",
        observed_versions={"policy_version": int(facts["policy_version"])},
        facts=facts,
        original_result_ref=f"domain://service/{service_id}/auth-policy",
    )


def _live_versions(path: str | Path, binding: dict[str, object]) -> dict[str, object]:
    with connect(path) as connection:
        row = connection.execute(
            """SELECT i.config_version, p.principal_version, a.policy_version
               FROM task_bindings AS b
               JOIN integrations AS i
                 ON i.tenant_id = b.tenant_id AND i.integration_id = b.integration_id
               JOIN principals AS p
                 ON p.tenant_id = b.tenant_id AND p.principal_id = b.principal_id
               LEFT JOIN auth_policies AS a
                 ON a.tenant_id = b.tenant_id AND a.service_id = b.service_id
               WHERE b.task_id = ?""",
            (binding["task_id"],),
        ).fetchone()
    if row is None:
        raise ScopeDenied("The live probe resources are outside TaskBinding scope.")
    return {
        "config_version": int(row["config_version"]),
        "principal_version": int(row["principal_version"]),
        "policy_version": int(row["policy_version"]) if row["policy_version"] is not None else None,
    }


def probe_endpoint_fact(
    path: str | Path,
    task_id: str,
    service_id: str,
    integration_id: str,
    base_url: str,
) -> dict[str, object]:
    binding = _bound_task(path, task_id)
    if service_id != binding["service_id"] or integration_id != binding["integration_id"]:
        raise ScopeDenied("Probe target is outside the immutable TaskBinding scope.")
    before = _live_versions(path, binding)
    result = probe_orders(
        path,
        base_url,
        tenant_id=str(binding["tenant_id"]),
        integration_id=str(binding["integration_id"]),
    )
    after = _live_versions(path, binding)
    event: dict[str, object] | None = None
    if result.event_id is not None:
        try:
            event = get_auth_event(path, str(binding["tenant_id"]), result.event_id)
        except LookupError:
            event = None
    event_matches = bool(
        event
        and event.get("integration_id") == binding["integration_id"]
        and event.get("principal_id") == binding["principal_id"]
        and event.get("service_id") == binding["service_id"]
        and event.get("route") == result.route
        and event.get("result_code") == ("AUTH_REJECTED" if result.status_code == 401 else "AUTH_ACCEPTED")
    )
    stable = before == after and result.config_version == before["config_version"]
    facts: dict[str, object] = {
        "service_id": service_id,
        "integration_id": integration_id,
        "principal_id": result.principal_id,
        "route": result.route,
        "http_status": result.status_code,
        "request_id": result.request_id,
        "auth_event_id": result.event_id,
        "auth_event_observed_at": event.get("observed_at") if event else None,
        "auth_event_result": event.get("result_code") if event else None,
        "auth_event_scope_valid": event_matches,
        "credential_ref": result.credential_ref,
        "business_order_id": result.body.get("order_id"),
        "business_order_status": result.body.get("status"),
        "versions_stable_during_probe": stable,
    }
    return _fact(
        binding,
        fact_type="endpoint_probe",
        resource_id=f"{service_id}:{integration_id}:{result.route}",
        data_source="http:loopback-demo-business-api",
        observed_versions={"before": before, "after": after},
        facts=facts,
        original_result_ref=f"http://127.0.0.1:loopback{result.route}#{result.request_id or 'missing-request-id'}",
        observed_at=event.get("observed_at") if event and isinstance(event.get("observed_at"), str) else utc_now(),
    )


def reserve_attempt(
    path: str | Path,
    task_id: str,
    kind: AttemptKind,
    limit: int,
    *,
    call_id: str,
    tool_call_id: str | None = None,
    tool_name: str | None = None,
    argument_digest: str | None = None,
    context_provenance: dict[str, object] | None = None,
    task_run_control: dict[str, object] | None = None,
) -> tuple[str, int]:
    if kind not in {"MODEL", "MCP"} or limit < 1:
        raise ValueError("Invalid D2 attempt kind or limit.")
    attempt_id = f"attempt-{uuid.uuid4()}"
    with connect(path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        if task_run_control is None and context_provenance is not None:
            candidate = context_provenance.get("task_run_control")
            task_run_control = candidate if isinstance(candidate, dict) and candidate else None
        if task_run_control is not None:
            from opspilot.domain.investigation_context import validate_task_run_context_in_transaction

            validate_task_run_context_in_transaction(connection, task_id, task_run_control)
        binding = connection.execute(
            "SELECT task_id FROM task_bindings WHERE task_id = ?", (task_id,)
        ).fetchone()
        if binding is None:
            raise ScopeDenied("Attempt cannot be reserved without a trusted TaskBinding.")
        used = int(
            connection.execute(
                "SELECT COUNT(*) AS n FROM d2_attempts WHERE task_id = ? AND kind = ?",
                (task_id, kind),
            ).fetchone()["n"]
        )
        if used >= limit:
            raise BudgetExhausted(kind, used, limit)
        connection.execute(
            """INSERT INTO d2_attempts
               (attempt_id, task_id, kind, call_id, tool_call_id, tool_name, argument_digest)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (attempt_id, task_id, kind, call_id, tool_call_id, tool_name, argument_digest),
        )
        if context_provenance is not None:
            if kind != "MODEL":
                raise ValueError("Context Provenance can only be attached to a MODEL attempt.")
            from opspilot.domain.episodic_memory import insert_context_provenance_in_transaction

            skill = context_provenance.get("selected_skill")
            memories = context_provenance.get("selected_memories", [])
            evidence_ids = context_provenance.get("evidence_ids", [])
            input_refs = context_provenance.get("selected_input_messages", [])
            run_control = context_provenance.get("task_run_control", {})
            if not isinstance(memories, list) or not isinstance(evidence_ids, list) or not isinstance(input_refs, list):
                raise ValueError("Context Provenance source lists must be arrays.")
            if not isinstance(run_control, dict):
                raise ValueError("Task Run control provenance must be an object.")
            insert_context_provenance_in_transaction(
                connection,
                task_id=task_id,
                attempt_id=attempt_id,
                model_id=str(context_provenance["model_id"]),
                prompt_version=str(context_provenance["prompt_version"]),
                prompt_digest=str(context_provenance["prompt_digest"]),
                tool_schema_version=str(context_provenance["tool_schema_version"]),
                tool_schema_digest=str(context_provenance["tool_schema_digest"]),
                selected_skill=skill if isinstance(skill, dict) else None,
                selected_memories=[item for item in memories if isinstance(item, dict)],
                evidence_ids=[str(item) for item in evidence_ids],
                selected_input_messages=[item for item in input_refs if isinstance(item, dict)],
                task_run_control=run_control,
            )
    return attempt_id, used + 1


def finish_attempt(
    path: str | Path,
    attempt_id: str,
    status: str,
    *,
    result_digest: str | None = None,
    error_class: str | None = None,
) -> None:
    with connect(path) as connection:
        connection.execute(
            """UPDATE d2_attempts SET status = ?, completed_at = CURRENT_TIMESTAMP,
                       result_digest = ?, error_class = ? WHERE attempt_id = ?""",
            (status, result_digest, error_class, attempt_id),
        )


def attempt_counts(path: str | Path, task_id: str) -> dict[str, int]:
    with connect(path) as connection:
        rows = connection.execute(
            "SELECT kind, COUNT(*) AS n FROM d2_attempts WHERE task_id = ? GROUP BY kind",
            (task_id,),
        ).fetchall()
    counts = {"MODEL": 0, "MCP": 0}
    counts.update({str(row["kind"]): int(row["n"]) for row in rows})
    return counts


def save_model_trace(
    path: str | Path,
    *,
    task_id: str,
    call_id: str,
    attempt_id: str,
    model_id: str,
    prompt_digest: str,
    input_evidence_ids: list[str],
    provider_response_id: str | None,
    tool_calls: list[dict[str, object]],
    assistant_text: str,
    usage: dict[str, object],
    status: str,
) -> None:
    with connect(path) as connection:
        connection.execute(
            """INSERT INTO d2_model_traces
               (call_id, task_id, attempt_id, model_id, prompt_digest,
                input_evidence_ids_json, provider_response_id, tool_calls_json,
                assistant_text, usage_json, status)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                call_id,
                task_id,
                attempt_id,
                model_id,
                prompt_digest,
                canonical_json(input_evidence_ids),
                provider_response_id,
                canonical_json(tool_calls),
                assistant_text[:2000],
                canonical_json(usage),
                status,
            ),
        )
        for call in tool_calls:
            connection.execute(
                """INSERT INTO d2_pending_tool_calls
                   (task_id, call_id, tool_call_id, tool_name, arguments_json)
                   VALUES (?, ?, ?, ?, ?)""",
                (
                    task_id,
                    call_id,
                    str(call["id"]),
                    str(call["name"]),
                    canonical_json(call.get("args", {})),
                ),
            )


def _pending_ref(call_id: str, tool_call_id: str) -> str:
    return f"{call_id}|{tool_call_id}"


def parse_pending_ref(value: str) -> tuple[str, str]:
    call_id, separator, tool_call_id = value.partition("|")
    if not separator or not call_id or not tool_call_id:
        raise ValueError("Invalid pending tool call reference.")
    return call_id, tool_call_id


def get_pending_tool_call(path: str | Path, task_id: str, reference: str) -> dict[str, object]:
    call_id, tool_call_id = parse_pending_ref(reference)
    with connect(path) as connection:
        row = connection.execute(
            """SELECT * FROM d2_pending_tool_calls
               WHERE task_id = ? AND call_id = ? AND tool_call_id = ? AND status = 'PENDING'""",
            (task_id, call_id, tool_call_id),
        ).fetchone()
    if row is None:
        raise D2Error("Pending model tool call is missing or already consumed.")
    item = _dict_row(row)
    item["arguments"] = json.loads(str(item.pop("arguments_json")))
    return item


def complete_pending_tool_call(
    path: str | Path, task_id: str, call_id: str, tool_call_id: str, status: str
) -> None:
    with connect(path) as connection:
        connection.execute(
            """UPDATE d2_pending_tool_calls SET status = ?
               WHERE task_id = ? AND call_id = ? AND tool_call_id = ?""",
            (status, task_id, call_id, tool_call_id),
        )


def record_tool_observation(
    path: str | Path,
    *,
    task_id: str,
    call_id: str,
    attempt_id: str | None,
    tool_call_id: str,
    tool_name: str,
    arguments: dict[str, object],
    status: str,
    result: dict[str, object] | None,
    error_class: str | None = None,
) -> dict[str, object]:
    binding = _bound_task(path, task_id)
    observation_id = f"observation-{uuid.uuid4()}"
    argument_digest = digest_json(arguments)
    result_digest = digest_json(result) if result is not None else None
    evidence_id: str | None = None
    progress_added = False

    if status == "OK" and result is not None:
        required = {
            "tenant_id", "task_id", "fact_type", "resource_id", "principal_id",
            "data_source", "observed_at", "observed_versions", "facts",
            "original_result_ref", "trust_class",
        }
        if set(result) != required:
            status = "PROTOCOL_ERROR"
            error_class = "INVALID_FACT_ENVELOPE"
            result = None
            result_digest = None
        elif (
            result["task_id"] != task_id
            or result["tenant_id"] != binding["tenant_id"]
            or result["principal_id"] != binding["principal_id"]
            or result["trust_class"] != "untrusted_tool_observation"
        ):
            status = "PROTOCOL_ERROR"
            error_class = "FACT_SCOPE_MISMATCH"
            result = None
            result_digest = None

    evidence_digest: str | None = None
    if status == "OK" and result is not None:
        evidence_digest = digest_json(
            {
                key: result[key]
                for key in (
                    "tenant_id", "task_id", "fact_type", "resource_id", "principal_id",
                    "data_source", "observed_versions", "facts", "trust_class",
                )
            }
        )
        with connect(path) as connection:
            existing = connection.execute(
                """SELECT evidence_id FROM d2_evidence
                   WHERE task_id = ? AND fact_type = ? AND resource_id = ? AND digest = ?
                   ORDER BY fetched_at DESC LIMIT 1""",
                (task_id, result["fact_type"], result["resource_id"], evidence_digest),
            ).fetchone()
            if existing is not None:
                evidence_id = str(existing["evidence_id"])
            else:
                evidence_id = f"evidence-{uuid.uuid4()}"
                connection.execute(
                    """INSERT INTO d2_evidence
                       (evidence_id, tenant_id, task_id, call_id, tool_call_id,
                        resource_id, principal_id, data_source, fetched_at,
                        observed_versions_json, fact_type, facts_json,
                        original_result_ref, trust_class, digest)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        evidence_id,
                        result["tenant_id"],
                        task_id,
                        call_id,
                        tool_call_id,
                        result["resource_id"],
                        result["principal_id"],
                        result["data_source"],
                        result["observed_at"],
                        canonical_json(result["observed_versions"]),
                        result["fact_type"],
                        canonical_json(result["facts"]),
                        f"observation://{observation_id}",
                        result["trust_class"],
                        evidence_digest,
                    ),
                )
                progress_added = True

    stored_result = result if result is not None else ({"error_code": error_class} if error_class else None)
    with connect(path) as connection:
        connection.execute(
            """INSERT INTO d2_tool_observations
               (observation_id, task_id, call_id, attempt_id, tool_call_id, tool_name,
                argument_digest, status, progress_added, error_class, result_digest,
                result_json, evidence_id)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                observation_id,
                task_id,
                call_id,
                attempt_id,
                tool_call_id,
                tool_name,
                argument_digest,
                status,
                1 if progress_added else 0,
                error_class,
                result_digest,
                canonical_json(stored_result) if stored_result is not None else None,
                evidence_id,
            ),
        )
    return {
        "observation_id": observation_id,
        "evidence_id": evidence_id,
        "progress_added": progress_added,
        "status": status,
        "tool_name": tool_name,
        "tool_call_id": tool_call_id,
        "call_id": call_id,
        "attempt_id": attempt_id,
        "result_digest": result_digest,
        "error_class": error_class,
    }


def list_evidence(path: str | Path, task_id: str, evidence_ids: list[str] | None = None) -> list[dict[str, object]]:
    with connect(path) as connection:
        if evidence_ids is not None:
            if not evidence_ids:
                return []
            placeholders = ",".join("?" for _ in evidence_ids)
            rows = connection.execute(
                f"SELECT * FROM d2_evidence WHERE task_id = ? AND evidence_id IN ({placeholders}) ORDER BY fetched_at",
                (task_id, *evidence_ids),
            ).fetchall()
        else:
            rows = connection.execute(
                "SELECT * FROM d2_evidence WHERE task_id = ? ORDER BY fetched_at",
                (task_id,),
            ).fetchall()
    result: list[dict[str, object]] = []
    for row in rows:
        item = _dict_row(row)
        item["observed_versions"] = json.loads(str(item.pop("observed_versions_json")))
        item["facts"] = json.loads(str(item.pop("facts_json")))
        result.append(item)
    return result


def list_observations(path: str | Path, task_id: str) -> list[dict[str, object]]:
    with connect(path) as connection:
        rows = connection.execute(
            "SELECT * FROM d2_tool_observations WHERE task_id = ? ORDER BY created_at, rowid",
            (task_id,),
        ).fetchall()
    result: list[dict[str, object]] = []
    for row in rows:
        item = _dict_row(row)
        if item.get("result_json"):
            item["result"] = json.loads(str(item.pop("result_json")))
        else:
            item.pop("result_json", None)
        item["progress_added"] = bool(item["progress_added"])
        result.append(item)
    return result


def list_model_traces(path: str | Path, task_id: str) -> list[dict[str, object]]:
    with connect(path) as connection:
        rows = connection.execute(
            "SELECT * FROM d2_model_traces WHERE task_id = ? ORDER BY created_at, rowid",
            (task_id,),
        ).fetchall()
    result: list[dict[str, object]] = []
    for row in rows:
        item = _dict_row(row)
        item["tool_calls"] = json.loads(str(item.pop("tool_calls_json")))
        item["input_evidence_ids"] = json.loads(str(item.pop("input_evidence_ids_json")))
        item["usage"] = json.loads(str(item.pop("usage_json")))
        result.append(item)
    return result


def _stable_diagnostic_fact_digest(item: dict[str, object]) -> str:
    facts = item.get("facts")
    if item.get("fact_type") != "endpoint_probe" or not isinstance(facts, dict):
        return digest_json(facts)
    # Per-probe correlation IDs and timestamps are expected to vary. Compare only
    # fields that can change the diagnosis or the Evidence Gate's safety result.
    stable_fields = (
        "service_id",
        "integration_id",
        "principal_id",
        "route",
        "http_status",
        "auth_event_result",
        "credential_ref",
        "versions_stable_during_probe",
        "auth_event_scope_valid",
        "business_order_id",
        "business_order_status",
    )
    return digest_json({key: facts.get(key) for key in stable_fields})


def evaluate_evidence_gate(
    path: str | Path,
    task_id: str,
    evidence_ids: list[str],
    diagnosis_draft: dict[str, object] | None = None,
) -> dict[str, object]:
    """Deterministic D2 gate. It deliberately does not read model text as a decision."""
    del diagnosis_draft  # Model prose is informational; only typed observations decide the gate.
    binding = get_task_binding(path, task_id)
    evidence = list_evidence(path, task_id, evidence_ids)
    observations = list_observations(path, task_id)
    counts = attempt_counts(path, task_id)
    used_ids = {str(item["evidence_id"]) for item in evidence}
    if used_ids != set(evidence_ids):
        return _gate("INCONCLUSIVE", "EVIDENCE_REFERENCE_INVALID", evidence_ids, missing=[], conflicting=evidence_ids)

    now = datetime.now(timezone.utc)
    conflicting: list[str] = []
    facts_by_type: dict[str, list[dict[str, object]]] = {}
    for item in evidence:
        fetched_text = str(item["fetched_at"])
        try:
            fetched = datetime.fromisoformat(fetched_text.replace("Z", "+00:00"))
            if fetched.tzinfo is None:
                fetched = fetched.replace(tzinfo=timezone.utc)
        except ValueError:
            conflicting.append(str(item["evidence_id"]))
            continue
        age = (now - fetched.astimezone(timezone.utc)).total_seconds()
        if (
            item["tenant_id"] != binding["tenant_id"]
            or item["task_id"] != task_id
            or item["principal_id"] != binding["principal_id"]
            or item["trust_class"] != "untrusted_tool_observation"
            or age < -30
            or age > EVIDENCE_MAX_AGE_SECONDS
        ):
            conflicting.append(str(item["evidence_id"]))
            continue
        facts_by_type.setdefault(str(item["fact_type"]), []).append(item)

    if conflicting:
        return _gate("INCONCLUSIVE", "EVIDENCE_SCOPE_OR_FRESHNESS_INVALID", evidence_ids, missing=[], conflicting=conflicting)

    sources = {
        "integration_config": "sqlite:integrations",
        "principal_status": "sqlite:principals",
        "auth_policy": "sqlite:auth_policies",
        "endpoint_probe": "http:loopback-demo-business-api",
    }
    for item in evidence:
        fact_type = str(item["fact_type"])
        if fact_type not in sources or item["data_source"] != sources[fact_type]:
            conflicting.append(str(item["evidence_id"]))
    if conflicting:
        return _gate("INCONCLUSIVE", "EVIDENCE_SOURCE_INVALID", evidence_ids, missing=[], conflicting=conflicting)

    for items in facts_by_type.values():
        seen: dict[str, str] = {}
        for item in items:
            version_key = canonical_json(item["observed_versions"])
            facts_digest = _stable_diagnostic_fact_digest(item)
            if version_key in seen and seen[version_key] != facts_digest:
                conflicting.extend(str(candidate["evidence_id"]) for candidate in items)
                break
            seen[version_key] = facts_digest
    if conflicting:
        return _gate("INCONCLUSIVE", "CONTRADICTORY_FACTS_AT_SAME_VERSION", evidence_ids, missing=[], conflicting=sorted(set(conflicting)))

    def newest(fact_type: str) -> dict[str, object] | None:
        items = facts_by_type.get(fact_type, [])
        return max(items, key=lambda item: str(item["fetched_at"])) if items else None

    config = newest("integration_config")
    principal = newest("principal_status")
    policy = newest("auth_policy")
    probe = newest("endpoint_probe")
    missing: list[str] = []
    if config is None:
        missing.append("integration_config")
    if principal is None:
        missing.append("principal_status")
    if policy is None:
        missing.append("auth_policy")
    if probe is None:
        missing.append("live_401_endpoint_probe")

    config_facts = config["facts"] if config else {}
    principal_facts = principal["facts"] if principal else {}
    policy_facts = policy["facts"] if policy else {}
    probe_facts = probe["facts"] if probe else {}
    probe_versions = probe["observed_versions"] if probe else {}
    before_versions = probe_versions.get("before", {}) if isinstance(probe_versions, dict) else {}
    after_versions = probe_versions.get("after", {}) if isinstance(probe_versions, dict) else {}

    scoped = True
    if config and (
        config["resource_id"] != binding["integration_id"]
        or config_facts.get("integration_id") != binding["integration_id"]
        or config_facts.get("principal_id") != binding["principal_id"]
    ):
        scoped = False
    if principal and (
        principal["resource_id"] != binding["principal_id"]
        or principal_facts.get("principal_id") != binding["principal_id"]
    ):
        scoped = False
    if policy and (
        policy["resource_id"] != binding["service_id"]
        or policy_facts.get("service_id") != binding["service_id"]
    ):
        scoped = False
    if probe and (
        probe_facts.get("service_id") != binding["service_id"]
        or probe_facts.get("integration_id") != binding["integration_id"]
        or probe_facts.get("principal_id") != binding["principal_id"]
        or probe_facts.get("route") != "/api/orders/demo-order"
        or probe["resource_id"] != f"{binding['service_id']}:{binding['integration_id']}:/api/orders/demo-order"
        or probe_facts.get("auth_event_scope_valid") is not True
    ):
        scoped = False
    if not scoped:
        return _gate("INCONCLUSIVE", "EVIDENCE_SCOPE_MISMATCH", evidence_ids, missing=[], conflicting=evidence_ids)

    no_progress = 0
    for observation in reversed(observations):
        if observation["progress_added"]:
            break
        no_progress += 1
    if no_progress >= 2:
        return _gate("INCONCLUSIVE", "REPEATED_QUERY_WITHOUT_NEW_EVIDENCE", evidence_ids, missing=missing, conflicting=[])

    if probe is not None and probe_facts.get("http_status") == 401:
        if probe_facts.get("versions_stable_during_probe") is not True:
            return _gate("INCONCLUSIVE", "RESOURCE_CHANGED_DURING_PROBE", evidence_ids, missing=missing, conflicting=[str(probe["evidence_id"])])
        if probe_facts.get("request_id") is None or probe_facts.get("auth_event_id") is None:
            return _gate("INCONCLUSIVE", "PROBE_NOT_CORRELATED_TO_AUTH_EVENT", evidence_ids, missing=missing, conflicting=[str(probe["evidence_id"])])

    if probe and principal and probe_facts.get("http_status") == 401:
        principal_version = principal_facts.get("principal_version")
        if before_versions.get("principal_version") != principal_version or after_versions.get("principal_version") != principal_version:
            return _gate("INCONCLUSIVE", "PRINCIPAL_VERSION_CONFLICT", evidence_ids, missing=missing, conflicting=[str(principal["evidence_id"]), str(probe["evidence_id"])])
        if principal_facts.get("status") == "DISABLED":
            return _gate("NO_ACTION", "PRINCIPAL_DISABLED", evidence_ids, missing=missing, conflicting=[])

    if missing:
        budget_spent = counts["MCP"] >= MAX_MCP_ATTEMPTS or counts["MODEL"] >= MAX_MODEL_CALLS
        if budget_spent:
            return _gate("INCONCLUSIVE", "EVIDENCE_MISSING_BUDGET_EXHAUSTED", evidence_ids, missing=missing, conflicting=[])
        return _gate("NEED_MORE", "REQUIRED_EVIDENCE_MISSING", evidence_ids, missing=missing, conflicting=[])

    if probe_facts.get("http_status") != 401:
        return _gate("NO_ACTION", "CURRENT_PROBE_NOT_401", evidence_ids, missing=[], conflicting=[])
    if probe_facts.get("auth_event_result") != "AUTH_REJECTED":
        return _gate("INCONCLUSIVE", "PROBE_AUTH_EVENT_CONFLICT", evidence_ids, missing=[], conflicting=[str(probe["evidence_id"])])

    expected_versions = {
        "config_version": config_facts.get("config_version"),
        "principal_version": principal_facts.get("principal_version"),
        "policy_version": policy_facts.get("policy_version"),
    }
    if before_versions != expected_versions or after_versions != expected_versions:
        return _gate("INCONCLUSIVE", "RESOURCE_VERSION_CONFLICT", evidence_ids, missing=[], conflicting=[str(config["evidence_id"]), str(principal["evidence_id"]), str(policy["evidence_id"]), str(probe["evidence_id"])])
    if principal_facts.get("status") != "ENABLED":
        return _gate("INCONCLUSIVE", "PRINCIPAL_STATUS_UNKNOWN", evidence_ids, missing=[], conflicting=[str(principal["evidence_id"])])
    current_ref = config_facts.get("credential_ref")
    accepted_ref = policy_facts.get("accepted_credential_ref")
    if not isinstance(current_ref, str) or not isinstance(accepted_ref, str):
        return _gate("INCONCLUSIVE", "CREDENTIAL_REFERENCE_INVALID", evidence_ids, missing=[], conflicting=[str(config["evidence_id"]), str(policy["evidence_id"])])
    if current_ref == accepted_ref:
        return _gate("NO_ACTION", "CREDENTIAL_REFERENCE_ALREADY_ACCEPTED", evidence_ids, missing=[], conflicting=[])
    return {
        "decision": "READY",
        "reason_code": "ENABLED_PRINCIPAL_AND_CREDENTIAL_REFERENCE_MISMATCH",
        "checked_fact_ids": evidence_ids,
        "missing_predicates": [],
        "stale_or_conflicting_ids": [],
        "plan_candidate": {
            "action_type": "SWITCH_CREDENTIAL_REF",
            "integration_id": binding["integration_id"],
            "new_credential_ref": accepted_ref,
            "expected_config_version": config_facts["config_version"],
            "expected_principal_version": principal_facts["principal_version"],
            "expected_auth_policy_version": policy_facts["policy_version"],
            "required_evidence_ids": evidence_ids,
        },
        "side_effects": [],
    }


def _gate(
    decision: str,
    reason_code: str,
    evidence_ids: list[str],
    *,
    missing: list[str],
    conflicting: list[str],
) -> dict[str, object]:
    return {
        "decision": decision,
        "reason_code": reason_code,
        "checked_fact_ids": evidence_ids,
        "missing_predicates": missing,
        "stale_or_conflicting_ids": conflicting,
        "side_effects": [],
    }


def save_immutable_report(path: str | Path, task_id: str, report: dict[str, object]) -> str:
    content = canonical_json(report)
    digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
    with connect(path) as connection:
        existing = connection.execute(
            "SELECT report_ref, content_digest FROM d2_reports WHERE task_id = ?", (task_id,)
        ).fetchone()
        if existing is not None:
            if existing["content_digest"] != digest:
                raise D2Error("An immutable D2 report already exists with different content.")
            return str(existing["report_ref"])
        report_ref = f"report-{uuid.uuid4()}"
        connection.execute(
            """INSERT INTO d2_reports
               (report_ref, task_id, content_digest, immutable_content_json)
               VALUES (?, ?, ?, ?)""",
            (report_ref, task_id, digest, content),
        )
        connection.execute(
            "UPDATE task_bindings SET status = 'COMPLETED' WHERE task_id = ?",
            (task_id,),
        )
    return report_ref


def read_report(path: str | Path, task_id: str) -> dict[str, object] | None:
    with connect(path) as connection:
        row = connection.execute(
            "SELECT report_ref, immutable_content_json FROM d2_reports WHERE task_id = ?", (task_id,)
        ).fetchone()
    if row is None:
        return None
    return {"report_ref": row["report_ref"], "report": json.loads(str(row["immutable_content_json"]))}


def build_report_body(
    path: str | Path,
    task_id: str,
    gate_decision: dict[str, object],
    diagnosis_draft: dict[str, object] | None,
) -> dict[str, object]:
    binding = get_task_binding(path, task_id)
    counts = attempt_counts(path, task_id)
    evidence = list_evidence(path, task_id)
    observations = list_observations(path, task_id)
    traces = list_model_traces(path, task_id)
    integration = get_integration_info(path, str(binding["tenant_id"]), str(binding["integration_id"]))
    return {
        "schema_version": "d2-report-v1",
        "task_binding": {
            "task_id": task_id,
            "thread_id": binding["thread_id"],
            "tenant_id": binding["tenant_id"],
            "actor_id": binding["actor_id"],
            "service_id": binding["service_id"],
            "integration_id": binding["integration_id"],
            "principal_id": binding["principal_id"],
            "ticket_id": binding["ticket_id"],
        },
        "gate_decision": gate_decision,
        "diagnosis_draft": diagnosis_draft or {},
        "evidence": evidence,
        "model_trace": traces,
        "mcp_trace": observations,
        "budget": {
            "limits": {"model_calls": MAX_MODEL_CALLS, "mcp_attempts": MAX_MCP_ATTEMPTS},
            "used": {"model_calls": counts["MODEL"], "mcp_attempts": counts["MCP"]},
        },
        "configuration_after_investigation": {
            "credential_ref": integration["credential_ref"],
            "config_version": integration["config_version"],
        },
        "side_effects": [],
        "known_limits": [
            "D2 is read-only; no approval, configuration update, or ticket write is implemented.",
            "The local trusted operator registry is a demonstration boundary, not production IAM.",
        ],
    }
