"""One-shot runner for the authorized AR-03 paired live experiment.

This script has no network action unless --execute-once is supplied. The
execution claim is exclusive and persistent so rerunning after a partial or
unknown outcome is refused.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import re
import subprocess
import sys
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parents[4]
EVIDENCE = ROOT / "docs" / "evidence" / "ar-03" / "real-llm-01"
RUNTIME = EVIDENCE / "runtime"
CASES_PATH = ROOT / "docs" / "evidence" / "ar-03-real-llm-01-prep" / "CASES.json"
FROZEN_BASE = "e416bd1398b5a4bca6cdf3360f3ae78037a2740b"
FROZEN_CASES_BLOB = "c29b5cf7630fa838a365634d0df5f9f0f2bfa834"
FROZEN_GOLD_BLOB = "88d5e6f40f027ce2622b957d8ab32b8d2b827381"
FROZEN_BUDGET_BLOB = "5a71096584b4003b5f30c53fd69ccfd11bbc53d4"
EXPERIMENT_ID = "AR-03-REAL-LLM-01"
MODEL = "deepseek-flash"
TARGET_EVENT_ID = "event-00000000-0000-4000-8000-000000000001"
TARGET_TRANSPORT_ID = "transport-00000000-0000-4000-8000-000000000002"
PROMPT = (
    "我们最近升级了回调协议，客户反馈重试行为和以前不一样。请查一下有权限访问的旧版、新版协议，"
    "分析具体变化，再结合这个订单的回调情况判断影响，最后整理一份处理说明草稿。不能确认的地方请明确告诉我。"
)
CASE_STATES = (
    ("AR03-LLM-01-QUEUED", "A", "QUEUED"),
    ("AR03-LLM-01-PROCESSED", "B", "PROCESSED"),
)
PROVIDER_TOTAL_LIMIT = 16
MCP_TOTAL_LIMIT = 12
PROVIDER_SCENARIO_LIMIT = 8
MCP_SCENARIO_LIMIT = 6
RESERVATION_USD_MICRO = 645_600
TOTAL_BUDGET_USD_MICRO = 10_500_000
API_ORIGIN = "http://ar03-real-live-local"
LOCAL_PASSWORDS = {
    "support-a": "ar03-local-live-support-only",
    "approver-a": "ar03-local-live-approver-only",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def _append_jsonl(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


def _git(*args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=ROOT, capture_output=True, text=True, check=False,
    )
    if result.returncode:
        raise RuntimeError("GIT_PREFLIGHT_FAILED:" + " ".join(args))
    return result.stdout.strip()


def _blob_at_head(path: str) -> str:
    return _git("rev-parse", f"HEAD:{path}")


def _validate_preflight(*, require_fresh_paths: bool) -> dict[str, Any]:
    from opspilot.config import load_local_environment

    shared_env = ROOT.parent.parent / ".env"
    if not shared_env.is_file():
        raise RuntimeError("MODEL_ENVIRONMENT_FILE_NOT_FOUND")
    load_local_environment(shared_env)

    branch = _git("branch", "--show-current")
    head = _git("rev-parse", "HEAD")
    if branch != "codex/ar03-real-llm-01-live":
        raise RuntimeError("LIVE_BRANCH_MISMATCH")
    if _git("merge-base", "--is-ancestor", FROZEN_BASE, "HEAD") is None:
        raise RuntimeError("AUTHORIZED_BASELINE_NOT_IN_HISTORY")
    if _blob_at_head("docs/evidence/ar-03-real-llm-01-prep/CASES.json") != FROZEN_CASES_BLOB:
        raise RuntimeError("FROZEN_CASES_BLOB_MISMATCH")
    if _blob_at_head("docs/evidence/ar-03-real-llm-01-prep/GOLD.md") != FROZEN_GOLD_BLOB:
        raise RuntimeError("FROZEN_GOLD_BLOB_MISMATCH")
    if _blob_at_head("docs/evidence/ar-03-real-llm-01-prep/BUDGET.md") != FROZEN_BUDGET_BLOB:
        raise RuntimeError("FROZEN_BUDGET_BLOB_MISMATCH")

    key = os.environ.get("OPSPILOT_MODEL_API_KEY", "").strip()
    model = os.environ.get("OPSPILOT_MODEL_NAME", "").strip()
    base_url = os.environ.get("OPSPILOT_MODEL_BASE_URL", "").strip()
    parsed = urlparse(base_url)
    if not key or model != MODEL:
        raise RuntimeError("MODEL_CREDENTIAL_OR_ID_MISMATCH")
    if (
        parsed.scheme != "https"
        or parsed.hostname != "api.deepseek.com"
        or parsed.port not in (None, 443)
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or parsed.path not in ("", "/", "/v1")
    ):
        raise RuntimeError("MODEL_ENDPOINT_MISMATCH")
    existing_opt_in = os.environ.get("OPSPILOT_ASSISTANT_PROVIDER_ENABLED", "").strip()
    existing_experiment = os.environ.get("OPSPILOT_ASSISTANT_EXPERIMENT_ID", "").strip()
    if existing_opt_in not in ("", "0", "false", "False"):
        raise RuntimeError("PROVIDER_OPT_IN_ALREADY_SET_OUTSIDE_RUNNER")
    if existing_experiment not in ("", EXPERIMENT_ID):
        raise RuntimeError("PROVIDER_EXPERIMENT_ID_ALREADY_SET_OUTSIDE_RUNNER")

    cases = json.loads(CASES_PATH.read_text(encoding="utf-8"))
    if cases.get("prompt") != PROMPT or cases.get("release") != "AR-03-REAL-LLM-01-PREP-v1":
        raise RuntimeError("FROZEN_CASE_PROMPT_MISMATCH")
    case_ids = [case.get("id") for case in cases.get("cases", [])]
    if case_ids != [case_id for case_id, _, _ in CASE_STATES]:
        raise RuntimeError("FROZEN_CASE_ORDER_MISMATCH")

    claim = EVIDENCE / "EXECUTION_CLAIM.json"
    if claim.exists():
        raise RuntimeError("EXPERIMENT_ALREADY_CLAIMED_NO_RETRY")
    if require_fresh_paths and RUNTIME.exists():
        raise RuntimeError("ISOLATED_RUNTIME_PATH_ALREADY_EXISTS_NO_OVERWRITE")
    if require_fresh_paths:
        for _, label, _ in CASE_STATES:
            case_dir = RUNTIME / f"scenario-{label}"
            if case_dir.exists():
                raise RuntimeError("SCENARIO_PATH_ALREADY_EXISTS_NO_OVERWRITE")

    from opspilot.domain.assistant_experiment import (
        MAX_PROVIDER_RESERVATION_USD_MICRO,
        PRICE_VERSION,
    )
    if MAX_PROVIDER_RESERVATION_USD_MICRO != RESERVATION_USD_MICRO:
        raise RuntimeError("FROZEN_RESERVATION_MISMATCH")
    total_reservation = PROVIDER_TOTAL_LIMIT * MAX_PROVIDER_RESERVATION_USD_MICRO
    if total_reservation > TOTAL_BUDGET_USD_MICRO:
        raise RuntimeError("AGGREGATE_BUDGET_ENVELOPE_UNSAFE")

    return {
        "status": "PREFLIGHT_READY",
        "branch": branch,
        "head": head,
        "authorized_base": FROZEN_BASE,
        "provider": "DeepSeek",
        "model": model,
        "base_url": base_url,
        "credential_present": True,
        "provider_opt_in_before_runner": False,
        "experiment_id_before_runner": existing_experiment or None,
        "request_parameters": {
            "thinking": "disabled",
            "max_tokens": 2048,
            "tool_choice": "auto when tools are supplied",
            "parallel_tool_calls": False,
            "stream": False,
            "timeout_seconds": 30,
            "sdk_retries": 0,
            "http_transport_retries": 0,
        },
        "budget": {
            "provider_total": PROVIDER_TOTAL_LIMIT,
            "mcp_total": MCP_TOTAL_LIMIT,
            "provider_per_scenario": PROVIDER_SCENARIO_LIMIT,
            "mcp_per_scenario": MCP_SCENARIO_LIMIT,
            "reservation_usd_micro_per_provider": MAX_PROVIDER_RESERVATION_USD_MICRO,
            "maximum_reservations_usd_micro": total_reservation,
            "approved_budget_usd_micro": TOTAL_BUDGET_USD_MICRO,
            "price_version": PRICE_VERSION,
        },
        "frozen_blobs": {
            "cases": FROZEN_CASES_BLOB,
            "gold": FROZEN_GOLD_BLOB,
            "budget": FROZEN_BUDGET_BLOB,
        },
        "runtime_path": str(RUNTIME),
        "provider_requests_before_execution": 0,
    }


def _safe_headers(headers, *, request: bool) -> dict[str, str]:
    allowed = {"content-type", "accept", "user-agent", "x-request-id", "request-id", "date", "content-length"}
    return {key.lower(): value for key, value in headers.items() if key.lower() in allowed}


def _safe_json_body(raw: bytes) -> Any:
    try:
        return json.loads(raw.decode("utf-8"))
    except Exception:
        return {"unparsed_body_bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}


def _error_chain(error: BaseException, secret: str) -> list[dict[str, str]]:
    chain: list[dict[str, str]] = []
    current: BaseException | None = error
    seen: set[int] = set()
    while current is not None and id(current) not in seen and len(chain) < 8:
        seen.add(id(current))
        message = str(current)
        if secret:
            message = message.replace(secret, "[REDACTED]")
        message = re.sub(r"(?i)(authorization|api[-_]?key)\s*[:=]\s*[^\s,;]+", r"\1=[REDACTED]", message)
        chain.append({"type": type(current).__name__, "message": message[:500]})
        current = current.__cause__ or current.__context__
    return chain


class _LiveRequestState:
    def __init__(self, provider_path: Path):
        self.provider_path = provider_path
        self.lock = threading.Lock()
        self.count = 0
        self.inflight = 0
        self.scenario_count: dict[str, int] = {"A": 0, "B": 0}
        self.secret = os.environ.get("OPSPILOT_MODEL_API_KEY", "")

    def begin(self, scenario: str, request, raw: bytes) -> int:
        body = _safe_json_body(raw)
        tools_present = isinstance(body, dict) and bool(body.get("tools"))
        if not isinstance(body, dict) or body.get("model") != MODEL:
            raise RuntimeError("LIVE_WIRE_MODEL_MISMATCH")
        if body.get("max_tokens") != 2048 or body.get("thinking") != {"type": "disabled"}:
            raise RuntimeError("LIVE_WIRE_OUTPUT_CONFIGURATION_MISMATCH")
        if "max_completion_tokens" in body:
            raise RuntimeError("LIVE_WIRE_OUTPUT_ALIAS_PROHIBITED")
        if tools_present and (
            body.get("tool_choice") != "auto"
            or body.get("parallel_tool_calls") is not False
        ):
            raise RuntimeError("LIVE_WIRE_TOOL_CONFIGURATION_MISMATCH")
        if body.get("stream") is not False:
            raise RuntimeError("LIVE_WIRE_STREAMING_PROHIBITED")
        if request.url.scheme != "https" or request.url.host != "api.deepseek.com":
            raise RuntimeError("LIVE_WIRE_DESTINATION_MISMATCH")
        with self.lock:
            if self.inflight:
                raise RuntimeError("LIVE_PROVIDER_CONCURRENCY_LIMIT")
            if self.count >= PROVIDER_TOTAL_LIMIT:
                raise RuntimeError("LIVE_PROVIDER_TOTAL_LIMIT")
            if self.scenario_count[scenario] >= PROVIDER_SCENARIO_LIMIT:
                raise RuntimeError("LIVE_PROVIDER_SCENARIO_LIMIT")
            self.count += 1
            self.scenario_count[scenario] += 1
            self.inflight = 1
            index = self.count
        _append_jsonl(self.provider_path, {
            "record_type": "provider_http_request",
            "evidence_level": "REAL_HTTPX_TRANSPORT_REQUEST",
            "utc_time": _now(),
            "scenario": scenario,
            "global_request_number": index,
            "scenario_request_number": self.scenario_count[scenario],
            "method": request.method,
            "url": str(request.url),
            "headers": _safe_headers(request.headers, request=True),
            "body": body,
        })
        return index

    def finish(self) -> None:
        with self.lock:
            self.inflight = 0


class _RecordingAsyncTransport(__import__("httpx").AsyncBaseTransport):
    def __init__(self, state: _LiveRequestState, scenario: str, inner=None):
        import httpx
        self.state = state
        self.scenario = scenario
        self.inner = inner or httpx.AsyncHTTPTransport(retries=0)

    async def handle_async_request(self, request):
        raw = await request.aread()
        request_number = self.state.begin(self.scenario, request, raw)
        try:
            response = await self.inner.handle_async_request(request)
            response_raw = await response.aread()
            _append_jsonl(self.state.provider_path, {
                "record_type": "provider_http_response",
                "evidence_level": "REAL_HTTPX_TRANSPORT_RESPONSE",
                "utc_time": _now(),
                "scenario": self.scenario,
                "global_request_number": request_number,
                "status_code": response.status_code,
                "headers": _safe_headers(response.headers, request=False),
                "body": _safe_json_body(response_raw),
            })
            return response
        except BaseException as error:
            _append_jsonl(self.state.provider_path, {
                "record_type": "provider_http_exception",
                "evidence_level": "REAL_HTTPX_TRANSPORT_EXCEPTION",
                "utc_time": _now(),
                "scenario": self.scenario,
                "global_request_number": request_number,
                "exception_chain": _error_chain(error, self.state.secret),
            })
            raise
        finally:
            self.state.finish()

    async def aclose(self) -> None:
        await self.inner.aclose()


class _RecordingSyncTransport(__import__("httpx").BaseTransport):
    def __init__(self, state: _LiveRequestState, scenario: str, inner=None):
        import httpx
        self.state = state
        self.scenario = scenario
        self.inner = inner or httpx.HTTPTransport(retries=0)

    def handle_request(self, request):
        raw = request.read()
        request_number = self.state.begin(self.scenario, request, raw)
        try:
            response = self.inner.handle_request(request)
            response_raw = response.read()
            _append_jsonl(self.state.provider_path, {
                "record_type": "provider_http_response",
                "evidence_level": "REAL_HTTPX_TRANSPORT_RESPONSE",
                "utc_time": _now(),
                "scenario": self.scenario,
                "global_request_number": request_number,
                "status_code": response.status_code,
                "headers": _safe_headers(response.headers, request=False),
                "body": _safe_json_body(response_raw),
            })
            return response
        except BaseException as error:
            _append_jsonl(self.state.provider_path, {
                "record_type": "provider_http_exception",
                "evidence_level": "REAL_HTTPX_TRANSPORT_EXCEPTION",
                "utc_time": _now(),
                "scenario": self.scenario,
                "global_request_number": request_number,
                "exception_chain": _error_chain(error, self.state.secret),
            })
            raise
        finally:
            self.state.finish()

    def close(self) -> None:
        self.inner.close()


def _wait_run(client, run_id: str, seconds: float = 75) -> dict[str, Any]:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        response = client.get(f"/api/runs/{run_id}")
        if response.status_code != 200:
            raise RuntimeError("RUN_READ_FAILED:" + str(response.status_code))
        run = response.json()
        if run["status"] in {"SUCCEEDED", "FAILED", "BLOCKED", "CANCELLED"}:
            return run
        time.sleep(0.1)
    raise TimeoutError("RUN_WAIT_TIMEOUT")


def _row_dict(row) -> dict[str, Any]:
    return {key: row[key] for key in row.keys()}


def _case_audit(db_path: Path, scenario: str, result: dict[str, Any]) -> None:
    from opspilot.domain.assistant_experiment import read_budget
    from opspilot.domain.database import connect

    with connect(db_path) as connection:
        call_rows = connection.execute(
            "SELECT * FROM assistant_calls ORDER BY created_at,call_id"
        ).fetchall()
        runs = connection.execute(
            "SELECT run_id,task_id,session_id,source_message_id,kind,status,blocked_reason,created_at,ended_at "
            "FROM task_runs ORDER BY created_at,run_id"
        ).fetchall()
        messages = connection.execute(
            "SELECT message_id,task_id,session_id,sequence,role,body,created_at,command_id,applied_run_id "
            "FROM messages ORDER BY sequence"
        ).fetchall()
        writes: dict[str, int] = {}
        for table in (
            "s3_diagnoses", "d3_plans", "d3_plan_authorizations", "d3_approvals",
            "d3_action_permissions", "d3_action_intents", "d3_action_ledgers",
            "d3_verification_receipts", "d3_report_artifacts", "d3_delivery_records",
            "s2_handoff_queue_entries", "s2_handoff_receipts",
            "s3_handoff_queue_entries", "s3_handoff_receipts",
        ):
            writes[table] = int(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
    call_values = [_row_dict(row) for row in call_rows]
    for row in call_values:
        for field in ("request_json", "result_json", "usage_json"):
            if isinstance(row.get(field), str):
                try:
                    row[field] = json.loads(row[field])
                except json.JSONDecodeError:
                    pass
    budget = read_budget(db_path, EXPERIMENT_ID)
    _append_jsonl(EVIDENCE / "TRACE.jsonl", {
        "record_type": "scenario_domain_trace",
        "evidence_level": "PERSISTED_FORMAL_API_WORKER_DOMAIN",
        "scenario": scenario,
        "run_ids": result.get("run_ids", []),
        "task_id": result.get("task_id"),
        "session_id": result.get("session_id"),
        "message_ids": result.get("message_ids", []),
        "runs": [_row_dict(row) for row in runs],
        "messages": [_row_dict(row) for row in messages],
        "assistant_calls": call_values,
        "budget": budget,
        "agent_business_write_counts": writes,
    })


def _run_case(case_id: str, label: str, receiver_state: str, live_state: _LiveRequestState) -> dict[str, Any]:
    import httpx
    from fastapi.testclient import TestClient
    from opspilot.assistant import create_assistant_model
    from opspilot.domain.assistant_experiment import read_budget
    from opspilot.domain.database import connect, reset_fixture
    from opspilot.domain.s3 import prepare_s3_fixture
    from opspilot.web.app import create_app

    case_dir = RUNTIME / f"scenario-{label}"
    db_path = case_dir / "domain.sqlite3"
    checkpoint_path = case_dir / "checkpoints.sqlite3"
    case_dir.mkdir(parents=True, exist_ok=False)
    if db_path.exists() or checkpoint_path.exists():
        raise RuntimeError("SCENARIO_DATABASE_ALREADY_EXISTS_NO_OVERWRITE")
    reset_fixture(db_path, "S1_POS")

    import opspilot.domain.s3 as s3_module
    original_uuid4 = s3_module.uuid.uuid4
    generated = iter((
        uuid.UUID("00000000-0000-4000-8000-000000000001"),
        uuid.UUID("00000000-0000-4000-8000-000000000002"),
    ))
    s3_module.uuid.uuid4 = lambda: next(generated)
    try:
        fixture = prepare_s3_fixture(
            db_path, "DELIVERED_PENDING", order_id="ar03-order", contract_version=2,
        )
    finally:
        s3_module.uuid.uuid4 = original_uuid4

    if receiver_state == "PROCESSED":
        with connect(db_path) as connection:
            connection.execute(
                "UPDATE s3_receivers SET status='PROCESSED',version=version+1 "
                "WHERE order_id='ar03-order' AND event_id=?",
                (TARGET_EVENT_ID,),
            )
    with connect(db_path) as connection:
        event_rows = connection.execute(
            "SELECT d.event_id,d.status,d.receiver_http_status,r.event_id AS receiver_event_id,r.status AS receiver_status "
            "FROM s3_deliveries d JOIN s3_receivers r ON r.order_id=d.order_id "
            "WHERE d.order_id='ar03-order'"
        ).fetchall()
    if len(event_rows) != 1:
        raise RuntimeError("FIXTURE_EVENT_CARDINALITY_MISMATCH")
    fixture_event = _row_dict(event_rows[0])
    if (
        fixture_event["event_id"] != TARGET_EVENT_ID
        or fixture_event["receiver_event_id"] != TARGET_EVENT_ID
        or fixture_event["status"] != "ACKNOWLEDGED"
        or fixture_event["receiver_http_status"] != 202
        or fixture_event["receiver_status"] != receiver_state
    ):
        raise RuntimeError("FIXTURE_EVENT_FACTS_MISMATCH")

    setup_record = {
        "record_type": "isolated_fixture_setup",
        "evidence_level": "TEST_SETUP_NOT_AGENT_OBSERVATION",
        "scenario": label,
        "case_id": case_id,
        "utc_time": _now(),
        "tenant_id": "tenant-a",
        "actor_id": "support-a",
        "order_id": "ar03-order",
        "event_id": TARGET_EVENT_ID,
        "delivery_status": "ACKNOWLEDGED",
        "delivery_http_status": 202,
        "receiver_status": receiver_state,
        "fixture_http": fixture.get("transport_trace", []),
        "fixture_return_summary": {k: fixture.get(k) for k in ("state", "order_id", "order_version", "contract_version", "receiver_http_status")},
        "provider_requests": 0,
    }
    _append_jsonl(EVIDENCE / "TRACE.jsonl", setup_record)

    provider_calls_before = live_state.count
    run_records: list[dict[str, Any]] = []
    session_id: str | None = None
    task_id: str | None = None
    message_ids: list[str] = []
    stop_reason: str | None = None

    def model_factory():
        return create_assistant_model(
            transport_async=_RecordingAsyncTransport(live_state, label),
            transport_sync=_RecordingSyncTransport(live_state, label),
        )

    app = create_app(
        db_path=db_path,
        checkpoint_db_path=checkpoint_path,
        start_worker=True,
        credentials=LOCAL_PASSWORDS,
        expected_origin=API_ORIGIN,
        assistant_model_factory=model_factory,
        assistant_experiment_id=EXPERIMENT_ID,
    )
    try:
        with TestClient(app) as client:
            login = client.post(
                "/api/auth/login",
                headers={"Origin": API_ORIGIN},
                json={"actor_id": "support-a", "password": LOCAL_PASSWORDS["support-a"]},
            )
            if login.status_code != 200:
                raise RuntimeError("SUPPORT_LOGIN_FAILED:" + str(login.status_code))
            headers = {"Origin": API_ORIGIN, "X-CSRF-Token": login.json()["csrf_token"]}
            session_id = client.post("/api/sessions", headers=headers).json()["session_id"]

            bind = client.post(
                f"/api/sessions/{session_id}/assistant/order",
                headers={**headers, "Idempotency-Key": f"ar03-live-{label}-bind"},
                json={
                    "order_id": "ar03-order",
                    "initial_message": "请开始核对我通过工作台授权的订单与回调问题。",
                },
            )
            if bind.status_code != 202:
                raise RuntimeError("TRUSTED_BINDING_REQUEST_FAILED:" + str(bind.status_code))
            task_id = bind.json()["task_id"]
            bind_run = _wait_run(client, bind.json()["run_id"])
            run_records.append({"purpose": "trusted_binding_admission", "accepted": bind.json(), "run": bind_run})
            message_ids.append(str(bind.json().get("source_message_id") or ""))
            binding_budget = read_budget(db_path, EXPERIMENT_ID)
            if binding_budget["status"] != "OPEN" or live_state.inflight:
                raise RuntimeError("EXPERIMENT_STOP_AFTER_BINDING_RUN")

            with connect(db_path) as connection:
                from opspilot.domain.s3 import get_s3_binding
                binding = get_s3_binding(connection, task_id)
            if (
                binding["tenant_id"] != "tenant-a"
                or binding["actor_id"] != "support-a"
                or binding["order_id"] != "ar03-order"
                or binding["resource_confirmed_by"] != "support-a"
            ):
                raise RuntimeError("TRUSTED_BINDING_FACT_MISMATCH")

            accepted = client.post(
                f"/api/sessions/{session_id}/assistant/messages",
                headers={**headers, "Idempotency-Key": f"ar03-live-{label}-frozen-goal"},
                json={"body": PROMPT, "task_id": task_id},
            )
            if accepted.status_code != 202:
                raise RuntimeError("FROZEN_GOAL_REQUEST_FAILED:" + str(accepted.status_code))
            message_ids.append(accepted.json()["message_id"])
            goal_run = _wait_run(client, accepted.json()["run_id"])
            run_records.append({"purpose": "frozen_business_goal", "accepted": accepted.json(), "run": goal_run})
            messages = client.get(f"/api/sessions/{session_id}/messages")
            if messages.status_code != 200:
                raise RuntimeError("SESSION_MESSAGES_READ_FAILED:" + str(messages.status_code))
            message_rows = messages.json().get("items", [])
            answer = next((
                row for row in message_rows
                if row.get("answer_source_message_id") == accepted.json()["message_id"]
            ), None)
            if answer is None:
                answer = next((
                    row for row in message_rows
                    if row.get("source_message_id") == accepted.json()["message_id"]
                    or row.get("message_id") == goal_run.get("answer_message_id")
                ), None)
            sources = client.get(f"/api/runs/{goal_run['run_id']}/assistant-sources")
            if sources.status_code == 403:
                raise RuntimeError("ASSISTANT_SOURCE_AUTHORIZATION_ANOMALY")
            if sources.status_code != 200:
                raise RuntimeError("ASSISTANT_SOURCE_READ_FAILED:" + str(sources.status_code))
            run_records[-1]["answer"] = answer
            run_records[-1]["sources"] = sources.json()
            if goal_run["status"] not in {"SUCCEEDED", "FAILED", "BLOCKED"}:
                stop_reason = "RUN_DID_NOT_REACH_TERMINAL_STATUS"
    except BaseException as error:
        stop_reason = type(error).__name__ + ":" + str(error)[:300]

    budget = read_budget(db_path, EXPERIMENT_ID)
    result = {
        "case_id": case_id,
        "scenario": label,
        "receiver_state": receiver_state,
        "session_id": session_id,
        "task_id": task_id,
        "run_ids": [record.get("accepted", {}).get("run_id") for record in run_records],
        "message_ids": [item for item in message_ids if item],
        "runs": run_records,
        "fixture_event": fixture_event,
        "budget": budget,
        "provider_http_count_delta": live_state.count - provider_calls_before,
        "provider_http_global_count": live_state.count,
        "mcp_campaign_count": budget.get("mcp_used", 0),
        "stop_reason": stop_reason,
    }
    _write_json(RUNTIME / f"scenario-{label}" / "result.json", result)
    _case_audit(db_path, label, result)
    if stop_reason:
        return result
    if budget["status"] != "OPEN":
        result["stop_reason"] = "EXPERIMENT_BUDGET_CLOSED_OR_UNKNOWN"
        _write_json(RUNTIME / f"scenario-{label}" / "result.json", result)
        return result
    return result


def _execute() -> int:
    import httpx
    from opspilot.config import load_local_environment

    # Preflight does not emit traffic. Credentials are loaded only into this
    # child process and are never written to trace or stdout.
    env_file = ROOT.parent.parent / ".env"
    load_local_environment(env_file)
    preflight = _validate_preflight(require_fresh_paths=True)
    claim = EVIDENCE / "EXECUTION_CLAIM.json"
    claim.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(claim), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        stream.write(json.dumps({
            "experiment_id": EXPERIMENT_ID,
            "claimed_at": _now(),
            "branch": preflight["branch"],
            "head": preflight["head"],
            "authorized_base": FROZEN_BASE,
            "provider_request_limit": PROVIDER_TOTAL_LIMIT,
            "mcp_limit": MCP_TOTAL_LIMIT,
            "status": "CLAIMED_NO_RETRY",
        }, sort_keys=True) + "\n")
        stream.flush()
        os.fsync(stream.fileno())

    os.environ["OPSPILOT_ASSISTANT_PROVIDER_ENABLED"] = "1"
    os.environ["OPSPILOT_ASSISTANT_EXPERIMENT_ID"] = EXPERIMENT_ID
    RUNTIME.mkdir(parents=True, exist_ok=False)
    _write_json(EVIDENCE / "PREFLIGHT.json", preflight)
    state = _LiveRequestState(EVIDENCE / "PROVIDER_HTTP.jsonl")
    results: list[dict[str, Any]] = []
    try:
        for case_id, label, receiver in CASE_STATES:
            scenario_result = _run_case(case_id, label, receiver, state)
            results.append(scenario_result)
            _write_json(EVIDENCE / "PROGRESS.json", {
                "experiment_id": EXPERIMENT_ID,
                "updated_at": _now(),
                "provider_http_count": state.count,
                "provider_http_inflight": state.inflight,
                "scenario_count": state.scenario_count,
                "results": results,
            })
            if state.inflight:
                scenario_result["stop_reason"] = "PROVIDER_RESULT_STILL_IN_FLIGHT_STOP_ALL"
                break
            if scenario_result.get("stop_reason"):
                break
            if scenario_result.get("budget", {}).get("status") != "OPEN":
                break
            # Unknown/provider usage failures permanently close each domain
            # ledger. This explicit check protects the paired case transition.
            db_path = RUNTIME / f"scenario-{label}" / "domain.sqlite3"
            from opspilot.domain.assistant_experiment import read_budget
            if read_budget(db_path, EXPERIMENT_ID)["status"] != "OPEN":
                break
        statuses = [item.get("runs", [{}])[-1].get("run", {}).get("status") for item in results]
        outcome = "COMPLETE" if len(results) == 2 and all(status == "SUCCEEDED" for status in statuses) else "PARTIAL"
        _write_json(EVIDENCE / "RESULTS.json", {
            "experiment_id": EXPERIMENT_ID,
            "outcome": outcome,
            "provider_requests": state.count,
            "provider_requests_by_scenario": state.scenario_count,
            "provider_inflight_at_stop": state.inflight,
            "mcp_total": sum(item.get("mcp_campaign_count", 0) for item in results),
            "scenario_results": results,
            "historical_experiments_modified": False,
            "business_action_writes": 0,
            "real_provider_requests": state.count,
            "written_at": _now(),
        })
        return 0
    except BaseException as error:
        _append_jsonl(EVIDENCE / "TRACE.jsonl", {
            "record_type": "experiment_stopped",
            "evidence_level": "RUNNER_OBSERVED",
            "utc_time": _now(),
            "exception_chain": _error_chain(error, state.secret),
            "provider_http_count": state.count,
            "provider_http_inflight": state.inflight,
            "provider_requests_by_scenario": state.scenario_count,
        })
        _write_json(EVIDENCE / "RESULTS.json", {
            "experiment_id": EXPERIMENT_ID,
            "outcome": "UNKNOWN_STOPPED" if state.inflight else "FAIL_STOPPED",
            "provider_requests": state.count,
            "provider_requests_by_scenario": state.scenario_count,
            "provider_inflight_at_stop": state.inflight,
            "partial_scenario_results": results,
            "stop_error_type": type(error).__name__,
            "real_provider_requests": state.count,
            "historical_experiments_modified": False,
            "business_action_writes": 0,
            "written_at": _now(),
        })
        return 2
    finally:
        try:
            _write_json(EVIDENCE / "BUDGET_LEDGER.json", _aggregate_budget(results, state))
        except BaseException:
            pass
        # The provider opt-in is confined to this process and is removed before
        # it exits. The persistent claim prevents any second execution.
        os.environ.pop("OPSPILOT_ASSISTANT_PROVIDER_ENABLED", None)
        os.environ.pop("OPSPILOT_ASSISTANT_EXPERIMENT_ID", None)


def _aggregate_budget(results: list[dict[str, Any]], state: _LiveRequestState) -> dict[str, Any]:
    provider_used = sum(int(item.get("budget", {}).get("provider_used", 0)) for item in results)
    mcp_used = sum(int(item.get("budget", {}).get("mcp_used", 0)) for item in results)
    reserved = sum(int(item.get("budget", {}).get("usd_reserved_micro", 0)) for item in results)
    settled = sum(int(item.get("budget", {}).get("usd_settled_micro", 0)) for item in results)
    return {
        "experiment_id": EXPERIMENT_ID,
        "currency": "USD",
        "limits": {
            "provider_requests": PROVIDER_TOTAL_LIMIT,
            "mcp_tools_call": MCP_TOTAL_LIMIT,
            "application_budget_usd_micro": TOTAL_BUDGET_USD_MICRO,
            "per_provider_reservation_usd_micro": RESERVATION_USD_MICRO,
            "per_scenario_provider": PROVIDER_SCENARIO_LIMIT,
            "per_scenario_mcp": MCP_SCENARIO_LIMIT,
        },
        "provider_http_attempts": state.count,
        "provider_ledger_dispatches": provider_used,
        "mcp_ledger_dispatches": mcp_used,
        "reserved_usd_micro": reserved,
        "settled_usd_micro": settled,
        "reserved_plus_settled_usd_micro": reserved + settled,
        "provider_requests_by_scenario": state.scenario_count,
        "price_version": "DEEPSEEK_FLASH_PEAK_2026-11-01",
        "unknown_results_keep_reservation": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--preflight-only", action="store_true")
    group.add_argument("--execute-once", action="store_true")
    args = parser.parse_args()
    sys.path.insert(0, str(ROOT))
    try:
        if args.preflight_only:
            from opspilot.config import load_local_environment
            load_local_environment(ROOT.parent.parent / ".env")
            result = _validate_preflight(require_fresh_paths=True)
            print(json.dumps(result, ensure_ascii=False, sort_keys=True))
            return 0
        return _execute()
    except BaseException as error:
        print(json.dumps({
            "status": "BLOCKED_BEFORE_PROVIDER_SEND",
            "error_type": type(error).__name__,
            "error": str(error)[:300],
            "provider_requests": 0,
        }, ensure_ascii=False, sort_keys=True))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
