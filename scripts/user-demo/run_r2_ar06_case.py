"""Prepare or run one frozen R2 evaluation case in an isolated User Demo runtime.

The CLI is deliberately inert by default. Fixture execution is exercised by the
tests through the same Web API helper. Live execution requires an exact case
acknowledgement, an explicit application-budget ceiling, a fresh runtime, a
matching managed Live process, and a valid pre-existing Runtime Grant.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
import uuid
from decimal import Decimal, InvalidOperation
from pathlib import Path
from urllib.parse import urlparse
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
USER_DEMO_DIR = ROOT / "scripts" / "user-demo"
EVAL_DIR = ROOT / "docs" / "evidence" / "r2-ar06-eval-01"
CASES_PATH = EVAL_DIR / "CASES.json"
FROZEN_HASHES_PATH = EVAL_DIR / "FROZEN_HASHES.json"
SUPPORTED_CASES = {"E02-H", "E05-D", "E06-H", "E07-D"}
CASE_S3_PROFILES = {
    "E02-H": "standard",
    "E05-D": "standard",
    "E06-H": "standard",
    "E07-D": "r2-e07-queued",
}
E07_ORDER_ID = "async-order"
E07_EVENT_ID = "event-00000000-0000-4000-8000-000000000001"
DEFAULT_API_ORIGIN = "http://127.0.0.1:8000"
DEFAULT_WEB_ORIGIN = "http://127.0.0.1:5173"
DEFAULT_RUN_TIMEOUT_SECONDS = 600
DEFAULT_MAX_RUN_MODEL_DISPATCHES = 8

for path in (ROOT, USER_DEMO_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))


class EvaluationPreflightError(RuntimeError):
    """A safe, non-secret reason a case cannot be prepared or run."""


def load_frozen_case(case_id: str) -> dict[str, Any]:
    """Return only an explicitly prepared, single-turn development case.

    The case text is read verbatim from the frozen Gold. Expected answers,
    forbidden conditions and rubric labels are never returned to the caller.
    """
    if case_id not in SUPPORTED_CASES:
        raise ValueError("LIVE_CASE_NOT_PREPARED:" + str(case_id))
    cases_bytes = CASES_PATH.read_bytes()
    freeze = json.loads(FROZEN_HASHES_PATH.read_text(encoding="utf-8"))
    expected_hash = freeze["files"]["CASES.json"]["sha256"]
    actual_hash = hashlib.sha256(cases_bytes).hexdigest()
    if actual_hash != expected_hash:
        raise EvaluationPreflightError("FROZEN_CASES_DIGEST_MISMATCH")
    document = json.loads(cases_bytes.decode("utf-8"))
    matches = [item for item in document["cases"] if item.get("case_id") == case_id]
    if len(matches) != 1:
        raise EvaluationPreflightError("FROZEN_CASE_ID_NOT_UNIQUE")
    case = matches[0]
    turns = case.get("user_turns")
    split = case.get("split")
    if split not in {"D", "H"} or not isinstance(turns, list) or len(turns) != 1:
        raise EvaluationPreflightError("CASE_REQUIRES_ONE_FROZEN_TURN")
    if not isinstance(turns[0], str) or not turns[0].strip():
        raise EvaluationPreflightError("FROZEN_CASE_INPUT_INVALID")
    # Keep the fields the executor needs; Gold outcomes never enter Context.
    return {
        "case_id": case_id,
        "split": split,
        "user_turns": list(turns),
        "gold_sha256": actual_hash,
    }


def initialize_case_runtime(
    case_id: str,
    runtime_name: str,
    *,
    root: str | Path | None = None,
) -> Path:
    """Create a new runtime using the existing User Demo initializer only."""
    from initialize_demo import initialize_user_demo
    from runtime_paths import resolve_user_demo_runtime

    load_frozen_case(case_id)
    repo_root = Path(root or ROOT).resolve()
    if runtime_name == "user-demo":
        raise EvaluationPreflightError("EVALUATION_REQUIRES_NAMED_ISOLATED_RUNTIME")
    try:
        runtime_dir = resolve_user_demo_runtime(runtime_name, root=repo_root)
    except ValueError as error:
        raise EvaluationPreflightError("USER_DEMO_RUNTIME_NAME_INVALID") from error
    initialize_user_demo(
        runtime_dir,
        require_absent_directory=True,
        s3_fixture_profile=CASE_S3_PROFILES[case_id] if case_id in CASE_S3_PROFILES else "standard",
    )
    return runtime_dir


def _table_exists(connection, name: str) -> bool:
    return connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,),
    ).fetchone() is not None


def _count(connection, table: str) -> int:
    if not _table_exists(connection, table):
        return 0
    return int(connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0])


def inspect_case_runtime(
    case_id: str,
    runtime_name: str,
    *,
    root: str | Path | None = None,
) -> dict[str, Any]:
    """Inspect an isolated runtime without opening it for writes."""
    import sqlite3

    from runtime_paths import resolve_user_demo_database_paths, resolve_user_demo_runtime

    if case_id not in SUPPORTED_CASES:
        raise ValueError("LIVE_CASE_NOT_PREPARED:" + str(case_id))
    repo_root = Path(root or ROOT).resolve()
    try:
        runtime_dir = resolve_user_demo_runtime(runtime_name, root=repo_root)
        domain_path, checkpoint_path = resolve_user_demo_database_paths(runtime_name, root=repo_root)
    except ValueError as error:
        raise EvaluationPreflightError("USER_DEMO_RUNTIME_PATH_REJECTED") from error
    if not runtime_dir.is_dir() or not domain_path.is_file() or not checkpoint_path.is_file():
        raise EvaluationPreflightError("ISOLATED_RUNTIME_INCOMPLETE")
    for path in (runtime_dir, domain_path, checkpoint_path):
        if path.is_symlink() or (getattr(path, "is_junction", None) and path.is_junction()):
            raise EvaluationPreflightError("ISOLATED_RUNTIME_REPARSE_POINT")

    connection = sqlite3.connect(domain_path.resolve().as_uri() + "?mode=ro", uri=True)
    connection.execute("PRAGMA query_only = ON")
    connection.row_factory = sqlite3.Row
    try:
        counts = {
            "sessions": _count(connection, "sessions"),
            "messages": _count(connection, "messages"),
            "task_bindings": _count(connection, "task_bindings"),
            "task_runs": _count(connection, "task_runs"),
            "personal_memories": _count(connection, "personal_memories"),
            "assistant_calls": _count(connection, "assistant_calls"),
            "provider_spends": _count(connection, "assistant_runtime_spends"),
            "provider_send_grants": _count(connection, "assistant_runtime_spends") and int(
                connection.execute(
                    "SELECT COUNT(*) FROM assistant_runtime_spends WHERE send_granted_at IS NOT NULL",
                ).fetchone()[0]
            ) or 0,
            "unknown_requests": _count(connection, "assistant_runtime_spends") and int(
                connection.execute(
                    "SELECT COUNT(*) FROM assistant_runtime_spends WHERE status='UNKNOWN'",
                ).fetchone()[0]
            ) or 0,
        }
        grant_present = any(
            _count(connection, table) > 0 for table in (
                "assistant_runtime_authority", "assistant_runtime_pools",
                "assistant_runtime_default_grant",
            )
        )
        result: dict[str, Any] = {
            "runtime_name": runtime_name,
            "domain_path": str(domain_path),
            "checkpoint_path": str(checkpoint_path),
            **counts,
            "runtime_grant_present": grant_present,
        }
        result["fresh"] = all(
            counts[key] == 0 for key in (
                "sessions", "messages", "task_bindings", "task_runs",
                "personal_memories", "assistant_calls", "provider_spends",
            )
        )
        if case_id == "E07-D":
            row = connection.execute(
                """SELECT d.status AS delivery_status,d.event_id AS delivery_event_id,
                          d.receiver_http_status,r.status AS receiver_status,
                          r.event_id AS receiver_event_id
                   FROM s3_deliveries d JOIN s3_receivers r
                     ON r.tenant_id=d.tenant_id AND r.service_id=d.service_id AND r.order_id=d.order_id
                   WHERE d.tenant_id='tenant-a' AND d.order_id=?""",
                (E07_ORDER_ID,),
            ).fetchone()
            if row is not None:
                result.update({
                    "s3_order_id": E07_ORDER_ID,
                    "delivery_status": str(row["delivery_status"]),
                    "receiver_http_status": row["receiver_http_status"],
                    "receiver_status": str(row["receiver_status"]),
                    "delivery_event_id": str(row["delivery_event_id"]),
                    "receiver_event_id": str(row["receiver_event_id"]),
                })
            else:
                result["s3_order_id"] = None
        return result
    finally:
        connection.close()


def _loopback_url(value: str, *, label: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost"}:
        raise EvaluationPreflightError(label + "_MUST_USE_LOCAL_LOOPBACK")
    return value.rstrip("/")


def _manifest_matches(runtime_name: str, runtime_dir: Path, root: Path) -> dict[str, Any]:
    manifest_path = runtime_dir / "processes.json"
    if not manifest_path.is_file():
        raise EvaluationPreflightError("MANAGED_LIVE_SERVICES_NOT_RUNNING")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as error:
        raise EvaluationPreflightError("MANAGED_PROCESS_MANIFEST_INVALID") from error
    expected = {
        "root": root,
        "domainDb": runtime_dir / "domain.sqlite3",
        "checkpointDb": runtime_dir / "checkpoint.sqlite3",
    }
    if manifest.get("runtimeName") != runtime_name:
        raise EvaluationPreflightError("MANAGED_PROCESS_RUNTIME_MISMATCH")
    for field, path in expected.items():
        recorded = manifest.get(field)
        if not isinstance(recorded, str) or Path(recorded).resolve() != path.resolve():
            raise EvaluationPreflightError("MANAGED_PROCESS_PATH_MISMATCH")
    if manifest.get("mode") != "Live":
        raise EvaluationPreflightError("MANAGED_PROCESS_NOT_STARTED_IN_LIVE_MODE")
    return manifest


def _budget_micro(value: str | Decimal) -> int:
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError) as error:
        raise EvaluationPreflightError("AUTHORIZED_BUDGET_INVALID") from error
    if not amount.is_finite() or amount <= 0:
        raise EvaluationPreflightError("AUTHORIZED_BUDGET_INVALID")
    micro = amount * Decimal(1_000_000)
    if micro != micro.to_integral_value():
        raise EvaluationPreflightError("AUTHORIZED_BUDGET_PRECISION_INVALID")
    return int(micro)


def live_preflight(
    case_id: str,
    runtime_name: str,
    *,
    authorized_max_cost_usd: str,
    api_origin: str = DEFAULT_API_ORIGIN,
    root: str | Path | None = None,
    client: Any | None = None,
) -> dict[str, Any]:
    """Check one fresh Live runtime and existing grant before any chat POST."""
    import httpx

    from runtime_admin import preflight as grant_preflight, read_env
    from runtime_paths import resolve_user_demo_runtime

    repo_root = Path(root or ROOT).resolve()
    api_origin = _loopback_url(api_origin, label="API_ORIGIN")
    state = inspect_case_runtime(case_id, runtime_name, root=repo_root)
    if not state["fresh"]:
        raise EvaluationPreflightError("CASE_RUNTIME_ALREADY_CONTAINS_SESSION_OR_RUN_DATA")
    if state["provider_send_grants"] or state["unknown_requests"]:
        raise EvaluationPreflightError("CASE_RUNTIME_ALREADY_HAS_PROVIDER_ACTIVITY")
    if case_id == "E07-D" and not (
        state.get("delivery_status") == "ACKNOWLEDGED"
        and state.get("receiver_http_status") == 202
        and state.get("receiver_status") == "QUEUED"
        and state.get("delivery_event_id") == E07_EVENT_ID
        and state.get("receiver_event_id") == E07_EVENT_ID
    ):
        raise EvaluationPreflightError("E07_TRUSTED_FIXTURE_MISMATCH")

    runtime_dir = resolve_user_demo_runtime(runtime_name, root=repo_root)
    _manifest_matches(runtime_name, runtime_dir, repo_root)
    domain_path = Path(state["domain_path"])
    grant = grant_preflight(domain_path, read_env())
    if int(grant["provider_sends"]) != 0 or int(grant["unknown_requests"]) != 0:
        raise EvaluationPreflightError("CASE_RUNTIME_PROVIDER_HISTORY_NOT_EMPTY")
    authorized_cap = _budget_micro(authorized_max_cost_usd)
    if int(grant["total_limit_usd_micro"]) > authorized_cap:
        raise EvaluationPreflightError("RUNTIME_GRANT_EXCEEDS_CASE_AUTHORIZED_CAP")
    # The default Assistant Run contract durably permits at most eight model
    # dispatches. Require enough unused pool for eight worst-case reservations.
    maximum_dispatch_reserve = (
        int(grant["one_max_request_reserve_usd_micro"])
        * DEFAULT_MAX_RUN_MODEL_DISPATCHES
    )
    if int(grant["remaining_usd_micro"]) < maximum_dispatch_reserve:
        raise EvaluationPreflightError("CASE_BUDGET_BELOW_EIGHT_REQUEST_RESERVES")

    owns_client = client is None
    check_client = client or httpx.Client(timeout=5.0, follow_redirects=False)
    try:
        response = check_client.get(api_origin + "/api/health")
    except Exception as error:
        raise EvaluationPreflightError("LOCAL_API_UNAVAILABLE") from error
    finally:
        if owns_client:
            check_client.close()
    if response.status_code != 200:
        raise EvaluationPreflightError("LOCAL_API_HEALTHCHECK_FAILED")
    health = response.json()
    if health.get("status") != "ok" or (health.get("worker") or {}).get("ready") is not True:
        raise EvaluationPreflightError("LOCAL_API_WORKER_NOT_READY")
    return {
        "status": "READY_FOR_EXPLICIT_CASE_RUN",
        "case_id": case_id,
        "runtime_name": runtime_name,
        "api_origin": api_origin,
        "provider_requests_so_far": 0,
        "unknown_requests": 0,
        "grant_remaining_usd_micro": int(grant["remaining_usd_micro"]),
        "grant_limit_usd_micro": int(grant["total_limit_usd_micro"]),
        "authorized_cap_usd_micro": authorized_cap,
        "maximum_provider_dispatches_per_run": DEFAULT_MAX_RUN_MODEL_DISPATCHES,
        "worst_case_run_reserve_usd_micro": maximum_dispatch_reserve,
        "task_binding_created": False,
    }


def _raise_for_status(response: Any, expected: set[int], label: str) -> dict[str, Any]:
    if response.status_code not in expected:
        raise EvaluationPreflightError(f"{label}_HTTP_{response.status_code}")
    try:
        value = response.json()
    except Exception as error:
        raise EvaluationPreflightError(label + "_INVALID_JSON") from error
    if not isinstance(value, dict):
        raise EvaluationPreflightError(label + "_INVALID_RESPONSE")
    return value


def _wait_for_terminal(client: Any, run_id: str, *, timeout_seconds: float) -> tuple[dict[str, Any], bool]:
    terminal = {"SUCCEEDED", "FAILED", "BLOCKED", "WAITING_INPUT", "WAITING_APPROVAL"}
    deadline = time.monotonic() + timeout_seconds
    while True:
        try:
            response = client.get(f"/api/runs/{run_id}")
        except Exception as error:
            raise EvaluationPreflightError("RUN_STATUS_READ_FAILED_NO_RESUBMIT") from error
        run = _raise_for_status(response, {200}, "RUN_STATUS")
        status = str(run.get("status", ""))
        if status in terminal:
            return run, False
        if time.monotonic() >= deadline:
            return run, True
        time.sleep(0.2)


def _token_values(value: Any) -> dict[str, int] | None:
    if isinstance(value, list):
        value = value[0] if value else None
    if not isinstance(value, dict):
        return None
    aliases = {
        "input_tokens": ("input_tokens", "prompt_tokens"),
        "output_tokens": ("output_tokens", "completion_tokens"),
        "total_tokens": ("total_tokens",),
    }
    result: dict[str, int] = {}
    for target, keys in aliases.items():
        number = next((value[key] for key in keys if value.get(key) is not None), None)
        if not isinstance(number, int):
            return None
        result[target] = number
    return result


def _result_metrics(trace: dict[str, Any], execution_mode: str) -> dict[str, Any]:
    spends = trace.get("runtime_spends", [])
    summary = trace.get("session_spend_summary", {})
    known_usage = [_token_values(row.get("usage_json")) for row in spends]
    received_spends = [row for row in spends if row.get("response_status") is not None]
    usage_complete = all(value is not None for value in (
        _token_values(row.get("usage_json")) for row in received_spends
    ))
    input_tokens = sum(item["input_tokens"] for item in known_usage if item is not None)
    output_tokens = sum(item["output_tokens"] for item in known_usage if item is not None)
    total_tokens = sum(item["total_tokens"] for item in known_usage if item is not None)
    settlement_complete = all(row.get("settled_usd_micro") is not None for row in spends)
    settled = sum(int(row["settled_usd_micro"]) for row in spends if row.get("settled_usd_micro") is not None)
    calls = trace.get("assistant_calls_actual_model_input_output", [])
    model_calls = [row for row in calls if row.get("kind") == "MODEL"]
    mcp_calls = [row for row in calls if row.get("kind") == "MCP"]
    fixture_usage = [_token_values(row.get("usage_json")) for row in model_calls]
    fixture_usage_complete = all(value is not None for value in fixture_usage)
    fixture_total = {
        "input_tokens": sum(row["input_tokens"] for row in fixture_usage if row is not None),
        "output_tokens": sum(row["output_tokens"] for row in fixture_usage if row is not None),
        "total_tokens": sum(row["total_tokens"] for row in fixture_usage if row is not None),
    } if fixture_usage_complete and execution_mode == "FIXTURE" else None
    return {
        "provider_send_grants": int(summary.get("send_granted_count", 0)),
        "provider_responses_received": int(summary.get("responses_received_count", 0)),
        "unknown_requests": int(summary.get("unknown_count", 0)),
        "provider_usage_complete": usage_complete,
        "provider_input_tokens": input_tokens if usage_complete and received_spends else None,
        "provider_output_tokens": output_tokens if usage_complete and received_spends else None,
        "provider_total_tokens": total_tokens if usage_complete and received_spends else None,
        "settled_usd_micro": settled if settlement_complete and spends else None,
        "provider_cost_usd": f"{Decimal(settled) / Decimal(1_000_000):.6f}"
        if settlement_complete and spends else None,
        "mcp_tools_call_count": len(mcp_calls),
        "mcp_tool_names": sorted(str(row.get("request_json", {}).get("name", "")) for row in mcp_calls),
        "observation_count": len(trace.get("observations", [])),
        "evidence_count": len(trace.get("evidence", [])),
        "fixture_model_dispatches": len(model_calls) if execution_mode == "FIXTURE" else 0,
        "fixture_token_metadata": fixture_total,
    }


def _execute_case_once(
    client: Any,
    *,
    case_id: str,
    runtime_name: str,
    support_password: str,
    api_origin: str,
    web_origin: str,
    root: str | Path | None = None,
    execution_mode: str = "LIVE",
    timeout_seconds: float = DEFAULT_RUN_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """Submit exactly one frozen user turn through the formal Web API.

    This function never retries login/session/message POSTs. If a submission
    response is ambiguous, the caller must inspect the same runtime instead of
    posting the case again.
    """
    if execution_mode not in {"LIVE", "FIXTURE"}:
        raise ValueError("EXECUTION_MODE_INVALID")
    case = load_frozen_case(case_id)
    repo_root = Path(root or ROOT).resolve()
    from runtime_paths import resolve_user_demo_runtime

    runtime_dir = resolve_user_demo_runtime(runtime_name, root=repo_root)
    pre_state = inspect_case_runtime(case_id, runtime_name, root=repo_root)
    if not pre_state["fresh"]:
        raise EvaluationPreflightError("CASE_RUNTIME_ALREADY_CONTAINS_SESSION_OR_RUN_DATA")
    if pre_state["provider_send_grants"] or pre_state["unknown_requests"]:
        raise EvaluationPreflightError("CASE_RUNTIME_ALREADY_HAS_PROVIDER_ACTIVITY")
    if case_id == "E07-D" and not (
        pre_state.get("delivery_status") == "ACKNOWLEDGED"
        and pre_state.get("receiver_http_status") == 202
        and pre_state.get("receiver_status") == "QUEUED"
        and pre_state.get("delivery_event_id") == E07_EVENT_ID
        and pre_state.get("receiver_event_id") == E07_EVENT_ID
    ):
        raise EvaluationPreflightError("E07_TRUSTED_FIXTURE_MISMATCH")
    output = runtime_dir / "evidence" / f"{case_id}.json"
    result_output = runtime_dir / "evidence" / f"{case_id}.result.json"
    if output.exists() or result_output.exists():
        raise EvaluationPreflightError("CASE_EVIDENCE_OUTPUT_ALREADY_EXISTS")
    api_origin = _loopback_url(api_origin, label="API_ORIGIN")
    web_origin = _loopback_url(web_origin, label="WEB_ORIGIN")
    started = time.monotonic()
    login_response = client.post(
        api_origin + "/api/auth/login",
        headers={"Origin": web_origin},
        json={"actor_id": "support-a", "password": support_password},
    )
    identity = _raise_for_status(login_response, {200}, "LOGIN")
    if identity.get("actor_id") != "support-a" or identity.get("tenant_id") != "tenant-a":
        raise EvaluationPreflightError("SUPPORT_IDENTITY_SCOPE_MISMATCH")
    csrf = str(identity.get("csrf_token", ""))
    if not csrf:
        raise EvaluationPreflightError("CSRF_TOKEN_MISSING")
    write_headers = {"Origin": web_origin, "X-CSRF-Token": csrf}
    session_response = client.post(api_origin + "/api/sessions", headers=write_headers)
    session = _raise_for_status(session_response, {201}, "SESSION_CREATE")
    session_id = str(session.get("session_id", ""))
    if not session_id:
        raise EvaluationPreflightError("SESSION_ID_MISSING")

    question = case["user_turns"][0]
    task_id: str | None = None
    if case_id == "E07-D":
        response = client.post(
            f"{api_origin}/api/sessions/{session_id}/assistant/order",
            headers={**write_headers, "Idempotency-Key": "r2-ar06-e07-" + uuid.uuid4().hex},
            json={"order_id": E07_ORDER_ID, "initial_message": question},
        )
        accepted = _raise_for_status(response, {200, 202}, "E07_TASK_BINDING_AND_RUN")
        task_id = str(accepted.get("task_id", "")) or None
    else:
        key_prefix = "r2-ar06-e05-" if case_id == "E05-D" else (
            "r2-ar06-" + case_id.lower().replace("-", "") + "-"
        )
        response = client.post(
            f"{api_origin}/api/sessions/{session_id}/assistant/messages",
            headers={
                **write_headers,
                "Idempotency-Key": key_prefix + uuid.uuid4().hex,
            },
            json={"body": question},
        )
        label = "E05_MESSAGE_AND_RUN" if case_id == "E05-D" else "HOLDOUT_MESSAGE_AND_RUN"
        accepted = _raise_for_status(response, {202}, label)
    run_id = str(accepted.get("run_id", ""))
    if not run_id:
        raise EvaluationPreflightError("RUN_ID_MISSING_AFTER_ACCEPTANCE")

    run, timed_out = _wait_for_terminal(client, run_id, timeout_seconds=timeout_seconds)
    elapsed_ms = max(0, round((time.monotonic() - started) * 1000))
    from export_live_evidence import export_session

    export_session(session_id, output, runtime_name=runtime_name, actor_id="support-a", root=repo_root)
    trace = json.loads(output.read_text(encoding="utf-8"))
    submitted = [row for row in trace["messages"] if row.get("role") == "USER"]
    if len(submitted) != 1 or submitted[0].get("body") != question:
        raise EvaluationPreflightError("EXPORTED_INPUT_DOES_NOT_MATCH_FROZEN_GOLD")
    exported_run = next((row for row in trace["runs"] if row.get("run_id") == run_id), None)
    if exported_run is None or exported_run.get("source_message_id") != submitted[0].get("message_id"):
        raise EvaluationPreflightError("EXPORTED_RUN_SOURCE_LINK_MISMATCH")
    if task_id and not any(row.get("task_id") == task_id for row in trace.get("task_bindings", [])):
        raise EvaluationPreflightError("EXPORTED_TRUSTED_TASK_BINDING_MISSING")

    result_record: dict[str, Any] = {
        "schema": "r2-ar06-auto-live-case-result-v1",
        "case_id": case_id,
        "split": case["split"],
        "execution_mode": execution_mode,
        "assessment_status": "UNVERIFIED",
        "assessor_note": "Structured evidence only; independent Rubric scoring is pending.",
        "gold_sha256": case["gold_sha256"],
        "frozen_input_sha256": hashlib.sha256(question.encode("utf-8")).hexdigest(),
        "runtime_name": runtime_name,
        "session_id": session_id,
        "task_id": task_id,
        "run_id": run_id,
        "run_status": str(run.get("status", "UNKNOWN")),
        "run_failure_code": run.get("waiting_reason") if run.get("status") != "SUCCEEDED" else None,
        "terminal_timeout": timed_out,
        "elapsed_ms": elapsed_ms,
        "trace_path": str(output),
        **_result_metrics(trace, execution_mode),
    }
    result_output.write_text(json.dumps(result_record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result_record


def execute_case(client: Any, **kwargs: Any) -> dict[str, Any]:
    """Serialize one case per isolated runtime and execute it at most once."""
    from runtime_paths import resolve_user_demo_runtime

    root = Path(kwargs.get("root") or ROOT).resolve()
    runtime_name = kwargs.get("runtime_name")
    if not isinstance(runtime_name, str):
        raise ValueError("USER_DEMO_RUNTIME_NAME_REQUIRED")
    runtime_dir = resolve_user_demo_runtime(runtime_name, root=root)
    lock_path = runtime_dir / ".r2-ar06-case-run.lock"
    try:
        descriptor = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as error:
        raise EvaluationPreflightError("CASE_RUN_ALREADY_ACTIVE_OR_REQUIRES_INSPECTION") from error
    try:
        os.write(descriptor, json.dumps({"pid": os.getpid(), "case_id": kwargs.get("case_id")}).encode("utf-8"))
        os.close(descriptor)
        descriptor = -1
        return _execute_case_once(client, **kwargs)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        try:
            lock_path.unlink()
        except FileNotFoundError:
            pass


def _local_support_password() -> str:
    from runtime_admin import read_env

    value = os.environ.get("OPSPILOT_WEB_SUPPORT_PASSWORD", "").strip()
    if value:
        return value
    return read_env().get("OPSPILOT_WEB_SUPPORT_PASSWORD", "").strip()


def _case_preflight_cli(args: argparse.Namespace) -> dict[str, Any]:
    state = inspect_case_runtime(args.case_id, args.runtime_name)
    if not state["fresh"]:
        raise EvaluationPreflightError("CASE_RUNTIME_ALREADY_CONTAINS_SESSION_OR_RUN_DATA")
    if state["runtime_grant_present"]:
        raise EvaluationPreflightError("OFFLINE_PREFLIGHT_REQUIRES_NO_RUNTIME_GRANT")
    if state["provider_send_grants"] or state["unknown_requests"]:
        raise EvaluationPreflightError("CASE_RUNTIME_ALREADY_HAS_PROVIDER_ACTIVITY")
    if args.case_id == "E07-D" and not (
        state.get("delivery_status") == "ACKNOWLEDGED"
        and state.get("receiver_http_status") == 202
        and state.get("receiver_status") == "QUEUED"
        and state.get("delivery_event_id") == E07_EVENT_ID
        and state.get("receiver_event_id") == E07_EVENT_ID
    ):
        raise EvaluationPreflightError("E07_TRUSTED_FIXTURE_MISMATCH")
    return {
        "status": "OFFLINE_READY",
        "case_id": args.case_id,
        "runtime_name": args.runtime_name,
        "fresh": state["fresh"],
        "runtime_grant_present": state["runtime_grant_present"],
        "provider_requests": 0,
        "unknown_requests": 0,
        "event_id": state.get("delivery_event_id"),
        "delivery_status": state.get("delivery_status"),
        "receiver_status": state.get("receiver_status"),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    prepare = sub.add_parser("prepare", help="Create a new named isolated runtime; never reuses one.")
    prepare.add_argument("--case-id", required=True, choices=sorted(SUPPORTED_CASES))
    prepare.add_argument("--runtime-name", required=True)

    preflight = sub.add_parser("preflight", help="Offline or explicit Live readiness checks; sends no chat message.")
    preflight.add_argument("--case-id", required=True, choices=sorted(SUPPORTED_CASES))
    preflight.add_argument("--runtime-name", required=True)
    preflight.add_argument("--mode", choices=("offline", "live"), default="offline")
    preflight.add_argument("--authorized-max-cost-usd")
    preflight.add_argument("--api-origin", default=DEFAULT_API_ORIGIN)

    live = sub.add_parser("run-live", help="Submit exactly one frozen turn; no automatic replay or retry.")
    live.add_argument("--case-id", required=True, choices=sorted(SUPPORTED_CASES))
    live.add_argument("--runtime-name", required=True)
    live.add_argument("--authorized-case-id", required=True)
    live.add_argument("--authorized-max-cost-usd", required=True)
    live.add_argument("--api-origin", default=DEFAULT_API_ORIGIN)
    live.add_argument("--web-origin", default=DEFAULT_WEB_ORIGIN)
    live.add_argument("--timeout-seconds", type=float, default=DEFAULT_RUN_TIMEOUT_SECONDS)
    args = parser.parse_args(argv)

    try:
        load_frozen_case(args.case_id)
        if args.command == "prepare":
            runtime_dir = initialize_case_runtime(args.case_id, args.runtime_name)
            state = inspect_case_runtime(args.case_id, args.runtime_name)
            print(json.dumps({
                "status": "ISOLATED_RUNTIME_CREATED",
                "runtime_name": args.runtime_name,
                "runtime_dir": str(runtime_dir),
                "fresh": state["fresh"],
                "runtime_grant_present": state["runtime_grant_present"],
                "provider_requests": 0,
            }, ensure_ascii=False))
            return 0
        if args.command == "preflight" and args.mode == "offline":
            print(json.dumps(_case_preflight_cli(args), ensure_ascii=False))
            return 0
        if args.command == "preflight":
            if not args.authorized_max_cost_usd:
                raise EvaluationPreflightError("LIVE_PREFLIGHT_REQUIRES_CASE_COST_AUTHORIZATION")
            import httpx

            with httpx.Client(timeout=5.0, follow_redirects=False) as client:
                result = live_preflight(
                    args.case_id, args.runtime_name,
                    authorized_max_cost_usd=args.authorized_max_cost_usd,
                    api_origin=args.api_origin, client=client,
                )
            print(json.dumps(result, ensure_ascii=False))
            return 0

        if args.authorized_case_id != args.case_id:
            raise EvaluationPreflightError("LIVE_AUTHORIZATION_CASE_MISMATCH")
        import httpx

        password = _local_support_password()
        if not password:
            raise EvaluationPreflightError("SUPPORT_PASSWORD_NOT_CONFIGURED_LOCALLY")
        api_origin = _loopback_url(args.api_origin, label="API_ORIGIN")
        web_origin = _loopback_url(args.web_origin, label="WEB_ORIGIN")
        with httpx.Client(base_url=api_origin, timeout=15.0, follow_redirects=False) as client:
            preflight_result = live_preflight(
                args.case_id, args.runtime_name,
                authorized_max_cost_usd=args.authorized_max_cost_usd,
                api_origin=api_origin, root=ROOT, client=client,
            )
            result = execute_case(
                client, case_id=args.case_id, runtime_name=args.runtime_name,
                support_password=password, api_origin=api_origin, web_origin=web_origin,
                root=ROOT, execution_mode="LIVE", timeout_seconds=args.timeout_seconds,
            )
        print(json.dumps({"preflight": preflight_result, "result": result}, ensure_ascii=False))
        return 0 if not result["terminal_timeout"] else 3
    except EvaluationPreflightError as error:
        code = str(error)
        if not code or len(code) > 160:
            code = type(error).__name__
        print(json.dumps({"status": "STOPPED", "reason": code}, ensure_ascii=False), file=sys.stderr)
        return 2
    except (RuntimeError, ValueError, OSError) as error:
        code = getattr(error, "code", None) or type(error).__name__
        print(json.dumps({"status": "STOPPED", "reason": str(code)[:160]}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
