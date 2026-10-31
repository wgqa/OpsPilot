from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import re
import socket
import sqlite3
import ssl
import sys
import tempfile
import time
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from urllib.parse import urlsplit

import httpx2
import openai
from openai import AsyncOpenAI

PROBE_ID = "AR-02-CONN-01-20261101"
MODEL = "deepseek-flash"
PROMPT = "请只回复：OK"
MAX_TOKENS = 64
TIMEOUT_SECONDS = 30
RESERVE_USD = Decimal("0.01")
MAX_INPUT_BYTES = 512
INPUT_RATE_PEAK = Decimal("0.30")
OUTPUT_RATE_PEAK = Decimal("1.20")
EXPECTED_HOST = "api.deepseek.com"
SENSITIVE_KEYS = ("authorization", "api_key", "api-key", "secret", "secret-key", "password", "cookie", "token")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def load_dotenv(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.is_file():
        return values
    for raw in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        if "=" not in line:
            continue
        name, value = line.split("=", 1)
        name = name.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]
        values[name] = value
    return values


def read_config(env_file: Path) -> tuple[str, str, str, str]:
    dotenv = load_dotenv(env_file)
    def take(name: str) -> tuple[str, str]:
        if name in os.environ:
            return os.environ[name], "process_environment"
        if name in dotenv:
            return dotenv[name], "env_file"
        return "", "missing"
    key, key_source = take("OPSPILOT_MODEL_API_KEY")
    base, base_source = take("OPSPILOT_MODEL_BASE_URL")
    model, model_source = take("OPSPILOT_MODEL_NAME")
    if not key:
        raise ValueError("OPSPILOT_MODEL_API_KEY is missing")
    if model != MODEL:
        raise ValueError("OPSPILOT_MODEL_NAME must be exactly deepseek-flash")
    parsed = urlsplit(base)
    if (
        parsed.scheme != "https"
        or parsed.hostname != EXPECTED_HOST
        or parsed.port not in (None, 443)
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or parsed.path not in ("", "/", "/v1", "/v1/")
    ):
        raise ValueError("base URL is outside the frozen DeepSeek endpoint allowlist")
    normalized = f"https://{EXPECTED_HOST}" + ("/v1" if parsed.path.rstrip("/") == "/v1" else "")
    return key, normalized, model, f"key={key_source};base={base_source};model={model_source}"


def expected_url(base_url: str) -> str:
    return base_url.rstrip("/") + "/chat/completions"


def safe_headers(headers) -> dict[str, str]:
    result: dict[str, str] = {}
    for name, value in headers.items():
        key = name.lower()
        result[name] = "[REDACTED]" if any(part in key for part in SENSITIVE_KEYS) else value
    return result


def safe_request(request) -> dict:
    raw = request.content
    body = json.loads(raw.decode("utf-8"))
    return {
        "method": request.method,
        "url": str(request.url),
        "host": request.url.host,
        "path": request.url.path,
        "headers_redacted": safe_headers(request.headers),
        "authorization_present": bool(request.headers.get("authorization")),
        "body": body,
        "body_sha256": hashlib.sha256(raw).hexdigest(),
        "body_bytes": len(raw),
    }


def validate_request(record: dict, base_url: str) -> None:
    body = record["body"]
    expected = expected_url(base_url)
    if record["method"] != "POST" or record["url"] != expected:
        raise AssertionError("unexpected request URL or method")
    if body.get("model") != MODEL:
        raise AssertionError("unexpected model")
    if body.get("max_tokens") != MAX_TOKENS or "max_completion_tokens" in body:
        raise AssertionError("output parameter mismatch")
    if body.get("thinking") != {"type": "disabled"}:
        raise AssertionError("thinking mode is not explicitly disabled")
    if "tools" in body or "tool_choice" in body:
        raise AssertionError("probe must not include tools")
    if not isinstance(body.get("messages"), list) or len(body["messages"]) != 1:
        raise AssertionError("probe must contain exactly one short message")
    if body["messages"][0] != {"role": "user", "content": PROMPT}:
        raise AssertionError("probe input differs from frozen text")
    if record["body_bytes"] > MAX_INPUT_BYTES:
        raise AssertionError("serialized request exceeds the frozen 512-byte input ceiling")


def response_payload() -> dict:
    return {
        "id": "local-mock-completion",
        "object": "chat.completion",
        "created": 1,
        "model": MODEL,
        "choices": [{
            "index": 0,
            "message": {"role": "assistant", "content": "OK"},
            "finish_reason": "stop",
        }],
        "usage": {"prompt_tokens": 5, "completion_tokens": 1, "total_tokens": 6},
    }


async def sdk_call(client: AsyncOpenAI):
    return await client.chat.completions.create(
        model=MODEL,
        messages=[{"role": "user", "content": PROMPT}],
        max_tokens=MAX_TOKENS,
        extra_body={"thinking": {"type": "disabled"}},
        timeout=TIMEOUT_SECONDS,
    )


def install_no_redirect_send(client: AsyncOpenAI):
    original_send = client._client.send
    async def send_without_redirects(request, *args, **kwargs):
        kwargs["follow_redirects"] = False
        return await original_send(request, *args, **kwargs)
    client._client.send = send_without_redirects

async def local_mock_success(base_url: str) -> dict:
    captured: list[dict] = []
    async def handler(request):
        record = safe_request(request)
        validate_request(record, base_url)
        captured.append(record)
        return httpx2.Response(200, json=response_payload(), request=request)
    client = AsyncOpenAI(
        api_key="LOCAL_MOCK_ONLY",
        base_url=base_url,
        max_retries=0,
        timeout=TIMEOUT_SECONDS,
    )
    original_transport = client._client._transport
    client._client._transport = httpx2.MockTransport(handler)
    try:
        if not isinstance(client._client, httpx2.AsyncClient):
            raise AssertionError("SDK default client is not HTTPX2")
        if client.max_retries != 0:
            raise AssertionError("SDK retries are not disabled")
        snapshot = {
            "client_type": type(client._client).__module__ + "." + type(client._client).__name__,
            "httpx2_version": getattr(httpx2, "__version__", "unknown"),
            "openai_version": openai.__version__,
            "trust_env": getattr(client._client, "_trust_env", None),
            "sdk_default_follow_redirects": getattr(client._client, "follow_redirects", None),
            "httpx2_transport_before_mock": type(original_transport).__module__ + "." + type(original_transport).__name__,
            "tls_verification_default": True,
            "max_retries": client.max_retries,
            "timeout_seconds": TIMEOUT_SECONDS,
        }
        install_no_redirect_send(client)
        completion = await sdk_call(client)
        if len(captured) != 1:
            raise AssertionError("local MockTransport did not observe exactly one call")
        if completion.id != "local-mock-completion" or completion.usage.total_tokens != 6:
            raise AssertionError("local mock response was not parsed")
        return {
            "status": "PASS",
            "sdk_default_client": snapshot,
            "request": captured[0],
            "response": response_payload(),
            "sdk_completion_id": completion.id,
            "sdk_usage": completion.usage.model_dump(),
            "actual_network": False,
            "provider_requests": 0,
        }
    finally:
        await client.close()
        await original_transport.aclose()


async def local_mock_connect_error(base_url: str) -> dict:
    captured: list[dict] = []
    async def handler(request):
        record = safe_request(request)
        validate_request(record, base_url)
        captured.append(record)
        raise httpx2.ConnectError("LOCAL_ONLY_CONNECT_ERROR", request=request)
    client = AsyncOpenAI(
        api_key="LOCAL_MOCK_ONLY",
        base_url=base_url,
        max_retries=0,
        timeout=TIMEOUT_SECONDS,
    )
    original_transport = client._client._transport
    client._client._transport = httpx2.MockTransport(handler)
    install_no_redirect_send(client)
    try:
        try:
            await sdk_call(client)
            raise AssertionError("local ConnectError was not raised")
        except openai.APIConnectionError as exc:
            chain = []
            current = exc
            while current is not None and len(chain) < 8:
                chain.append(type(current).__name__)
                current = current.__cause__ or current.__context__
            if "ConnectError" not in chain or len(captured) != 1:
                raise AssertionError("local ConnectError chain or HTTPX2 capture was incomplete")
            return {
                "status": "PASS",
                "request": captured[0],
                "http_response": None,
                "exception_type_chain": chain,
                "phase": "local HTTPX2 MockTransport handler raised before any response",
                "actual_network": False,
                "provider_requests": 0,
            }
    finally:
        await client.close()
        await original_transport.aclose()

def reserve_once(ledger: Path, metadata: dict) -> None:
    if ledger.parent.exists() and any(ledger.parent.iterdir()):
        raise FileExistsError("single-use ledger directory already has a record")
    ledger.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_CREAT | os.O_EXCL | os.O_RDWR
    fd = os.open(ledger, flags, 0o600)
    os.close(fd)
    db = None
    try:
        db = sqlite3.connect(ledger, timeout=5, isolation_level=None)
        db.execute("PRAGMA journal_mode=DELETE")
        db.execute("PRAGMA synchronous=FULL")
        db.execute(
            "CREATE TABLE attempt (probe_id TEXT PRIMARY KEY, state TEXT NOT NULL, "
            "request_sha256 TEXT NOT NULL, model TEXT NOT NULL, reserve_usd TEXT NOT NULL, "
            "started_at TEXT NOT NULL, result_json TEXT)"
        )
        db.execute("BEGIN IMMEDIATE")
        db.execute(
            "INSERT INTO attempt(probe_id,state,request_sha256,model,reserve_usd,started_at) "
            "VALUES(?,?,?,?,?,?)",
            (
                PROBE_ID,
                "ATTEMPT_RESERVED",
                metadata["request_sha256"],
                MODEL,
                str(RESERVE_USD),
                utc_now(),
            ),
        )
        db.execute("COMMIT")
    except Exception:
        # The file itself is a consumed permit, even if initialization fails.
        raise
    finally:
        if db is not None:
            db.close()


def finish_ledger(ledger: Path, state: str, result: dict) -> None:
    db = sqlite3.connect(ledger, timeout=5, isolation_level=None)
    try:
        db.execute("PRAGMA synchronous=FULL")
        db.execute("BEGIN IMMEDIATE")
        db.execute(
            "UPDATE attempt SET state=?, result_json=? WHERE probe_id=? AND state='ATTEMPT_RESERVED'",
            (state, json.dumps(result, ensure_ascii=False, sort_keys=True), PROBE_ID),
        )
        if db.total_changes != 1:
            raise RuntimeError("reserved attempt row was not updated exactly once")
        db.execute("COMMIT")
    finally:
        db.close()

def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    raw = json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    temp.write_text(raw, encoding="utf-8")
    with temp.open("rb+") as stream:
        os.fsync(stream.fileno())
    os.replace(temp, path)


def test_single_use_guard(temp_root: Path) -> dict:
    with tempfile.TemporaryDirectory(prefix="ar02-conn-01-local-", dir=temp_root) as temp:
        path = Path(temp) / "ledger.sqlite3"
        meta = {"request_sha256": "local-only-test"}
        reserve_once(path, meta)
        try:
            reserve_once(path, meta)
        except FileExistsError:
            second_rejected = True
        else:
            second_rejected = False
        if not second_rejected:
            raise AssertionError("second permit was not rejected")
        db = sqlite3.connect(path)
        try:
            row = db.execute(
                "SELECT probe_id,state,request_sha256,model,reserve_usd FROM attempt"
            ).fetchone()
        finally:
            db.close()
        if row != (PROBE_ID, "ATTEMPT_RESERVED", "local-only-test", MODEL, str(RESERVE_USD)):
            raise AssertionError("durable permit did not match expected state")
        return {
            "status": "PASS",
            "first_permit": "persisted_ATTEMPT_RESERVED",
            "second_permit": "rejected_before_network_io",
            "uses_temporary_test_ledger": True,
        }


def write_preflight(out: Path, base_url: str) -> dict:
    safe = asyncio.run(local_mock_success(base_url))
    failed = asyncio.run(local_mock_connect_error(base_url))
    guard = test_single_use_guard(out.parent)
    record = {
        "created_at": utc_now(),
        "model": MODEL,
        "base_host": EXPECTED_HOST,
        "base_path": urlsplit(base_url).path or "/",
        "expected_completion_url": expected_url(base_url),
        "max_tokens": MAX_TOKENS,
        "thinking": {"type": "disabled"},
        "tools_included": False,
        "tool_choice_included": False,
        "timeout_seconds": TIMEOUT_SECONDS,
        "max_retries": 0,
        "max_input_request_bytes": MAX_INPUT_BYTES,
        "fee_bound": {
            "input_token_assumption": 512,
            "output_token_cap": MAX_TOKENS,
            "peak_input_cache_miss_usd_per_million": str(INPUT_RATE_PEAK),
            "peak_output_usd_per_million": str(OUTPUT_RATE_PEAK),
            "estimated_peak_usd": str((Decimal(512) * INPUT_RATE_PEAK / Decimal(1_000_000) + Decimal(MAX_TOKENS) * OUTPUT_RATE_PEAK / Decimal(1_000_000))),
            "application_reserve_usd": str(RESERVE_USD),
            "provider_hard_cap": False,
        },
        "success_mock": safe,
        "connect_error_mock": failed,
        "single_use_guard": guard,
        "provider_requests": 0,
        "status": "PASS",
    }
    write_json(out, record)
    return record


def network_diagnostic(host: str, timeout: float = 5.0) -> dict:
    if host != EXPECTED_HOST:
        raise ValueError("diagnostic host not on allowlist")
    started = time.monotonic()
    addresses = sorted({
        item[4][0]
        for item in socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    })
    if not addresses:
        raise RuntimeError("DNS returned no addresses")
    errors = []
    tls_result = None
    for address in addresses:
        try:
            raw = socket.create_connection((address, 443), timeout=timeout)
            with raw:
                context = ssl.create_default_context()
                with context.wrap_socket(raw, server_hostname=host) as tls:
                    tls_result = {
                        "resolved_ip": address,
                        "protocol": tls.version(),
                        "cipher": tls.cipher()[0] if tls.cipher() else None,
                        "certificate_verified": True,
                    }
                    break
        except Exception as exc:
            errors.append({"ip": address, "type": type(exc).__name__})
    return {
        "host": host,
        "port": 443,
        "dns": "PASS",
        "resolved_addresses": addresses,
        "tcp_tls": "PASS" if tls_result else "FAIL",
        "tls": tls_result,
        "connection_errors": errors,
        "http_request_sent": False,
        "completion_requests_sent": 0,
        "duration_ms": round((time.monotonic() - started) * 1000),
        "checked_at": utc_now(),
    }


def sanitize_exception(exc: BaseException, secrets: tuple[str, ...] = ()) -> list[dict]:
    items = []
    current: BaseException | None = exc
    while current is not None and len(items) < 8:
        message = str(current)
        message = re.sub(r"(?i)(bearer\s+)[^\s,;]+", r"\1[REDACTED]", message)
        message = re.sub(r"sk-[A-Za-z0-9_-]{8,}", "[REDACTED]", message)
        message = re.sub(r"https?://[^\s\"']+", "[URL_REDACTED]", message)
        for secret in secrets:
            if secret:
                message = message.replace(secret, "[REDACTED]")
        items.append({"type": type(current).__name__, "message_redacted": message[:300]})
        current = current.__cause__ or current.__context__
    return items


async def send_once(env_file: Path, ledger: Path, trace_path: Path, result_path: Path) -> dict:
    stopped_marker = Path(__file__).resolve().parent / "TRACE" / "STOPPED_NO_RETRY.json"
    if stopped_marker.exists():
        raise RuntimeError("single authorized request has been consumed; stopped by evidence marker")
    if ledger.exists() or (ledger.parent.exists() and any(ledger.parent.iterdir())):
        raise FileExistsError("single-use ledger directory already has a record; no request was sent")
    if trace_path.exists() or result_path.exists():
        raise FileExistsError("live trace or result already exists; no request was sent")
    key, base_url, model, source = read_config(env_file)
    if model != MODEL:
        raise ValueError("unexpected model")
    # Repeat the free protocol check immediately before consuming the permit.
    preflight = await local_mock_success(base_url)
    request_summary = preflight["request"]
    if request_summary["body_bytes"] > MAX_INPUT_BYTES:
        raise ValueError("short request exceeds 512-byte input ceiling")
    expected = expected_url(base_url)
    config = {
        "probe_id": PROBE_ID,
        "model": MODEL,
        "base_host": EXPECTED_HOST,
        "base_path": urlsplit(base_url).path or "/",
        "expected_url": expected,
        "prompt_sha256": hashlib.sha256(PROMPT.encode("utf-8")).hexdigest(),
        "request_sha256": request_summary["body_sha256"],
        "request_body_bytes": request_summary["body_bytes"],
        "max_tokens": MAX_TOKENS,
        "thinking": {"type": "disabled"},
        "tools_included": False,
        "tool_choice_included": False,
        "timeout_seconds": TIMEOUT_SECONDS,
        "max_retries": 0,
        "follow_redirects": False,
        "reserve_usd": str(RESERVE_USD),
        "config_sources": source,
    }
    # SDK default client is the locked HTTPX2 wrapper; do not inject a custom live transport.
    client = AsyncOpenAI(
        api_key=key,
        base_url=base_url,
        max_retries=0,
        timeout=TIMEOUT_SECONDS,
    )
    if not isinstance(client._client, httpx2.AsyncClient):
        await client.close()
        raise RuntimeError("OpenAI SDK default client is not HTTPX2")
    if client.max_retries != 0:
        await client.close()
        raise RuntimeError("OpenAI SDK automatic retries are enabled")
    send_count = 0
    original_send = client._client.send
    live_trace = {
        "probe_id": PROBE_ID,
        "status": "ATTEMPT_RESERVED_NO_HTTPX2_SEND_YET",
        "request": None,
        "http_response": None,
        "exception_chain": [],
        "httpx2_send_count": 0,
    }

    async def observed_send(request, *args, **kwargs):
        nonlocal send_count
        send_count += 1
        if send_count > 1:
            raise RuntimeError("single-request guard blocked a second HTTPX2 send")
        current = safe_request(request)
        validate_request(current, base_url)
        if current["url"] != expected:
            raise AssertionError("HTTPX2 URL changed after preflight")
        if current["body_sha256"] != config["request_sha256"]:
            raise AssertionError("HTTPX2 request body changed after preflight")
        live_trace["status"] = "HTTPX2_SEND_ENTERED"
        live_trace["request"] = current
        live_trace["httpx2_send_count"] = send_count
        live_trace["started_at"] = utc_now()
        write_json(trace_path, live_trace)
        try:
            kwargs["follow_redirects"] = False
            response = await original_send(request, *args, **kwargs)
        except BaseException as exc:
            live_trace["status"] = "HTTPX2_SEND_ERROR_NO_RESPONSE"
            live_trace["exception_chain"] = sanitize_exception(exc, (key,))
            live_trace["finished_at"] = utc_now()
            write_json(trace_path, live_trace)
            raise
        raw_response = await response.aread()
        try:
            response_json = json.loads(raw_response.decode("utf-8"))
        except Exception:
            response_json = {"unparsed_body_sha256": hashlib.sha256(raw_response).hexdigest(),
                             "body_bytes": len(raw_response)}
        live_trace["status"] = "HTTP_RESPONSE_RECEIVED"
        live_trace["finished_at"] = utc_now()
        live_trace["http_response"] = {
            "status_code": response.status_code,
            "headers_redacted": safe_headers(response.headers),
            "body": response_json,
            "body_sha256": hashlib.sha256(raw_response).hexdigest(),
            "body_bytes": len(raw_response),
        }
        write_json(trace_path, live_trace)
        return response

    # The SDK wrapper is kept intact; only its instance send method is wrapped for observation.
    client._client.send = observed_send
    if ledger.exists():
        await client.close()
        raise FileExistsError("single-use ledger was created concurrently; no request was sent")
    reserve_once(ledger, config)
    write_json(trace_path, live_trace)
    started = time.monotonic()
    try:
        completion = await sdk_call(client)
        result = completion.model_dump(mode="json")
        usage = result.get("usage") or {}
        prompt_tokens = int(usage.get("prompt_tokens") or 0)
        completion_tokens = int(usage.get("completion_tokens") or 0)
        total_tokens = int(usage.get("total_tokens") or 0)
        cost = (
            Decimal(prompt_tokens) * INPUT_RATE_PEAK / Decimal(1_000_000)
            + Decimal(completion_tokens) * OUTPUT_RATE_PEAK / Decimal(1_000_000)
        )
        valid = bool(
            result.get("id")
            and result.get("model")
            and usage
            and total_tokens
            and result.get("choices")
            and result["choices"][0].get("message", {}).get("content") is not None
        )
        state = "COMPLETED" if valid else "UNKNOWN"
        summary = {
            "probe_id": PROBE_ID,
            "status": "CONNECTIVITY_PROBE_PASS" if valid else "UNKNOWN",
            "completion_id": result.get("id"),
            "model": result.get("model"),
            "finish_reason": result["choices"][0].get("finish_reason") if result.get("choices") else None,
            "output": result["choices"][0].get("message", {}).get("content") if result.get("choices") else None,
            "usage": {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": total_tokens,
            },
            "fee_estimate_usd_at_peak_rates": str(cost.quantize(Decimal("0.00000001"))),
            "rates_usd_per_million": {
                "input_cache_miss_peak": str(INPUT_RATE_PEAK),
                "output_peak": str(OUTPUT_RATE_PEAK),
            },
            "reserved_usd": str(RESERVE_USD),
            "actual_httpx2_send_count": send_count,
            "duration_ms": round((time.monotonic() - started) * 1000),
            "response_http_status": (live_trace.get("http_response") or {}).get("status_code"),
            "usage_within_input_ceiling": prompt_tokens <= 512,
            "usage_within_output_ceiling": completion_tokens <= MAX_TOKENS,
            "provider_bill_confirmed": False,
            "source_config": source,
        }
        if not valid or send_count != 1 or summary["response_http_status"] != 200:
            summary["status"] = "UNKNOWN"
            state = "UNKNOWN"
        write_json(result_path, summary)
        finish_ledger(ledger, state, summary)
        return summary
    except BaseException as exc:
        failure = {
            "probe_id": PROBE_ID,
            "status": "UNKNOWN",
            "completion_request_attempts": 1,
            "httpx2_send_count": send_count,
            "error_chain": sanitize_exception(exc, (key,)),
            "provider_received_or_billed": "UNKNOWN",
            "reserved_usd": str(RESERVE_USD),
            "automatic_retry": False,
        }
        live_trace["status"] = live_trace["status"] if send_count else "FAILED_BEFORE_HTTPX2_SEND_AFTER_RESERVATION"
        live_trace.setdefault("exception_chain", sanitize_exception(exc, (key,)))
        live_trace.setdefault("finished_at", utc_now())
        write_json(trace_path, live_trace)
        write_json(result_path, failure)
        finish_ledger(ledger, "UNKNOWN", failure)
        return failure
    finally:
        await client.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("preflight", "network-diagnostic", "send-once"))
    parser.add_argument("--env-file", type=Path)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--ledger", type=Path)
    parser.add_argument("--trace", type=Path)
    args = parser.parse_args()
    if args.mode == "preflight":
        if args.env_file is None or args.out is None:
            parser.error("preflight needs --env-file and --out")
        _, base_url, _, _ = read_config(args.env_file)
        result = write_preflight(args.out, base_url)
        print(json.dumps({
            "status": result["status"],
            "expected_url": result["expected_completion_url"],
            "model": result["model"],
            "max_tokens": result["max_tokens"],
            "thinking": result["thinking"],
            "tools_included": result["tools_included"],
            "provider_requests": 0,
            "evidence_path": str(args.out),
        }, ensure_ascii=False))
        return 0
    if args.mode == "network-diagnostic":
        result = network_diagnostic(EXPECTED_HOST)
        if args.out:
            write_json(args.out, result)
        print(json.dumps(result, ensure_ascii=False))
        return 0 if result["tcp_tls"] == "PASS" else 2
    if args.env_file is None or args.ledger is None or args.trace is None or args.out is None:
        parser.error("send-once needs --env-file, --ledger, --trace, and --out")
    if args.ledger.exists():
        print(json.dumps({"status": "BLOCKED", "reason": "single-use ledger already exists; no request sent"}))
        return 3
    result = asyncio.run(send_once(args.env_file, args.ledger, args.trace, args.out))
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result.get("status") == "CONNECTIVITY_PROBE_PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
