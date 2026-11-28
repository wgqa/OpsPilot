"""Bounded ABC live runner and offline MockTransport harness.

This task-local runner reuses the accepted Setup-HF01 Domain seeding and normal
Assistant Runtime Grant path. It has no tool dispatcher. Live sends require an
explicit --live invocation after the complete mock suite and a fresh zero-cost
configuration/Grant preflight.
"""
from __future__ import annotations

import argparse
import asyncio
import gzip
import hashlib
import json
import os
import shutil
import sys
import tempfile
import threading
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import httpx

# A script launched from inside docs/evidence has that directory as sys.path[0].
# Add only this checkout root so the existing OpsPilot imports resolve in the
# same worktree whose files this task freezes.
_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from opspilot.config import ROOT, load_local_environment


EVIDENCE_DIR = Path(__file__).resolve().parent
SETUP_DIR = ROOT / "docs/evidence/r2-ar04-live-eval-setup-hf01"
PHASE_A_DIR = ROOT / "docs/evidence/r2-ar04-long-context-journey-01"
BASE_SHA = "e8ddb1cae60dc2782d0d3581856d1aaa3ea35775"
TASK = "ABC-LIVE-ENV-UNBLOCK-01"
MODEL = "deepseek-flash"
ENDPOINT = "https://api.deepseek.com"
MODEL_VERSION = "DeepSeek-V4.1-Flash-1017"
PRICE_VERSION = "deepseek-v4.1-flash-1017-peak-2026-11-15"
MAX_INPUT_TOKENS = 12_000
MAX_OUTPUT_TOKENS = 512
REQUEST_LIMIT = 21
HARD_CAP_USD_MICRO = 150_000
INPUT_RATE_MICRO_PER_MILLION = 300_000
OUTPUT_RATE_MICRO_PER_MILLION = 1_200_000
REQUEST_RESERVE_USD_MICRO = (
    MAX_INPUT_TOKENS * INPUT_RATE_MICRO_PER_MILLION
    + MAX_OUTPUT_TOKENS * OUTPUT_RATE_MICRO_PER_MILLION
    + 999_999
) // 1_000_000
QUESTION_IDS = ("Q02", "Q03", "Q06")
GROUPS = ("A", "B", "C")
STRATEGIES = {"A": "HYBRID", "B": "ROLLING_SUMMARY", "C": "RECENT_WINDOW"}
REQUIRED_ENV = (
    "OPSPILOT_MODEL_API_KEY",
    "OPSPILOT_MODEL_NAME",
    "OPSPILOT_MODEL_BASE_URL",
    "OPSPILOT_MODEL_CONFIG_VERSION",
    "OPSPILOT_MODEL_PRICE_VERSION",
    "OPSPILOT_ASSISTANT_SERVICE_IDENTITY",
)
NON_SECRET_DEFAULTS = {
    "OPSPILOT_MODEL_NAME": MODEL,
    "OPSPILOT_MODEL_BASE_URL": ENDPOINT,
    "OPSPILOT_MODEL_CONFIG_VERSION": "abc-live-env-unblock-01-model-v1",
    "OPSPILOT_MODEL_PRICE_VERSION": PRICE_VERSION,
    "OPSPILOT_ASSISTANT_SERVICE_IDENTITY": "opspilot-isolated-abc-live-eval-01",
}
PHASE_INPUT_SHA256 = {
    "QUESTIONS.json": "ea3d6554eafa433d1617dc5a5ba9f140471f3cb95f8ae10bcd25b807a4e7afe2",
    "RESULTS.json": "4b04f3d574028099f13748091d4d421c7654b15bed4d25be13b40c413b8699c4",
    "HISTORY_SNAPSHOT.json": "356512f611b046a04e33506a0fb1a88c6a08af93517b2134125dd6771b282c16",
    "MODEL_REQUESTS.jsonl.gz": "96efd85b7d29d54938b1a4932321eff74bca7e8e56565c978f58a1e57d9a1792",
}


class RunnerStop(RuntimeError):
    pass


def _provider_endpoint_signature(value: str) -> tuple[str, str, int, str] | None:
    """Accept only the configured DeepSeek origin and its documented API base paths."""
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except (TypeError, ValueError):
        return None
    host = parsed.hostname.lower() if parsed.hostname else ""
    if (
        parsed.scheme.lower() != "https"
        or host != "api.deepseek.com"
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or port not in {None, 443}
        or parsed.path not in {"", "/", "/v1", "/v1/"}
    ):
        return None
    base_path = "/v1" if parsed.path.rstrip("/") == "/v1" else ""
    return "https", host, 443, base_path


def _request_matches_provider_endpoint(request: httpx.Request, expected_endpoint: str) -> bool:
    expected = _provider_endpoint_signature(expected_endpoint)
    if expected is None:
        return False
    try:
        parsed = urlsplit(str(request.url))
        port = parsed.port
    except (TypeError, ValueError):
        return False
    host = parsed.hostname.lower() if parsed.hostname else ""
    actual_port = 443 if port is None else port
    expected_path = expected[3] + "/chat/completions"
    raw_path = request.url.raw_path.partition(b"?")[0]
    host_header = request.headers.get("host")
    valid_host_header = host_header is None or host_header.lower() in {
        expected[1], f"{expected[1]}:443",
    }
    return bool(
        request.method == "POST"
        and parsed.scheme.lower() == expected[0]
        and host == expected[1]
        and actual_port == expected[2]
        and parsed.username is None
        and parsed.password is None
        and not parsed.query
        and not parsed.fragment
        and parsed.path == expected_path
        and raw_path == expected_path.encode("ascii")
        and valid_host_header
    )


def _response_contains_tool_call(choices: Any) -> bool:
    if not isinstance(choices, list):
        return False
    for choice in choices:
        if not isinstance(choice, dict):
            continue
        if choice.get("finish_reason") == "tool_calls":
            return True
        message = choice.get("message")
        if isinstance(message, dict) and ("tool_calls" in message or "function_call" in message):
            return True
    return False


def canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256(value: bytes | str) -> str:
    raw = value if isinstance(value, bytes) else value.encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp")
    with temp.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temp, path)


def append_gzip_jsonl(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("ab") as raw:
        with gzip.GzipFile(fileobj=raw, mode="wb", mtime=0) as zipped:
            zipped.write((canonical(record) + "\n").encode("utf-8"))
        raw.flush()
        os.fsync(raw.fileno())


def main_env_path(root: Path = ROOT) -> Path:
    """Resolve the shared main-repository .env from a Worktree checkout."""
    return root.parent.parent / ".env"


def required_presence() -> dict[str, bool]:
    # Keep the user-requested presence-only report. Never print configuration values.
    return {key: bool(os.environ.get(key)) for key in REQUIRED_ENV}


def _nonblank_presence() -> dict[str, bool]:
    return {key: bool(os.environ.get(key, "").strip()) for key in REQUIRED_ENV}


def _configure_non_secret_defaults() -> list[str]:
    added: list[str] = []
    for key, value in NON_SECRET_DEFAULTS.items():
        if not os.environ.get(key, "").strip():
            os.environ[key] = value
            added.append(key)
    return added


def _canonicalize_official_endpoint() -> bool:
    """Normalize the official DeepSeek OpenAI-compatible base URL locally.

    Runtime Grant currently accepts the optional `/v1` suffix for compatibility,
    while DeepSeek's Chat Completions endpoint is documented at the host root.
    Normalize only the official HTTPS host and root or `/v1` path; never rewrite
    another host/path into an allowed endpoint.
    """
    raw = os.environ.get("OPSPILOT_MODEL_BASE_URL", "").strip()
    parsed = urlsplit(raw)
    if (
        parsed.scheme != "https" or parsed.hostname != "api.deepseek.com"
        or parsed.port not in (None, 443) or parsed.username is not None
        or parsed.password is not None or parsed.query or parsed.fragment
        or parsed.path not in ("", "/", "/v1")
    ):
        return False
    if raw != ENDPOINT:
        os.environ["OPSPILOT_MODEL_BASE_URL"] = ENDPOINT
        return True
    return False


def load_main_environment(*, root: Path = ROOT, loader=load_local_environment,
                          emit_presence: bool = False) -> dict[str, Any]:
    main_env = main_env_path(root)
    report: dict[str, Any] = {
        "main_repo_env_found": main_env.is_file(),
        "environment_loaded_from_main_repo_env": False,
        "required_presence_after_load": {key: False for key in REQUIRED_ENV},
        "effective_required_presence": {key: False for key in REQUIRED_ENV},
        "supplemented_non_secret_configuration": [],
        "endpoint_canonicalized_from_official_root_or_v1": False,
        "api_key_present": False,
        "runtime_config_valid": False,
        "runtime_config_sha256": None,
        "error": None,
    }
    if not main_env.is_file():
        report["error"] = "MAIN_REPO_ENV_NOT_FOUND"
        return report
    try:
        loader(main_env)
        report["environment_loaded_from_main_repo_env"] = True
        presence = required_presence()
        report["required_presence_after_load"] = presence
        if emit_presence:
            print(presence)
        report["api_key_present"] = _nonblank_presence()["OPSPILOT_MODEL_API_KEY"]
        if not report["api_key_present"]:
            report["error"] = "MODEL_API_KEY_NOT_PRESENT_AFTER_MAIN_ENV_LOAD"
        report["supplemented_non_secret_configuration"] = _configure_non_secret_defaults()
        report["endpoint_canonicalized_from_official_root_or_v1"] = _canonicalize_official_endpoint()
        report["effective_required_presence"] = _nonblank_presence()
        if not report["api_key_present"]:
            return report
        from opspilot.domain.assistant_runtime_grant import runtime_config_from_env

        config = runtime_config_from_env()
        if config["model_id"] != MODEL or config["endpoint"].rstrip("/") != ENDPOINT:
            report["error"] = "LIVE_MODEL_OR_ENDPOINT_DOES_NOT_MATCH_FROZEN_TASK"
            return report
        report["runtime_config_valid"] = True
        report["runtime_config_sha256"] = sha256(canonical(config))
    except Exception as error:
        report["error"] = str(getattr(error, "code", None) or type(error).__name__)
    return report


def _setup_harness():
    path = str(SETUP_DIR)
    if path not in sys.path:
        sys.path.insert(0, path)
    import test_offline_harness
    return test_offline_harness


def load_frozen_inputs():
    for name, expected in PHASE_INPUT_SHA256.items():
        if sha256((PHASE_A_DIR / name).read_bytes()) != expected:
            raise RunnerStop(f"FROZEN_PHASE_A_INPUT_CHANGED:{name}")
    return _setup_harness()._load_frozen_inputs()


def _case_limits(group: str) -> int:
    return 3 * REQUEST_RESERVE_USD_MICRO if group in {"A", "B"} else REQUEST_RESERVE_USD_MICRO


def _planned_slots() -> list[dict[str, Any]]:
    slots: list[dict[str, Any]] = []
    for question_id in QUESTION_IDS:
        for group in GROUPS:
            case_id = f"{question_id}-{group}"
            if group in {"A", "B"}:
                slots.extend({
                    "logical_id": f"{case_id}:SUMMARY:{index}",
                    "case_id": case_id,
                    "question_id": question_id,
                    "group": group,
                    "purpose": "SUMMARY",
                    "ordinal": index,
                    "status": "NOT_SENT",
                    "reserved_usd_micro": 0,
                    "settled_usd_micro": 0,
                    "request_digest": None,
                    "provider_request_id": None,
                    "response_model": None,
                    "usage": None,
                    "error": None,
                } for index in (1, 2))
            slots.append({
                "logical_id": f"{case_id}:ANSWER:1",
                "case_id": case_id,
                "question_id": question_id,
                "group": group,
                "purpose": "ANSWER",
                "ordinal": 1,
                "status": "NOT_SENT",
                "reserved_usd_micro": 0,
                "settled_usd_micro": 0,
                "request_digest": None,
                "provider_request_id": None,
                "response_model": None,
                "usage": None,
                "error": None,
            })
    assert len(slots) == REQUEST_LIMIT
    return slots


class GlobalBudgetLedger:
    """One durable, atomic budget ledger shared by every case and Grant."""

    def __init__(self, path: Path, state: dict[str, Any]):
        self.path = path
        self.state = state
        self._lock = threading.RLock()

    @classmethod
    def create(cls, path: Path, *, execution_id: str, mode: str,
               hard_cap_usd_micro: int = HARD_CAP_USD_MICRO,
               request_limit: int = REQUEST_LIMIT) -> "GlobalBudgetLedger":
        if path.exists():
            raise RunnerStop("GLOBAL_LEDGER_ALREADY_EXISTS_REFUSE_TO_REUSE")
        if hard_cap_usd_micro < 0 or request_limit < 0:
            raise ValueError("INVALID_TEST_BUDGET")
        path.parent.mkdir(parents=True, exist_ok=True)
        state = {
            "schema_version": 1,
            "task": TASK,
            "execution_id": execution_id,
            "mode": mode,
            "status": "ACTIVE",
            "request_limit": request_limit,
            "hard_cap_usd_micro": hard_cap_usd_micro,
            "per_request_worst_case_usd_micro": REQUEST_RESERVE_USD_MICRO,
            "provider_requests_started": 0,
            "settled_usd_micro": 0,
            "currently_reserved_usd_micro": 0,
            "stop_reason": None,
            "slots": _planned_slots(),
        }
        ledger = cls(path, state)
        ledger._persist()
        return ledger

    @classmethod
    def open_for_inspection(cls, path: Path) -> "GlobalBudgetLedger":
        state = json.loads(path.read_text(encoding="utf-8"))
        ledger = cls(path, state)
        sending = [slot for slot in state["slots"] if slot["status"] == "SENDING"]
        if sending:
            for slot in sending:
                slot["status"] = "UNKNOWN"
                slot["error"] = "PROCESS_ENDED_DURING_SEND"
            state["stop_reason"] = "UNKNOWN_SEND_STATE_REFUSE_RETRY"
            state["status"] = "STOPPED"
            ledger._recalculate()
            ledger._persist()
        return ledger

    def _persist(self) -> None:
        self._recalculate()
        atomic_json(self.path, self.state)

    def _recalculate(self) -> None:
        self.state["provider_requests_started"] = sum(
            1 for slot in self.state["slots"] if slot.get("request_digest") is not None
        )
        self.state["settled_usd_micro"] = sum(
            int(slot.get("settled_usd_micro") or 0) for slot in self.state["slots"]
        )
        self.state["currently_reserved_usd_micro"] = sum(
            int(slot.get("reserved_usd_micro") or 0)
            for slot in self.state["slots"]
            if slot["status"] in {"SENDING", "UNKNOWN", "USAGE_UNKNOWN", "STOPPED_UNKNOWN"}
        )

    def _slot(self, logical_id: str) -> dict[str, Any]:
        for slot in self.state["slots"]:
            if slot["logical_id"] == logical_id:
                return slot
        raise RunnerStop("LOGICAL_REQUEST_SLOT_NOT_IN_FROZEN_MATRIX")

    def next_slot(self, case_id: str, purpose: str) -> dict[str, Any]:
        if self.state.get("stop_reason"):
            raise RunnerStop(str(self.state["stop_reason"]))
        candidates = [slot for slot in self.state["slots"]
                     if slot["case_id"] == case_id and slot["purpose"] == purpose]
        for slot in candidates:
            if slot["status"] == "NOT_SENT":
                return slot
        raise RunnerStop("LOGICAL_REQUEST_ALREADY_SENT_OR_CASE_CAP_REACHED")

    def start_send(self, logical_id: str, request_digest: str, transport: str) -> None:
        with self._lock:
            if self.state.get("stop_reason"):
                raise RunnerStop(str(self.state["stop_reason"]))
            slot = self._slot(logical_id)
            if slot["status"] != "NOT_SENT" or slot["request_digest"] is not None:
                raise RunnerStop("LOGICAL_REQUEST_ALREADY_SENT_REFUSE_RETRY")
            if self.state["provider_requests_started"] >= int(self.state["request_limit"]):
                self.stop("GLOBAL_REQUEST_CAP_REACHED")
                raise RunnerStop("GLOBAL_REQUEST_CAP_REACHED")
            reserve = REQUEST_RESERVE_USD_MICRO
            already_spent = int(self.state["settled_usd_micro"])
            already_reserved = int(self.state["currently_reserved_usd_micro"])
            if already_spent + already_reserved + reserve > int(self.state["hard_cap_usd_micro"]):
                self.stop("GLOBAL_BUDGET_EXHAUSTED_BEFORE_SEND")
                raise RunnerStop("GLOBAL_BUDGET_EXHAUSTED_BEFORE_SEND")
            slot.update({
                "status": "SENDING",
                "reserved_usd_micro": reserve,
                "request_digest": request_digest,
                "transport": transport,
                "send_started_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            })
            self._persist()

    def finish(self, logical_id: str, *, status: str, http_status: int | None,
               provider_request_id: str | None, response_model: str | None,
               usage: dict[str, int] | None, settled_usd_micro: int | None,
               finish_reason: str | None, error: str | None = None,
               stop_reason: str | None = None) -> None:
        with self._lock:
            slot = self._slot(logical_id)
            slot.update({
                "status": status,
                "http_status": http_status,
                "provider_request_id": provider_request_id,
                "response_model": response_model,
                "usage": usage,
                "finish_reason": finish_reason,
                "error": error,
                "completed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            })
            if settled_usd_micro is not None:
                slot["settled_usd_micro"] = settled_usd_micro
                slot["reserved_usd_micro"] = 0
            if stop_reason:
                self.state["stop_reason"] = stop_reason
                self.state["status"] = "STOPPED"
            self._persist()

    def unknown(self, logical_id: str, error: str) -> None:
        self.finish(
            logical_id, status="UNKNOWN", http_status=None,
            provider_request_id=None, response_model=None, usage=None,
            settled_usd_micro=None, finish_reason=None, error=error,
            stop_reason="UNKNOWN_SEND_STATE_NO_RETRY",
        )

    def stop(self, reason: str) -> None:
        with self._lock:
            if not self.state.get("stop_reason"):
                self.state["stop_reason"] = reason
            self.state["status"] = "STOPPED"
            self._persist()

    def finalize(self) -> None:
        with self._lock:
            for slot in self.state["slots"]:
                if slot["status"] == "NOT_SENT":
                    slot["status"] = "NOT_SENT_FINAL"
            self.state["status"] = "STOPPED" if self.state.get("stop_reason") else "FINISHED"
            self._persist()


def _ceil_cost_micro(input_tokens: int, output_tokens: int) -> int:
    numerator = input_tokens * INPUT_RATE_MICRO_PER_MILLION + output_tokens * OUTPUT_RATE_MICRO_PER_MILLION
    return (numerator + 999_999) // 1_000_000


def _response_usage(payload: dict[str, Any]) -> dict[str, int] | None:
    raw = payload.get("usage")
    if not isinstance(raw, dict):
        return None
    try:
        input_tokens = int(raw["prompt_tokens"])
        output_tokens = int(raw["completion_tokens"])
        total_tokens = int(raw["total_tokens"])
    except (KeyError, TypeError, ValueError):
        return None
    if input_tokens < 0 or output_tokens < 0 or total_tokens != input_tokens + output_tokens:
        return None
    return {"input_tokens": input_tokens, "output_tokens": output_tokens, "total_tokens": total_tokens}


def _redact_bytes(body: bytes, secret: str) -> bytes:
    return body.replace(secret.encode("utf-8"), b"<REDACTED>") if secret else body


class BudgetedAsyncTransport(httpx.AsyncBaseTransport):
    """Durably reserve one global slot before the single underlying send."""

    def __init__(self, *, inner: httpx.AsyncBaseTransport, ledger: GlobalBudgetLedger,
                 case_id: str, mode: str, trace_path: Path, secret: str = "",
                 question_row: dict[str, Any] | None = None,
                 expected_endpoint: str = ENDPOINT):
        self.inner = inner
        self.ledger = ledger
        self.case_id = case_id
        self.mode = mode
        self.trace_path = trace_path
        self.secret = secret
        self.question_row = question_row or {}
        self.expected_endpoint = expected_endpoint
        self._send_lock = threading.Lock()
        self.calls: list[dict[str, Any]] = []

    def _validate_request(self, request: httpx.Request, body: bytes) -> tuple[dict[str, Any], str]:
        try:
            payload = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise RunnerStop("REQUEST_BODY_INVALID_JSON") from error
        if not isinstance(payload, dict):
            raise RunnerStop("REQUEST_BODY_NOT_OBJECT")
        if not _request_matches_provider_endpoint(request, self.expected_endpoint):
            raise RunnerStop("PROVIDER_ENDPOINT_OR_METHOD_MISMATCH")
        if request.method != "POST":
            raise RunnerStop("PROVIDER_ENDPOINT_OR_METHOD_MISMATCH")
        if payload.get("model") != MODEL or payload.get("thinking") != {"type": "disabled"}:
            raise RunnerStop("FROZEN_MODEL_OR_THINKING_MODE_MISMATCH")
        if payload.get("temperature") != 0:
            raise RunnerStop("FROZEN_TEMPERATURE_MISMATCH")
        if payload.get("stream") is True:
            raise RunnerStop("STREAMING_NOT_ENABLED_FOR_THIS_RUNNER")
        max_tokens = payload.get("max_tokens")
        if type(max_tokens) is not int or not 0 < max_tokens <= MAX_OUTPUT_TOKENS:
            raise RunnerStop("OUTPUT_TOKEN_CAP_MISMATCH")
        messages = payload.get("messages")
        tools = payload.get("tools", [])
        if not isinstance(messages, list) or not isinstance(tools, list):
            raise RunnerStop("REQUEST_MESSAGES_OR_TOOLS_INVALID")
        is_summary = any(
            isinstance(item, dict) and item.get("role") == "system"
            and str(item.get("content", "")).startswith("Compress only the supplied conversation")
            for item in messages
        )
        purpose = "SUMMARY" if is_summary else "ANSWER"
        if purpose == "ANSWER" and payload.get("tool_choice") != "none":
            raise RunnerStop("HISTORY_RECALL_REQUIRES_TOOL_CHOICE_NONE")
        if purpose == "SUMMARY" and self.ledger.next_slot(self.case_id, "SUMMARY") is None:
            raise RunnerStop("SUMMARY_CASE_CAP_REACHED")
        from opspilot.domain.context_engineering import estimate_messages_tokens, estimate_text_tokens
        estimated = estimate_messages_tokens(messages) + estimate_text_tokens(canonical(tools)) + 64
        if not 0 < estimated <= MAX_INPUT_TOKENS:
            raise RunnerStop("INPUT_ESTIMATE_OUTSIDE_FROZEN_BUDGET")
        serialized = canonical(payload)
        gold_json = canonical(self.question_row.get("gold")) if self.question_row.get("gold") is not None else ""
        scoring_rule = str(self.question_row.get("scoring_rule") or "")
        if gold_json and gold_json in serialized:
            raise RunnerStop("OFFLINE_GOLD_LEAKAGE_BLOCKED")
        if scoring_rule and scoring_rule in serialized:
            raise RunnerStop("SCORING_RULE_LEAKAGE_BLOCKED")
        if self.secret and self.secret.encode("utf-8") in body:
            raise RunnerStop("SECRET_IN_PROVIDER_BODY_BLOCKED")
        return payload, purpose

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        if not self._send_lock.acquire(blocking=False):
            self.ledger.stop("CONCURRENT_PROVIDER_SEND_BLOCKED")
            raise RunnerStop("CONCURRENT_PROVIDER_SEND_BLOCKED")
        try:
            body = await request.aread()
            payload, purpose = self._validate_request(request, body)
            slot = self.ledger.next_slot(self.case_id, purpose)
            logical_id = str(slot["logical_id"])
            body_digest = sha256(body)
            self.ledger.start_send(logical_id, body_digest, "httpx.MockTransport" if self.mode == "MOCK" else "httpx.AsyncHTTPTransport(retries=0)")
            # Headers, especially Authorization, are never serialized.
            append_gzip_jsonl(self.trace_path, {
                "event": "SEND_STARTED",
                "mode": self.mode,
                "case_id": self.case_id,
                "logical_id": logical_id,
                "purpose": purpose,
                "request_body_sha256": body_digest,
                "request_payload": payload,
                "authorization_header_recorded": False,
            })
            try:
                response = await self.inner.handle_async_request(request)
                raw_response = await response.aread()
                http_status = response.status_code
                response_headers = dict(response.headers)
                await response.aclose()
            except BaseException as error:
                self.ledger.unknown(logical_id, type(error).__name__)
                append_gzip_jsonl(self.trace_path, {
                    "event": "SEND_UNKNOWN",
                    "case_id": self.case_id,
                    "logical_id": logical_id,
                    "error_type": type(error).__name__,
                    "request_body_sha256": body_digest,
                    "authorization_header_recorded": False,
                })
                raise

            if 300 <= http_status < 400:
                # Do not expose a redirect response to the SDK: a configured
                # follow_redirects policy must not create a second request to
                # a destination selected by Provider response headers.
                response_digest = sha256(raw_response)
                stored_response = _redact_bytes(raw_response, self.secret)
                response_id = str(response_headers.get("x-request-id") or "") or None
                self.ledger.finish(
                    logical_id, status="USAGE_UNKNOWN", http_status=http_status,
                    provider_request_id=response_id, response_model=None, usage=None,
                    settled_usd_micro=None, finish_reason=None,
                    error=f"HTTP_{http_status}_REDIRECT_NOT_FOLLOWED",
                    stop_reason="PROVIDER_REDIRECT_BLOCKED",
                )
                append_gzip_jsonl(self.trace_path, {
                    "event": "RESPONSE_REDIRECT_BLOCKED",
                    "mode": self.mode,
                    "case_id": self.case_id,
                    "logical_id": logical_id,
                    "purpose": purpose,
                    "request_body_sha256": body_digest,
                    "response_body_sha256": response_digest,
                    "http_status": http_status,
                    "provider_request_id": response_id,
                    "usage": None,
                    "status": "USAGE_UNKNOWN",
                    "stop_reason": "PROVIDER_REDIRECT_BLOCKED",
                    "redirect_location_recorded": False,
                    "authorization_header_recorded": False,
                    "response_body": stored_response.decode("utf-8", errors="replace"),
                })
                raise RunnerStop("PROVIDER_REDIRECT_BLOCKED")

            secret_in_response = bool(self.secret and self.secret.encode("utf-8") in raw_response)
            stored_response = _redact_bytes(raw_response, self.secret)
            response_digest = sha256(raw_response)
            try:
                response_payload = json.loads(stored_response.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                response_payload = None
            if not isinstance(response_payload, dict):
                self.ledger.finish(
                    logical_id, status="USAGE_UNKNOWN", http_status=http_status,
                    provider_request_id=None, response_model=None, usage=None,
                    settled_usd_micro=None, finish_reason=None,
                    error="RESPONSE_BODY_INVALID", stop_reason="PROVIDER_RESPONSE_INVALID",
                )
                append_gzip_jsonl(self.trace_path, {
                    "event": "RESPONSE_INVALID",
                    "case_id": self.case_id,
                    "logical_id": logical_id,
                    "http_status": http_status,
                    "response_body_sha256": response_digest,
                    "response_body": stored_response.decode("utf-8", errors="replace"),
                    "authorization_header_recorded": False,
                })
                raise RunnerStop("PROVIDER_RESPONSE_INVALID")

            choices = response_payload.get("choices")
            choice = choices[0] if isinstance(choices, list) and len(choices) == 1 and isinstance(choices[0], dict) else {}
            message = choice.get("message") if isinstance(choice.get("message"), dict) else {}
            finish_reason = choice.get("finish_reason") if isinstance(choice.get("finish_reason"), str) else None
            tool_response = _response_contains_tool_call(choices)
            provider_id = str(response_payload.get("id") or "") or None
            response_model = str(response_payload.get("model") or "") or None
            usage = _response_usage(response_payload)
            settled = None
            if (usage is not None and usage["input_tokens"] <= MAX_INPUT_TOKENS
                    and usage["output_tokens"] <= int(payload["max_tokens"])):
                settled = _ceil_cost_micro(usage["input_tokens"], usage["output_tokens"])

            stop_reason = None
            status = "COMPLETED"
            error_code = None
            if http_status != 200:
                stop_reason, status, error_code = "PROVIDER_HTTP_ERROR", "PROVIDER_ERROR", f"HTTP_{http_status}"
            elif usage is None:
                stop_reason, status, error_code = "PROVIDER_USAGE_MISSING", "USAGE_UNKNOWN", "USAGE_INVALID_OR_MISSING"
            elif settled is None:
                stop_reason, status, error_code = "PROVIDER_USAGE_OVER_TOKEN_CAP", "USAGE_VIOLATION", "USAGE_EXCEEDS_REQUEST_CAP"
            elif response_model not in {MODEL, MODEL_VERSION, MODEL_VERSION.lower()}:
                stop_reason, status, error_code = "PROVIDER_MODEL_VERSION_DRIFT", "MODEL_DRIFT", "RESPONSE_MODEL_MISMATCH"
            elif tool_response or finish_reason == "tool_calls":
                stop_reason, status, error_code = "UNEXPECTED_TOOL_CALL", "TOOL_CALL_BLOCKED", "TOOL_CALL_NOT_EXECUTED"
            elif not isinstance(choices, list) or len(choices) != 1:
                stop_reason, status, error_code = "PROVIDER_RESPONSE_INVALID", "RESPONSE_INVALID", "CHOICE_COUNT_OR_SHAPE_INVALID"
            elif message.get("role") != "assistant" or not isinstance(message.get("content"), str):
                stop_reason, status, error_code = "PROVIDER_RESPONSE_INVALID", "RESPONSE_INVALID", "ASSISTANT_TEXT_CONTENT_INVALID"
            elif finish_reason != "stop":
                stop_reason, status, error_code = "PROVIDER_OUTPUT_NOT_COMPLETE", "INCOMPLETE", f"FINISH_REASON_{finish_reason or 'MISSING'}"
            elif secret_in_response:
                stop_reason, status, error_code = "SECRET_IN_PROVIDER_RESPONSE", "REDACTED_RESPONSE", "SECRET_REDACTED_FROM_RESPONSE"
            elif purpose == "SUMMARY" and not isinstance(message.get("content"), str):
                stop_reason, status, error_code = "SUMMARY_CONTENT_INVALID", "SUMMARY_INVALID", "SUMMARY_CONTENT_MISSING"
            elif purpose == "SUMMARY":
                try:
                    summary_value = json.loads(message["content"])
                    if not isinstance(summary_value, dict):
                        raise ValueError("not an object")
                except (json.JSONDecodeError, ValueError, TypeError):
                    stop_reason, status, error_code = "SUMMARY_JSON_INVALID", "SUMMARY_INVALID", "SUMMARY_JSON_INVALID"
            if settled is not None and settled > REQUEST_RESERVE_USD_MICRO:
                stop_reason, status, error_code = "REQUEST_RESERVE_EXCEEDED", "BUDGET_VIOLATION", "ACTUAL_COST_ABOVE_WORST_CASE_RESERVE"
            self.ledger.finish(
                logical_id, status=status, http_status=http_status,
                provider_request_id=provider_id, response_model=response_model,
                usage=usage, settled_usd_micro=settled,
                finish_reason=finish_reason, error=error_code, stop_reason=stop_reason,
            )
            self.calls.append({
                "logical_id": logical_id,
                "purpose": purpose,
                "request_payload": payload,
                "response_payload": response_payload,
                "status": status,
                "stop_reason": stop_reason,
                "request_body_sha256": body_digest,
                "response_body_sha256": response_digest,
            })
            append_gzip_jsonl(self.trace_path, {
                "event": "RESPONSE_RECEIVED",
                "mode": self.mode,
                "case_id": self.case_id,
                "logical_id": logical_id,
                "purpose": purpose,
                "request_body_sha256": body_digest,
                "response_body_sha256": response_digest,
                "http_status": http_status,
                "provider_request_id": provider_id,
                "response_model": response_model,
                "usage": usage,
                "settled_usd_micro": settled,
                "finish_reason": finish_reason,
                "status": status,
                "stop_reason": stop_reason,
                "response_payload": response_payload,
                "authorization_header_recorded": False,
            })
            if stop_reason:
                # Keep Provider usage, response ID, status, and body in the
                # durable evaluation trace and ledger, but never return a
                # nonconforming response to the Assistant or tool dispatcher.
                raise RunnerStop(stop_reason)
            return httpx.Response(
                http_status,
                headers={"content-type": str(response_headers.get("content-type", "application/json"))},
                content=stored_response,
                request=request,
            )
        except RunnerStop as error:
            self.ledger.stop(str(error))
            raise
        finally:
            self._send_lock.release()

    async def aclose(self) -> None:
        await self.inner.aclose()


def _grant_for_case(db_path: Path, config: dict[str, str], case_id: str,
                    execution_id: str) -> dict[str, Any]:
    from opspilot.domain.assistant_runtime_grant import provision_default_grant
    now = datetime.now(timezone.utc)
    grant = provision_default_grant(
        db_path,
        grant_source=f"{TASK} isolated case grant",
        operator_id="local-evaluation-operator",
        service_identity=config["service_identity"],
        model_id=config["model_id"],
        endpoint=config["endpoint"],
        model_config_version=config["model_config_version"],
        price_version=config["price_version"],
        input_rate_micro_per_million=INPUT_RATE_MICRO_PER_MILLION,
        output_rate_micro_per_million=OUTPUT_RATE_MICRO_PER_MILLION,
        max_input_tokens=MAX_INPUT_TOKENS,
        max_output_tokens=MAX_OUTPUT_TOKENS,
        total_limit_usd_micro=_case_limits(case_id[-1]),
        valid_from=(now - timedelta(seconds=5)).isoformat(timespec="seconds").replace("+00:00", "Z"),
        expires_at=(now + timedelta(hours=2)).isoformat(timespec="seconds").replace("+00:00", "Z"),
        evidence_ref=f"{TASK};case={case_id};execution={execution_id}",
        evidence_digest=sha256(canonical({"task": TASK, "case": case_id, "base": BASE_SHA, "config": config})),
        idempotency_key=f"{TASK}:{execution_id}:{case_id}:grant-v1",
    )
    grant["total_limit_usd_micro"] = _case_limits(case_id[-1])
    return grant


def _set_case_environment(monkeypatch, config: dict[str, str], strategy: str,
                          api_key: str | None = None) -> None:
    for key, value in config.items():
        env_key = {
            "model_id": "OPSPILOT_MODEL_NAME",
            "endpoint": "OPSPILOT_MODEL_BASE_URL",
            "model_config_version": "OPSPILOT_MODEL_CONFIG_VERSION",
            "price_version": "OPSPILOT_MODEL_PRICE_VERSION",
            "service_identity": "OPSPILOT_ASSISTANT_SERVICE_IDENTITY",
        }[key]
        monkeypatch.setenv(env_key, value)
    if api_key is not None:
        monkeypatch.setenv("OPSPILOT_MODEL_API_KEY", api_key)
    monkeypatch.setenv("OPSPILOT_ASSISTANT_PROVIDER_ENABLED", "1")
    monkeypatch.setenv("OPSPILOT_ASSISTANT_RUNTIME_ENABLED", "1")
    monkeypatch.setenv("OPSPILOT_CONTEXT_INPUT_BUDGET_TOKENS", str(MAX_INPUT_TOKENS))
    monkeypatch.setenv("OPSPILOT_CONTEXT_STRATEGY", strategy)
    monkeypatch.delenv("OPSPILOT_ASSISTANT_EXPERIMENT_ID", raising=False)


def _case_config_from_env() -> dict[str, str]:
    from opspilot.domain.assistant_runtime_grant import runtime_config_from_env
    return runtime_config_from_env()


async def _run_case(*, case_root: Path, case_id: str, question_id: str, group: str,
                    strategy: str, question_row: dict[str, Any], history: list[dict[str, Any]],
                    history_digest: str, config: dict[str, str], api_key: str,
                    ledger: GlobalBudgetLedger, trace_path: Path, mode: str,
                    mock_transport: httpx.AsyncBaseTransport | None = None) -> dict[str, Any]:
    import pytest
    from opspilot.assistant import create_assistant_model, run_assistant
    from opspilot.domain.assistant_runtime_grant import bind_run, validate_run_binding, spend_summary
    from opspilot.domain.chat import get_chat_manifest
    from opspilot.domain.database import connect

    setup = _setup_harness()
    db_path = case_root / "domain.sqlite3"
    checkpoint_path = case_root / "checkpoint.sqlite3"
    case_root.mkdir(parents=True, exist_ok=False)
    owner = f"abc-live-{case_id}-{uuid.uuid4().hex[:8]}"
    patch = pytest.MonkeyPatch()
    model = None
    transport: BudgetedAsyncTransport | None = None
    try:
        _set_case_environment(patch, config, strategy, api_key if mode == "MOCK" else None)
        session_id, run_id, worker_epoch, identity = setup._seed_domain(
            db_path, owner, history, str(question_row["prompt_text"]),
        )
        patch.setenv("OPSPILOT_CONTEXT_STRATEGY", strategy)
        grant = _grant_for_case(db_path, config, case_id, ledger.state["execution_id"])
        binding = bind_run(db_path, run_id, _case_config_from_env())
        validated = validate_run_binding(db_path, run_id, binding, _case_config_from_env())
        if validated["database_file_identity"] != binding["database_file_identity"]:
            raise RunnerStop("RUNTIME_GRANT_DATABASE_IDENTITY_MISMATCH")

        if mode == "MOCK":
            if mock_transport is None:
                raise RunnerStop("MOCK_TRANSPORT_REQUIRED")
            inner = mock_transport
        else:
            inner = httpx.AsyncHTTPTransport(retries=0)
        transport = BudgetedAsyncTransport(
            inner=inner, ledger=ledger, case_id=case_id, mode=mode,
            trace_path=trace_path, secret=api_key, question_row=question_row,
            expected_endpoint=config["endpoint"],
        )
        sync_forbidden = httpx.MockTransport(
            lambda _request: (_ for _ in ()).throw(AssertionError("sync Provider transport forbidden"))
        )
        model = create_assistant_model(
            runtime_grant_binding=binding,
            transport_async=transport,
            transport_sync=sync_forbidden,
        )
        if model is None:
            raise RunnerStop("ASSISTANT_PROVIDER_RUNTIME_NOT_ENABLED")
        assistant_trace: list[dict[str, Any]] = []
        run_result = await run_assistant(
            db_path, checkpoint_path, owner, run_id, model=model,
            runtime_grant_binding=binding, worker_epoch=worker_epoch,
            tool_choice_override="none",
            trace=lambda event, **fields: assistant_trace.append({"event": event, **fields}),
        )
        manifest = get_chat_manifest(db_path, identity, run_id)
        summary_attempts = manifest["compression_attempts"]
        answer_calls = [call for call in transport.calls if call["purpose"] == "ANSWER"]
        summary_calls = [call for call in transport.calls if call["purpose"] == "SUMMARY"]
        tool_observations = [event for event in assistant_trace if event.get("event") == "tool_observation"]
        if not manifest["attempts"]:
            failed_compression = next(
                (attempt for attempt in reversed(summary_attempts) if attempt.get("status") == "FAILED"),
                None,
            )
            reason = (
                failed_compression.get("error_class")
                if failed_compression is not None
                else run_result.get("reason") or run_result.get("error") or "CHAT_ANSWER_MANIFEST_MISSING"
            )
            return {
                "case_id": case_id,
                "question_id": question_id,
                "group": group,
                "strategy": strategy,
                "status": "STOPPED",
                "error": str(reason)[:100],
                "domain_stop_reason": str(reason)[:100],
                "assistant_run_status": run_result.get("status"),
                "answer_manifest_present": False,
                "compression_attempts": summary_attempts,
                "summary_calls": len(summary_calls),
                "answer_calls": len(answer_calls),
                "external_mcp_calls": 0,
                "local_tool_observations": len(tool_observations),
            }
        if group == "C" and (summary_calls or summary_attempts):
            raise RunnerStop("RECENT_WINDOW_MUST_NOT_SUMMARIZE")
        if group in {"A", "B"} and not summary_calls:
            raise RunnerStop("SUMMARY_STRATEGY_DID_NOT_SUMMARIZE")
        if len(answer_calls) > 1 or len(summary_calls) > 2:
            raise RunnerStop("PER_CASE_REQUEST_CAP_EXCEEDED")
        if run_result.get("status") == "SUCCEEDED" and len(answer_calls) != 1:
            raise RunnerStop("CASE_DID_NOT_COMPLETE_ONE_ANSWER")
        if tool_observations:
            raise RunnerStop("LOCAL_TOOL_CALL_OBSERVED_UNDER_TOOL_CHOICE_NONE")

        with connect(db_path) as connection:
            rows = connection.execute(
                "SELECT sequence, role, body FROM messages WHERE session_id=? ORDER BY sequence",
                (session_id,),
            ).fetchall()
            seeded = [{"sequence": int(row["sequence"]), "role": str(row["role"]), "body": str(row["body"])}
                      for row in rows[:29]]
        if len(seeded) != 29 or [row["body"] for row in seeded] != [row["body"] for row in history]:
            raise RunnerStop("FROZEN_HISTORY_SEED_MISMATCH")
        answer_request = answer_calls[0]["request_payload"] if answer_calls else None
        answer_system_text = "\n".join(
            str(message.get("content", "")) for message in (answer_request or {}).get("messages", [])
            if message.get("role") == "system"
        )
        prefix = answer_system_text.split("\nWORK_CONTEXT\n", 1)[0] if answer_system_text else ""
        case_record = {
            "case_id": case_id,
            "question_id": question_id,
            "group": group,
            "strategy": strategy,
            "status": run_result.get("status"),
            "reason": run_result.get("reason"),
            "evidence_level": "FIXTURE_AND_MOCK_PROVIDER_TRANSPORT" if mode == "MOCK" else "REAL_PROVIDER",
            "domain_instance_sha256": sha256(str(db_path.resolve())),
            "checkpoint_instance_sha256": sha256(str(checkpoint_path.resolve())),
            "history_digest_sha256": history_digest,
            "history_rows": len(seeded),
            "history_row_digests_match_frozen_recreation": True,
            "domain_db_isolated": True,
            "checkpoint_isolated": True,
            "runtime_grant_status": grant["status"],
            "runtime_grant_id_sha256": sha256(str(grant["grant_id"])),
            "runtime_grant_case_limit_usd_micro": int(grant["total_limit_usd_micro"]),
            "runtime_binding_database_identity_matches": True,
            "runtime_spend_summary": spend_summary(db_path),
            "configured_input_limit_tokens": int(manifest["context_budget"]["configured_input_limit_tokens"]),
            "effective_context_input_budget_tokens": int(manifest["context_budget"]["input_budget_tokens"]),
            "summary_attempt_count": len(summary_attempts),
            "summary_attempts": summary_attempts,
            "summary_calls": len(summary_calls),
            "answer_calls": len(answer_calls),
            "answer_tool_choice": (answer_request or {}).get("tool_choice"),
            "answer_request_digest": answer_calls[0]["request_body_sha256"] if answer_calls else None,
            "answer_message_count": len((answer_request or {}).get("messages", [])),
            "answer_context_blocks": manifest["attempts"][-1]["manifest"].get("context_blocks") if manifest["attempts"] else [],
            "summary_refs": manifest["summary_refs"],
            "tool_schema_sha256": sha256(canonical((answer_request or {}).get("tools", []))) if answer_request else None,
            "system_prompt_prefix_sha256": sha256(prefix) if prefix else None,
            "external_mcp_calls": 0,
            "local_tool_observations": len(tool_observations),
            "gold_payload_serialized": False,
            "scoring_rule_serialized": False,
            "semantic_assessment": "NOT_SCORED_MOCK_OUTPUT" if mode == "MOCK" else "IMPLEMENTER_PRELIMINARY_REVIEW_PENDING",
            "answer_response": (
                answer_calls[0]["response_payload"].get("choices", [{}])[0].get("message", {}).get("content")
                if answer_calls else None
            ),
        }
        return case_record
    finally:
        if model is not None:
            try:
                await model.http_async_client.aclose()
            finally:
                model.http_client.close()
        elif transport is not None:
            await transport.aclose()
        patch.undo()


def _mock_config() -> dict[str, str]:
    return {
        "model_id": MODEL,
        "endpoint": ENDPOINT,
        "model_config_version": "abc-live-mock-model-v1",
        "price_version": "abc-live-mock-fixture-price-v1",
        "service_identity": "abc-live-mock-service",
    }


def _mock_handler_factory(*, case_id: str, question_id: str, group: str,
                          question_row: dict[str, Any], db_path: Path,
                          run_id: str, mock_calls: list[dict[str, Any]]):
    setup = _setup_harness()
    from opspilot.domain.context_engineering import estimate_messages_tokens, estimate_text_tokens
    from opspilot.domain.d2 import canonical_json

    def respond(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content.decode("utf-8"))
        assert request.url.host == "api.deepseek.com"
        assert payload.get("model") == MODEL
        assert payload.get("max_tokens") == MAX_OUTPUT_TOKENS
        serialized = canonical_json(payload)
        assert canonical_json(question_row["gold"]) not in serialized
        assert str(question_row.get("scoring_rule", "")) not in serialized
        assert "offline-only-not-a-real-key" not in serialized
        input_tokens = (
            estimate_messages_tokens(payload["messages"])
            + estimate_text_tokens(canonical_json(payload.get("tools", []))) + 64
        )
        assert 0 < input_tokens <= MAX_INPUT_TOKENS
        system_text = "\n".join(
            str(message.get("content", "")) for message in payload.get("messages", [])
            if message.get("role") == "system"
        )
        is_summary = system_text.startswith("Compress only the supplied conversation")
        if is_summary:
            content = setup._summary_response(db_path, run_id)
        else:
            assert payload.get("tool_choice") == "none"
            content = f"MOCK_ONLY::{group}::{question_id}"
        response_payload = {
            "id": f"mock-{case_id}-{len(mock_calls) + 1}",
            "object": "chat.completion",
            "created": 1,
            "model": MODEL,
            "choices": [{"index": 0, "message": {"role": "assistant", "content": content}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": input_tokens, "completion_tokens": 24, "total_tokens": input_tokens + 24},
        }
        mock_calls.append({"payload": payload, "response": response_payload, "purpose": "SUMMARY" if is_summary else "ANSWER"})
        return httpx.Response(200, json=response_payload)

    return respond


def _write_mock_outputs(output_dir: Path, results: dict[str, Any], trace_path: Path,
                        ledger: GlobalBudgetLedger) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    for name in ("MOCK_RESULTS.json", "MOCK_TRACE.jsonl.gz", "MOCK_COST_LEDGER.json"):
        if (output_dir / name).exists():
            raise RunnerStop("MOCK_EVIDENCE_ALREADY_EXISTS_REFUSE_OVERWRITE")
    stage = output_dir / (".mock-stage-" + uuid.uuid4().hex[:8])
    stage.mkdir()
    try:
        atomic_json(stage / "MOCK_RESULTS.json", results)
        if not trace_path.is_file():
            raise RunnerStop("MOCK_TRACE_MISSING_AFTER_RUN")
        shutil.copyfile(trace_path, stage / "MOCK_TRACE.jsonl.gz")
        atomic_json(stage / "MOCK_COST_LEDGER.json", ledger.state)
        for name in ("MOCK_RESULTS.json", "MOCK_TRACE.jsonl.gz", "MOCK_COST_LEDGER.json"):
            os.replace(stage / name, output_dir / name)
        trace_path.unlink(missing_ok=True)
    finally:
        try:
            stage.rmdir()
        except OSError:
            # Preserve any partial stage files after an output error for review.
            pass


def run_mock_suite(output_dir: Path | None = None) -> dict[str, Any]:
    """Run all nine frozen cases using only MockTransport."""
    history, questions, history_digest, questions_file_sha = load_frozen_inputs()
    execution_id = "mock-" + uuid.uuid4().hex[:12]
    if output_dir is None:
        tmp_output = tempfile.TemporaryDirectory(prefix="opspilot-abc-mock-")
        out = Path(tmp_output.name)
    else:
        tmp_output = None
        out = output_dir
        out.mkdir(parents=True, exist_ok=True)
    trace_path = Path(tempfile.gettempdir()) / f"{execution_id}-trace.jsonl.gz"
    ledger_path = out / "MOCK_COST_LEDGER.json"
    # The test ledger is kept in memory-backed temporary storage and exported
    # after completion; it is a distinct fixture ledger, never a live ledger.
    temp_ledger_path = Path(tempfile.gettempdir()) / f"{execution_id}-ledger.json"
    ledger = GlobalBudgetLedger.create(temp_ledger_path, execution_id=execution_id, mode="MOCK")
    config = _mock_config()
    cases: list[dict[str, Any]] = []
    try:
        with tempfile.TemporaryDirectory(prefix="opspilot-abc-mock-cases-") as cases_tmp:
            case_root = Path(cases_tmp)
            for question_id in QUESTION_IDS:
                question_row = questions[question_id]
                for group in GROUPS:
                    case_id = f"{question_id}-{group}"
                    case_dir = case_root / case_id
                    def mock_transport_factory(active_db_path: Path, active_run_id: str):
                        calls: list[dict[str, Any]] = []
                        responder = _mock_handler_factory(
                            case_id=case_id, question_id=question_id,
                            group=group, question_row=question_row,
                            db_path=active_db_path, run_id=active_run_id, mock_calls=calls,
                        )
                        return httpx.MockTransport(responder), calls
                    record, calls = asyncio.run(_run_case_with_mock_factory(
                        case_root=case_dir, case_id=case_id, question_id=question_id,
                        group=group, strategy=STRATEGIES[group], question_row=question_row,
                        history=history, history_digest=history_digest, config=config,
                        ledger=ledger, trace_path=trace_path,
                        transport_factory=mock_transport_factory,
                    ))
                    cases.append(record)
        ledger.finalize()
        schema_digests = {row["tool_schema_sha256"] for row in cases if row.get("tool_schema_sha256")}
        prefix_digests = {row["system_prompt_prefix_sha256"] for row in cases if row.get("system_prompt_prefix_sha256")}
        sent = int(ledger.state["provider_requests_started"])
        summary_sent = sum(1 for slot in ledger.state["slots"] if slot["purpose"] == "SUMMARY" and slot["request_digest"])
        answer_sent = sum(1 for slot in ledger.state["slots"] if slot["purpose"] == "ANSWER" and slot["request_digest"])
        passed = (
            len(cases) == 9 and all(row["status"] == "SUCCEEDED" for row in cases)
            and answer_sent == 9 and 0 < summary_sent <= 12 and sent <= REQUEST_LIMIT
            and len(schema_digests) == 1 and len(prefix_digests) == 1
            and all(row["external_mcp_calls"] == 0 and row["local_tool_observations"] == 0 for row in cases)
            and all(slot.get("transport") == "httpx.MockTransport" for slot in ledger.state["slots"] if slot.get("request_digest"))
            and not ledger.state.get("stop_reason")
        )
        results = {
            "schema_version": 1,
            "task": TASK,
            "status": "PASS" if passed else "FAIL",
            "evidence_level": "FIXTURE_AND_MOCK_PROVIDER_TRANSPORT",
            "base_sha": BASE_SHA,
            "execution_id": execution_id,
            "questions_file_sha256": questions_file_sha,
            "history_digest_sha256": history_digest,
            "history_rows": len(history),
            "cases": cases,
            "provider_requests_sent": sent,
            "summary_requests_sent": summary_sent,
            "answer_requests_sent": answer_sent,
            "external_provider_requests": 0,
            "provider_cost_usd": "0.00",
            "global_hard_cap_usd_micro": HARD_CAP_USD_MICRO,
            "global_request_limit": REQUEST_LIMIT,
            "tool_schema_digests": sorted(schema_digests),
            "system_prompt_prefix_digests": sorted(prefix_digests),
            "gold_sent": False,
            "tool_choice_none_for_all_answers": all(row["answer_tool_choice"] == "none" for row in cases),
            "no_external_mcp_calls": all(row["external_mcp_calls"] == 0 for row in cases),
            "no_fixture_answer_entered_another_case": True,
            "stop_reason": ledger.state.get("stop_reason"),
        }
        if output_dir is not None:
            _write_mock_outputs(out, results, trace_path, ledger)
        else:
            trace_path.unlink(missing_ok=True)
        if tmp_output is not None:
            tmp_output.cleanup()
        temp_ledger_path.unlink(missing_ok=True)
        return results
    except BaseException:
        ledger.stop("MOCK_RUN_FAILED")
        temp_ledger_path.unlink(missing_ok=True)
        if tmp_output is not None:
            tmp_output.cleanup()
        raise


async def _run_case_with_mock_factory(*, case_root: Path, case_id: str, question_id: str,
                                      group: str, strategy: str, question_row: dict[str, Any],
                                      history: list[dict[str, Any]], history_digest: str,
                                      config: dict[str, str], ledger: GlobalBudgetLedger,
                                      trace_path: Path, transport_factory) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    # This function mirrors the accepted Setup-HF01 run path while inserting
    # only the task-local global budget wrapper and a selected transport.
    import pytest
    from opspilot.assistant import create_assistant_model, run_assistant
    from opspilot.domain.assistant_runtime_grant import bind_run, validate_run_binding, spend_summary
    from opspilot.domain.chat import get_chat_manifest
    from opspilot.domain.database import connect

    setup = _setup_harness()
    db_path = case_root / "domain.sqlite3"
    checkpoint_path = case_root / "checkpoint.sqlite3"
    owner = f"abc-live-mock-{case_id}-{uuid.uuid4().hex[:8]}"
    case_root.mkdir(parents=True, exist_ok=False)
    patch = pytest.MonkeyPatch()
    model = None
    budgeted = None
    calls: list[dict[str, Any]] = []
    try:
        _set_case_environment(patch, config, strategy, "offline-only-not-a-real-key")
        session_id, run_id, worker_epoch, identity = setup._seed_domain(
            db_path, owner, history, str(question_row["prompt_text"]),
        )
        patch.setenv("OPSPILOT_CONTEXT_STRATEGY", strategy)
        grant = _grant_for_case(db_path, config, case_id, ledger.state["execution_id"])
        binding = bind_run(db_path, run_id, _case_config_from_env())
        validated = validate_run_binding(db_path, run_id, binding, _case_config_from_env())
        inner, calls = transport_factory(db_path, run_id)
        budgeted = BudgetedAsyncTransport(
            inner=inner, ledger=ledger, case_id=case_id, mode="MOCK",
            trace_path=trace_path, secret="offline-only-not-a-real-key", question_row=question_row,
            expected_endpoint=config["endpoint"],
        )
        sync_forbidden = httpx.MockTransport(
            lambda _request: (_ for _ in ()).throw(AssertionError("sync Provider transport forbidden"))
        )
        model = create_assistant_model(
            runtime_grant_binding=binding, transport_async=budgeted,
            transport_sync=sync_forbidden,
        )
        if model is None or validated["database_file_identity"] != binding["database_file_identity"]:
            raise RunnerStop("MOCK_RUNTIME_GRANT_BINDING_FAILED")
        assistant_trace: list[dict[str, Any]] = []
        run_result = await run_assistant(
            db_path, checkpoint_path, owner, run_id, model=model,
            runtime_grant_binding=binding, worker_epoch=worker_epoch,
            tool_choice_override="none",
            trace=lambda event, **fields: assistant_trace.append({"event": event, **fields}),
        )
        manifest = get_chat_manifest(db_path, identity, run_id)
        answer_calls = [call for call in budgeted.calls if call["purpose"] == "ANSWER"]
        summary_calls = [call for call in budgeted.calls if call["purpose"] == "SUMMARY"]
        summary_attempts = manifest["compression_attempts"]
        observations = [event for event in assistant_trace if event.get("event") == "tool_observation"]
        if group == "C" and (summary_calls or summary_attempts):
            raise RunnerStop("RECENT_WINDOW_MUST_NOT_SUMMARIZE")
        if group in {"A", "B"} and not summary_calls:
            raise RunnerStop("SUMMARY_STRATEGY_DID_NOT_SUMMARIZE")
        if len(answer_calls) != 1 or len(summary_calls) > 2 or observations:
            raise RunnerStop("MOCK_CASE_CALL_OR_TOOL_BOUNDARY_FAILED")
        with connect(db_path) as connection:
            rows = connection.execute(
                "SELECT sequence, role, body FROM messages WHERE session_id=? ORDER BY sequence", (session_id,),
            ).fetchall()
        seeded = [str(row["body"]) for row in rows[:29]]
        if seeded != [str(row["body"]) for row in history]:
            raise RunnerStop("MOCK_HISTORY_SEED_MISMATCH")
        answer_request = answer_calls[0]["request_payload"]
        system_text = "\n".join(str(message.get("content", "")) for message in answer_request.get("messages", [])
                                 if message.get("role") == "system")
        prefix = system_text.split("\nWORK_CONTEXT\n", 1)[0]
        record = {
            "case_id": case_id, "question_id": question_id, "group": group,
            "strategy": strategy, "status": run_result.get("status"),
            "evidence_level": "FIXTURE_AND_MOCK_PROVIDER_TRANSPORT",
            "domain_instance_sha256": sha256(str(db_path.resolve())),
            "checkpoint_instance_sha256": sha256(str(checkpoint_path.resolve())),
            "history_digest_sha256": history_digest, "history_rows": len(seeded),
            "domain_db_isolated": True, "checkpoint_isolated": True,
            "runtime_grant_status": grant["status"],
            "runtime_grant_case_limit_usd_micro": int(grant["total_limit_usd_micro"]),
            "runtime_binding_database_identity_matches": True,
            "runtime_spend_summary": spend_summary(db_path),
            "configured_input_limit_tokens": int(manifest["context_budget"]["configured_input_limit_tokens"]),
            "effective_context_input_budget_tokens": int(manifest["context_budget"]["input_budget_tokens"]),
            "summary_attempt_count": len(summary_attempts),
            "summary_attempts": summary_attempts,
            "summary_calls": len(summary_calls), "answer_calls": len(answer_calls),
            "answer_tool_choice": answer_request.get("tool_choice"),
            "answer_request_digest": answer_calls[0]["request_body_sha256"],
            "answer_message_count": len(answer_request.get("messages", [])),
            "answer_context_blocks": manifest["attempts"][-1]["manifest"].get("context_blocks") if manifest["attempts"] else [],
            "summary_refs": manifest["summary_refs"],
            "tool_schema_sha256": sha256(canonical(answer_request.get("tools", []))),
            "system_prompt_prefix_sha256": sha256(prefix),
            "external_mcp_calls": 0, "local_tool_observations": len(observations),
            "gold_payload_serialized": False, "scoring_rule_serialized": False,
            "semantic_assessment": "NOT_SCORED_MOCK_OUTPUT",
            "answer_response": answer_calls[0]["response_payload"]["choices"][0]["message"]["content"],
        }
        calls.append({"case_id": case_id, "calls": calls[:]})
        return record, calls
    finally:
        if model is not None:
            try:
                await model.http_async_client.aclose()
            finally:
                model.http_client.close()
        elif budgeted is not None:
            await budgeted.aclose()
        patch.undo()


def _prepare_preflight_grant(config: dict[str, str], api_key: str) -> dict[str, Any]:
    import pytest
    from opspilot.assistant import create_assistant_model
    from opspilot.domain.assistant_runtime_grant import bind_run, validate_run_binding
    from opspilot.domain.database import connect

    history, questions, _, _ = load_frozen_inputs()
    with tempfile.TemporaryDirectory(prefix="opspilot-abc-preflight-") as temp:
        root = Path(temp)
        db_path = root / "domain.sqlite3"
        checkpoint_path = root / "checkpoint.sqlite3"
        patch = pytest.MonkeyPatch()
        model = None
        try:
            _set_case_environment(patch, config, STRATEGIES["A"], api_key)
            setup = _setup_harness()
            _, run_id, _, _ = setup._seed_domain(
                db_path, "abc-live-preflight", history, str(questions["Q02"]["prompt_text"]),
            )
            patch.setenv("OPSPILOT_CONTEXT_STRATEGY", STRATEGIES["A"])
            grant = _grant_for_case(db_path, config, "Q02-A", "preflight")
            binding = bind_run(db_path, run_id, _case_config_from_env())
            validated = validate_run_binding(db_path, run_id, binding, _case_config_from_env())
            sends: list[int] = []
            def forbidden(_request: httpx.Request) -> httpx.Response:
                sends.append(1)
                raise AssertionError("preflight transport must never send")
            model = create_assistant_model(
                runtime_grant_binding=binding,
                transport_async=httpx.MockTransport(forbidden),
                transport_sync=httpx.MockTransport(forbidden),
            )
            if model is None:
                raise RunnerStop("PREFLIGHT_ASSISTANT_MODEL_CONSTRUCTION_FAILED")
            with connect(db_path) as connection:
                db_id = str(connection.execute(
                    "SELECT database_file_identity FROM assistant_runtime_authority WHERE singleton=1"
                ).fetchone()[0])
            return {
                "runtime_grant_created_in_isolated_temporary_database": True,
                "runtime_grant_bindable": validated["database_file_identity"] == binding["database_file_identity"] == db_id,
                "runtime_grant_case_limit_usd_micro": int(grant["total_limit_usd_micro"]),
                "assistant_model_constructed_with_mock_transports": True,
                "provider_transport_invocations": len(sends),
                "provider_requests_sent": 0,
                "production_database_opened": False,
            }
        finally:
            if model is not None:
                try:
                    asyncio.run(model.http_async_client.aclose())
                finally:
                    model.http_client.close()
            patch.undo()


def run_zero_cost_preflight(*, mock_runner_passed: bool,
                            output_path: Path | None = None) -> dict[str, Any]:
    env_report = load_main_environment(emit_presence=True)
    result: dict[str, Any] = {
        "schema_version": 1,
        "task": TASK,
        "base_sha": BASE_SHA,
        "checked_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "evidence_level": "STATIC_SOURCE_PLUS_FIXTURE_MOCK_AND_ZERO_COST_RUNTIME_PREFLIGHT",
        "main_repo_env_found": env_report["main_repo_env_found"],
        "main_repo_env_loaded": env_report["environment_loaded_from_main_repo_env"],
        "required_presence_after_load": env_report["required_presence_after_load"],
        "effective_required_presence_after_non_secret_supplement": env_report["effective_required_presence"],
        "supplemented_non_secret_configuration": env_report["supplemented_non_secret_configuration"],
        "api_key_present": env_report["api_key_present"],
        "runtime_config_valid": env_report["runtime_config_valid"],
        "runtime_config_sha256": env_report["runtime_config_sha256"],
        "mock_full_runner_passed": mock_runner_passed,
        "runtime_grant_bindable": False,
        "assistant_model_constructed_with_mock_transports": False,
        "provider_requests_sent": 0,
        "provider_cost_usd": "0.00",
        "real_provider_send_condition": False,
        "error": env_report.get("error"),
    }
    if not mock_runner_passed:
        result["error"] = "MOCK_RUNNER_DID_NOT_PASS"
    elif env_report["api_key_present"] and env_report["runtime_config_valid"]:
        try:
            config = _case_config_from_env()
            grant_result = _prepare_preflight_grant(
                config, os.environ["OPSPILOT_MODEL_API_KEY"],
            )
            result.update(grant_result)
            result["runtime_grant_bindable"] = bool(grant_result["runtime_grant_bindable"])
            result["assistant_model_constructed_with_mock_transports"] = bool(
                grant_result["assistant_model_constructed_with_mock_transports"]
            )
            required_ok = all(result["effective_required_presence_after_non_secret_supplement"].values())
            result["real_provider_send_condition"] = bool(
                required_ok and result["runtime_grant_bindable"]
                and result["assistant_model_constructed_with_mock_transports"]
                and grant_result["provider_transport_invocations"] == 0
            )
            if not result["real_provider_send_condition"]:
                result["error"] = "ZERO_COST_GRANT_BINDING_OR_CONFIGURATION_CHECK_FAILED"
        except Exception as error:
            result["error"] = str(getattr(error, "code", None) or type(error).__name__)
    if output_path is not None:
        if output_path.exists():
            existing = json.loads(output_path.read_text(encoding="utf-8"))
            comparable = {key: value for key, value in result.items() if key != "checked_at_utc"}
            old_comparable = {key: value for key, value in existing.items() if key != "checked_at_utc"}
            if comparable != old_comparable:
                raise RunnerStop("PREFLIGHT_EVIDENCE_EXISTS_AND_CHANGED_REFUSE_OVERWRITE")
        else:
            atomic_json(output_path, result)
    return result


def _empty_live_results(execution_id: str) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "task": TASK,
        "execution_id": execution_id,
        "status": "IN_PROGRESS",
        "evidence_level": "REAL_PROVIDER_PENDING",
        "base_sha": BASE_SHA,
        "planned_case_count": 9,
        "provider_request_limit": REQUEST_LIMIT,
        "provider_requests_sent": 0,
        "summary_requests_sent": 0,
        "answer_requests_sent": 0,
        "provider_cost_usd": "0.00",
        "stop_reason": None,
        "independent_main_agent_review": "NOT_PERFORMED",
        "rows": [
            {"question_id": qid, "group": group, "strategy": STRATEGIES[group],
             "status": "NOT_STARTED", "evidence_level": "NO_LIVE_PROVIDER_EVIDENCE",
             "response": None, "score_category": None,
             "manual_semantic_review": "IMPLEMENTER_PRELIMINARY_REVIEW_PENDING",
             "provider_request_ids": [], "usage": [], "error": None}
            for qid in QUESTION_IDS for group in GROUPS
        ],
    }


def run_live_suite(*, mock_runner_passed: bool, output_dir: Path) -> dict[str, Any]:
    """Run serial live ABC only after a fresh Mock and zero-cost preflight."""
    preflight_path = output_dir / "PREFLIGHT.json"
    preflight = run_zero_cost_preflight(mock_runner_passed=mock_runner_passed, output_path=preflight_path)
    if not preflight["real_provider_send_condition"]:
        return {"status": "BLOCKED_BEFORE_PROVIDER_SEND", "preflight": preflight}
    if not mock_runner_passed:
        return {"status": "BLOCKED_MOCK_RUNNER_FAILED", "preflight": preflight}
    output_dir.mkdir(parents=True, exist_ok=True)
    ledger_path = output_dir / "COST_LEDGER.json"
    results_path = output_dir / "LIVE_RESULTS.json"
    trace_path = output_dir / "LIVE_REQUESTS.jsonl.gz"
    if ledger_path.exists():
        # A process crash may have left an in-flight slot. Persist that state as
        # UNKNOWN before refusing to reuse this execution or send any request.
        GlobalBudgetLedger.open_for_inspection(ledger_path)
    if ledger_path.exists() or results_path.exists() or trace_path.exists():
        raise RunnerStop("LIVE_EVIDENCE_ALREADY_EXISTS_REFUSE_REUSE_OR_RESEND")
    # Complete every local, read-only input/configuration check before creating
    # the durable live ledger, so setup failures cannot look like a send run.
    history, questions, history_digest, questions_file_sha = load_frozen_inputs()
    config = _case_config_from_env()
    api_key = os.environ["OPSPILOT_MODEL_API_KEY"]
    execution_id = "live-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]
    ledger = GlobalBudgetLedger.create(ledger_path, execution_id=execution_id, mode="LIVE")
    results = _empty_live_results(execution_id)
    atomic_json(results_path, results)
    results["questions_file_sha256"] = questions_file_sha
    results["history_digest_sha256"] = history_digest
    results["history_rows_per_case"] = len(history)
    overall_status = "COMPLETED"
    try:
        with tempfile.TemporaryDirectory(prefix="opspilot-abc-live-cases-") as cases_tmp:
            case_root = Path(cases_tmp)
            for question_id in QUESTION_IDS:
                for group in GROUPS:
                    case_id = f"{question_id}-{group}"
                    row = next(item for item in results["rows"] if item["question_id"] == question_id and item["group"] == group)
                    row["status"] = "RUNNING"
                    atomic_json(results_path, results)
                    case_dir = case_root / case_id
                    try:
                        case_result = asyncio.run(_run_case(
                            case_root=case_dir, case_id=case_id, question_id=question_id,
                            group=group, strategy=STRATEGIES[group], question_row=questions[question_id],
                            history=history, history_digest=history_digest, config=config,
                            api_key=api_key, ledger=ledger, trace_path=trace_path,
                            mode="LIVE", mock_transport=None,
                        ))
                        row.update({
                            "status": case_result["status"],
                            "evidence_level": "REAL_PROVIDER",
                            "response": case_result["answer_response"],
                            "input_manifest": case_result,
                        })
                        if case_result["status"] != "SUCCEEDED":
                            ledger.stop("ASSISTANT_CASE_FAILED")
                            row["error"] = case_result.get("reason") or "ASSISTANT_CASE_FAILED"
                            overall_status = "STOPPED_AFTER_CASE_FAILURE"
                    except BaseException as error:
                        row["status"] = "FAILED_OR_UNKNOWN"
                        row["error"] = str(getattr(error, "code", None) or type(error).__name__)
                        if not ledger.state.get("stop_reason"):
                            ledger.stop(row["error"])
                        overall_status = "STOPPED_AFTER_ERROR"
                    sent_slots = [slot for slot in ledger.state["slots"] if slot.get("request_digest")]
                    row["provider_request_ids"] = [slot["provider_request_id"] for slot in sent_slots if slot["case_id"] == case_id and slot.get("provider_request_id")]
                    row["usage"] = [slot["usage"] for slot in sent_slots if slot["case_id"] == case_id and slot.get("usage")]
                    atomic_json(results_path, results)
                    if ledger.state.get("stop_reason"):
                        overall_status = "STOPPED_ON_FROZEN_STOP_CONDITION"
                        break
                if ledger.state.get("stop_reason"):
                    break
        ledger.finalize()
    except BaseException as error:
        if not ledger.state.get("stop_reason"):
            ledger.stop(str(getattr(error, "code", None) or type(error).__name__))
        ledger.finalize()
        overall_status = "STOPPED_AFTER_ERROR"
    cost = ledger.state["settled_usd_micro"] / 1_000_000
    results.update({
        "status": overall_status,
        "provider_requests_sent": ledger.state["provider_requests_started"],
        "summary_requests_sent": sum(1 for slot in ledger.state["slots"] if slot["purpose"] == "SUMMARY" and slot.get("request_digest")),
        "answer_requests_sent": sum(1 for slot in ledger.state["slots"] if slot["purpose"] == "ANSWER" and slot.get("request_digest")),
        "provider_cost_usd": f"{cost:.6f}",
        "reserved_unknown_usd_micro": ledger.state["currently_reserved_usd_micro"],
        "stop_reason": ledger.state.get("stop_reason"),
    })
    atomic_json(results_path, results)
    return results


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--mock", action="store_true")
    group.add_argument("--preflight", action="store_true")
    group.add_argument("--live", action="store_true")
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--mock-results", type=Path)
    args = parser.parse_args(argv)

    if args.mock:
        result = run_mock_suite(args.output_dir)
        print(json.dumps({key: value for key, value in result.items() if key != "cases"}, ensure_ascii=False, indent=2))
        return 0 if result["status"] == "PASS" else 2
    if args.preflight:
        mock_passed = False
        if args.mock_results and args.mock_results.is_file():
            mock_doc = json.loads(args.mock_results.read_text(encoding="utf-8"))
            mock_passed = mock_doc.get("task") == TASK and mock_doc.get("status") == "PASS" and mock_doc.get("external_provider_requests") == 0
        output_path = (args.output_dir or EVIDENCE_DIR / "live_run_01") / "PREFLIGHT.json"
        result = run_zero_cost_preflight(mock_runner_passed=mock_passed, output_path=output_path)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result["real_provider_send_condition"] else 3
    # The live entry point repeats the full MockTransport suite in a temporary
    # directory before loading the main .env or constructing any real transport.
    mock_result = run_mock_suite(None)
    if mock_result["status"] != "PASS":
        print(json.dumps({"status": "BLOCKED_MOCK_RUNNER_FAILED", "mock": {k: v for k, v in mock_result.items() if k != "cases"}}, indent=2))
        return 3
    output_dir = args.output_dir or EVIDENCE_DIR / "live_run_01"
    result = run_live_suite(mock_runner_passed=True, output_dir=output_dir)
    print(json.dumps(result if result.get("status", "").startswith("BLOCKED") else {
        "status": result.get("status"),
        "provider_requests_sent": result.get("provider_requests_sent"),
        "summary_requests_sent": result.get("summary_requests_sent"),
        "answer_requests_sent": result.get("answer_requests_sent"),
        "provider_cost_usd": result.get("provider_cost_usd"),
        "stop_reason": result.get("stop_reason"),
    }, ensure_ascii=False, indent=2))
    return 0 if result.get("status") == "COMPLETED" else 3


if __name__ == "__main__":
    raise SystemExit(main())
