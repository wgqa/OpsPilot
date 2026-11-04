"""One-shot live runner for the three authorized AR-03 remainder conditions.

The paid path requires a clean frozen checkout, the exact committed user grant,
an exclusive persistent claim, and the request reservation ledger. The free
preflight uses the formal FastAPI/Worker/MCP/Domain path with an explicit
HTTPX MockTransport and a temporary database; it cannot send an external call.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import secrets
import subprocess
import sys
import tempfile
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
PUBLIC_EVIDENCE = ROOT / "docs" / "evidence" / "ar-03" / "material-remainder-live-01"
BASE_RUNNER = ROOT / "docs" / "evidence" / "ar-03" / "material-live-01" / "run_live.py"
CASES_PATH = ROOT / "docs" / "evidence" / "ar-03" / "material-01" / "CASES.json"
RUNTIME = ROOT.parent.parent / ".runtime" / "ar03-material-remainder-live-01-live"
CLAIM = RUNTIME / "claim.json"
DOMAIN_DB = RUNTIME / "domain.sqlite3"
CHECKPOINT_DIR = RUNTIME / "checkpoints"
PRIVATE_RAW = RUNTIME / "raw"
BRANCH = "codex/ar03-material-remainder-01-live"
BASE_SHA = "abd25e20b308df3c95f81c4039295908f399ef71"
MAIN_SHA = "ec8c3582f6d145eec9979c43607302731411ead8"
CASES_BLOB = "faf16fbb857278e98f8afbe179fe327855132967"
EXPERIMENT_ID = "AR-03-MATERIAL-REMAINDER-01"
MODEL = "deepseek-flash"
PROVIDER_LIMIT = 16
MCP_LIMIT: int | None = None
BUDGET_USD_MICRO = 10_500_000
RESERVATION_USD_MICRO = 645_600
CONTEXT_LIMIT = 12_000
CAMPAIGN_WALL_SECONDS = 3_600
CASE_ORDER = (
    "MAT-05-BOUND-PROCESSED", "MAT-06-SKILL-OFF", "MAT-06-SKILL-ON",
)
CASE_MODES = {
    "MAT-05-BOUND-PROCESSED": (True, "ON", "checkpoints/mat-05.sqlite3"),
    "MAT-06-SKILL-OFF": (False, "OFF", "checkpoints/mat-06-off.sqlite3"),
    "MAT-06-SKILL-ON": (False, "ON", "checkpoints/mat-06-on.sqlite3"),
}
AUTH_RECORD = PUBLIC_EVIDENCE / "PAID_AUTHORIZATION.json"
TOKEN_ENV = "OPSPILOT_AR03_MATERIAL_REMAINDER_LIVE_ONE_SHOT_TOKEN"
EXPERIMENT_ENV = "OPSPILOT_ASSISTANT_EXPERIMENT_ID"
PROVIDER_OPT_IN_ENV = "OPSPILOT_ASSISTANT_PROVIDER_ENABLED"
MODEL_KEY_ENV = "OPSPILOT_MODEL_API_KEY"
MODEL_NAME_ENV = "OPSPILOT_MODEL_NAME"
MODEL_BASE_ENV = "OPSPILOT_MODEL_BASE_URL"
SKILL_MODE_ENV = "OPSPILOT_AR03_MATERIAL_SKILL_MODE"
EXPECTED_BLOBS = {
    "PROJECT_NORTH_STAR.md": "1f737712c7a36ceb34433ac09c3fbba3c3305542",
    "AGENTS.md": "32c45506cceeaa8c76a5c56bf8360ff476b58856",
    ".agents/skills/opspilot-slice-review/SKILL.md": "d405c8d413d633824b279202cc1503dab4cf0b03",
}


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _git(*args: str, check: bool = True) -> str:
    result = subprocess.run(
        ["git", *args], cwd=ROOT, capture_output=True, text=True, check=False,
    )
    if check and result.returncode:
        raise RuntimeError("GIT_PREFLIGHT_FAILED:" + " ".join(args))
    return result.stdout.strip()


def _blob(path: str) -> str:
    return _git("rev-parse", f"HEAD:{path}")


def _load_environment() -> None:
    from opspilot.config import load_local_environment

    env_path = ROOT.parent.parent / ".env"
    if not env_path.is_file():
        raise RuntimeError("MODEL_ENVIRONMENT_FILE_NOT_FOUND")
    load_local_environment(env_path)


def _load_base_runner():
    spec = importlib.util.spec_from_file_location(
        "ar03_material_remainder_live_helper", BASE_RUNNER,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("BASE_RUNNER_IMPORT_FAILED")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.EVIDENCE = PRIVATE_RAW
    module.RUNTIME = RUNTIME
    module.DOMAIN_DB = DOMAIN_DB
    module.CHECKPOINT_DB = CHECKPOINT_DIR / "mat-05.sqlite3"
    module.BRANCH = BRANCH
    module.BASE_SHA = BASE_SHA
    module.EXPERIMENT_ID = EXPERIMENT_ID
    module.MODEL = MODEL
    module.PROVIDER_LIMIT = PROVIDER_LIMIT
    module.MCP_LIMIT = MCP_LIMIT
    module.BUDGET_USD_MICRO = BUDGET_USD_MICRO
    module.RESERVATION_USD_MICRO = RESERVATION_USD_MICRO
    module.CONTEXT_LIMIT = CONTEXT_LIMIT
    module.CAMPAIGN_WALL_SECONDS = CAMPAIGN_WALL_SECONDS
    return module


def _expected_authorization() -> dict[str, Any]:
    from opspilot.assistant import _material_remainder_live_expected_authorization

    return _material_remainder_live_expected_authorization()


def _validate_preflight(*, require_clean: bool = True) -> dict[str, Any]:
    """Validate live prerequisites without sending Provider traffic or claiming."""
    _load_environment()
    branch = _git("branch", "--show-current")
    head = _git("rev-parse", "HEAD")
    if branch != BRANCH:
        raise RuntimeError("MATERIAL_REMAINDER_BRANCH_MISMATCH")
    ancestry = subprocess.run(
        ["git", "merge-base", "--is-ancestor", BASE_SHA, "HEAD"],
        cwd=ROOT, capture_output=True, check=False,
    )
    if ancestry.returncode != 0:
        raise RuntimeError("AUTHORIZED_BASE_NOT_IN_HISTORY")
    for path, expected in EXPECTED_BLOBS.items():
        if _blob(path) != expected:
            raise RuntimeError("FROZEN_PROJECT_RULE_BLOB_MISMATCH:" + path)
    if _blob("docs/evidence/ar-03/material-01/CASES.json") != CASES_BLOB:
        raise RuntimeError("FROZEN_MAT_CASES_BLOB_MISMATCH")

    if require_clean:
        if _git("status", "--porcelain=v1"):
            raise RuntimeError("WORKTREE_NOT_CLEAN_BEFORE_LIVE")
    remote = subprocess.run(
        ["git", "ls-remote", "origin", "refs/heads/main"],
        cwd=ROOT, capture_output=True, text=True, check=False,
    )
    if remote.returncode != 0:
        raise RuntimeError("REMOTE_MAIN_UNVERIFIED")
    remote_main = remote.stdout.split()[0] if remote.stdout.split() else ""
    if remote_main != MAIN_SHA:
        raise RuntimeError("REMOTE_MAIN_CHANGED_FROM_FREEZE")

    from opspilot.config import MODEL_API_KEY, MODEL_BASE_URL, MODEL_NAME
    key = os.environ.get(MODEL_API_KEY, "").strip()
    model = os.environ.get(MODEL_NAME, "").strip()
    base_url = os.environ.get(MODEL_BASE_URL, "").strip()
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
    if os.environ.get(PROVIDER_OPT_IN_ENV, "").strip() not in ("", "0", "false", "False"):
        raise RuntimeError("PROVIDER_OPT_IN_PRESET_BEFORE_CLAIM")
    if os.environ.get(EXPERIMENT_ENV, "").strip() or os.environ.get(TOKEN_ENV, ""):
        raise RuntimeError("EXPERIMENT_ID_OR_CLAIM_TOKEN_PRESET")

    authorization = json.loads(AUTH_RECORD.read_text(encoding="utf-8"))
    if type(authorization) is not dict or authorization != _expected_authorization():
        raise RuntimeError("PAID_AUTHORIZATION_RECORD_MISMATCH")

    from opspilot.domain.assistant import run_limits_for_experiment
    from opspilot.domain.assistant_experiment import (
        AR03_MATERIAL_REMAINDER_MCP_LIMIT, BUDGET_USD_MICRO as DOMAIN_BUDGET,
        MAX_PROVIDER_RESERVATION_USD_MICRO, PRICE_VERSION,
        PROVIDER_LIMIT as DOMAIN_PROVIDER_LIMIT, _limits_for_experiment,
    )
    from opspilot.domain.context_engineering import context_budget_for_model

    context = context_budget_for_model(MODEL)
    if int(context["input_budget_tokens"]) != CONTEXT_LIMIT:
        raise RuntimeError("CONTEXT_BUDGET_MISMATCH")
    if (
        DOMAIN_PROVIDER_LIMIT != PROVIDER_LIMIT or MCP_LIMIT is not None
        or AR03_MATERIAL_REMAINDER_MCP_LIMIT is not None
        or _limits_for_experiment(EXPERIMENT_ID) != (PROVIDER_LIMIT, None)
        or run_limits_for_experiment(EXPERIMENT_ID) != (PROVIDER_LIMIT, None)
        or DOMAIN_BUDGET != BUDGET_USD_MICRO
        or MAX_PROVIDER_RESERVATION_USD_MICRO != RESERVATION_USD_MICRO
        or PRICE_VERSION != authorization["price_version"]
        or PROVIDER_LIMIT * RESERVATION_USD_MICRO > BUDGET_USD_MICRO
    ):
        raise RuntimeError("PERSISTED_CAMPAIGN_BUDGET_OR_PRICE_MISMATCH")
    if RUNTIME.exists() or CLAIM.exists() or DOMAIN_DB.exists() or CHECKPOINT_DIR.exists():
        raise RuntimeError("LIVE_RUNTIME_OR_ONE_SHOT_ALREADY_EXISTS")
    for name in ("RESULTS.json", "TRACE.jsonl", "PROVIDER_HTTP.jsonl", "BUDGET_LEDGER.json", "EXECUTION_CLAIM.json"):
        if (PUBLIC_EVIDENCE / name).exists():
            raise RuntimeError("LIVE_EVIDENCE_ALREADY_EXISTS:" + name)

    return {
        "status": "PREFLIGHT_READY",
        "experiment_id": EXPERIMENT_ID,
        "branch": branch,
        "head": head,
        "base_sha": BASE_SHA,
        "remote_main": remote_main,
        "project_blobs": EXPECTED_BLOBS,
        "frozen_cases_blob": CASES_BLOB,
        "authorization_record_sha256": hashlib.sha256(AUTH_RECORD.read_bytes()).hexdigest(),
        "provider": "DeepSeek",
        "model": MODEL,
        "base_url": base_url,
        "credential_present": True,
        "provider_opt_in_before_claim": False,
        "one_shot_claim_present": False,
        "request_parameters": {
            "thinking": {"type": "disabled"}, "max_tokens": 2048,
            "tool_choice": "auto when tools are supplied", "parallel_tool_calls": False,
            "stream": False, "provider_timeout_seconds": 30,
            "sdk_retries": 0, "http_transport_retries": 0,
            "provider_concurrency": 1,
        },
        "limits": {
            "provider": PROVIDER_LIMIT, "mcp_count_limit": None,
            "application_budget_usd_micro": BUDGET_USD_MICRO,
            "reserve_usd_micro_per_provider": RESERVATION_USD_MICRO,
            "max_reserved_usd_micro": PROVIDER_LIMIT * RESERVATION_USD_MICRO,
            "price_version": PRICE_VERSION,
            "input_context_tokens": CONTEXT_LIMIT,
            "assistant_run_seconds": 60, "task_active_ms": 300_000,
            "mcp_handler_seconds": 12, "recursion_limit": 36,
            "campaign_wall_clock_seconds": CAMPAIGN_WALL_SECONDS,
        },
        "cases": list(CASE_ORDER),
        "domain_db": str(DOMAIN_DB),
        "checkpoint_dir": str(CHECKPOINT_DIR),
        "raw_evidence_dir": str(PRIVATE_RAW),
        "provider_requests_before_execution": 0,
        "business_writes_allowed": False,
    }


def _mock_chat_openai_factory(helper, state, handler, clients):
    import httpx
    from langchain_openai import ChatOpenAI

    async_transport = helper._RecordingAsyncTransport(
        state, inner=httpx.MockTransport(handler),
    )
    async_client = httpx.AsyncClient(
        timeout=httpx.Timeout(30), trust_env=False, follow_redirects=False,
        transport=async_transport,
    )
    sync_client = httpx.Client(
        timeout=httpx.Timeout(30), trust_env=False, follow_redirects=False,
        transport=httpx.MockTransport(
            lambda request: (_ for _ in ()).throw(AssertionError("offline preflight sync path used"))
        ),
    )
    clients.append((async_client, sync_client))
    return ChatOpenAI(
        model=MODEL, api_key="offline-mock-only", base_url="https://api.deepseek.com/v1",
        temperature=0, timeout=30, max_retries=0, stream_usage=True,
        include_response_headers=True, http_async_client=async_client,
        http_client=sync_client, http_socket_options=(),
        extra_body={"max_tokens": 2048, "thinking": {"type": "disabled"}},
    )


def _offline_mock_preflight() -> dict[str, Any]:
    """Run one bounded formal Worker case with no external network transport."""
    import httpx
    from fastapi.testclient import TestClient
    from opspilot.domain.assistant_experiment import initialize_experiment, read_budget
    from opspilot.domain.database import connect
    from opspilot.web.app import create_app

    runtime_root = ROOT.parent.parent / ".runtime"
    runtime_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="ar03-material-remainder-preflight-", dir=runtime_root) as temp:
        temp_root = Path(temp)
        helper = _load_base_runner()
        helper.RUNTIME = temp_root
        helper.DOMAIN_DB = temp_root / "domain.sqlite3"
        helper.CHECKPOINT_DB = temp_root / "checkpoints" / "mat-05.sqlite3"
        helper.EVIDENCE = temp_root / "raw"
        helper._bootstrap_fresh_campaign_database(helper.DOMAIN_DB)
        initialize_experiment(helper.DOMAIN_DB, EXPERIMENT_ID)
        fixture = helper._prepare_fixture(helper.DOMAIN_DB)
        transition = helper._set_receiver_processed(helper.DOMAIN_DB, str(fixture["event_id"]))

        case_id = "MAT-05-BOUND-PROCESSED"
        inputs = helper._case_inputs()
        if inputs[case_id] != inputs["MAT-04-BOUND-QUEUED"]:
            raise RuntimeError("MAT05_FROZEN_INPUT_MISMATCH")
        accepted = helper._create_user_run(case_id, inputs[case_id], bound=True)
        state = helper._CampaignState(temp_root / "raw" / "PROVIDER_HTTP.jsonl", helper.DOMAIN_DB)
        state.case_id = case_id
        state.run_id = str(accepted["run_id"])
        requests: list[dict[str, Any]] = []
        responses: list[str] = []

        def completion_body(request, number: int) -> dict[str, Any]:
            if number in {1, 2}:
                tool_name = (
                    "get_callback_delivery" if number == 1
                    else "get_receiver_processing"
                )
                tool_id = "offline-delivery" if number == 1 else "offline-receiver"
                reason = (
                    "Verify the bound order's current delivery" if number == 1
                    else "Verify same-Event receiver processing"
                )
                message = {
                    "role": "assistant", "content": None,
                    "tool_calls": [
                        {"id": tool_id, "type": "function", "function": {
                            "name": tool_name,
                            "arguments": json.dumps({"reason": reason}),
                        }},
                    ],
                }
                finish_reason = "tool_calls"
                completion_id = "offline-remainder-preflight-tools"
            else:
                message = {
                    "role": "assistant",
                    "content": "离线预检模拟答复：此合成内容不是实际模型结论。",
                }
                finish_reason = "stop"
                completion_id = "offline-remainder-preflight-answer"
            return {
                "id": completion_id,
                "object": "chat.completion",
                "created": 1793740000,
                "model": MODEL,
                "choices": [{"index": 0, "message": message, "finish_reason": finish_reason}],
                "usage": {"prompt_tokens": 90, "completion_tokens": 22, "total_tokens": 112},
            }

        def handler(request):
            body = json.loads(request.content.decode("utf-8"))
            requests.append({"url": str(request.url), "method": request.method, "body": body})
            number = len(requests)
            if number > 3:
                raise AssertionError("offline preflight attempted unexpected fourth Provider request")
            responses.append({
                1: "offline-remainder-preflight-delivery-tool",
                2: "offline-remainder-preflight-receiver-tool",
                3: "offline-remainder-preflight-answer",
            }[number])
            return httpx.Response(200, json=completion_body(request, number), request=request)

        clients = []
        def factory():
            return _mock_chat_openai_factory(helper, state, handler, clients)

        # Mark the resulting audit explicitly as synthetic. It still exercises
        # the production serializer, persistent reservation, Worker, MCP and Domain.
        classify = helper._classify_case_outcome
        def classify_mock(**kwargs):
            outcome = classify(**kwargs)
            outcome["provider_outcome"] = "MOCKTRANSPORT_SYNTHETIC_USAGE_KNOWN"
            outcome["outcome_level"] = "DETERMINISTIC_MOCKTRANSPORT_NOT_REAL_PROVIDER"
            return outcome
        helper._classify_case_outcome = classify_mock

        app = create_app(
            db_path=helper.DOMAIN_DB, checkpoint_db_path=helper.CHECKPOINT_DB,
            start_worker=True, credentials={"support-a": helper.SUPPORT_PASSWORD},
            expected_origin=helper.API_ORIGIN, assistant_model_factory=factory,
            assistant_experiment_id=EXPERIMENT_ID,
        )
        try:
            with TestClient(app) as client:
                headers = helper._login(client)
                run = helper._wait_run(client, str(accepted["run_id"]), seconds=90)
            audited = helper._audit_case({
                **accepted,
                "case_id": case_id,
                "run_id": str(accepted["run_id"]),
                "session_id": str(accepted["session_id"]),
                "message_id": str(accepted["message_id"]),
                "skill_mode": "ON",
                "fixture_event_id": fixture["event_id"],
                "fixture_receiver_state": "PROCESSED",
            }, 0, 0)
        finally:
            for async_client, sync_client in clients:
                try:
                    import asyncio
                    asyncio.run(async_client.aclose())
                except Exception:
                    pass
                sync_client.close()

        budget = read_budget(helper.DOMAIN_DB, EXPERIMENT_ID)
        if run.get("status") != "SUCCEEDED" or not audited.get("answer"):
            raise RuntimeError("OFFLINE_FORMAL_WORKER_CASE_INCOMPLETE")
        if (
            len(requests) != 3 or budget["provider_used"] != 3 or budget["mcp_used"] != 2
            or state.unknown or budget["mcp_limit"] is not None
        ):
            raise RuntimeError("OFFLINE_MOCK_BUDGET_OR_USAGE_MISMATCH")
        tool_names = {
            item["function"]["name"]
            for item in (requests[0]["body"].get("tools") or [])
        }
        if not {"get_callback_delivery", "get_receiver_processing"}.issubset(tool_names):
            raise RuntimeError("OFFLINE_TOOL_SCHEMA_MISSING")
        mcp_calls = audited.get("mcp_calls", [])
        if (
            [call.get("request", {}).get("name") for call in mcp_calls]
            != ["get_callback_delivery", "get_receiver_processing"]
            or any(call.get("status") != "OK" for call in mcp_calls)
        ):
            raise RuntimeError("OFFLINE_MCP_OBSERVATION_SEQUENCE_OR_STATUS_MISMATCH")
        serialized_mcp_results = [
            json.dumps(call.get("result"), ensure_ascii=False, sort_keys=True)
            for call in mcp_calls
        ]
        if (
            any(str(fixture["event_id"]) not in result for result in serialized_mcp_results)
            or "ACKNOWLEDGED" not in serialized_mcp_results[0]
            or "202" not in serialized_mcp_results[0]
            or "PROCESSED" not in serialized_mcp_results[1]
        ):
            raise RuntimeError("OFFLINE_MCP_FACTS_NOT_SAME_EVENT_OR_EXPECTED_STATE")
        tool_messages_after_first = [
            message for message in requests[1]["body"].get("messages", [])
            if message.get("role") == "tool"
        ]
        tool_messages_after_second = [
            message for message in requests[2]["body"].get("messages", [])
            if message.get("role") == "tool"
        ]
        if len(tool_messages_after_first) != 1 or len(tool_messages_after_second) != 2:
            raise RuntimeError("OFFLINE_NEXT_MODEL_DECISION_DID_NOT_RECEIVE_PRIOR_OBSERVATIONS")
        for item in requests:
            body = item["body"]
            if (
                item["url"] != "https://api.deepseek.com/v1/chat/completions"
                or item["method"] != "POST" or body.get("model") != MODEL
                or body.get("max_tokens") != 2048 or body.get("thinking") != {"type": "disabled"}
                or body.get("stream") is not False
                or (body.get("tools") and body.get("tool_choice") != "auto")
                or (body.get("tools") and body.get("parallel_tool_calls") is not False)
                or "max_completion_tokens" in body
            ):
                raise RuntimeError("OFFLINE_SERIALIZED_REQUEST_CONTRACT_MISMATCH")
        for table in helper.BUSINESS_WRITE_TABLES:
            if audited["business_write_counts"].get(table, 0) != 0:
                raise RuntimeError("OFFLINE_PREFLIGHT_BUSINESS_WRITE_DETECTED:" + table)
        if not transition["same_event_id"] or transition["after"]["status"] != "PROCESSED":
            raise RuntimeError("OFFLINE_PROCESSED_FIXTURE_ASSOCIATION_INVALID")
        if not audited["source_validation"].get("current"):
            raise RuntimeError("OFFLINE_SOURCE_CURRENTNESS_FAILED")

        return {
            "status": "OFFLINE_PREFLIGHT_PASSED",
            "evidence_level": "DETERMINISTIC_FIXTURE_MODEL_WITH_HTTPX_MOCKTRANSPORT_AND_REAL_LOCAL_MCP_DOMAIN",
            "experiment_id": EXPERIMENT_ID,
            "case_id": case_id,
            "run_status": run.get("status"),
            "persisted_answer_kind": audited.get("answer_messages", [{}])[-1].get("answer_kind"),
            "provider_http_requests": 3,
            "external_provider_requests": 0,
            "mock_completion_ids": responses,
            "mock_usage": {"input_tokens": 270, "output_tokens": 66, "total_tokens": 336},
            "mcp_dispatches": budget["mcp_used"],
            "mcp_limit": budget["mcp_limit"],
            "mcp_observation_names": [call["request"]["name"] for call in mcp_calls],
            "mcp_observation_results": [
                call["result"] for call in mcp_calls
            ],
            "model_redecision_after_observations": True,
            "event_id": fixture["event_id"],
            "receiver_status": transition["after"]["status"],
            "delivery_status": transition["delivery"]["status"],
            "delivery_http_status": transition["delivery"]["receiver_http_status"],
            "source_current": audited["source_validation"].get("current"),
            "business_write_rows": audited["business_write_counts"],
            "paid_claim_consumed": False,
            "final_runtime_created": False,
        }


def _consume_one_shot_claim(preflight: dict[str, Any]) -> str:
    """Atomically consume the user's sole Campaign claim; never overwrite it."""
    from opspilot.assistant import (
        MATERIAL_REMAINDER_LIVE_AUTHORIZATION_ID,
        MATERIAL_REMAINDER_LIVE_TOKEN_ENV,
        _material_remainder_live_expected_claim,
    )

    if preflight.get("status") != "PREFLIGHT_READY":
        raise RuntimeError("PAID_CLAIM_REQUIRES_READY_PREFLIGHT")
    branch = _git("branch", "--show-current")
    head = _git("rev-parse", "HEAD")
    if (
        branch != BRANCH or preflight.get("branch") != BRANCH
        or preflight.get("head") != head
        or preflight.get("base_sha") != BASE_SHA
        or preflight.get("frozen_cases_blob") != CASES_BLOB
        or preflight.get("remote_main") != MAIN_SHA
        or _git("status", "--porcelain=v1")
    ):
        raise RuntimeError("PAID_CLAIM_HEAD_CHANGED_AFTER_PREFLIGHT")
    if RUNTIME.exists() or CLAIM.exists():
        raise RuntimeError("ONE_SHOT_ALREADY_CONSUMED_OR_RUNTIME_EXISTS")
    token = secrets.token_urlsafe(48)
    auth_bytes = AUTH_RECORD.read_bytes()
    authorization = json.loads(auth_bytes.decode("utf-8"))
    auth_digest = hashlib.sha256(auth_bytes).hexdigest()
    if (
        authorization != _expected_authorization()
        or preflight.get("authorization_record_sha256") != auth_digest
    ):
        raise RuntimeError("PAID_AUTHORIZATION_CHANGED_AFTER_PREFLIGHT")
    claim = _material_remainder_live_expected_claim(
        auth_digest,
        branch=BRANCH,
        head=preflight["head"],
    )
    claim.update({
        "claimed_at": datetime.now(timezone.utc).isoformat(),
        "token_sha256": hashlib.sha256(token.encode("utf-8")).hexdigest(),
    })
    RUNTIME.mkdir(parents=True, exist_ok=False)
    fd = os.open(CLAIM, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(json.dumps(claim, sort_keys=True, separators=(",", ":")) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        # The unique runtime remains present, so the attempt cannot be reset.
        raise
    os.environ[MATERIAL_REMAINDER_LIVE_TOKEN_ENV] = token
    os.environ[PROVIDER_OPT_IN_ENV] = "1"
    os.environ[EXPERIMENT_ENV] = EXPERIMENT_ID
    return token


def _campaign_stop_reason(helper, state) -> str | None:
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
    if budget["usd_reserved_micro"] + budget["usd_settled_micro"] >= BUDGET_USD_MICRO:
        return "APPLICATION_BUDGET_REACHED"
    if state.started_monotonic is not None and time.monotonic() - state.started_monotonic >= CAMPAIGN_WALL_SECONDS:
        return "CAMPAIGN_WALL_CLOCK_LIMIT"
    return None


def _finalize_private(helper, results: list[dict[str, Any]], state, stop_reason: str | None) -> None:
    from opspilot.domain.assistant_experiment import read_budget

    budget = read_budget(DOMAIN_DB, EXPERIMENT_ID)
    if stop_reason and state.request_count == 0:
        outcome = "BLOCKED_BEFORE_PROVIDER_SEND"
    elif stop_reason and (state.unknown or "UNKNOWN" in stop_reason or "VIOLATION" in stop_reason):
        outcome = "UNKNOWN_STOPPED"
    elif stop_reason:
        outcome = "PARTIAL_STOPPED"
    elif len(results) == len(CASE_ORDER):
        outcome = "COMPLETE_CASE_SET_RUN"
    else:
        outcome = "PARTIAL_CASE_SET"
    helper._write_json(PRIVATE_RAW / "RESULTS.json", {
        "experiment_id": EXPERIMENT_ID, "outcome": outcome,
        "provider_http_requests": state.request_count,
        "mcp_dispatches": budget.get("mcp_used", 0),
        "case_count_expected": len(CASE_ORDER), "case_count_executed": len(results),
        "scenario_results": results, "stop_reason": stop_reason,
        "business_write_counts": results[-1]["business_write_counts"] if results else {},
        "written_at": datetime.now(timezone.utc).isoformat(),
        "historical_experiment_records_modified": False,
    })
    helper._write_json(PRIVATE_RAW / "BUDGET_LEDGER.json", {
        "experiment_id": EXPERIMENT_ID, "currency": "USD",
        "limits": {
            "provider_requests": PROVIDER_LIMIT, "mcp_tools_call_count_limit": None,
            "application_budget_usd_micro": BUDGET_USD_MICRO,
            "reservation_usd_micro_per_provider": RESERVATION_USD_MICRO,
            "maximum_reservations_usd_micro": PROVIDER_LIMIT * RESERVATION_USD_MICRO,
            "wall_clock_seconds": CAMPAIGN_WALL_SECONDS,
        },
        "actual": budget,
        "unknown_results_keep_reservation": True,
        "usage_based_settlements_are_estimates_not_provider_invoice": True,
    })
    failures = [
        f"- `{item.get('case_id')}`: run={item.get('run', {}).get('status')}, "
        f"provider={item.get('provider_count_delta')}, MCP={item.get('mcp_count_delta')}, "
        f"answer_persisted={'yes' if item.get('answer') else 'no'}."
        for item in results
        if item.get("run", {}).get("status") != "SUCCEEDED" or not item.get("answer")
    ]
    helper._write_json(PRIVATE_RAW / "FAILURES.json", {
        "case_failures": failures,
        "campaign_stop_reason": stop_reason,
        "no_retry": True,
    })


def _execute_once(preflight: dict[str, Any]) -> dict[str, Any]:
    from opspilot.domain.assistant_experiment import initialize_experiment, read_budget

    _consume_one_shot_claim(preflight)
    helper = None
    try:
        helper = _load_base_runner()
        helper._bootstrap_fresh_campaign_database(DOMAIN_DB)
        initialize_experiment(DOMAIN_DB, EXPERIMENT_ID)
        initial_budget = read_budget(DOMAIN_DB, EXPERIMENT_ID)
        if (
            initial_budget["provider_used"] != 0 or initial_budget["mcp_used"] != 0
            or initial_budget["status"] != "OPEN"
            or initial_budget["usd_reserved_micro"] != 0
            or initial_budget["mcp_limit"] is not None
            or initial_budget["provider_limit"] != PROVIDER_LIMIT
            or initial_budget["budget_usd_micro"] != BUDGET_USD_MICRO
        ):
            raise RuntimeError("NEW_CAMPAIGN_LEDGER_NOT_EMPTY_OR_MISMATCHED")
        fixture = helper._prepare_fixture(DOMAIN_DB)
        processed = helper._set_receiver_processed(DOMAIN_DB, str(fixture["event_id"]))
        PRIVATE_RAW.mkdir(parents=True, exist_ok=True)
        CHECKPOINT_DIR.mkdir(parents=True, exist_ok=False)
        state = helper._CampaignState(PRIVATE_RAW / "PROVIDER_HTTP.jsonl", DOMAIN_DB)
        state.started_monotonic = time.monotonic()
        results: list[dict[str, Any]] = []
        stop_reason: str | None = None
        for case_id in CASE_ORDER:
            stop_reason = _campaign_stop_reason(helper, state) if results else None
            if stop_reason:
                break
            bound, mode, checkpoint_relative = CASE_MODES[case_id]
            helper.CHECKPOINT_DB = RUNTIME / checkpoint_relative
            if case_id == "MAT-05-BOUND-PROCESSED":
                if not processed["same_event_id"] or processed["after"]["status"] != "PROCESSED":
                    raise RuntimeError("MAT05_CURRENT_FIXTURE_STATE_INVALID")
            inputs = helper._case_inputs()
            if case_id == "MAT-05-BOUND-PROCESSED" and inputs[case_id] != inputs["MAT-04-BOUND-QUEUED"]:
                raise RuntimeError("MAT05_FROZEN_INPUT_MISMATCH")
            before = read_budget(DOMAIN_DB, EXPERIMENT_ID)
            item = helper._run_case(case_id, inputs[case_id], bound, mode, state)
            results.append(item)
            provider_unknown = state.unknown or item.get("outcome_level") in {
                "PROVIDER_RESULT_UNKNOWN", "UNKNOWN_STOPPED",
            }
            if provider_unknown:
                stop_reason = "UNKNOWN_PROVIDER_OR_USAGE_STOP_ALL"
                break
            if item.get("source_validation", {}).get("current") is not True:
                stop_reason = "SOURCE_CURRENTNESS_ANOMALY_STOP_ALL"
                break
            if item.get("business_write_counts") and any(item["business_write_counts"].values()):
                stop_reason = "UNAUTHORIZED_BUSINESS_WRITE_STOP_ALL"
                break
            if any(
                call.get("request", {}).get("name") not in helper.ALLOWED_TOOLS
                for call in item.get("mcp_calls", [])
                if isinstance(call.get("request"), dict)
            ):
                stop_reason = "UNAPPROVED_TOOL_EXECUTION_STOP_ALL"
                break
            budget_after = read_budget(DOMAIN_DB, EXPERIMENT_ID)
            if budget_after["provider_used"] - before["provider_used"] > PROVIDER_LIMIT:
                stop_reason = "PROVIDER_REQUEST_LIMIT_REACHED"
                break
            stop_reason = _campaign_stop_reason(helper, state)
            if stop_reason:
                break
        if state.inflight:
            stop_reason = "PROVIDER_REQUEST_STILL_IN_FLIGHT_STOP_ALL"
        _finalize_private(helper, results, state, stop_reason)
        return {
            "outcome": "UNKNOWN_STOPPED" if state.unknown else (
                "PARTIAL_STOPPED" if stop_reason else "COMPLETE_CASE_SET_RUN"
            ),
            "stop_reason": stop_reason,
            "cases_executed": [item.get("case_id") for item in results],
            "provider_requests": state.request_count,
            "campaign_budget": read_budget(DOMAIN_DB, EXPERIMENT_ID),
        }
    except BaseException as error:
        PRIVATE_RAW.mkdir(parents=True, exist_ok=True)
        stop_record = {
            "record_type": "campaign_stopped",
            "evidence_level": "FORMAL_RUNNER_OBSERVED",
            "occurred_at": datetime.now(timezone.utc).isoformat(),
            "exception_type": type(error).__name__,
            "message": str(error)[:300],
            "claim_consumed": True,
            "retry_allowed": False,
        }
        if helper is not None:
            helper._append_jsonl(PRIVATE_RAW / "TRACE.jsonl", stop_record)
        else:
            with (PRIVATE_RAW / "TRACE.jsonl").open("a", encoding="utf-8") as stream:
                stream.write(_json(stop_record) + "\n")
        raise
    finally:
        # The consumed claim stays immutable. Only process-local opt-in material
        # is cleared; no historical or current ledger row is released.
        os.environ.pop(TOKEN_ENV, None)
        os.environ.pop(PROVIDER_OPT_IN_ENV, None)
        os.environ.pop(EXPERIMENT_ENV, None)
        os.environ.pop(SKILL_MODE_ENV, None)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--preflight-only", action="store_true")
    args = parser.parse_args(argv)
    try:
        preflight = _validate_preflight(require_clean=True)
        offline = _offline_mock_preflight()
        preflight["offline_mock_preflight"] = offline
        preflight["paid_claim_consumed"] = False
        preflight["external_provider_requests"] = 0
        if args.preflight_only:
            print(json.dumps(preflight, ensure_ascii=False, sort_keys=True, indent=2))
            return 0
        outcome = _execute_once(preflight)
        print(json.dumps({"status": "LIVE_CAMPAIGN_FINISHED", **outcome}, ensure_ascii=False, sort_keys=True, indent=2))
        return 0
    except BaseException as error:
        payload = {
            "status": "BLOCKED_BEFORE_PROVIDER_SEND" if not CLAIM.exists() else "STOPPED_AFTER_CLAIM",
            "error_type": type(error).__name__,
            "error": str(error)[:400],
            "claim_exists": CLAIM.exists(),
            "retry_allowed": False if CLAIM.exists() else "not_consumed",
        }
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
