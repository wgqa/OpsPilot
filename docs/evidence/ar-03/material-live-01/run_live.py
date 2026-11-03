"""One-shot, bounded real-model runner for AR-03-MATERIAL-LIVE-01.

Importing this module and --preflight-only perform no Provider I/O. The live
path always uses the formal FastAPI Worker and the repository Assistant; the
HTTPX transport only records and enforces the frozen request envelope.
"""
from __future__ import annotations

import argparse
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
EVIDENCE = ROOT / "docs" / "evidence" / "ar-03" / "material-live-01"
CASES_PATH = ROOT / "docs" / "evidence" / "ar-03" / "material-01" / "CASES.json"
RUNTIME = ROOT / ".runtime" / "ar03-material-live-01"
DOMAIN_DB = RUNTIME / "domain.sqlite3"
CHECKPOINT_DB = RUNTIME / "checkpoints.sqlite3"
BRANCH = "codex/ar03-material-01-public"
BASE_SHA = "3ec06caa6a2d8ef370592d33164be3077a0a5f6f"
FREEZE_SHA = "434a8b027f0072036b46bc624d1defab8703b775"
CASES_BLOB = "faf16fbb857278e98f8afbe179fe327855132967"
EXPERIMENT_ID = "AR-03-MATERIAL-LIVE-01"
MODEL = "deepseek-flash"
API_ORIGIN = "http://ar03-material-live.local"
SUPPORT_PASSWORD = "ar03-material-live-offline-support"
PROVIDER_LIMIT = 16
MCP_LIMIT = 10
BUDGET_USD_MICRO = 10_500_000
RESERVATION_USD_MICRO = 645_600
CONTEXT_LIMIT = 12_000
CAMPAIGN_WALL_SECONDS = 3_600
TERMINAL_RUN_STATES = {"SUCCEEDED", "FAILED", "BLOCKED", "CANCELLED"}
ALLOWED_TOOLS = {
    "search_project_knowledge",
    "list_scoped_protocol_documents",
    "read_scoped_protocol_excerpt",
    "compare_scoped_protocols",
    "load_protocol_upgrade_skill",
    "get_order_status",
    "get_callback_delivery",
    "get_receiver_processing",
    "get_callback_transport_history",
}
BUSINESS_WRITE_TABLES = (
    "s3_diagnoses", "d3_plans", "d3_plan_authorizations", "d3_approvals",
    "d3_action_permissions", "d3_action_intents", "d3_action_ledgers",
    "d3_verification_receipts", "d3_report_artifacts", "d3_delivery_records",
    "s2_handoff_queue_entries", "s2_handoff_receipts",
    "s3_handoff_queue_entries", "s3_handoff_receipts",
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe(value: Any) -> Any:
    if isinstance(value, dict):
        result = {}
        for key, item in value.items():
            if re.search(r"(?i)(api.?key|authorization|password|secret|cookie)", str(key)):
                result[str(key)] = "[REDACTED]"
            else:
                result[str(key)] = _safe(item)
        return result
    if isinstance(value, list):
        return [_safe(item) for item in value]
    return value


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(_safe(value), ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def _append_jsonl(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(_safe(value), ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


def _git(*args: str, check: bool = True) -> str:
    result = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=False)
    if check and result.returncode:
        raise RuntimeError("GIT_PREFLIGHT_FAILED:" + " ".join(args))
    return result.stdout.strip()


def _blob_at_head(path: str) -> str:
    return _git("rev-parse", f"HEAD:{path}")


def _load_environment() -> Path:
    from opspilot.config import load_local_environment

    shared_env = ROOT.parent.parent / ".env"
    if not shared_env.is_file():
        raise RuntimeError("MODEL_ENVIRONMENT_FILE_NOT_FOUND")
    load_local_environment(shared_env)
    return shared_env


def _case_inputs() -> dict[str, str]:
    casebook = json.loads(CASES_PATH.read_text(encoding="utf-8"))
    items = {row["id"]: row for row in casebook["cases"]}
    return {
        "MAT-01-PROTOCOL-EXCERPT": items["MAT-01-PROTOCOL-EXCERPT"]["input"],
        "MAT-02-USER-MATERIAL-UNBOUND": items["MAT-02-USER-MATERIAL-UNBOUND"]["input"],
        "MAT-03-USER-MATERIAL-MALFORMED": items["MAT-03-USER-MATERIAL-MALFORMED"]["input"],
        "MAT-04-BOUND-QUEUED": items["MAT-04-BOUND-QUEUED"]["input"],
        "MAT-05-BOUND-PROCESSED": items["MAT-04-BOUND-QUEUED"]["input"],
        "MAT-06-SKILL-OFF": items["MAT-06-SKILL-ON-OFF"]["input"],
        "MAT-06-SKILL-ON": items["MAT-06-SKILL-ON-OFF"]["input"],
    }


def _validate_preflight() -> dict[str, Any]:
    _load_environment()
    branch = _git("branch", "--show-current")
    head = _git("rev-parse", "HEAD")
    if branch != BRANCH:
        raise RuntimeError("MATERIAL_LIVE_BRANCH_MISMATCH")
    for required_sha, error_code in (
        (BASE_SHA, "AUTHORIZED_BASELINE_NOT_IN_HISTORY"),
        (FREEZE_SHA, "FREEZE_COMMIT_NOT_IN_HISTORY"),
    ):
        check = subprocess.run(
            ["git", "merge-base", "--is-ancestor", required_sha, "HEAD"],
            cwd=ROOT, capture_output=True, check=False,
        )
        if check.returncode != 0:
            raise RuntimeError(error_code)
    if _blob_at_head("docs/evidence/ar-03/material-01/CASES.json") != CASES_BLOB:
        raise RuntimeError("FROZEN_CASES_BLOB_MISMATCH")

    tracked_diff = _git("diff", "--name-only")
    staged_diff = _git("diff", "--cached", "--name-only")
    if tracked_diff or staged_diff:
        raise RuntimeError("WORKTREE_OR_INDEX_NOT_CLEAN")
    untracked = _git("ls-files", "--others", "--exclude-standard").splitlines()
    evidence_runs_prefix = EVIDENCE.relative_to(ROOT).as_posix().rstrip("/") + "/runs/"
    unexpected = [path for path in untracked if not path.startswith(evidence_runs_prefix)]
    if unexpected:
        raise RuntimeError("UNEXPECTED_UNTRACKED_FILES_PRESENT")

    key = os.environ.get("OPSPILOT_MODEL_API_KEY", "").strip()
    model = os.environ.get("OPSPILOT_MODEL_NAME", "").strip()
    base_url = os.environ.get("OPSPILOT_MODEL_BASE_URL", "").strip()
    parsed = urlparse(base_url)
    if not key or model != MODEL:
        raise RuntimeError("MODEL_CREDENTIAL_OR_ID_MISMATCH")
    if (
        parsed.scheme != "https" or parsed.hostname != "api.deepseek.com"
        or parsed.port not in (None, 443) or parsed.username is not None
        or parsed.password is not None or parsed.query or parsed.fragment
        or parsed.path not in ("", "/", "/v1")
    ):
        raise RuntimeError("MODEL_ENDPOINT_MISMATCH")
    opt_in = os.environ.get("OPSPILOT_ASSISTANT_PROVIDER_ENABLED", "").strip()
    experiment_env = os.environ.get("OPSPILOT_ASSISTANT_EXPERIMENT_ID", "").strip()
    if opt_in not in ("", "0", "false", "False") or experiment_env:
        raise RuntimeError("PROVIDER_OPT_IN_OR_EXPERIMENT_ID_PRESET")

    from opspilot.domain.assistant_experiment import (
        BUDGET_USD_MICRO, MAX_PROVIDER_RESERVATION_USD_MICRO,
        AR03_MATERIAL_LIVE_MCP_LIMIT, MCP_LIMIT, PRICE_VERSION,
        PROVIDER_LIMIT as DOMAIN_PROVIDER_LIMIT,
    )
    from opspilot.domain.context_engineering import context_budget_for_model

    context = context_budget_for_model(MODEL)
    if int(context["input_budget_tokens"]) != CONTEXT_LIMIT:
        raise RuntimeError("CONTEXT_BUDGET_MISMATCH")
    if MAX_PROVIDER_RESERVATION_USD_MICRO != RESERVATION_USD_MICRO:
        raise RuntimeError("REQUEST_RESERVATION_MISMATCH")
    max_reserve = PROVIDER_LIMIT * RESERVATION_USD_MICRO
    if max_reserve > BUDGET_USD_MICRO or BUDGET_USD_MICRO != 10_500_000:
        raise RuntimeError("CAMPAIGN_BUDGET_ENVELOPE_UNSAFE")
    if (
        DOMAIN_PROVIDER_LIMIT != PROVIDER_LIMIT
        or AR03_MATERIAL_LIVE_MCP_LIMIT != 10
        or MCP_LIMIT != 12
        or BUDGET_USD_MICRO != 10_500_000
    ):
        raise RuntimeError("EXISTING_BUDGET_CONSTANTS_MISMATCH")

    cases = _case_inputs()
    if list(cases) != [
        "MAT-01-PROTOCOL-EXCERPT", "MAT-02-USER-MATERIAL-UNBOUND",
        "MAT-03-USER-MATERIAL-MALFORMED", "MAT-04-BOUND-QUEUED",
        "MAT-05-BOUND-PROCESSED", "MAT-06-SKILL-OFF", "MAT-06-SKILL-ON",
    ]:
        raise RuntimeError("FROZEN_CASE_SET_INVALID")
    claim = EVIDENCE / "EXECUTION_CLAIM.json"
    outputs = ["PROVIDER_HTTP.jsonl", "TRACE.jsonl", "RESULTS.json", "BUDGET_LEDGER.json", "PROGRESS.json"]
    if claim.exists() or any((EVIDENCE / name).exists() for name in outputs):
        raise RuntimeError("EXPERIMENT_ALREADY_CLAIMED_OR_EVIDENCE_EXISTS")
    if RUNTIME.exists() or DOMAIN_DB.exists() or CHECKPOINT_DB.exists():
        raise RuntimeError("ISOLATED_RUNTIME_PATH_ALREADY_EXISTS")

    try:
        remote = _git("ls-remote", "origin", "refs/heads/main", f"refs/heads/{BRANCH}")
        remote_state = remote if remote else "REMOTE_REFS_EMPTY"
    except RuntimeError:
        remote_state = "REMOTE_UNVERIFIED"
    try:
        main_head = _git("rev-parse", "main")
    except RuntimeError:
        main_head = "UNVERIFIED"
    return {
        "status": "PREFLIGHT_READY",
        "experiment_id": EXPERIMENT_ID,
        "branch": branch,
        "head": head,
        "authorized_base": BASE_SHA,
        "freeze_commit": FREEZE_SHA,
        "local_main_head": main_head,
        "remote_refs": remote_state,
        "frozen_cases_blob": CASES_BLOB,
        "provider": "DeepSeek",
        "model": model,
        "base_url": base_url,
        "credential_present": True,
        "provider_opt_in_before_runner": False,
        "request_parameters": {
            "thinking": "disabled", "max_tokens": 2048,
            "tool_choice": "auto when tools are supplied",
            "parallel_tool_calls": False, "stream": False,
            "timeout_seconds": 30, "sdk_retries": 0,
            "http_transport_retries": 0, "provider_concurrency": 1,
        },
        "context_input_limit_tokens": CONTEXT_LIMIT,
        "budget": {
            "provider_requests": PROVIDER_LIMIT,
            "mcp_tools_call": AR03_MATERIAL_LIVE_MCP_LIMIT,
            "application_budget_usd_micro": BUDGET_USD_MICRO,
            "reservation_usd_micro_per_provider": RESERVATION_USD_MICRO,
            "maximum_reservations_usd_micro": max_reserve,
            "price_version": PRICE_VERSION,
            "wall_clock_stop_seconds": CAMPAIGN_WALL_SECONDS,
        },
        "case_count": len(cases),
        "cases": list(cases),
        "runtime_db_path": str(DOMAIN_DB),
        "checkpoint_db_path": str(CHECKPOINT_DB),
        "provider_requests_before_execution": 0,
        "business_write_tools_exposed": False,
    }


def _safe_headers(headers, request: bool) -> dict[str, str]:
    allowed = {"content-type", "accept", "user-agent", "x-request-id", "request-id", "date", "content-length"}
    return {key.lower(): value for key, value in headers.items() if key.lower() in allowed}


def _json_body(raw: bytes) -> Any:
    try:
        return json.loads(raw.decode("utf-8"))
    except Exception:
        return {"unparsed_bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}


def _error_chain(error: BaseException) -> list[dict[str, str]]:
    chain: list[dict[str, str]] = []
    current: BaseException | None = error
    seen: set[int] = set()
    secret = os.environ.get("OPSPILOT_MODEL_API_KEY", "")
    while current is not None and id(current) not in seen and len(chain) < 8:
        seen.add(id(current))
        message = str(current)
        if secret:
            message = message.replace(secret, "[REDACTED]")
        message = re.sub(r"(?i)(authorization|api[-_]?key)\s*[:=]\s*[^\s,;]+", r"\1=[REDACTED]", message)
        chain.append({"type": type(current).__name__, "message": message[:500]})
        current = current.__cause__ or current.__context__
    return chain


class _CampaignState:
    def __init__(self, provider_log: Path, db_path: Path):
        self.provider_log = provider_log
        self.db_path = db_path
        self.lock = threading.Lock()
        self.request_count = 0
        self.inflight = 0
        self.unknown = False
        self.started_monotonic: float | None = None
        self.case_id: str | None = None
        self.run_id: str | None = None

    def begin(self, request, raw: bytes) -> int:
        body = _json_body(raw)
        if not isinstance(body, dict):
            raise RuntimeError("LIVE_WIRE_BODY_INVALID")
        if (
            body.get("model") != MODEL or body.get("thinking") != {"type": "disabled"}
            or body.get("max_tokens") != 2048 or "max_completion_tokens" in body
            or body.get("stream") is not False
        ):
            raise RuntimeError("LIVE_WIRE_MODEL_OR_OUTPUT_CONFIGURATION_MISMATCH")
        if request.method != "POST" or str(request.url) != "https://api.deepseek.com/v1/chat/completions":
            raise RuntimeError("LIVE_WIRE_ENDPOINT_MISMATCH")
        tools = body.get("tools") or []
        names = {
            item.get("function", {}).get("name")
            for item in tools if isinstance(item, dict)
        }
        if tools and (body.get("tool_choice") != "auto" or body.get("parallel_tool_calls") is not False):
            raise RuntimeError("LIVE_WIRE_TOOL_CONFIGURATION_MISMATCH")
        if names - ALLOWED_TOOLS:
            raise RuntimeError("UNAPPROVED_TOOL_SCHEMA_EXPOSED")
        if self.case_id in {"MAT-02-USER-MATERIAL-UNBOUND", "MAT-03-USER-MATERIAL-MALFORMED", "MAT-01-PROTOCOL-EXCERPT", "MAT-06-SKILL-OFF", "MAT-06-SKILL-ON"}:
            if names & {"get_order_status", "get_callback_delivery", "get_receiver_processing", "get_callback_transport_history"}:
                raise RuntimeError("BUSINESS_TOOL_EXPOSED_WITHOUT_TASK_BINDING")
        if self.case_id == "MAT-06-SKILL-OFF" and "load_protocol_upgrade_skill" in names:
            raise RuntimeError("SKILL_OFF_TOOL_STILL_EXPOSED")
        if self.case_id == "MAT-06-SKILL-ON" and "load_protocol_upgrade_skill" not in names:
            raise RuntimeError("SKILL_ON_TOOL_NOT_EXPOSED")

        from opspilot.domain.context_engineering import (
            context_budget_for_model, estimate_messages_tokens, estimate_text_tokens,
        )
        from opspilot.domain.d2 import canonical_json
        context_tokens = (
            estimate_messages_tokens(body.get("messages") or [])
            + estimate_text_tokens(canonical_json(tools)) + 8
        )
        if context_tokens > min(CONTEXT_LIMIT, int(context_budget_for_model(MODEL)["input_budget_tokens"])):
            raise RuntimeError("LIVE_CONTEXT_INPUT_LIMIT_EXCEEDED")

        from opspilot.domain.assistant_experiment import PRICE_VERSION, read_budget
        from opspilot.domain.database import connect
        budget = read_budget(self.db_path, EXPERIMENT_ID)
        if (
            not budget.get("initialized") or budget.get("status") != "OPEN"
            or budget["provider_limit"] != PROVIDER_LIMIT
            or budget["mcp_limit"] != MCP_LIMIT
            or budget["budget_usd_micro"] != BUDGET_USD_MICRO
            or budget["price_version"] != PRICE_VERSION
            or budget["provider_used"] > PROVIDER_LIMIT or budget["mcp_used"] > MCP_LIMIT
            or budget["usd_reserved_micro"] + budget["usd_settled_micro"] > BUDGET_USD_MICRO
            or budget["provider_used"] != self.request_count + 1
        ):
            raise RuntimeError("DURABLE_CAMPAIGN_RESERVATION_MISSING_OR_OVER_LIMIT")
        with connect(self.db_path) as connection:
            reserved = connection.execute(
                "SELECT * FROM ar02_live_dispatches WHERE experiment_id=? AND kind='MODEL' AND status='RESERVED'",
                (EXPERIMENT_ID,),
            ).fetchall()
            current_call = connection.execute(
                "SELECT * FROM assistant_calls WHERE run_id=? AND kind='MODEL' AND status='RESERVED' ORDER BY created_at DESC LIMIT 1",
                (self.run_id,),
            ).fetchone()
        if (
            len(reserved) != 1 or reserved[0]["run_id"] != self.run_id
            or current_call is None or reserved[0]["logical_key"] != current_call["logical_key"]
            or int(reserved[0]["reserved_usd_micro"]) != RESERVATION_USD_MICRO
        ):
            raise RuntimeError("PROVIDER_SEND_WITHOUT_MATCHED_DURABLE_RESERVATION")
        now = time.monotonic()
        if self.started_monotonic is None:
            self.started_monotonic = now
        elif now - self.started_monotonic >= CAMPAIGN_WALL_SECONDS:
            raise RuntimeError("CAMPAIGN_WALL_CLOCK_LIMIT")
        with self.lock:
            if self.inflight:
                raise RuntimeError("LIVE_PROVIDER_CONCURRENCY_LIMIT")
            if self.request_count >= PROVIDER_LIMIT:
                raise RuntimeError("LIVE_PROVIDER_REQUEST_LIMIT")
            self.request_count += 1
            self.inflight = 1
            index = self.request_count
        _append_jsonl(self.provider_log, {
            "record_type": "provider_http_request",
            "evidence_level": "REAL_HTTPX_TRANSPORT_REQUEST",
            "utc_time": _now(), "case_id": self.case_id,
            "run_id": self.run_id, "global_request_number": index,
            "estimated_context_input_tokens": context_tokens,
            "context_input_limit_tokens": CONTEXT_LIMIT,
            "method": request.method, "url": str(request.url),
            "headers": _safe_headers(request.headers, request=True),
            "body": body,
        })
        return index

    def finish(self) -> None:
        with self.lock:
            self.inflight = 0


class _RecordingAsyncTransport(__import__("httpx").AsyncBaseTransport):
    def __init__(self, state: _CampaignState, inner=None):
        import httpx
        self.state = state
        self.inner = inner or httpx.AsyncHTTPTransport(retries=0)

    async def handle_async_request(self, request):
        raw = await request.aread()
        index = self.state.begin(request, raw)
        try:
            response = await self.inner.handle_async_request(request)
            response_raw = await response.aread()
            _append_jsonl(self.state.provider_log, {
                "record_type": "provider_http_response",
                "evidence_level": "REAL_HTTPX_TRANSPORT_RESPONSE",
                "utc_time": _now(), "case_id": self.state.case_id,
                "run_id": self.state.run_id, "global_request_number": index,
                "status_code": response.status_code,
                "headers": _safe_headers(response.headers, request=False),
                "body": _json_body(response_raw),
            })
            return response
        except BaseException as error:
            self.state.unknown = True
            _append_jsonl(self.state.provider_log, {
                "record_type": "provider_http_exception",
                "evidence_level": "REAL_HTTPX_TRANSPORT_EXCEPTION",
                "utc_time": _now(), "case_id": self.state.case_id,
                "run_id": self.state.run_id, "global_request_number": index,
                "exception_chain": _error_chain(error),
            })
            raise
        finally:
            self.state.finish()

    async def aclose(self) -> None:
        await self.inner.aclose()


class _NoSyncTransport(__import__("httpx").BaseTransport):
    """Formal Assistant is async; prohibit accidental synchronous network I/O."""
    def handle_request(self, request):
        raise RuntimeError("LIVE_SYNC_PROVIDER_TRANSPORT_PROHIBITED")

    def close(self) -> None:
        return None


def _login(client) -> dict[str, str]:
    response = client.post(
        "/api/auth/login", headers={"Origin": API_ORIGIN},
        json={"actor_id": "support-a", "password": SUPPORT_PASSWORD},
    )
    if response.status_code != 200:
        raise RuntimeError("LOCAL_SUPPORT_LOGIN_FAILED:" + str(response.status_code))
    return {"Origin": API_ORIGIN, "X-CSRF-Token": response.json()["csrf_token"]}


def _wait_run(client, run_id: str, seconds: float = 330) -> dict[str, Any]:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        response = client.get(f"/api/runs/{run_id}")
        if response.status_code != 200:
            raise RuntimeError("RUN_READ_FAILED:" + str(response.status_code))
        run = response.json()
        if run.get("status") in TERMINAL_RUN_STATES:
            return run
        time.sleep(0.1)
    raise TimeoutError("RUN_WAIT_TIMEOUT")


def _prepare_fixture(db_path: Path) -> dict[str, Any]:
    from opspilot.domain.s3 import prepare_s3_fixture
    from opspilot.domain.database import connect

    setup = prepare_s3_fixture(
        db_path, "DELIVERED_PENDING", tenant_id="tenant-a",
        order_id="ar03-order", contract_version=2, queue_age_seconds=60,
    )
    with connect(db_path) as connection:
        delivery = dict(connection.execute(
            "SELECT * FROM s3_deliveries WHERE tenant_id='tenant-a' AND order_id='ar03-order'"
        ).fetchone())
        receiver = dict(connection.execute(
            "SELECT * FROM s3_receivers WHERE tenant_id='tenant-a' AND order_id='ar03-order'"
        ).fetchone())
    if (
        delivery["status"] != "ACKNOWLEDGED" or delivery["receiver_http_status"] != 202
        or receiver["status"] != "QUEUED" or delivery["event_id"] != receiver["event_id"]
    ):
        raise RuntimeError("TRUSTED_FIXTURE_INITIAL_STATE_INVALID")
    event = {
        "tenant_id": "tenant-a", "order_id": "ar03-order",
        "event_id": delivery["event_id"],
        "transport_request_id": delivery["transport_request_id"],
        "delivery_status": delivery["status"], "http_status": delivery["receiver_http_status"],
        "receiver_state": receiver["status"],
        "delivery_version": delivery["version"], "receiver_version": receiver["version"],
        "setup_source": "prepare_s3_fixture; local loopback receiver HTTP POST; not an Agent action",
        "transport_trace": setup.get("transport_trace", []),
    }
    _append_jsonl(EVIDENCE / "TRACE.jsonl", {
        "record_type": "trusted_fixture_prepared",
        "evidence_level": "LOCAL_TEST_FIXTURE_SETUP_NOT_AGENT_OBSERVATION",
        "utc_time": _now(), "fixture": event,
    })
    return event


def _bootstrap_fresh_campaign_database(db_path: Path) -> None:
    """Seed trusted demo principals only when this campaign DB is truly new.

    ``reset_fixture`` is intentionally destructive and therefore must never be
    used against an existing campaign database. The live runner creates its
    runtime directory with ``exist_ok=False`` before reaching this function;
    the explicit DB/SQLite-sidecar check also protects direct callers.
    """
    from opspilot.domain.database import reset_fixture

    path = Path(db_path)
    sidecars = (Path(str(path) + "-wal"), Path(str(path) + "-shm"))
    if path.exists() or any(sidecar.exists() for sidecar in sidecars):
        raise RuntimeError("CAMPAIGN_DATABASE_NOT_FRESH")
    reset_fixture(path, "S1_POS")


def _set_receiver_processed(db_path: Path, expected_event_id: str) -> dict[str, Any]:
    from opspilot.domain.database import connect

    with connect(db_path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        before = connection.execute(
            "SELECT event_id,status,version FROM s3_receivers WHERE tenant_id='tenant-a' AND order_id='ar03-order'"
        ).fetchone()
        delivery = connection.execute(
            "SELECT event_id,status,receiver_http_status FROM s3_deliveries WHERE tenant_id='tenant-a' AND order_id='ar03-order'"
        ).fetchone()
        if (
            before is None or delivery is None or before["event_id"] != expected_event_id
            or delivery["event_id"] != expected_event_id or before["status"] != "QUEUED"
            or delivery["status"] != "ACKNOWLEDGED" or delivery["receiver_http_status"] != 202
        ):
            raise RuntimeError("FIXTURE_EVENT_CORRELATION_INVALID_BEFORE_PROCESSED_SETUP")
        changed = connection.execute(
            "UPDATE s3_receivers SET status='PROCESSED',version=version+1 "
            "WHERE tenant_id='tenant-a' AND order_id='ar03-order' AND event_id=? AND status='QUEUED'",
            (expected_event_id,),
        )
        if changed.rowcount != 1:
            raise RuntimeError("FIXTURE_RECEIVER_TRANSITION_FAILED")
        after = connection.execute(
            "SELECT event_id,status,version FROM s3_receivers WHERE tenant_id='tenant-a' AND order_id='ar03-order'"
        ).fetchone()
    result = {
        "before": dict(before), "after": dict(after), "delivery": dict(delivery),
        "same_event_id": after["event_id"] == delivery["event_id"] == expected_event_id,
        "preparation_only": True,
    }
    _append_jsonl(EVIDENCE / "TRACE.jsonl", {
        "record_type": "trusted_receiver_fixture_transition",
        "evidence_level": "LOCAL_FIXTURE_PREPARATION_NOT_AGENT_ACTION",
        "utc_time": _now(), "transition": result,
    })
    return result


def _create_user_run(case_id: str, body: str, bound: bool) -> dict[str, Any]:
    from fastapi.testclient import TestClient
    from opspilot.web.app import create_app

    app = create_app(
        db_path=DOMAIN_DB, checkpoint_db_path=CHECKPOINT_DB, start_worker=False,
        credentials={"support-a": SUPPORT_PASSWORD}, expected_origin=API_ORIGIN,
        assistant_experiment_id=EXPERIMENT_ID,
    )
    with TestClient(app) as client:
        headers = _login(client)
        session_id = client.post("/api/sessions", headers=headers).json()["session_id"]
        key = "ar03-material-" + uuid.uuid4().hex
        _append_jsonl(EVIDENCE / "TRACE.jsonl", {
            "record_type": "frozen_user_input_submitted",
            "evidence_level": "FORMAL_LOCAL_FASTAPI_REQUEST",
            "utc_time": _now(), "case_id": case_id,
            "session_id": session_id, "user_text": body,
            "user_text_sha256": hashlib.sha256(body.encode("utf-8")).hexdigest(),
            "idempotency_key": key,
        })
        if bound:
            response = client.post(
                f"/api/sessions/{session_id}/assistant/order",
                headers={**headers, "Idempotency-Key": key},
                json={"order_id": "ar03-order", "initial_message": body},
            )
        else:
            response = client.post(
                f"/api/sessions/{session_id}/assistant/messages",
                headers={**headers, "Idempotency-Key": key}, json={"body": body},
            )
        if response.status_code != 202:
            raise RuntimeError("FORMAL_ASSISTANT_REQUEST_REJECTED:" + str(response.status_code) + ":" + response.text[:300])
        accepted = response.json()
        if bound:
            from opspilot.domain.d2 import configure_s3_experiment_budget, task_attempt_limits
            from opspilot.domain.execution_budget import execution_budget_snapshot
            before = execution_budget_snapshot(DOMAIN_DB, str(accepted["task_id"]))
            if before["deadline_ms"] != 300_000:
                raise RuntimeError("TASK_ACTIVE_TIME_BUDGET_MISMATCH")
            configured = configure_s3_experiment_budget(DOMAIN_DB, str(accepted["task_id"]), 16, 10)
            if configured != {"MODEL": 16, "MCP": 10} or task_attempt_limits(DOMAIN_DB, str(accepted["task_id"])) != configured:
                raise RuntimeError("TRUSTED_TASK_BUDGET_CONFIGURATION_MISMATCH")
            after = execution_budget_snapshot(DOMAIN_DB, str(accepted["task_id"]))
            if after["deadline_ms"] != before["deadline_ms"]:
                raise RuntimeError("TASK_ACTIVE_TIME_BUDGET_CHANGED")
            accepted["trusted_attempt_limits"] = configured
            accepted["active_time_deadline_ms"] = after["deadline_ms"]
        accepted.update({"case_id": case_id, "session_id": session_id, "bound": bound})
        _append_jsonl(EVIDENCE / "TRACE.jsonl", {
            "record_type": "formal_assistant_request_accepted",
            "evidence_level": "FASTAPI_DOMAIN_PERSISTENCE",
            "utc_time": _now(), "case_id": case_id,
            "accepted": accepted,
        })
        return accepted


def _call_model_factory(state: _CampaignState):
    from opspilot.assistant import create_assistant_model

    return create_assistant_model(
        transport_async=_RecordingAsyncTransport(state),
        transport_sync=_NoSyncTransport(),
    )


def _decode_json(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value


def _nonnegative_tokens(value: Any) -> bool:
    return type(value) is int and value >= 0


def _call_usage_totals(call: dict[str, Any]) -> dict[str, int] | None:
    usage = call.get("usage")
    if not isinstance(usage, list) or not usage:
        return None
    totals = {"input_tokens": 0, "output_tokens": 0}
    observed = False
    for item in usage:
        if item is None:
            continue
        if (
            not isinstance(item, dict)
            or not _nonnegative_tokens(item.get("input_tokens"))
            or not _nonnegative_tokens(item.get("output_tokens"))
        ):
            return None
        totals["input_tokens"] += item["input_tokens"]
        totals["output_tokens"] += item["output_tokens"]
        observed = True
    return totals if observed else None


def _call_completion_ids(call: dict[str, Any]) -> list[str]:
    result = call.get("result")
    if not isinstance(result, list):
        return []
    ids: list[str] = []
    for message in result:
        if not isinstance(message, dict):
            continue
        data = message.get("data")
        metadata = data.get("response_metadata") if isinstance(data, dict) else None
        completion_id = metadata.get("id") if isinstance(metadata, dict) else None
        if isinstance(completion_id, str) and completion_id.strip():
            ids.append(completion_id)
    return ids


def _call_answer_texts(call: dict[str, Any]) -> list[str]:
    result = call.get("result")
    if not isinstance(result, list):
        return []
    texts: list[str] = []
    for message in result:
        if not isinstance(message, dict):
            continue
        data = message.get("data")
        content = data.get("content") if isinstance(data, dict) else None
        if isinstance(content, str) and content.strip():
            texts.append(content.strip())
    return texts


def _classify_case_outcome(
    *, run: dict[str, Any], answer: dict[str, Any] | None,
    calls: list[dict[str, Any]], dispatches: list[dict[str, Any]],
    expected_run_id: str, expected_source_message_id: str,
) -> dict[str, Any]:
    """Separate persisted Provider evidence from a non-empty user delivery."""
    model_calls = [call for call in calls if call.get("kind") == "MODEL"]
    model_dispatches = [dispatch for dispatch in dispatches if dispatch.get("kind") == "MODEL"]
    dispatch_by_key = {item.get("logical_key"): item for item in model_dispatches}
    completion_ids: list[str] = []
    valid_completion_keys: set[str] = set()
    unknown = False
    violation = False

    for dispatch in model_dispatches:
        if dispatch.get("status") in {"RESERVED", "UNKNOWN"} or dispatch.get("usage_state") == "UNKNOWN":
            unknown = True
        if dispatch.get("usage_state") == "VIOLATION":
            violation = True

    for call in model_calls:
        if call.get("status") in {"RESERVED", "UNKNOWN"}:
            unknown = True
        dispatch = dispatch_by_key.get(call.get("logical_key"))
        ids = _call_completion_ids(call)
        call_usage = _call_usage_totals(call)
        if (
            call.get("status") == "OK" and ids and call_usage is not None
            and isinstance(dispatch, dict) and dispatch.get("status") == "OK"
            and dispatch.get("usage_state") == "KNOWN"
            and isinstance(dispatch.get("usage"), dict)
            and _nonnegative_tokens(dispatch["usage"].get("input_tokens"))
            and _nonnegative_tokens(dispatch["usage"].get("output_tokens"))
            and call_usage["input_tokens"] == dispatch["usage"].get("input_tokens")
            and call_usage["output_tokens"] == dispatch["usage"].get("output_tokens")
        ):
            completion_ids.extend(ids)
            valid_completion_keys.add(str(call.get("logical_key")))

    if unknown:
        provider_outcome = "UNKNOWN"
    elif violation:
        provider_outcome = "KNOWN_INVALID"
    elif valid_completion_keys:
        provider_outcome = "KNOWN_VALID"
    elif model_calls or model_dispatches:
        provider_outcome = "KNOWN_INVALID"
    else:
        provider_outcome = "NOT_SENT"

    has_body = (
        isinstance(answer, dict)
        and isinstance(answer.get("body"), str)
        and bool(answer["body"].strip())
    )
    if has_body and answer.get("answer_kind") == "PROGRAM_LIMIT":
        delivery_kind = "PROGRAM_FAILURE_NOTIFICATION"
    elif not has_body:
        delivery_kind = "NONE"
    elif (
        answer.get("answer_kind") == "CHAT_MODEL"
        and answer.get("answer_run_id") == expected_run_id
        and answer.get("answer_source_message_id") == expected_source_message_id
        and run.get("run_id") == expected_run_id
        and provider_outcome == "KNOWN_VALID"
        and any(
            answer["body"].strip() in _call_answer_texts(call)
            for call in model_calls
            if str(call.get("logical_key")) in valid_completion_keys
        )
    ):
        delivery_kind = "MODEL_ANSWER"
    else:
        delivery_kind = "UNVERIFIED_NONMODEL_ANSWER"

    if provider_outcome == "UNKNOWN":
        outcome_level = "PROVIDER_RESULT_UNKNOWN"
        reason = "A model dispatch or Usage record is unresolved."
    elif delivery_kind == "PROGRAM_FAILURE_NOTIFICATION":
        outcome_level = "PROGRAM_FAILURE_NOTIFICATION"
        reason = "The persisted user delivery is a typed program limit/failure notice."
    elif delivery_kind == "MODEL_ANSWER":
        if run.get("status") == "SUCCEEDED":
            outcome_level = "REAL_PROVIDER_AND_FORMAL_WORKER"
            reason = None
        else:
            outcome_level = "UNVERIFIED_NONMODEL_ANSWER"
            reason = "The persisted model answer is not associated with a successful Run."
    elif delivery_kind == "UNVERIFIED_NONMODEL_ANSWER":
        outcome_level = "UNVERIFIED_NONMODEL_ANSWER"
        reason = "A non-empty delivery lacks the typed model source and matching Provider evidence."
    elif provider_outcome == "KNOWN_VALID":
        outcome_level = "REAL_PROVIDER_COMPLETION_WITHOUT_PERSISTED_ANSWER"
        reason = "A valid Provider completion exists, but no exact-source model answer was persisted."
    else:
        outcome_level = "NO_ANSWER_NO_EXECUTION"
        reason = "No model completion and no persisted user answer were proven."

    return {
        "provider_outcome": provider_outcome,
        "user_delivery_kind": delivery_kind,
        "outcome_level": outcome_level,
        "completion_ids": sorted(set(completion_ids)),
        "reason": reason,
    }


def _audit_case(case: dict[str, Any], provider_before: int, mcp_before: int) -> dict[str, Any]:
    from fastapi.testclient import TestClient
    from opspilot.domain.assistant_experiment import read_budget
    from opspilot.domain.database import connect
    from opspilot.web.app import create_app

    case_id = str(case["case_id"])
    run_id = str(case["run_id"])
    session_id = str(case["session_id"])
    app = create_app(
        db_path=DOMAIN_DB, checkpoint_db_path=CHECKPOINT_DB, start_worker=False,
        credentials={"support-a": SUPPORT_PASSWORD}, expected_origin=API_ORIGIN,
        assistant_experiment_id=EXPERIMENT_ID,
    )
    with TestClient(app) as client:
        headers = _login(client)
        run_response = client.get(f"/api/runs/{run_id}")
        if run_response.status_code != 200:
            raise RuntimeError("FINAL_RUN_READ_FAILED:" + str(run_response.status_code))
        run = run_response.json()
        message_response = client.get(f"/api/sessions/{session_id}/messages", headers=headers)
        if message_response.status_code != 200:
            raise RuntimeError("SESSION_MESSAGES_READ_FAILED:" + str(message_response.status_code))
        messages = message_response.json().get("items", [])
        sources_response = client.get(f"/api/runs/{run_id}/assistant-sources", headers=headers)
        if sources_response.status_code != 200:
            raise RuntimeError("ASSISTANT_SOURCE_READ_FAILED:" + str(sources_response.status_code))
        sources = sources_response.json()
    with connect(DOMAIN_DB) as connection:
        calls = connection.execute(
            "SELECT * FROM assistant_calls WHERE run_id=? ORDER BY created_at,rowid", (run_id,)
        ).fetchall()
        task_row = connection.execute(
            "SELECT task_id FROM task_runs WHERE run_id=?", (run_id,),
        ).fetchone()
        task_id = str(task_row["task_id"]) if task_row and task_row["task_id"] else None
        assistant_row = connection.execute(
            "SELECT core,delivery_attempt_id FROM assistant_runs WHERE run_id=?", (run_id,),
        ).fetchone()
        observations = []
        if task_id:
            observations = [dict(row) for row in connection.execute(
                "SELECT o.*,a.run_id AS attempt_run_id FROM d2_tool_observations o "
                "JOIN d2_attempts a ON a.attempt_id=o.attempt_id AND a.task_id=o.task_id "
                "WHERE o.task_id=? AND a.run_id=? ORDER BY o.created_at,o.observation_id",
                (task_id, run_id),
            ).fetchall()]
        user_rows = [row for row in messages if row.get("role") == "USER" and row.get("message_id") == case.get("message_id")]
        answer_rows = [row for row in messages if row.get("answer_source_message_id") == case.get("message_id")]
        business_writes = {}
        for table in BUSINESS_WRITE_TABLES:
            business_writes[table] = int(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
        mcp_calls = []
        model_calls = []
        dispatches = []
        for row in calls:
            data = dict(row)
            has_error_code = "error_code" in data
            record = {
                "call_id": data["call_id"], "kind": data["kind"], "logical_key": data["logical_key"],
                "status": data["status"], "created_at": data["created_at"],
                "completed_at": data["completed_at"], "observation_id": data["observation_id"],
                "evidence_id": data["evidence_id"],
                "error_code": data.get("error_code"),
                "error_code_state": (
                    "RECORDED" if has_error_code
                    else "UNKNOWN_NOT_IN_ASSISTANT_CALLS_SCHEMA"
                ),
                "request": _decode_json(data["request_json"]),
                "result": _decode_json(data["result_json"]),
                "usage": _decode_json(data["usage_json"]),
            }
            if data["kind"] == "MCP":
                mcp_calls.append(record)
            else:
                model_calls.append(record)
        dispatch_rows = connection.execute(
            "SELECT kind,logical_key,status,usage_state,usage_json,error_code "
            "FROM ar02_live_dispatches WHERE experiment_id=? AND run_id=? "
            "ORDER BY created_at,dispatch_id",
            (EXPERIMENT_ID, run_id),
        ).fetchall()
        for dispatch_row in dispatch_rows:
            dispatch = dict(dispatch_row)
            dispatch["usage"] = _decode_json(dispatch.pop("usage_json"))
            dispatches.append(dispatch)
    if len(user_rows) != 1 or len(answer_rows) > 1:
        raise RuntimeError("USER_MESSAGE_OR_ANSWER_ASSOCIATION_INVALID")
    if sources.get("current") is not True:
        raise RuntimeError("ASSISTANT_SOURCES_NOT_CURRENT:" + str(sources.get("exclusion_reason")))
    if assistant_row is None or assistant_row["core"] != "ASSISTANT_V1":
        raise RuntimeError("FORMAL_ASSISTANT_CORE_MISMATCH")
    if any(item["run_id"] != run_id for item in observations):
        raise RuntimeError("CROSS_RUN_OBSERVATION_ASSOCIATION")
    bad_tools = []
    for call in mcp_calls:
        name = call.get("request", {}).get("name") if isinstance(call.get("request"), dict) else None
        if name not in ALLOWED_TOOLS:
            bad_tools.append(name)
    if bad_tools:
        raise RuntimeError("UNAUTHORIZED_OR_UNREGISTERED_MCP_TOOL:" + ",".join(str(item) for item in bad_tools))
    budget = read_budget(DOMAIN_DB, EXPERIMENT_ID)
    answer_message = answer_rows[-1] if answer_rows else None
    answer = answer_message.get("body") if answer_message else None
    outcome = _classify_case_outcome(
        run=run, answer=answer_message, calls=model_calls, dispatches=dispatches,
        expected_run_id=run_id, expected_source_message_id=str(case.get("message_id")),
    )
    result = {
        **case,
        "run": run,
        "run_failure_reason": (
            run.get("waiting_reason") if run.get("status") in {"FAILED", "BLOCKED"} else None
        ),
        "assistant_core": assistant_row["core"],
        "user_message": user_rows[0],
        "answer_messages": answer_rows,
        "answer": answer,
        "source_validation": sources,
        "model_call_count": len(model_calls),
        "mcp_call_count": len(mcp_calls),
        "model_calls": model_calls,
        "mcp_calls": mcp_calls,
        "campaign_dispatches": dispatches,
        "d2_observations": observations,
        "campaign_budget": budget,
        "provider_count_delta": budget["provider_used"] - provider_before,
        "mcp_count_delta": budget["mcp_used"] - mcp_before,
        "business_write_counts": business_writes,
        **outcome,
    }
    _append_jsonl(EVIDENCE / "TRACE.jsonl", {
        "record_type": "formal_case_result",
        "evidence_level": "FASTAPI_WORKER_ASSISTANT_MCP_DOMAIN_PERSISTED_TRACE",
        "utc_time": _now(), "case_id": case_id,
        "result": result,
    })
    return result


def _run_case(case_id: str, body: str, bound: bool, mode: str, state: _CampaignState) -> dict[str, Any]:
    from fastapi.testclient import TestClient
    from opspilot.domain.assistant_experiment import read_budget
    from opspilot.domain.database import connect
    from opspilot.web.app import create_app

    budget_before = read_budget(DOMAIN_DB, EXPERIMENT_ID)
    accepted = _create_user_run(case_id, body, bound)
    state.case_id = case_id
    state.run_id = str(accepted["run_id"])
    os.environ["OPSPILOT_AR03_MATERIAL_SKILL_MODE"] = mode
    app = create_app(
        db_path=DOMAIN_DB, checkpoint_db_path=CHECKPOINT_DB, start_worker=True,
        credentials={"support-a": SUPPORT_PASSWORD}, expected_origin=API_ORIGIN,
        assistant_model_factory=lambda: _call_model_factory(state),
        assistant_experiment_id=EXPERIMENT_ID,
    )
    started = time.monotonic()
    with TestClient(app) as client:
        headers = _login(client)
        run = _wait_run(client, str(accepted["run_id"]))
    duration = time.monotonic() - started
    with connect(DOMAIN_DB) as connection:
        message = connection.execute(
            "SELECT message_id FROM messages WHERE message_id=? AND session_id=?",
            (accepted["message_id"], accepted["session_id"]),
        ).fetchone()
    if message is None:
        raise RuntimeError("ACCEPTED_USER_MESSAGE_NOT_PERSISTED")
    result = _audit_case({
        **accepted, "case_id": case_id, "run_id": str(accepted["run_id"]),
        "session_id": str(accepted["session_id"]), "message_id": str(accepted["message_id"]),
        "skill_mode": mode,
    }, int(budget_before["provider_used"]), int(budget_before["mcp_used"]))
    result["worker_duration_seconds"] = round(duration, 3)
    result["run_status_observed_before_audit"] = run.get("status")
    _write_json(EVIDENCE / "PROGRESS.json", {
        "experiment_id": EXPERIMENT_ID, "updated_at": _now(),
        "current_case": case_id, "provider_inflight": state.inflight,
        "provider_result_unknown": state.unknown,
        "campaign_budget": read_budget(DOMAIN_DB, EXPERIMENT_ID),
        "completed_cases": len([
            line for line in (EVIDENCE / "TRACE.jsonl").read_text(encoding="utf-8").splitlines()
            if '"record_type":"formal_case_result"' in line
        ]),
    })
    return result


def _campaign_stop_reason(state: _CampaignState) -> str | None:
    from opspilot.domain.assistant_experiment import read_budget
    from opspilot.domain.database import connect

    budget = read_budget(DOMAIN_DB, EXPERIMENT_ID)
    with connect(DOMAIN_DB) as connection:
        dispatches = [dict(row) for row in connection.execute(
            "SELECT kind,status,usage_state,error_code FROM ar02_live_dispatches "
            "WHERE experiment_id=? ORDER BY created_at,dispatch_id", (EXPERIMENT_ID,),
        ).fetchall()]
    if state.unknown or any(
        row["status"] in {"RESERVED", "UNKNOWN"}
        or (row["kind"] == "MODEL" and row["usage_state"] != "KNOWN")
        for row in dispatches
    ):
        return "UNKNOWN_PROVIDER_OR_USAGE_STOP_ALL"
    if any(row["usage_state"] == "VIOLATION" for row in dispatches):
        return "PROVIDER_USAGE_VIOLATION_STOP_ALL"
    if budget["status"] != "OPEN":
        return "CAMPAIGN_BUDGET_CLOSED_STOP_ALL"
    if budget["provider_used"] >= PROVIDER_LIMIT:
        return "PROVIDER_REQUEST_LIMIT_REACHED"
    if budget["mcp_used"] >= MCP_LIMIT:
        return "MCP_TOOL_CALL_LIMIT_REACHED"
    if budget["usd_reserved_micro"] + budget["usd_settled_micro"] >= BUDGET_USD_MICRO:
        return "APPLICATION_BUDGET_REACHED"
    if time.monotonic() - (state.started_monotonic or time.monotonic()) >= CAMPAIGN_WALL_SECONDS:
        return "CAMPAIGN_WALL_CLOCK_LIMIT"
    return None


def _finalize(results: list[dict[str, Any]], state: _CampaignState, stop_reason: str | None) -> None:
    from opspilot.domain.assistant_experiment import read_budget

    budget = read_budget(DOMAIN_DB, EXPERIMENT_ID)
    if stop_reason and state.request_count == 0:
        outcome = "BLOCKED_BEFORE_PROVIDER_SEND"
    elif stop_reason and (state.unknown or "UNKNOWN" in stop_reason or "VIOLATION" in stop_reason):
        outcome = "UNKNOWN_STOPPED"
    elif stop_reason:
        outcome = "PARTIAL_STOPPED"
    elif len(results) == 7:
        outcome = "COMPLETE_CASE_SET_RUN"
    else:
        outcome = "PARTIAL_CASE_SET"
    _write_json(EVIDENCE / "RESULTS.json", {
        "experiment_id": EXPERIMENT_ID, "outcome": outcome,
        "provider_http_requests": state.request_count,
        "mcp_dispatches": budget.get("mcp_used", 0),
        "case_count_expected": 7, "case_count_executed": len(results),
        "scenario_results": results, "stop_reason": stop_reason,
        "business_write_counts": results[-1]["business_write_counts"] if results else {},
        "historical_experiment_records_modified": False,
        "written_at": _now(),
    })
    _write_json(EVIDENCE / "BUDGET_LEDGER.json", {
        "experiment_id": EXPERIMENT_ID, "currency": "USD",
        "limits": {
            "provider_requests": PROVIDER_LIMIT, "mcp_tools_call": MCP_LIMIT,
            "application_budget_usd_micro": BUDGET_USD_MICRO,
            "reservation_usd_micro_per_provider": RESERVATION_USD_MICRO,
            "max_reservation_for_16_requests_usd_micro": PROVIDER_LIMIT * RESERVATION_USD_MICRO,
            "wall_clock_seconds": CAMPAIGN_WALL_SECONDS,
        },
        "actual": budget, "transport_http_attempts": state.request_count,
        "unknown_results_keep_reservation": True,
        "usage_based_settlements_are_estimates_not_provider_invoice": True,
    })
    failures = [
        f"- `{item['case_id']}`: Run `{item['run'].get('status')}`, "
        f"answer persisted={'yes' if item.get('answer') else 'no'}, "
        f"Provider={item['provider_count_delta']}, MCP={item['mcp_count_delta']}."
        for item in results if item["run"].get("status") != "SUCCEEDED" or not item.get("answer")
    ]
    text = [
        "# AR-03-MATERIAL-LIVE-01 failures and stops", "",
        "All original RED/GREEN logs remain unchanged in `runs/`. No request is retried.", "",
        "## Live run observations", "",
    ]
    text.extend(failures or ["- No Worker/answer failure was observed in completed cases."])
    text.extend(["", "## Campaign stop", "", f"- Stop reason: `{stop_reason or 'FROZEN_CASE_SET_FINISHED'}`."])
    (EVIDENCE / "FAILURES.md").write_text("\n".join(text) + "\n", encoding="utf-8")


def _execute_once() -> int:
    from opspilot.config import load_local_environment
    from opspilot.domain.assistant_experiment import initialize_experiment, read_budget

    preflight = _validate_preflight()
    claim = EVIDENCE / "EXECUTION_CLAIM.json"
    fd = os.open(str(claim), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        stream.write(json.dumps({
            "experiment_id": EXPERIMENT_ID, "claimed_at": _now(),
            "branch": preflight["branch"], "head": preflight["head"],
            "base_sha": BASE_SHA, "status": "CLAIMED_ONE_SHOT_NO_RETRY",
            "provider_limit": PROVIDER_LIMIT, "mcp_limit": MCP_LIMIT,
            "application_budget_usd_micro": BUDGET_USD_MICRO,
        }, sort_keys=True) + "\n")
        stream.flush()
        os.fsync(stream.fileno())
    RUNTIME.mkdir(parents=True, exist_ok=False)
    _write_json(EVIDENCE / "PREFLIGHT.json", preflight)

    # This process alone opts in. The key is loaded from the shared ignored .env,
    # is never copied or emitted, and the stdio MCP child strips it in Assistant.
    load_local_environment(ROOT.parent.parent / ".env")
    os.environ["OPSPILOT_ASSISTANT_PROVIDER_ENABLED"] = "1"
    os.environ["OPSPILOT_ASSISTANT_EXPERIMENT_ID"] = EXPERIMENT_ID
    _bootstrap_fresh_campaign_database(DOMAIN_DB)
    initialize_experiment(DOMAIN_DB, EXPERIMENT_ID)
    initial_budget = read_budget(DOMAIN_DB, EXPERIMENT_ID)
    if (
        initial_budget["provider_used"] != 0 or initial_budget["mcp_used"] != 0
        or initial_budget["status"] != "OPEN"
        or initial_budget["usd_reserved_micro"] != 0
        or initial_budget["provider_limit"] != PROVIDER_LIMIT
        or initial_budget["mcp_limit"] != MCP_LIMIT
        or initial_budget["budget_usd_micro"] != BUDGET_USD_MICRO
    ):
        raise RuntimeError("NEW_CAMPAIGN_LEDGER_NOT_EMPTY")

    state = _CampaignState(EVIDENCE / "PROVIDER_HTTP.jsonl", DOMAIN_DB)
    results: list[dict[str, Any]] = []
    stop_reason: str | None = None
    try:
        fixture = _prepare_fixture(DOMAIN_DB)
        inputs = _case_inputs()
        ordered = [
            ("MAT-01-PROTOCOL-EXCERPT", False, "ON"),
            ("MAT-02-USER-MATERIAL-UNBOUND", False, "ON"),
            ("MAT-03-USER-MATERIAL-MALFORMED", False, "ON"),
            ("MAT-04-BOUND-QUEUED", True, "ON"),
            ("MAT-05-BOUND-PROCESSED", True, "ON"),
            ("MAT-06-SKILL-OFF", False, "OFF"),
            ("MAT-06-SKILL-ON", False, "ON"),
        ]
        for case_id, bound, mode in ordered:
            stop_reason = _campaign_stop_reason(state) if results else None
            if stop_reason:
                break
            if case_id == "MAT-05-BOUND-PROCESSED":
                transition = _set_receiver_processed(DOMAIN_DB, str(fixture["event_id"]))
                fixture["receiver_state"] = "PROCESSED"
                fixture["receiver_version"] = transition["after"]["version"]
            from opspilot.domain.assistant_experiment import read_budget as _read
            budget_before = _read(DOMAIN_DB, EXPERIMENT_ID)
            accepted = _create_user_run(case_id, inputs[case_id], bound)
            state.case_id = case_id
            state.run_id = str(accepted["run_id"])
            os.environ["OPSPILOT_AR03_MATERIAL_SKILL_MODE"] = mode
            from fastapi.testclient import TestClient
            from opspilot.web.app import create_app
            app = create_app(
                db_path=DOMAIN_DB, checkpoint_db_path=CHECKPOINT_DB, start_worker=True,
                credentials={"support-a": SUPPORT_PASSWORD}, expected_origin=API_ORIGIN,
                assistant_model_factory=lambda: _call_model_factory(state),
                assistant_experiment_id=EXPERIMENT_ID,
            )
            run_started = time.monotonic()
            with TestClient(app) as client:
                _login(client)
                run = _wait_run(client, state.run_id)
            item = _audit_case({
                **accepted, "case_id": case_id, "run_id": state.run_id,
                "session_id": str(accepted["session_id"]),
                "message_id": str(accepted["message_id"]), "skill_mode": mode,
                "fixture_event_id": fixture["event_id"] if bound else None,
                "fixture_receiver_state": fixture["receiver_state"] if bound else None,
            }, int(budget_before["provider_used"]), int(budget_before["mcp_used"]))
            item["run_status_observed"] = run.get("status")
            item["worker_duration_seconds"] = round(time.monotonic() - run_started, 3)
            results.append(item)
            _write_json(EVIDENCE / "PROGRESS.json", {
                "experiment_id": EXPERIMENT_ID, "updated_at": _now(),
                "provider_http_count": state.request_count,
                "provider_inflight": state.inflight, "provider_result_unknown": state.unknown,
                "completed_case_ids": [row["case_id"] for row in results],
                "budget": read_budget(DOMAIN_DB, EXPERIMENT_ID),
            })
            illegal = any(
                call.get("request", {}).get("name") not in ALLOWED_TOOLS
                for call in item.get("mcp_calls", [])
                if isinstance(call.get("request"), dict)
            )
            if illegal:
                stop_reason = "UNAPPROVED_TOOL_EXECUTION_STOP_ALL"
                break
            stop_reason = _campaign_stop_reason(state)
            if stop_reason:
                break
        if state.inflight:
            stop_reason = "PROVIDER_REQUEST_STILL_IN_FLIGHT_STOP_ALL"
        _finalize(results, state, stop_reason)
        return 0 if not stop_reason else 2
    except BaseException as error:
        stop_reason = "UNKNOWN_STOPPED" if state.inflight or state.unknown else type(error).__name__ + ":" + str(error)[:300]
        _append_jsonl(EVIDENCE / "TRACE.jsonl", {
            "record_type": "campaign_stopped",
            "evidence_level": "RUNNER_OBSERVED",
            "utc_time": _now(), "exception_chain": _error_chain(error),
            "provider_http_requests": state.request_count,
            "provider_inflight": state.inflight,
        })
        if DOMAIN_DB.exists():
            _finalize(results, state, stop_reason)
        else:
            _write_json(EVIDENCE / "RESULTS.json", {
                "experiment_id": EXPERIMENT_ID,
                "outcome": "BLOCKED_BEFORE_PROVIDER_SEND" if state.request_count == 0 else "FAIL_STOPPED",
                "provider_http_requests": state.request_count,
                "stop_reason": stop_reason,
                "partial_results": results,
            })
        return 2
    finally:
        os.environ.pop("OPSPILOT_ASSISTANT_PROVIDER_ENABLED", None)
        os.environ.pop("OPSPILOT_ASSISTANT_EXPERIMENT_ID", None)
        os.environ.pop("OPSPILOT_AR03_MATERIAL_SKILL_MODE", None)


def main() -> int:
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--preflight-only", action="store_true")
    group.add_argument("--execute-once", action="store_true")
    args = parser.parse_args()
    sys.path.insert(0, str(ROOT))
    try:
        if args.preflight_only:
            result = _validate_preflight()
            print(json.dumps(result, ensure_ascii=False, sort_keys=True))
            return 0
        return _execute_once()
    except BaseException as error:
        print(json.dumps({
            "status": "BLOCKED_BEFORE_PROVIDER_SEND",
            "error_type": type(error).__name__, "reason": str(error)[:300],
        }, ensure_ascii=False, sort_keys=True))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
