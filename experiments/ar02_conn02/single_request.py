from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone
from decimal import Decimal, ROUND_CEILING
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import sys
import uuid
from typing import Any

import httpx
from langchain_core.messages import HumanMessage
from langchain_openai import ChatOpenAI


BASE_URL = "https://api.deepseek.com"
ENDPOINT = BASE_URL + "/chat/completions"
MODEL = "deepseek-flash"
PROMPT = "请只回复：OK"
MAX_TOKENS = 64
TIMEOUT_SECONDS = 30
RESERVE_MICRO_USD = 10_000
AUTHORIZATION_ID = "AR02-CONN02-20261101-01"
ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "docs" / "evidence" / "ar-02" / "conn-02"
ONE_SHOT_DB = EVIDENCE / "runs" / "authorization.sqlite3"
TRACE_PATH = EVIDENCE / "TRACE.jsonl"
PREFLIGHT_PROOF = EVIDENCE / "PREFLIGHT.json"


class StopBeforeSend(RuntimeError):
    pass


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sha256_hex(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def expected_body() -> dict[str, Any]:
    return {
        "model": MODEL,
        "messages": [{"role": "user", "content": PROMPT}],
        "thinking": {"type": "disabled"},
        "max_tokens": MAX_TOKENS,
        "stream": False,
    }


def validate_wire(request: httpx.Request) -> tuple[dict[str, Any], str]:
    if request.method != "POST":
        raise StopBeforeSend("METHOD_MISMATCH")
    if str(request.url) != ENDPOINT:
        raise StopBeforeSend("ENDPOINT_MISMATCH")
    try:
        body = json.loads(request.content)
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError) as exc:
        raise StopBeforeSend("REQUEST_BODY_NOT_JSON") from exc
    if body != expected_body():
        raise StopBeforeSend("REQUEST_BODY_MISMATCH")
    if request.headers.get("authorization", "").startswith("Bearer ") is False:
        raise StopBeforeSend("AUTHORIZATION_HEADER_MISSING")
    digest = sha256_hex(canonical_bytes(body))
    return body, digest


class TraceWriter:
    def __init__(self, path: Path, *, create: bool):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        mode = "x" if create else "a"
        self._file = path.open(mode, encoding="utf-8", newline="\n")

    def emit(self, event: str, **fields: Any) -> None:
        row = {"at": now_utc(), "event": event, **fields}
        self._file.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
        self._file.flush()
        os.fsync(self._file.fileno())

    def close(self) -> None:
        self._file.close()


class OneShotLedger:
    def __init__(self, path: Path):
        self.path = path

    def reserve_exclusive(self, body_digest: str) -> str:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        os.close(fd)
        attempt_id = "conn02-" + str(uuid.uuid4())
        connection = sqlite3.connect(self.path, timeout=5, isolation_level=None)
        try:
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("PRAGMA journal_mode=DELETE")
            connection.execute("PRAGMA synchronous=FULL")
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                """CREATE TABLE authorizations(
                    authorization_id TEXT PRIMARY KEY,
                    scope TEXT NOT NULL UNIQUE,
                    request_digest TEXT NOT NULL,
                    reserved_micro_usd INTEGER NOT NULL CHECK(reserved_micro_usd=10000),
                    created_utc TEXT NOT NULL
                )"""
            )
            connection.execute(
                """CREATE TABLE attempts(
                    attempt_id TEXT PRIMARY KEY,
                    authorization_id TEXT NOT NULL UNIQUE REFERENCES authorizations(authorization_id),
                    status TEXT NOT NULL CHECK(status IN
                      ('ATTEMPT_RESERVED','OUTBOUND_STARTED','PASS_CONNECTIVITY_ONLY',
                       'FAIL_STOPPED','UNKNOWN_STOPPED','BLOCKED_NOT_SENT')),
                    request_count INTEGER NOT NULL CHECK(request_count BETWEEN 0 AND 1),
                    request_digest TEXT NOT NULL,
                    created_utc TEXT NOT NULL,
                    updated_utc TEXT NOT NULL,
                    http_status INTEGER,
                    completion_id TEXT,
                    model_version TEXT,
                    output_text TEXT,
                    usage_json TEXT,
                    estimated_micro_usd INTEGER,
                    error_class TEXT,
                    error_detail TEXT
                )"""
            )
            created = now_utc()
            connection.execute(
                """INSERT INTO authorizations
                   (authorization_id,scope,request_digest,reserved_micro_usd,created_utc)
                   VALUES(?,?,?,?,?)""",
                (AUTHORIZATION_ID, "AR-02-CONN-02-ONE-COMPLETION", body_digest,
                 RESERVE_MICRO_USD, created),
            )
            connection.execute(
                """INSERT INTO attempts
                   (attempt_id,authorization_id,status,request_count,request_digest,created_utc,updated_utc)
                   VALUES(?,?, 'ATTEMPT_RESERVED', 0, ?, ?, ?)""",
                (attempt_id, AUTHORIZATION_ID, body_digest, created, created),
            )
            connection.execute("COMMIT")
            return attempt_id
        except BaseException:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise
        finally:
            connection.close()

    def mark_outbound_started(self, attempt_id: str, body_digest: str) -> None:
        connection = sqlite3.connect(self.path, timeout=5, isolation_level=None)
        try:
            connection.execute("PRAGMA synchronous=FULL")
            connection.execute("BEGIN IMMEDIATE")
            cursor = connection.execute(
                """UPDATE attempts SET status='OUTBOUND_STARTED',request_count=1,updated_utc=?
                   WHERE attempt_id=? AND authorization_id=? AND status='ATTEMPT_RESERVED'
                     AND request_count=0 AND request_digest=?""",
                (now_utc(), attempt_id, AUTHORIZATION_ID, body_digest),
            )
            if cursor.rowcount != 1:
                raise StopBeforeSend("PERSISTED_RESERVATION_NOT_AVAILABLE")
            connection.execute("COMMIT")
        except BaseException:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise
        finally:
            connection.close()

    def finish(
        self,
        attempt_id: str,
        status: str,
        *,
        http_status: int | None = None,
        completion_id: str | None = None,
        model_version: str | None = None,
        output_text: str | None = None,
        usage: dict[str, Any] | None = None,
        estimated_micro_usd: int | None = None,
        error_class: str | None = None,
        error_detail: str | None = None,
        expected_prior_status: str | None = None,
    ) -> None:
        connection = sqlite3.connect(self.path, timeout=5, isolation_level=None)
        try:
            connection.execute("PRAGMA synchronous=FULL")
            connection.execute("BEGIN IMMEDIATE")
            predicate = "status IN ('ATTEMPT_RESERVED','OUTBOUND_STARTED')"
            values = [status, now_utc(), http_status, completion_id, model_version, output_text,
                      json.dumps(usage, ensure_ascii=False, sort_keys=True) if usage is not None else None,
                      estimated_micro_usd, error_class, error_detail, attempt_id, AUTHORIZATION_ID]
            if expected_prior_status is not None:
                predicate = "status=?"
                values.append(expected_prior_status)
            cursor = connection.execute(
                f"""UPDATE attempts SET status=?,updated_utc=?,http_status=?,completion_id=?,
                   model_version=?,output_text=?,usage_json=?,estimated_micro_usd=?,
                   error_class=?,error_detail=?
                   WHERE attempt_id=? AND authorization_id=? AND {predicate}""",
                values,
            )
            if cursor.rowcount != 1:
                raise RuntimeError("ATTEMPT_FINALIZATION_CONFLICT")
            connection.execute("COMMIT")
        except BaseException:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise
        finally:
            connection.close()

    def snapshot(self) -> dict[str, Any]:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        try:
            auth = dict(connection.execute("SELECT * FROM authorizations").fetchone())
            attempt = dict(connection.execute("SELECT * FROM attempts").fetchone())
            return {"authorization": auth, "attempt": attempt}
        finally:
            connection.close()


def redact(value: Any, secret: str | None) -> Any:
    if isinstance(value, str):
        return value.replace(secret, "[REDACTED]") if secret else value
    if isinstance(value, list):
        return [redact(item, secret) for item in value]
    if isinstance(value, dict):
        return {key: redact(item, secret) for key, item in value.items()}
    return value


class WireCapture:
    def __init__(self, *, live: bool, trace: TraceWriter | None = None,
                 ledger: OneShotLedger | None = None, attempt_id: str | None = None,
                 secret: str | None = None):
        self.live = live
        self.trace = trace
        self.secret = secret
        self.ledger = ledger
        self.attempt_id = attempt_id
        self.request_count = 0
        self.outbound_marked = False
        self.responses: list[dict[str, Any]] = []
        self.raw_response: dict[str, Any] | None = None
        self.request_digest: str | None = None
        self.last_exception: BaseException | None = None

    async def on_request(self, request: httpx.Request) -> None:
        self.request_count += 1
        if self.request_count != 1:
            raise StopBeforeSend("MORE_THAN_ONE_HTTP_REQUEST")
        body, digest = validate_wire(request)
        self.request_digest = digest
        if self.live:
            if self.trace:
                self.trace.emit(
                    "http_request_pre_send_validated",
                    method=request.method,
                    endpoint=str(request.url),
                    body=body,
                    body_sha256=digest,
                    authorization_header="present_redacted",
                    request_number=1,
                )
            if self.ledger is None or self.attempt_id is None:
                raise StopBeforeSend("MISSING_PERSISTED_ATTEMPT")
            self.ledger.mark_outbound_started(self.attempt_id, digest)
            self.outbound_marked = True
            if self.trace:
                self.trace.emit("provider_transport_send_committed", request_number=1,
                                persisted_state="OUTBOUND_STARTED")
        elif self.trace:
            self.trace.emit(
                "mock_http_request",
                method=request.method,
                endpoint=str(request.url),
                body=body,
                body_sha256=digest,
                authorization_header="dummy_redacted",
                request_number=1,
                transport="HTTPX_MOCKTRANSPORT",
            )

    async def on_response(self, response: httpx.Response) -> None:
        await response.aread()
        try:
            parsed = response.json()
            if not isinstance(parsed, dict):
                parsed = {"response_json_type": type(parsed).__name__}
        except ValueError:
            parsed = {"unparsed_body_utf8": response.text[:4096]}
        parsed = redact(parsed, self.secret)
        self.raw_response = parsed
        request_id = response.headers.get("x-request-id") or response.headers.get("request-id")
        record = {
            "http_status": response.status_code,
            "content_type": response.headers.get("content-type"),
            "request_id": request_id,
            "body": parsed,
        }
        self.responses.append(record)
        if self.trace:
            self.trace.emit("http_response", **record)


def make_clients(
    *,
    transport_async: httpx.AsyncBaseTransport,
    transport_sync: httpx.BaseTransport,
    capture: WireCapture,
) -> tuple[httpx.AsyncClient, httpx.Client]:
    async_client = httpx.AsyncClient(
        timeout=httpx.Timeout(TIMEOUT_SECONDS),
        trust_env=False,
        follow_redirects=False,
        transport=transport_async,
        event_hooks={"request": [capture.on_request], "response": [capture.on_response]},
    )
    sync_client = httpx.Client(
        timeout=httpx.Timeout(TIMEOUT_SECONDS),
        trust_env=False,
        follow_redirects=False,
        transport=transport_sync,
    )
    return async_client, sync_client


def make_model(key: str, async_client: httpx.AsyncClient, sync_client: httpx.Client) -> ChatOpenAI:
    return ChatOpenAI(
        model=MODEL,
        base_url=BASE_URL,
        api_key=key,
        max_retries=0,
        timeout=TIMEOUT_SECONDS,
        temperature=None,
        streaming=False,
        http_async_client=async_client,
        http_client=sync_client,
        http_socket_options=(),
        extra_body={"thinking": {"type": "disabled"}, "max_tokens": MAX_TOKENS},
    )


def mock_completion() -> dict[str, Any]:
    return {
        "id": "mock-conn02-completion",
        "object": "chat.completion",
        "created": 1,
        "model": MODEL,
        "choices": [{
            "index": 0,
            "message": {"role": "assistant", "content": "OK"},
            "finish_reason": "stop",
        }],
        "usage": {"prompt_tokens": 9, "completion_tokens": 1, "total_tokens": 10},
    }


async def offline_preflight() -> dict[str, Any]:
    calls = {"count": 0}

    async def mock_handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        return httpx.Response(200, json=mock_completion(), request=request)

    capture = WireCapture(live=False)
    mock_async = httpx.MockTransport(mock_handler)
    mock_sync = httpx.MockTransport(lambda request: httpx.Response(500, request=request))
    async_client, sync_client = make_clients(
        transport_async=mock_async, transport_sync=mock_sync, capture=capture
    )
    try:
        model = make_model("offline-dummy-key", async_client, sync_client)
        message = await model.ainvoke([HumanMessage(content=PROMPT)])
        if calls["count"] != 1 or capture.request_count != 1 or len(capture.responses) != 1:
            raise StopBeforeSend("OFFLINE_TRANSPORT_CARDINALITY_MISMATCH")
        if str(capture.responses[0]["http_status"]) != "200" or message.content != "OK":
            raise StopBeforeSend("OFFLINE_SDK_ROUNDTRIP_FAILED")
        return {
            "status": "PASS_OFFLINE_PREFLIGHT",
            "evidence_level": "EXPLICIT_HTTPX_MOCKTRANSPORT_ONLY",
            "external_requests": 0,
            "mock_requests": calls["count"],
            "sdk_http_requests": capture.request_count,
            "endpoint": ENDPOINT,
            "body": expected_body(),
            "body_sha256": capture.request_digest,
            "response": capture.raw_response,
            "observed_model_output": message.content,
            "max_retries": 0,
            "timeout_seconds": TIMEOUT_SECONDS,
            "trust_env": False,
            "follow_redirects": False,
            "transport_retries": 0,
            "sender_source_sha256": sha256_hex(Path(__file__).read_bytes()),
        }
    finally:
        await async_client.aclose()
        sync_client.close()


def read_api_key(credential_file: Path | None) -> tuple[str | None, str]:
    value = os.environ.get("OPSPILOT_MODEL_API_KEY")
    if value and value.strip():
        return value.strip(), "process_environment"
    if credential_file is None or not credential_file.is_file():
        return None, "missing"
    matches: list[str] = []
    for line in credential_file.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        name, separator, raw = stripped.partition("=")
        if separator and name.strip() == "OPSPILOT_MODEL_API_KEY":
            candidate = raw.strip()
            if len(candidate) >= 2 and candidate[0] == candidate[-1] and candidate[0] in "\"'":
                candidate = candidate[1:-1]
            if candidate:
                matches.append(candidate)
    if len(matches) == 1:
        return matches[0], "designated_local_config"
    return None, "missing_or_ambiguous"


def peak_cost_micro_usd(usage: dict[str, Any]) -> int:
    prompt_tokens = usage.get("prompt_tokens")
    completion_tokens = usage.get("completion_tokens")
    total_tokens = usage.get("total_tokens")
    if any(type(v) is not int or v < 0 for v in
           (prompt_tokens, completion_tokens, total_tokens)):
        raise ValueError("USAGE_FIELDS_INVALID")
    if prompt_tokens + completion_tokens != total_tokens:
        raise ValueError("USAGE_TOTAL_MISMATCH")
    # USD 0.30/M input and USD 1.20/M output, represented in micro-USD.
    micro = Decimal(prompt_tokens) * Decimal("0.30") + Decimal(completion_tokens) * Decimal("1.20")
    return int(micro.to_integral_value(rounding=ROUND_CEILING))


def completion_summary(capture: WireCapture, message: Any) -> dict[str, Any]:
    raw = capture.raw_response or {}
    choices = raw.get("choices")
    choice = choices[0] if isinstance(choices, list) and len(choices) == 1 else {}
    raw_message = choice.get("message") if isinstance(choice, dict) else {}
    raw_message = raw_message if isinstance(raw_message, dict) else {}
    usage = raw.get("usage")
    output = raw_message.get("content")
    completion_id = raw.get("id")
    model_version = raw.get("model")
    errors: list[str] = []
    if len(capture.responses) != 1:
        errors.append("HTTP_RESPONSE_CARDINALITY_NOT_ONE")
    response = capture.responses[0] if len(capture.responses) == 1 else {}
    if response.get("http_status") != 200:
        errors.append("HTTP_STATUS_NOT_200")
    if raw.get("object") != "chat.completion":
        errors.append("COMPLETION_OBJECT_INVALID")
    if not isinstance(completion_id, str) or not completion_id:
        errors.append("COMPLETION_ID_MISSING")
    if not isinstance(model_version, str) or not model_version:
        errors.append("MODEL_VERSION_MISSING")
    if not isinstance(output, str) or not output.strip():
        errors.append("MODEL_OUTPUT_MISSING")
    if not isinstance(usage, dict):
        errors.append("USAGE_MISSING")
        estimated = None
    else:
        try:
            estimated = peak_cost_micro_usd(usage)
        except ValueError as error:
            errors.append(str(error))
            estimated = None
    if choice.get("finish_reason") != "stop":
        errors.append("COMPLETION_NOT_STOPPED_NORMALLY")
    return {
        "valid": not errors,
        "errors": errors,
        "http_status": response.get("http_status"),
        "request_id": response.get("request_id"),
        "completion_id": completion_id,
        "model_version": model_version,
        "system_fingerprint": raw.get("system_fingerprint"),
        "output": output,
        "output_matches_requested_ok": isinstance(output, str) and output.strip() == "OK",
        "usage": usage,
        "peak_cost_estimate_micro_usd": estimated,
        "peak_cost_estimate_usd": (
            str((Decimal(estimated) / Decimal(1_000_000)).quantize(Decimal("0.000001")))
            if estimated is not None else None
        ),
        "sdk_output": redact(message.content, capture.secret) if message is not None else None,
    }


def validate_proof(proof_path: Path, source_path: Path | None = None) -> tuple[dict[str, Any] | None, str | None]:
    if not proof_path.is_file():
        return None, "OFFLINE_PREFLIGHT_PROOF_MISSING"
    proof = json.loads(proof_path.read_text(encoding="utf-8"))
    if proof.get("status") != "PASS_OFFLINE_PREFLIGHT" or proof.get("body") != expected_body():
        return None, "OFFLINE_PREFLIGHT_PROOF_MISMATCH"
    if proof.get("body_sha256") != sha256_hex(canonical_bytes(expected_body())):
        return None, "OFFLINE_PREFLIGHT_DIGEST_MISMATCH"
    source = source_path or Path(__file__)
    if proof.get("sender_source_sha256") != sha256_hex(source.read_bytes()):
        return None, "SENDER_CHANGED_AFTER_PREFLIGHT"
    return proof, None


async def reserve_only(credential_file: Path | None, proof_path: Path) -> dict[str, Any]:
    proof, reason = validate_proof(proof_path)
    if proof is None:
        return {"status": "BLOCKED_NOT_SENT", "reason": reason}
    key, key_source = read_api_key(credential_file)
    if not key:
        return {"status": "BLOCKED_NOT_SENT", "reason": "MODEL_CREDENTIAL_MISSING"}
    if ONE_SHOT_DB.exists() or TRACE_PATH.exists():
        return {"status": "BLOCKED_NOT_SENT", "reason": "ONE_SHOT_PATH_ALREADY_EXISTS"}
    ledger = OneShotLedger(ONE_SHOT_DB)
    try:
        attempt_id = ledger.reserve_exclusive(proof["body_sha256"])
    except FileExistsError:
        return {"status": "BLOCKED_NOT_SENT", "reason": "AUTHORIZATION_ID_ALREADY_USED"}
    trace = TraceWriter(TRACE_PATH, create=True)
    trace.emit(
        "authorization_reserved",
        authorization_id=AUTHORIZATION_ID,
        attempt_id=attempt_id,
        request_digest=proof["body_sha256"],
        status="ATTEMPT_RESERVED",
        reserved_micro_usd=RESERVE_MICRO_USD,
        credential_source=key_source,
        credential_value="never_logged",
    )
    trace.close()
    return {
        "status": "ATTEMPT_RESERVED",
        "authorization_id": AUTHORIZATION_ID,
        "attempt_id": attempt_id,
        "request_digest": proof["body_sha256"],
        "reserved_micro_usd": RESERVE_MICRO_USD,
        "outbound_requests": 0,
        "ledger": ledger.snapshot(),
    }


async def send_once(credential_file: Path | None, proof_path: Path) -> dict[str, Any]:
    proof, reason = validate_proof(proof_path)
    if proof is None:
        return {"status": "BLOCKED_NOT_SENT", "reason": reason}
    if not ONE_SHOT_DB.is_file() or not TRACE_PATH.is_file():
        return {"status": "BLOCKED_NOT_SENT", "reason": "DURABLE_RESERVATION_MISSING"}
    ledger = OneShotLedger(ONE_SHOT_DB)
    snapshot = ledger.snapshot()
    attempt_id = snapshot["attempt"]["attempt_id"]
    prior = snapshot["attempt"]["status"]
    if (snapshot["authorization"]["authorization_id"] != AUTHORIZATION_ID
            or snapshot["authorization"]["reserved_micro_usd"] != RESERVE_MICRO_USD
            or snapshot["authorization"]["request_digest"] != proof["body_sha256"]
            or snapshot["attempt"]["request_digest"] != proof["body_sha256"]):
        return {"status": "BLOCKED_NOT_SENT", "reason": "PERSISTED_RESERVATION_MISMATCH"}
    if prior == "OUTBOUND_STARTED":
        return {
            "status": "UNKNOWN_STOPPED",
            "reason": "PRIOR_OUTBOUND_STARTED_DO_NOT_RETRY",
            "attempt_id": attempt_id,
            "ledger": snapshot,
        }
    if prior != "ATTEMPT_RESERVED" or snapshot["attempt"]["request_count"] != 0:
        return {
            "status": prior if prior in {
                "PASS_CONNECTIVITY_ONLY", "FAIL_STOPPED", "UNKNOWN_STOPPED", "BLOCKED_NOT_SENT"
            } else "BLOCKED_NOT_SENT",
            "reason": "ONE_SHOT_AUTHORIZATION_ALREADY_CONSUMED",
            "attempt_id": attempt_id,
            "ledger": snapshot,
        }
    prior_trace = [json.loads(line) for line in TRACE_PATH.read_text(encoding="utf-8").splitlines() if line]
    if len(prior_trace) != 1 or prior_trace[0].get("event") != "authorization_reserved":
        ledger.finish(attempt_id, "BLOCKED_NOT_SENT", error_class="TRACE_NOT_PRISTINE",
                      expected_prior_status="ATTEMPT_RESERVED")
        return {
            "status": "BLOCKED_NOT_SENT",
            "reason": "TRACE_NOT_PRISTINE",
            "attempt_id": attempt_id,
            "ledger": ledger.snapshot(),
        }
    key, key_source = read_api_key(credential_file)
    if not key:
        ledger.finish(attempt_id, "BLOCKED_NOT_SENT", error_class="MODEL_CREDENTIAL_MISSING",
                      expected_prior_status="ATTEMPT_RESERVED")
        trace = TraceWriter(TRACE_PATH, create=False)
        trace.emit("blocked_not_sent", reason="MODEL_CREDENTIAL_MISSING")
        trace.close()
        return {
            "status": "BLOCKED_NOT_SENT",
            "reason": "MODEL_CREDENTIAL_MISSING",
            "attempt_id": attempt_id,
            "ledger": ledger.snapshot(),
        }
    trace = TraceWriter(TRACE_PATH, create=False)
    trace.emit("send_authorized_from_persisted_reservation",
               authorization_id=AUTHORIZATION_ID, attempt_id=attempt_id,
               credential_source=key_source, credential_value="never_logged")
    capture = WireCapture(live=True, trace=trace, ledger=ledger,
                          attempt_id=attempt_id, secret=key)
    transport_async = httpx.AsyncHTTPTransport(retries=0)
    transport_sync = httpx.HTTPTransport(retries=0)
    async_client, sync_client = make_clients(
        transport_async=transport_async, transport_sync=transport_sync, capture=capture
    )
    message = None
    final_status = "BLOCKED_NOT_SENT"
    details: dict[str, Any] = {}
    try:
        model = make_model(key, async_client, sync_client)
        message = await model.ainvoke([HumanMessage(content=PROMPT)])
        details = completion_summary(capture, message)
        if details["valid"]:
            final_status = "PASS_CONNECTIVITY_ONLY"
        elif capture.outbound_marked and len(capture.responses) == 1:
            final_status = "FAIL_STOPPED"
        elif capture.outbound_marked:
            final_status = "UNKNOWN_STOPPED"
    except BaseException as error:
        error_detail = str(error).replace(key, "[REDACTED]")
        if not capture.outbound_marked:
            final_status = "BLOCKED_NOT_SENT"
        elif len(capture.responses) == 1:
            final_status = "FAIL_STOPPED"
        else:
            final_status = "UNKNOWN_STOPPED"
        details = {
            "error_class": type(error).__name__,
            "error_detail_redacted": error_detail[:1000],
            "request_hook_count": capture.request_count,
            "response_hook_count": len(capture.responses),
        }
    finally:
        await async_client.aclose()
        sync_client.close()
    expected_prior_status = "OUTBOUND_STARTED" if capture.outbound_marked else "ATTEMPT_RESERVED"
    try:
        if final_status in {"PASS_CONNECTIVITY_ONLY", "FAIL_STOPPED"}:
            usage = details.get("usage") if isinstance(details.get("usage"), dict) else None
            ledger.finish(
                attempt_id,
                final_status,
                http_status=details.get("http_status"),
                completion_id=details.get("completion_id"),
                model_version=details.get("model_version"),
                output_text=details.get("output"),
                usage=usage,
                estimated_micro_usd=details.get("peak_cost_estimate_micro_usd"),
                error_class=";".join(details.get("errors", [])) or None,
                error_detail=details.get("error_detail_redacted"),
                expected_prior_status=expected_prior_status,
            )
        elif final_status == "UNKNOWN_STOPPED":
            ledger.finish(
                attempt_id, final_status,
                http_status=(capture.responses[0]["http_status"] if capture.responses else None),
                error_class=details.get("error_class", "UNKNOWN"),
                error_detail=details.get("error_detail_redacted", "OUTBOUND_RESULT_UNKNOWN"),
                expected_prior_status=expected_prior_status,
            )
        else:
            ledger.finish(
                attempt_id, final_status,
                error_class=details.get("error_class", "PRE_SEND_BLOCK"),
                error_detail=details.get("error_detail_redacted", details.get("reason", "NOT_SENT")),
                expected_prior_status=expected_prior_status,
            )
    except RuntimeError:
        # A concurrent sender may already own the single dispatch. Never overwrite its state.
        concurrent = ledger.snapshot()
        state = concurrent["attempt"]["status"]
        if state == "OUTBOUND_STARTED":
            final_status = "UNKNOWN_STOPPED"
        elif state in {"PASS_CONNECTIVITY_ONLY", "FAIL_STOPPED", "UNKNOWN_STOPPED", "BLOCKED_NOT_SENT"}:
            final_status = state
        details["ledger_finalization_conflict"] = "PERSISTED_STATE_WON"
    final_snapshot = ledger.snapshot()
    trace.emit("final_result", status=final_status, details=details,
               local_request_hook_count=capture.request_count,
               persisted_outbound_count=final_snapshot["attempt"]["request_count"],
               response_count=len(capture.responses))
    trace.close()
    return {
        "status": final_status,
        "authorization_id": AUTHORIZATION_ID,
        "attempt_id": attempt_id,
        "reserved_micro_usd": RESERVE_MICRO_USD,
        "local_request_hook_count": capture.request_count,
        "persisted_outbound_count": final_snapshot["attempt"]["request_count"],
        "response_count": len(capture.responses),
        "details": details,
        "ledger": final_snapshot,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--offline-preflight", action="store_true")
    group.add_argument("--reserve-only", action="store_true")
    group.add_argument("--send-once", action="store_true")
    parser.add_argument("--credential-file", type=Path)
    parser.add_argument("--preflight-proof", type=Path, default=PREFLIGHT_PROOF)
    args = parser.parse_args()
    if args.offline_preflight:
        result = asyncio.run(offline_preflight())
        if result["status"] == "PASS_OFFLINE_PREFLIGHT":
            try:
                with args.preflight_proof.open("x", encoding="utf-8", newline="\n") as stream:
                    json.dump(result, stream, ensure_ascii=False, sort_keys=True, indent=2)
                    stream.write("\n")
            except FileExistsError:
                result = {"status": "PREFLIGHT_PROOF_ALREADY_EXISTS", "proof": str(args.preflight_proof)}
        print(json.dumps(result, ensure_ascii=True, indent=2))
        return 0 if result["status"] == "PASS_OFFLINE_PREFLIGHT" else 2
    if args.reserve_only:
        result = asyncio.run(reserve_only(args.credential_file, args.preflight_proof))
        print(json.dumps(result, ensure_ascii=True, indent=2))
        return 0 if result["status"] == "ATTEMPT_RESERVED" else 2
    result = asyncio.run(send_once(args.credential_file, args.preflight_proof))
    print(json.dumps(result, ensure_ascii=True, indent=2))
    return 0 if result["status"] == "PASS_CONNECTIVITY_ONLY" else 2


if __name__ == "__main__":
    sys.exit(main())
