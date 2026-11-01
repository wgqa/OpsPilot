"""One authorized DeepSeek request using Python's stdlib urllib, no SDK/HTTPX."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from decimal import Decimal, ROUND_CEILING
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import ssl
import sys
import uuid
from urllib.error import HTTPError, URLError
from urllib.request import (
    HTTPSHandler,
    HTTPRedirectHandler,
    ProxyHandler,
    Request,
    build_opener,
)


BASE_URL = "https://api.deepseek.com/v1"
ENDPOINT = BASE_URL + "/chat/completions"
MODEL = "deepseek-flash"
PROMPT = "请只回复：OK"
MAX_TOKENS = 64
TIMEOUT_SECONDS = 30
RESERVED_MICRO_USD = 10_000
AUTHORIZATION_ID = "AR-02-LIVE-CONNECTION-DIAG-03-20261101-01"
SCOPE = "AR-02-LIVE-CONNECTION-DIAG-03-ONE-URLLIB-POST"
ROOT = Path(__file__).resolve().parents[4]
EVIDENCE = Path(__file__).resolve().parent
RUNS = EVIDENCE / "runs"
DB_PATH = RUNS / "authorization.sqlite3"
TRACE_PATH = EVIDENCE / "TRACE.jsonl"
PROOF_PATH = EVIDENCE / "PREFLIGHT_PROOF.json"
CREDENTIAL_FILE = Path(r"D:\学习\agent新项目\.env")


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def canonical_bytes(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":")).encode("utf-8")


def digest_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def expected_body() -> dict[str, object]:
    return {
        "model": MODEL,
        "messages": [{"role": "user", "content": PROMPT}],
        "thinking": {"type": "disabled"},
        "max_tokens": MAX_TOKENS,
        "stream": False,
    }


def build_request(key: str) -> tuple[Request, str]:
    body = canonical_bytes(expected_body())
    request = Request(
        ENDPOINT,
        data=body,
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )
    if request.full_url != ENDPOINT or request.get_method() != "POST":
        raise RuntimeError("WIRE_ENDPOINT_OR_METHOD_MISMATCH")
    try:
        parsed = json.loads(request.data)
    except (TypeError, json.JSONDecodeError) as exc:
        raise RuntimeError("WIRE_BODY_NOT_JSON") from exc
    if parsed != expected_body():
        raise RuntimeError("WIRE_BODY_MISMATCH")
    if not any(name.lower() == "authorization" for name, _ in request.header_items()):
        raise RuntimeError("AUTHORIZATION_HEADER_MISSING")
    return request, digest_bytes(body)


def read_api_key(path: Path) -> tuple[str | None, str]:
    if not path.is_file():
        return None, "MISSING"
    values: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        name, separator, raw = stripped.partition("=")
        if separator and name.strip() == "OPSPILOT_MODEL_API_KEY":
            value = raw.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                value = value[1:-1]
            if value:
                values.append(value)
    if len(values) != 1:
        return None, "MISSING_OR_AMBIGUOUS"
    return values[0], "DESIGNATED_LOCAL_CONFIG"


def redact(value: str, secret: str) -> str:
    return value.replace(secret, "[REDACTED]") if secret else value


def redact_json(value: object, secret: str) -> object:
    if isinstance(value, str):
        return redact(value, secret)
    if isinstance(value, list):
        return [redact_json(item, secret) for item in value]
    if isinstance(value, dict):
        return {str(key): redact_json(item, secret) for key, item in value.items()}
    return value


def emit(event: str, **fields: object) -> None:
    RUNS.mkdir(parents=True, exist_ok=True)
    row = {"at": now_utc(), "event": event, **fields}
    with TRACE_PATH.open("a", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


def offline_preflight() -> dict[str, object]:
    request, body_hash = build_request("offline-dummy")
    result = {
        "status": "PASS_OFFLINE_PREFLIGHT",
        "transport": "NO_NETWORK_REQUEST_CONSTRUCTION_ONLY",
        "external_requests": 0,
        "url": request.full_url,
        "method": request.get_method(),
        "body": expected_body(),
        "body_sha256": body_hash,
        "authorization_header": "present_redacted",
        "max_requests": 1,
        "timeout_seconds": TIMEOUT_SECONDS,
        "retries": 0,
        "redirects": False,
        "proxy": "disabled",
        "sender_source_sha256": digest_bytes(Path(__file__).read_bytes()),
    }
    if PROOF_PATH.exists():
        raise RuntimeError("PREFLIGHT_PROOF_ALREADY_EXISTS")
    PROOF_PATH.parent.mkdir(parents=True, exist_ok=True)
    with PROOF_PATH.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(result, stream, ensure_ascii=False, sort_keys=True, indent=2)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    return result


def verify_proof() -> tuple[dict[str, object], str]:
    proof = json.loads(PROOF_PATH.read_text(encoding="utf-8"))
    expected = expected_body()
    expected_hash = digest_bytes(canonical_bytes(expected))
    if (proof.get("status") != "PASS_OFFLINE_PREFLIGHT"
            or proof.get("body") != expected
            or proof.get("body_sha256") != expected_hash
            or proof.get("sender_source_sha256") != digest_bytes(Path(__file__).read_bytes())
            or proof.get("external_requests") != 0):
        raise RuntimeError("OFFLINE_PREFLIGHT_PROOF_MISMATCH")
    return proof, expected_hash


def reserve_only() -> dict[str, object]:
    _, body_hash = verify_proof()
    key, credential_source = read_api_key(CREDENTIAL_FILE)
    if not key:
        return {"status": "BLOCKED_NOT_SENT", "reason": "MODEL_CREDENTIAL_MISSING"}
    if DB_PATH.exists() or TRACE_PATH.exists():
        return {"status": "BLOCKED_NOT_SENT", "reason": "ONE_SHOT_PATH_ALREADY_EXISTS"}
    RUNS.mkdir(parents=True, exist_ok=True)
    fd = os.open(DB_PATH, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    os.close(fd)
    attempt_id = "urllib-" + str(uuid.uuid4())
    connection = sqlite3.connect(DB_PATH, timeout=5, isolation_level=None)
    try:
        connection.execute("PRAGMA journal_mode=DELETE")
        connection.execute("PRAGMA synchronous=FULL")
        connection.execute("BEGIN IMMEDIATE")
        connection.execute("""CREATE TABLE authorization(
            authorization_id TEXT PRIMARY KEY,
            scope TEXT NOT NULL UNIQUE,
            request_sha256 TEXT NOT NULL,
            reserved_micro_usd INTEGER NOT NULL CHECK(reserved_micro_usd=10000),
            created_at TEXT NOT NULL
        )""")
        connection.execute("""CREATE TABLE attempt(
            attempt_id TEXT PRIMARY KEY,
            authorization_id TEXT NOT NULL UNIQUE REFERENCES authorization(authorization_id),
            status TEXT NOT NULL CHECK(status IN
              ('ATTEMPT_RESERVED','OUTBOUND_STARTED','PASS_CONNECTIVITY_ONLY',
               'FAIL_STOPPED','UNKNOWN_STOPPED','BLOCKED_NOT_SENT')),
            request_count INTEGER NOT NULL CHECK(request_count BETWEEN 0 AND 1),
            request_sha256 TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            http_status INTEGER,
            completion_id TEXT,
            model_version TEXT,
            output_text TEXT,
            usage_json TEXT,
            estimated_micro_usd INTEGER,
            error_class TEXT,
            error_detail TEXT
        )""")
        stamp = now_utc()
        connection.execute(
            "INSERT INTO authorization VALUES(?,?,?,?,?)",
            (AUTHORIZATION_ID, SCOPE, body_hash, RESERVED_MICRO_USD, stamp),
        )
        connection.execute(
            "INSERT INTO attempt(attempt_id,authorization_id,status,request_count,request_sha256,created_at,updated_at) "
            "VALUES(?,?,'ATTEMPT_RESERVED',0,?,?,?)",
            (attempt_id, AUTHORIZATION_ID, body_hash, stamp, stamp),
        )
        connection.execute("COMMIT")
    except BaseException:
        if connection.in_transaction:
            connection.execute("ROLLBACK")
        raise
    finally:
        connection.close()
    first = {
        "at": now_utc(),
        "event": "authorization_reserved",
        "authorization_id": AUTHORIZATION_ID,
        "attempt_id": attempt_id,
        "scope": SCOPE,
        "request_sha256": body_hash,
        "reserved_micro_usd": RESERVED_MICRO_USD,
        "status": "ATTEMPT_RESERVED",
        "credential_source": credential_source,
        "credential_value": "never_logged",
    }
    with TRACE_PATH.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(first, ensure_ascii=False, sort_keys=True) + "\n")
        stream.flush()
        os.fsync(stream.fileno())
    return {
        "status": "ATTEMPT_RESERVED",
        "authorization_id": AUTHORIZATION_ID,
        "attempt_id": attempt_id,
        "request_sha256": body_hash,
        "reserved_micro_usd": RESERVED_MICRO_USD,
        "outbound_count": 0,
        "credential_source": credential_source,
    }


def update_attempt(expected_status: str, status: str, *, request_count: int,
                   http_status: int | None = None, completion_id: str | None = None,
                   model_version: str | None = None, output_text: str | None = None,
                   usage: dict[str, object] | None = None, estimated: int | None = None,
                   error_class: str | None = None, error_detail: str | None = None) -> None:
    connection = sqlite3.connect(DB_PATH, timeout=5, isolation_level=None)
    try:
        connection.execute("PRAGMA synchronous=FULL")
        connection.execute("BEGIN IMMEDIATE")
        cursor = connection.execute(
            """UPDATE attempt SET status=?,request_count=?,updated_at=?,http_status=?,
               completion_id=?,model_version=?,output_text=?,usage_json=?,estimated_micro_usd=?,
               error_class=?,error_detail=? WHERE authorization_id=? AND status=? AND request_count=?""",
            (status, request_count, now_utc(), http_status, completion_id, model_version,
             output_text, json.dumps(usage, sort_keys=True) if usage is not None else None,
             estimated, error_class, error_detail, AUTHORIZATION_ID, expected_status,
             0 if expected_status == "ATTEMPT_RESERVED" else 1),
        )
        if cursor.rowcount != 1:
            raise RuntimeError("PERSISTED_ONE_SHOT_STATE_MISMATCH")
        connection.execute("COMMIT")
    except BaseException:
        if connection.in_transaction:
            connection.execute("ROLLBACK")
        raise
    finally:
        connection.close()


def cause_chain(error: BaseException, secret: str) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    seen: set[int] = set()
    pending: list[BaseException] = [error]
    while pending and len(items) < 8:
        current = pending.pop(0)
        if id(current) in seen:
            continue
        seen.add(id(current))
        items.append({
            "type": type(current).__name__,
            "message": redact(str(current), secret)[:500],
        })
        cause = getattr(current, "__cause__", None)
        context = getattr(current, "__context__", None)
        reason = getattr(current, "reason", None)
        for nested in (cause, context, reason if isinstance(reason, BaseException) else None):
            if isinstance(nested, BaseException) and id(nested) not in seen:
                pending.append(nested)
    return items


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def estimated_peak_cost(usage: dict[str, object]) -> int:
    prompt = usage.get("prompt_tokens")
    completion = usage.get("completion_tokens")
    total = usage.get("total_tokens")
    if any(type(value) is not int or value < 0 for value in (prompt, completion, total)):
        raise ValueError("USAGE_INVALID")
    if prompt + completion != total:
        raise ValueError("USAGE_TOTAL_MISMATCH")
    micro = Decimal(prompt) * Decimal("0.30") + Decimal(completion) * Decimal("1.20")
    return int(micro.to_integral_value(rounding=ROUND_CEILING))


def send_once() -> dict[str, object]:
    proof, body_hash = verify_proof()
    if not DB_PATH.is_file() or not TRACE_PATH.is_file():
        return {"status": "BLOCKED_NOT_SENT", "reason": "DURABLE_RESERVATION_MISSING"}
    connection = sqlite3.connect(DB_PATH, timeout=5)
    connection.row_factory = sqlite3.Row
    authorization = dict(connection.execute("SELECT * FROM authorization").fetchone())
    attempt = dict(connection.execute("SELECT * FROM attempt").fetchone())
    connection.close()
    trace_rows = [json.loads(line) for line in TRACE_PATH.read_text(encoding="utf-8").splitlines() if line]
    if (authorization["authorization_id"] != AUTHORIZATION_ID
            or authorization["scope"] != SCOPE
            or authorization["reserved_micro_usd"] != RESERVED_MICRO_USD
            or authorization["request_sha256"] != body_hash
            or attempt["status"] != "ATTEMPT_RESERVED"
            or attempt["request_count"] != 0
            or attempt["request_sha256"] != body_hash
            or len(trace_rows) != 1
            or trace_rows[0].get("event") != "authorization_reserved"):
        return {"status": "BLOCKED_NOT_SENT", "reason": "PERSISTED_AUTHORIZATION_MISMATCH"}
    secret, credential_source = read_api_key(CREDENTIAL_FILE)
    if not secret:
        return {"status": "BLOCKED_NOT_SENT", "reason": "MODEL_CREDENTIAL_MISSING"}
    request, request_hash = build_request(secret)
    if request_hash != body_hash:
        return {"status": "BLOCKED_NOT_SENT", "reason": "REQUEST_DIGEST_MISMATCH"}

    # Persist the one-shot send before opening a socket. Any following failure consumes it.
    update_attempt("ATTEMPT_RESERVED", "OUTBOUND_STARTED", request_count=1)
    emit("outbound_started", authorization_id=AUTHORIZATION_ID, attempt_id=attempt["attempt_id"],
         url=ENDPOINT, request_sha256=body_hash, request_number=1,
         authorization_header="present_redacted", credential_source=credential_source)

    responses: list[dict[str, object]] = []
    result: dict[str, object]
    opener = build_opener(
        ProxyHandler({}),
        HTTPSHandler(context=ssl.create_default_context()),
        NoRedirect(),
    )
    try:
        try:
            response = opener.open(request, timeout=TIMEOUT_SECONDS)
            status_code = response.getcode()
            headers = response.headers
            raw_bytes = response.read(1_000_000)
            response.close()
        except HTTPError as http_error:
            status_code = http_error.code
            headers = http_error.headers
            raw_bytes = http_error.read(1_000_000)
            http_error.close()
        decoded = raw_bytes.decode("utf-8", errors="replace")
        try:
            payload = json.loads(decoded)
            if not isinstance(payload, dict):
                payload = {"response_type": type(payload).__name__}
        except json.JSONDecodeError:
            payload = {"body_text": redact(decoded, secret)[:4096]}
        payload = redact_json(payload, secret)
        payload = payload if isinstance(payload, dict) else {"response_type": type(payload).__name__}
        response_meta = {
            "http_status": status_code,
            "request_id": headers.get("x-request-id") or headers.get("request-id"),
            "content_type": headers.get("content-type"),
            "body": payload,
        }
        responses.append(response_meta)
        emit("http_response", **response_meta)
        choices = payload.get("choices")
        choice = choices[0] if isinstance(choices, list) and choices else {}
        message = choice.get("message") if isinstance(choice, dict) else {}
        message = message if isinstance(message, dict) else {}
        usage = payload.get("usage") if isinstance(payload.get("usage"), dict) else None
        try:
            estimated = estimated_peak_cost(usage) if usage else None
            usage_error = None
        except ValueError as exc:
            estimated = None
            usage_error = str(exc)
        completion_id = payload.get("id") if isinstance(payload.get("id"), str) else None
        model_version = payload.get("model") if isinstance(payload.get("model"), str) else None
        output_text = message.get("content") if isinstance(message.get("content"), str) else None
        cost_within_reserve = estimated is not None and estimated <= RESERVED_MICRO_USD
        valid = (status_code == 200 and payload.get("object") == "chat.completion"
                 and completion_id and model_version and output_text and usage is not None
                 and usage_error is None and cost_within_reserve
                 and choice.get("finish_reason") == "stop")
        final_status = "PASS_CONNECTIVITY_ONLY" if valid else "FAIL_STOPPED"
        error = payload.get("error")
        error_class = (usage_error or ("COST_USAGE_EXCEEDS_RESERVATION" if estimated is not None and not cost_within_reserve else None)
                       or ("PROVIDER_ERROR_RESPONSE" if error else None))
        update_attempt("OUTBOUND_STARTED", final_status, request_count=1,
                       http_status=status_code, completion_id=completion_id,
                       model_version=model_version, output_text=redact(output_text or "", secret) or None,
                       usage=usage, estimated=estimated, error_class=error_class)
        result = {
            "status": final_status,
            "http_status": status_code,
            "request_id": response_meta["request_id"],
            "completion_id": completion_id,
            "model_version": model_version,
            "output": redact(output_text or "", secret),
            "usage": usage,
            "peak_cost_estimate_micro_usd": estimated,
            "response_count": 1,
            "request_count": 1,
            "error": error,
        }
    except BaseException as error:
        chains = cause_chain(error, secret)
        if responses:
            status_code = responses[0]["http_status"]
            final_status = "FAIL_STOPPED"
        else:
            status_code = None
            final_status = "UNKNOWN_STOPPED"
        detail = json.dumps(chains, ensure_ascii=False, sort_keys=True)
        update_attempt("OUTBOUND_STARTED", final_status, request_count=1,
                       http_status=status_code, error_class=type(error).__name__,
                       error_detail=detail[:2000])
        emit("send_error", status=final_status, cause_chain=chains,
             request_number=1, response_count=len(responses))
        result = {
            "status": final_status,
            "error_class": type(error).__name__,
            "cause_chain": chains,
            "http_status": status_code,
            "response_count": len(responses),
            "request_count": 1,
            "actual_billing": "UNKNOWN" if not responses else "CHECK_USAGE",
        }
    emit("final_result", **result)
    return {
        "authorization_id": AUTHORIZATION_ID,
        "attempt_id": attempt["attempt_id"],
        "reserved_micro_usd": RESERVED_MICRO_USD,
        "result": result,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--offline-preflight", action="store_true")
    group.add_argument("--reserve-only", action="store_true")
    group.add_argument("--send-once", action="store_true")
    args = parser.parse_args()
    try:
        if args.offline_preflight:
            result = offline_preflight()
        elif args.reserve_only:
            result = reserve_only()
        else:
            result = send_once()
    except BaseException as error:
        result = {"status": "BLOCKED_NOT_SENT", "error_class": type(error).__name__,
                  "error_detail": str(error)[:1000]}
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result.get("status") in {"PASS_OFFLINE_PREFLIGHT", "ATTEMPT_RESERVED", "PASS_CONNECTIVITY_ONLY"} else 2


if __name__ == "__main__":
    sys.exit(main())
