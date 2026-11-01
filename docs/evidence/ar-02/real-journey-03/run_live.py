"""One-shot, bounded AR-02 real journey through the formal local API/Worker.

This runner is evidence tooling only. It never prints or writes Provider secrets,
never retries a submitted turn, and refuses to reuse an existing runtime DB.
"""
from __future__ import annotations

import hashlib
import json
import os
import secrets
import sqlite3
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[4]
OUT = Path(os.environ.get("OPSPILOT_AR02_LIVE_OUTPUT_DIR", str(Path(__file__).resolve().parent))).resolve()
RUNTIME = ROOT / ".runtime" / "ar02-real-journey-03-20261101"
DB = RUNTIME / "domain.sqlite3"
CHECKPOINT = RUNTIME / "checkpoints.sqlite3"
EXPERIMENT = "AR-02-REAL-JOURNEY-03"
EXPECTED_HEAD = os.environ.get("OPSPILOT_AR02_EXPECTED_HEAD", "").strip()
EXPECTED_BRANCH = "codex/ar02-real-journey-03"
CASES_REL = Path("docs/evidence/ar-02/real-journey/CASES.json")
SMOKE_REL = Path("docs/evidence/ar-02/hf-01/SMOKE_INPUTS.md")
EXPECTED_SMOKE_BLOB = "ee9b1623a2296905c425449709a2f9ae6563caca"
EXPECTED_CASES_BLOB = "0b8411942ec99724d9aa10d45faa50a58676836b"
ORIGIN = "http://127.0.0.1:8765"
TERMINAL = {"SUCCEEDED", "FAILED", "CANCELLED", "ABORTED", "BLOCKED"}

# Running this evidence script by path puts its directory, not the checkout, at
# sys.path[0]. Bind the verified checkout before importing product modules.
sys.path.insert(0, str(ROOT))

TRACE = OUT / "TRACE.jsonl"
LOG = OUT / "runs" / "live.log"
RESULTS = OUT / "RESULTS.json"
SETUP = OUT / "PREPARATION.json"
HTTP_TRACE = OUT / "PROVIDER_HTTP.jsonl"


def _write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _append(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n")
        stream.flush()


def _log(message: str) -> None:
    LOG.parent.mkdir(parents=True, exist_ok=True)
    line = f"{time.strftime('%Y-%m-%dT%H:%M:%S%z')} {message}"
    with LOG.open("a", encoding="utf-8") as stream:
        stream.write(line + "\n")
        stream.flush()
    print(line, flush=True)


def _git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True, stderr=subprocess.STDOUT).strip()


def _git_blob(path: Path) -> str:
    return _git("hash-object", str(path))


def _loads(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return value


def _safe_value(value: Any) -> Any:
    if isinstance(value, dict):
        secret_names = {"authorization", "api_key", "api-key", "x-api-key", "cookie", "set-cookie", "password"}
        return {
            str(key): "[REDACTED]" if str(key).lower() in secret_names else _safe_value(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_safe_value(item) for item in value]
    return value


def _safe_headers(headers: Any) -> dict[str, str]:
    allowed = {
        "content-type", "content-length", "date", "server", "user-agent",
        "x-request-id", "request-id", "x-ds-trace-id", "x-ratelimit-limit-tokens",
        "x-ratelimit-remaining-tokens", "x-ratelimit-reset-tokens",
    }
    return {key.lower(): value for key, value in headers.items() if key.lower() in allowed}


def _live_model_factory():
    """Use the approved production factory with passive, secret-safe HTTP hooks."""
    from opspilot.assistant import create_assistant_model

    model = create_assistant_model()
    if model is None:
        raise RuntimeError("PROVIDER_MODEL_FACTORY_DISABLED")

    async def on_request(request: Any) -> None:
        raw = request.read()
        try:
            body: Any = json.loads(raw.decode("utf-8")) if raw else None
        except (UnicodeDecodeError, ValueError):
            body = {"body_sha256": hashlib.sha256(raw).hexdigest(), "body_bytes": len(raw)}
        _append(HTTP_TRACE, {
            "event": "provider_http_request",
            "timestamp": time.time(),
            "method": request.method,
            "url": str(request.url),
            "headers": _safe_headers(request.headers),
            "body": _safe_value(body),
            "authorization_logged": False,
        })

    async def on_response(response: Any) -> None:
        await response.aread()
        try:
            body: Any = json.loads(response.content.decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            body = {
                "body_sha256": hashlib.sha256(response.content).hexdigest(),
                "body_bytes": len(response.content),
            }
        _append(HTTP_TRACE, {
            "event": "provider_http_response",
            "timestamp": time.time(),
            "status_code": response.status_code,
            "http_version": response.http_version,
            "headers": _safe_headers(response.headers),
            "body": _safe_value(body),
            "authorization_logged": False,
        })

    def on_sync_request(request: Any) -> None:
        raw = request.read()
        try:
            body: Any = json.loads(raw.decode("utf-8")) if raw else None
        except (UnicodeDecodeError, ValueError):
            body = {"body_sha256": hashlib.sha256(raw).hexdigest(), "body_bytes": len(raw)}
        _append(HTTP_TRACE, {
            "event": "provider_http_request", "timestamp": time.time(),
            "method": request.method, "url": str(request.url),
            "headers": _safe_headers(request.headers), "body": _safe_value(body),
            "authorization_logged": False,
        })

    def on_sync_response(response: Any) -> None:
        raw = response.read()
        try:
            body: Any = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            body = {"body_sha256": hashlib.sha256(raw).hexdigest(), "body_bytes": len(raw)}
        _append(HTTP_TRACE, {
            "event": "provider_http_response", "timestamp": time.time(),
            "status_code": response.status_code, "http_version": response.http_version,
            "headers": _safe_headers(response.headers), "body": _safe_value(body),
            "authorization_logged": False,
        })

    model.http_async_client.event_hooks["request"].append(on_request)
    model.http_async_client.event_hooks["response"].append(on_response)
    model.http_client.event_hooks["request"].append(on_sync_request)
    model.http_client.event_hooks["response"].append(on_sync_response)
    return model


def _fresh_preflight() -> dict[str, Any]:
    if _git("rev-parse", "HEAD") != EXPECTED_HEAD:
        raise RuntimeError("LIVE_BASELINE_HEAD_MISMATCH")
    if _git("branch", "--show-current") != EXPECTED_BRANCH:
        raise RuntimeError("LIVE_BRANCH_MISMATCH")
    try:
        subprocess.run(["git", "diff", "--quiet"], cwd=ROOT, check=True, capture_output=True)
        subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=ROOT, check=True, capture_output=True)
    except subprocess.CalledProcessError as error:
        raise RuntimeError("TRACKED_WORKTREE_DIRTY") from error
    status_lines = _git("status", "--porcelain=v1", "-uall").splitlines()
    allowed_prefix = "docs/evidence/ar-02/real-journey-03/"
    unexpected = [line for line in status_lines if line[3:].replace("\\", "/") and not line[3:].replace("\\", "/").startswith(allowed_prefix)]
    if unexpected:
        raise RuntimeError("TRACKED_WORKTREE_DIRTY")
    smoke_blob = _git_blob(SMOKE_REL)
    if smoke_blob != EXPECTED_SMOKE_BLOB:
        raise RuntimeError("FROZEN_SMOKE_INPUT_BLOB_MISMATCH")
    cases_blob = _git_blob(CASES_REL)
    if cases_blob != EXPECTED_CASES_BLOB:
        raise RuntimeError("FROZEN_CASES_BLOB_MISMATCH")
    cases = json.loads((ROOT / CASES_REL).read_text(encoding="utf-8"))
    if len(cases.get("journey", [])) != 6:
        raise RuntimeError("FROZEN_CASE_COUNT_MISMATCH")
    if not os.environ.get("OPSPILOT_MODEL_API_KEY", "").strip():
        raise RuntimeError("PROVIDER_CREDENTIAL_MISSING")
    if os.environ.get("OPSPILOT_MODEL_NAME", "").strip() != "deepseek-flash":
        raise RuntimeError("PROVIDER_MODEL_MISMATCH")
    base = os.environ.get("OPSPILOT_MODEL_BASE_URL", "").strip()
    from urllib.parse import urlparse

    parsed = urlparse(base)
    if (parsed.scheme, parsed.hostname, parsed.port, parsed.path, parsed.query, parsed.fragment) != (
        "https", "api.deepseek.com", None, "", "", ""
    ):
        raise RuntimeError("PROVIDER_ENDPOINT_MISMATCH")
    if os.environ.get("OPSPILOT_ASSISTANT_PROVIDER_ENABLED") != "1":
        raise RuntimeError("LIVE_PROVIDER_OPT_IN_MISSING")
    if os.environ.get("OPSPILOT_ASSISTANT_EXPERIMENT_ID") != EXPERIMENT:
        raise RuntimeError("LIVE_EXPERIMENT_ID_MISMATCH")
    if DB.exists() or CHECKPOINT.exists():
        raise RuntimeError("ISOLATED_RUNTIME_ALREADY_EXISTS")
    for name in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
        if os.environ.get(name):
            # The model factory has trust_env=False; report presence only.
            proxy_environment[name] = True
    return {
        "repository": "wgqa/OpsPilot",
        "branch": EXPECTED_BRANCH,
        "head": EXPECTED_HEAD,
        "smoke_inputs_blob": smoke_blob,
        "cases_blob": cases_blob,
        "provider": "DeepSeek Chat Completions",
        "model": "deepseek-flash",
        "endpoint_origin": "https://api.deepseek.com",
        "secret_value_logged": False,
        "credential_source": "existing user-local environment file, loaded in memory for this process only",
        "httpx_trust_env": False,
        "httpx_retries": 0,
        "sdk_max_retries": 0,
        "request_timeout_seconds": 30,
        "request_max_tokens": 2048,
        "thinking": {"type": "disabled"},
        "tool_choice": "auto when tools are offered",
        "parallel_tool_calls": False,
        "provider_limit": 16,
        "mcp_tools_call_limit": 12,
        "per_dispatch_reservation_usd": "0.645600",
        "experiment_budget_usd": "10.50",
        "max_reserved_total_usd": "10.329600",
        "proxy_environment_present": dict(proxy_environment),
        "isolated_domain_db": str(DB.relative_to(ROOT)),
        "isolated_checkpoint_db": str(CHECKPOINT.relative_to(ROOT)),
        "both_runtime_files_absent": True,
        "paid_requests_so_far": 0,
    }


proxy_environment: dict[str, bool] = {}


def _wait_run(client: TestClient, run_id: str, timeout: float = 100.0) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        response = client.get(f"/api/runs/{run_id}")
        if response.status_code != 200:
            raise RuntimeError(f"RUN_READ_FAILED_{response.status_code}")
        run = response.json()
        if run.get("status") in TERMINAL or run.get("ended_at"):
            return run
        time.sleep(0.2)
    raise TimeoutError("RUN_WAIT_TIMEOUT")


def _db_snapshot(db_path: Path, run_id: str) -> dict[str, Any]:
    from opspilot.domain.assistant_experiment import read_budget
    from opspilot.domain.database import connect

    with connect(db_path) as connection:
        run = connection.execute("SELECT * FROM task_runs WHERE run_id=?", (run_id,)).fetchone()
        assistant_calls = connection.execute(
            "SELECT * FROM assistant_calls WHERE run_id=? ORDER BY created_at,call_id", (run_id,)
        ).fetchall()
        message_rows = connection.execute(
            "SELECT * FROM messages WHERE applied_run_id=? OR message_id=(SELECT source_message_id FROM task_runs WHERE run_id=?) ORDER BY sequence",
            (run_id, run_id),
        ).fetchall()
        dispatches = connection.execute(
            "SELECT * FROM ar02_live_dispatches WHERE experiment_id=? AND run_id=? ORDER BY created_at,dispatch_id",
            (EXPERIMENT, run_id),
        ).fetchall()
        domain_writes = {}
        for table in ("s3_diagnoses", "d3_action_intents", "d3_action_ledgers", "s3_handoff_receipts"):
            domain_writes[table] = int(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
    calls: list[dict[str, Any]] = []
    for row in assistant_calls:
        record = dict(row)
        calls.append({
            "call_id": record.get("call_id"),
            "kind": record.get("kind"),
            "logical_key": record.get("logical_key"),
            "status": record.get("status"),
            "created_at": record.get("created_at"),
            "completed_at": record.get("completed_at"),
            "request": _loads(record.get("request_json")),
            "result": _loads(record.get("result_json")),
            "usage": _loads(record.get("usage_json")),
            "evidence_id": record.get("evidence_id"),
            "observation_id": record.get("observation_id"),
        })
    dispatch_records = []
    for row in dispatches:
        record = dict(row)
        dispatch_records.append({
            key: record.get(key) for key in (
                "dispatch_id", "kind", "logical_key", "status", "usage_state",
                "reserved_usd_micro", "settled_usd_micro", "usage_json", "error_code",
                "created_at", "completed_at", "request_digest",
            )
        })
    return {
        "run": dict(run) if run else None,
        "calls": calls,
        "dispatches": dispatch_records,
        "messages": [dict(row) for row in message_rows],
        "budget": read_budget(db_path, EXPERIMENT),
        "domain_write_counts": domain_writes,
    }


def _hard_stop(snapshot: dict[str, Any]) -> str | None:
    budget = snapshot.get("budget") or {}
    if budget.get("status") != "OPEN":
        return "EXPERIMENT_BUDGET_CLOSED"
    for dispatch in snapshot.get("dispatches", []):
        if dispatch.get("status") in {"UNKNOWN", "RESERVED"}:
            return "DISPATCH_OUTCOME_UNKNOWN_OR_IN_FLIGHT"
        if dispatch.get("kind") == "MODEL" and (
            dispatch.get("status") != "OK" or dispatch.get("usage_state") != "KNOWN"
        ):
            return "MODEL_USAGE_NOT_KNOWN"
        if dispatch.get("kind") == "MCP" and dispatch.get("status") != "OK":
            return "MCP_DISPATCH_NOT_CONFIRMED"
    if int(budget.get("provider_used", 0)) >= 16:
        return "PROVIDER_LIMIT_REACHED"
    if int(budget.get("mcp_used", 0)) >= 12:
        return "MCP_LIMIT_REACHED"
    return None


def _record_api(event: str, payload: dict[str, Any]) -> None:
    _append(TRACE, {"event": event, "timestamp": time.time(), **payload})


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    if TRACE.exists() or LOG.exists() or RESULTS.exists() or SETUP.exists() or HTTP_TRACE.exists():
        raise RuntimeError("LIVE_EVIDENCE_OUTPUT_ALREADY_EXISTS")
    RUNTIME.parent.mkdir(parents=True, exist_ok=True)
    RUNTIME.mkdir(parents=True, exist_ok=False)
    _log("PREFLIGHT start; Provider requests remain 0")

    from opspilot.config import load_local_environment
    env_file = Path(os.environ.get("OPSPILOT_AR02_ENV_FILE", str(ROOT / ".env")))
    load_local_environment(env_file)
    from opspilot.assistant import create_assistant_model
    from opspilot.domain.assistant_experiment import initialize_experiment, read_budget
    from opspilot.domain.database import connect, reset_fixture
    from opspilot.domain.s3 import prepare_s3_fixture
    from opspilot.web.app import create_app

    preflight = _fresh_preflight()
    model = create_assistant_model()
    if model is None:
        raise RuntimeError("PROVIDER_MODEL_FACTORY_DISABLED")
    try:
        if (
            model.model_name != "deepseek-flash"
            or model.max_retries != 0
            or model.request_timeout != 30
            or model.extra_body != {"max_tokens": 2048, "thinking": {"type": "disabled"}}
            or model.http_async_client.trust_env is not False
            or model.http_client.trust_env is not False
        ):
            raise RuntimeError("PROVIDER_CLIENT_CONFIGURATION_MISMATCH")
    finally:
        import asyncio

        asyncio.run(model.http_async_client.aclose())
        model.http_client.close()

    reset_fixture(DB, "S1_POS")
    setup = prepare_s3_fixture(DB, "DELIVERED_PENDING", order_id="ar02-order", contract_version=2)
    setup["base_demo_initialization"] = "reset_fixture(S1_POS); preparation only, not Agent evidence"
    _write(SETUP, setup)
    with connect(DB) as connection:
        pre_run_counts = {
            "task_runs": int(connection.execute("SELECT COUNT(*) FROM task_runs").fetchone()[0]),
            "assistant_runs": int(connection.execute("SELECT COUNT(*) FROM assistant_runs").fetchone()[0]),
            "task_bindings": int(connection.execute("SELECT COUNT(*) FROM task_bindings").fetchone()[0]),
            "diagnoses": int(connection.execute("SELECT COUNT(*) FROM s3_diagnoses").fetchone()[0]),
            "action_intents": int(connection.execute("SELECT COUNT(*) FROM d3_action_intents").fetchone()[0]),
            "action_ledgers": int(connection.execute("SELECT COUNT(*) FROM d3_action_ledgers").fetchone()[0]),
            "handoff_receipts": int(connection.execute("SELECT COUNT(*) FROM s3_handoff_receipts").fetchone()[0]),
        }
    if pre_run_counts["task_runs"] or pre_run_counts["assistant_runs"] or pre_run_counts["task_bindings"]:
        raise RuntimeError("ISOLATED_DB_NOT_EMPTY_BEFORE_JOURNEY")
    initialize_experiment(DB, EXPERIMENT)
    budget = read_budget(DB, EXPERIMENT)
    if budget.get("status") != "OPEN" or budget.get("provider_used") != 0 or budget.get("mcp_used") != 0:
        raise RuntimeError("NEW_EXPERIMENT_BUDGET_NOT_EMPTY")
    preflight["fixture_preparation"] = {
        "method": "prepare_s3_fixture through a local loopback receiver",
        "agent_actions": setup.get("agent_actions"),
        "state": setup.get("state"),
        "order_id": setup.get("order_id"),
        "order_version": setup.get("order_version"),
        "contract_version": setup.get("contract_version"),
        "receiver_http_status": setup.get("receiver_http_status"),
        "transport_trace": setup.get("transport_trace"),
        "business_state_is_setup_not_agent_evidence": True,
    }
    preflight["pre_run_database_counts"] = pre_run_counts
    preflight["initial_budget"] = budget
    _write(OUT / "PREFLIGHT.json", preflight)
    _record_api("preflight_passed", {"preflight": preflight})
    _log("PREFLIGHT PASS; isolated DB, one Worker, 0 Provider dispatches, 0 MCP calls")
    _log("LIVE execution starting with frozen S02-1..S02-5 only; no retries and stop on UNKNOWN/limit/security anomaly")

    from opspilot.domain.assistant_experiment import read_budget

    password = secrets.token_urlsafe(24)
    passwords = {
        "support-a": password,
        "approver-a": secrets.token_urlsafe(24),
        "support-b": secrets.token_urlsafe(24),
        "approver-b": secrets.token_urlsafe(24),
    }
    app = create_app(
        db_path=DB,
        checkpoint_db_path=CHECKPOINT,
        start_worker=True,
        credentials=passwords,
        expected_origin=ORIGIN,
        assistant_model_factory=_live_model_factory,
        assistant_experiment_id=EXPERIMENT,
    )
    results: dict[str, Any] = {
        "status": "RUNNING",
        "experiment_id": EXPERIMENT,
        "head": EXPECTED_HEAD,
        "provider": "deepseek-flash",
        "started_at": time.time(),
        "turns": [],
        "provider_requests": 0,
        "mcp_tools_calls": 0,
        "stop_reason": None,
        "business_writes": {"diagnosis": 0, "approval": 0, "repair": 0, "deliver": 0, "handoff": 0},
    }
    with TestClient(app, base_url=ORIGIN) as client:
        health = client.get("/api/health")
        if health.status_code != 200 or health.json().get("worker", {}).get("status") != "running":
            raise RuntimeError("FORMAL_WORKER_NOT_READY")
        login = client.post(
            "/api/auth/login",
            headers={"Origin": ORIGIN},
            json={"actor_id": "support-a", "password": password},
        )
        if login.status_code != 200:
            raise RuntimeError("ISOLATED_SUPPORT_LOGIN_FAILED")
        headers = {"Origin": ORIGIN, "X-CSRF-Token": login.json()["csrf_token"]}
        _record_api("worker_ready_and_login", {
            "health": health.json(),
            "actor_id": login.json().get("actor_id"),
            "tenant_id": login.json().get("tenant_id"),
            "role": login.json().get("role"),
            "secret_logged": False,
        })

        cases = json.loads((ROOT / CASES_REL).read_text(encoding="utf-8"))["journey"]
        journey = [
            {"id": f"S02-{i}", "session_group": "s02", "case": cases[i]}
            for i in range(1, 6)
        ]
        session_ids: dict[str, str] = {}
        task_id: str | None = None
        for item in journey:
            case_id = item["id"]
            group = item["session_group"]
            if group not in session_ids:
                created = client.post("/api/sessions", headers=headers)
                if created.status_code != 201:
                    raise RuntimeError(f"SESSION_CREATE_FAILED_{group}_{created.status_code}")
                session_id = created.json()["session_id"]
                session_ids[group] = session_id
                scope = client.get(f"/api/sessions/{session_id}/assistant/scopes", headers=headers)
                if scope.status_code != 200 or scope.json().get("selected_project") != "orders-callback":
                    raise RuntimeError(f"TRUSTED_SESSION_SCOPE_UNAVAILABLE_{group}")
                _record_api("session_and_scope_ready", {
                    "group": group, "session_id": session_id,
                    "scope": scope.json(), "http_status": scope.status_code,
                })

            prompt = str(item["case"]["prompt"])
            session_id = session_ids[group]
            request_headers = {**headers, "Idempotency-Key": f"ar02-rj03-{case_id.lower()}"}
            if case_id == "S02-3":
                resources = client.get("/api/s3/order-resources", headers=headers)
                if resources.status_code != 200 or not any(
                    resource.get("order_id") == "ar02-order"
                    and resource.get("selection_status") == "REGISTERED_AND_READ_AUTHORIZED"
                    for resource in resources.json().get("items", [])
                ):
                    raise RuntimeError("TRUSTED_ORDER_RESOURCE_NOT_AVAILABLE")
                response = client.post(
                    f"/api/sessions/{session_id}/assistant/order",
                    headers=request_headers,
                    json={"order_id": "ar02-order", "initial_message": prompt},
                )
                _record_api("trusted_order_selection", {
                    "http_status": resources.status_code,
                    "selected_order_id": "ar02-order",
                    "resource": next(r for r in resources.json()["items"] if r.get("order_id") == "ar02-order"),
                    "trust_boundary": "authenticated SUPPORT API, not chat text",
                })
            else:
                body = {"body": prompt}
                if task_id and case_id in {"S02-4", "S02-5"}:
                    body["task_id"] = task_id
                response = client.post(
                    f"/api/sessions/{session_id}/assistant/messages",
                    headers=request_headers,
                    json=body,
                )
            if response.status_code != 202:
                _record_api("turn_rejected_before_run", {
                    "turn_id": case_id, "http_status": response.status_code,
                    "response": response.json() if response.headers.get("content-type", "").startswith("application/json") else response.text,
                })
                results["status"] = "STOPPED_BEFORE_ALL_TURNS"
                results["stop_reason"] = f"USER_TURN_REJECTED_{case_id}"
                break

            accepted = response.json()
            run_id = accepted.get("run_id")
            source_message_id = accepted.get("message_id") or accepted.get("source_message_id")
            if case_id == "S02-3":
                task_id = accepted.get("task_id")
                if not task_id:
                    raise RuntimeError("TRUSTED_ORDER_API_DID_NOT_RETURN_TASK")
            _record_api("user_turn_submitted", {
                "turn_id": case_id,
                "session_id": session_id,
                "task_id": task_id if group == "s02" else None,
                "source_message_id": source_message_id,
                "run_id": run_id,
                "prompt": prompt,
                "api_response": accepted,
                "idempotency_key": request_headers["Idempotency-Key"],
                "retry_count": 0,
            })
            if not run_id:
                raise RuntimeError(f"RUN_ID_MISSING_{case_id}")
            run = _wait_run(client, str(run_id))
            messages_response = client.get(f"/api/sessions/{session_id}/messages", headers=headers)
            if messages_response.status_code != 200:
                raise RuntimeError(f"SESSION_MESSAGES_READ_FAILED_{case_id}")
            messages = messages_response.json().get("items", [])
            answer = next((m for m in messages if m.get("answer_source_message_id") == source_message_id), None)
            snapshot = _db_snapshot(DB, str(run_id))
            budget = snapshot["budget"]
            provider_count = int(budget.get("provider_used", 0))
            mcp_count = int(budget.get("mcp_used", 0))
            results["provider_requests"] = provider_count
            results["mcp_tools_calls"] = mcp_count
            turn_result = {
                "turn_id": case_id,
                "session_id": session_id,
                "task_id": task_id if group == "s02" else None,
                "source_message_id": source_message_id,
                "run_id": run_id,
                "run_status": run.get("status"),
                "run_started_at": run.get("started_at"),
                "run_ended_at": run.get("ended_at"),
                "answer_status": accepted.get("answer_status"),
                "answer_message": answer,
                "assistant_trace": snapshot["calls"],
                "dispatches": snapshot["dispatches"],
                "budget_after_turn": budget,
                "domain_write_counts": snapshot["domain_write_counts"],
                "frozen_requirements": item["case"].get("required", []),
                "frozen_forbidden": item["case"].get("forbidden", []),
            }
            results["turns"].append(turn_result)
            _record_api("turn_result", turn_result)
            _log(
                f"{case_id} terminal={run.get('status')} provider_used={provider_count} "
                f"mcp_used={mcp_count} answer={'present' if answer else 'missing'} "
                f"budget={budget.get('status')}"
            )

            stop_reason = _hard_stop(snapshot)
            if run.get("status") != "SUCCEEDED":
                stop_reason = stop_reason or f"RUN_NOT_SUCCEEDED_{case_id}"
            if answer is None:
                stop_reason = stop_reason or f"PERSISTED_ANSWER_MISSING_{case_id}"
            if stop_reason:
                results["status"] = "STOPPED_ON_HARD_CONDITION"
                results["stop_reason"] = stop_reason
                _log(f"STOP {stop_reason}; no more turns will be submitted")
                break

        # Record final persistent facts and forbidden side-effect totals.
        with connect(DB) as connection:
            all_runs = connection.execute(
                "SELECT run_id,status,kind,task_id,source_message_id,started_at,ended_at FROM task_runs ORDER BY created_at,run_id"
            ).fetchall()
            all_writes = {}
            for table in ("s3_diagnoses", "d3_approvals", "d3_action_intents", "d3_action_ledgers", "s3_handoff_receipts", "s3_handoff_queue"):
                exists = connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone()
                all_writes[table] = int(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]) if exists else 0
        results["runs"] = [dict(row) for row in all_runs]
        results["domain_write_counts"] = all_writes
        results["final_budget"] = read_budget(DB, EXPERIMENT)
        results["sessions"] = session_ids
        results["task_id"] = task_id
        results["ended_at"] = time.time()
        if results["status"] == "RUNNING":
            results["status"] = "COMPLETED_S02_FIVE_TURNS"
        _write(RESULTS, results)
        _record_api("experiment_finished", {
            "status": results["status"],
            "stop_reason": results["stop_reason"],
            "final_budget": results["final_budget"],
            "domain_write_counts": all_writes,
        })
        _log(
            f"END {results['status']} turns={len(results['turns'])} "
            f"provider={results['provider_requests']} mcp={results['mcp_tools_calls']} "
            f"reserved_usd_micro={results['final_budget'].get('usd_reserved_micro')} "
            f"settled_usd_micro={results['final_budget'].get('usd_settled_micro')}"
        )
    return 0 if results["status"] == "COMPLETED_S02_FIVE_TURNS" else 2


if __name__ == "__main__":
    try:
        exit_code = main()
    except Exception as error:
        safe = f"{type(error).__name__}:{str(error)[:300]}"
        _log(f"FATAL {safe}; any submitted turns remain submitted; no retry authorized")
        if RESULTS.exists():
            result = json.loads(RESULTS.read_text(encoding="utf-8"))
            result["status"] = "STOPPED_ON_FATAL"
            result["stop_reason"] = safe
            _write(RESULTS, result)
        else:
            _write(RESULTS, {
                "status": "STOPPED_ON_FATAL",
                "experiment_id": EXPERIMENT,
                "head": EXPECTED_HEAD,
                "provider_requests": 0,
                "mcp_tools_calls": 0,
                "stop_reason": safe,
            })
        raise
    else:
        raise SystemExit(exit_code)
