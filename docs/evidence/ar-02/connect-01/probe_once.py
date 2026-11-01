"""Offline-only protocol fixture for AR-02-CONN-01.

This module deliberately has no live Provider sender. The consumed one-shot
authorization cannot be restored by copying or deleting local files.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import inspect
import json
import os
import sqlite3
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from urllib.parse import urlsplit

import httpx2
import openai
from openai import AsyncOpenAI

LOCKED_ASYNC_OPENAI = AsyncOpenAI

MODEL = "deepseek-flash"
PROMPT = "请只回复：OK"
MOCK_KEY = "LOCAL_MOCK_ONLY"
MAX_TOKENS = 64
TIMEOUT_SECONDS = 30
RESERVE_USD = Decimal("0.01")
EXPECTED_HOST = "api.deepseek.com"
EXPECTED_OPENAI_VERSION = "3.33.0"
EXPECTED_HTTPX2_VERSION = "2.13.1"
PROXY_ENV_NAMES = (
    "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY",
    "http_proxy", "https_proxy", "all_proxy", "no_proxy",
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def validate_endpoint(base_url: str) -> str:
    parsed = urlsplit(base_url)
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
    suffix = "/v1" if parsed.path.rstrip("/") == "/v1" else ""
    return f"https://{EXPECTED_HOST}{suffix}"


def expected_url(base_url: str) -> str:
    return validate_endpoint(base_url).rstrip("/") + "/chat/completions"


def _check_locked_sdk() -> None:
    if openai.__version__ != EXPECTED_OPENAI_VERSION:
        raise RuntimeError("locked OpenAI SDK version mismatch")
    if getattr(httpx2, "__version__", None) != EXPECTED_HTTPX2_VERSION:
        raise RuntimeError("locked HTTPX2 version mismatch")
    if "http_client" not in inspect.signature(LOCKED_ASYNC_OPENAI).parameters:
        raise RuntimeError("OpenAI SDK does not support explicit http_client injection")


def _reject_proxy_environment() -> None:
    present = [name for name in PROXY_ENV_NAMES if os.environ.get(name)]
    if present:
        # Names only; never disclose proxy URLs or credentials.
        raise RuntimeError("proxy environment is present; offline preflight refuses it")


def safe_headers(headers) -> dict[str, str]:
    result: dict[str, str] = {}
    for name, value in headers.items():
        lowered = name.lower()
        if any(
            marker in lowered
            for marker in (
                "authorization", "cookie", "api-key", "api_key",
                "secret", "password", "token",
            )
        ):
            result[name] = "[REDACTED]"
        else:
            result[name] = value
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
    if record["method"] != "POST" or record["url"] != expected_url(base_url):
        raise AssertionError("unexpected request URL or method")
    if body.get("model") != MODEL:
        raise AssertionError("unexpected model")
    if body.get("max_tokens") != MAX_TOKENS or "max_completion_tokens" in body:
        raise AssertionError("output parameter mismatch")
    if body.get("thinking") != {"type": "disabled"}:
        raise AssertionError("thinking mode is not explicitly disabled")
    if "tools" in body or "tool_choice" in body:
        raise AssertionError("offline probe must not include tools")
    if body.get("messages") != [{"role": "user", "content": PROMPT}]:
        raise AssertionError("probe input differs from frozen text")
    if record["body_bytes"] > 512:
        raise AssertionError("serialized probe request exceeds 512 bytes")


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


async def create_offline_client(base_url: str, transport) -> AsyncOpenAI:
    """Build an SDK client only when a local MockTransport is explicitly supplied."""
    normalized = validate_endpoint(base_url)
    if type(transport) is not httpx2.MockTransport:
        raise RuntimeError("HF01_NO_MOCK_TRANSPORT: explicit HTTPX2 MockTransport required")
    _check_locked_sdk()
    _reject_proxy_environment()
    http_client = httpx2.AsyncClient(
        transport=transport,
        timeout=TIMEOUT_SECONDS,
        follow_redirects=False,
        trust_env=False,
    )
    try:
        client = AsyncOpenAI(
            api_key=MOCK_KEY,
            base_url=normalized,
            max_retries=0,
            timeout=TIMEOUT_SECONDS,
            http_client=http_client,
        )
    except BaseException:
        await http_client.aclose()
        raise
    if client.max_retries != 0:
        await client.close()
        raise RuntimeError("OpenAI SDK automatic retries are enabled")
    return client


async def sdk_call(client: AsyncOpenAI):
    return await client.chat.completions.create(
        model=MODEL,
        messages=[{"role": "user", "content": PROMPT}],
        max_tokens=MAX_TOKENS,
        extra_body={"thinking": {"type": "disabled"}},
        timeout=TIMEOUT_SECONDS,
    )


async def local_mock_success(base_url: str) -> dict:
    captured: list[dict] = []

    async def handler(request):
        record = safe_request(request)
        validate_request(record, base_url)
        captured.append(record)
        return httpx2.Response(200, json=response_payload(), request=request)

    transport = httpx2.MockTransport(handler)
    client = await create_offline_client(base_url, transport)
    try:
        completion = await sdk_call(client)
        if len(captured) != 1:
            raise AssertionError("MockTransport did not observe exactly one request")
        if completion.id != "local-mock-completion" or completion.usage.total_tokens != 6:
            raise AssertionError("synthetic response or Usage was not parsed")
        return {
            "status": "PASS",
            "sdk": {
                "openai": openai.__version__,
                "httpx2": httpx2.__version__,
                "injected_http_client_type": "httpx2.AsyncClient",
                "explicit_http_client_injected": True,
                "transport_type": "httpx2.MockTransport",
                "trust_env": False,
                "follow_redirects": False,
                "max_retries": client.max_retries,
            },
            "request": captured[0],
            "response": response_payload(),
            "sdk_completion_id": completion.id,
            "sdk_usage": completion.usage.model_dump(),
            "actual_network": False,
            "provider_requests": 0,
        }
    finally:
        await client.close()


async def local_mock_connect_error(base_url: str) -> dict:
    captured: list[dict] = []

    async def handler(request):
        record = safe_request(request)
        validate_request(record, base_url)
        captured.append(record)
        raise httpx2.ConnectError("LOCAL_ONLY_CONNECT_ERROR", request=request)

    client = await create_offline_client(base_url, httpx2.MockTransport(handler))
    try:
        try:
            await sdk_call(client)
        except openai.APIConnectionError as exc:
            chain: list[str] = []
            current: BaseException | None = exc
            while current is not None and len(chain) < 8:
                chain.append(type(current).__name__)
                current = current.__cause__ or current.__context__
            if "ConnectError" not in chain or len(captured) != 1:
                raise AssertionError("offline exception chain or request capture is incomplete")
            return {
                "status": "PASS",
                "request": captured[0],
                "http_response": None,
                "exception_type_chain": chain,
                "failure_phase": "local MockTransport handler raised before a response",
                "actual_network": False,
                "provider_requests": 0,
                "http_responses": 0,
            }
        raise AssertionError("injected local ConnectError did not fail")
    finally:
        await client.close()


def simulate_reserve_once(
    ledger: Path,
    authorization_id: str,
    request_sha256: str,
    reserve_usd: Decimal = RESERVE_USD,
) -> None:
    """Simulation-only durable permit; this function cannot enable network sending."""
    ledger.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(ledger, timeout=10, isolation_level=None)
    try:
        connection.execute("PRAGMA synchronous=FULL")
        connection.execute(
            "CREATE TABLE IF NOT EXISTS simulated_permits ("
            "authorization_id TEXT PRIMARY KEY, state TEXT NOT NULL, "
            "request_sha256 TEXT NOT NULL, reserve_usd TEXT NOT NULL, created_at TEXT NOT NULL)"
        )
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute(
            "SELECT request_sha256 FROM simulated_permits WHERE authorization_id=?",
            (authorization_id,),
        ).fetchone()
        if row is not None:
            if row[0] != request_sha256:
                raise ValueError("same simulated authorization has a different request digest")
            raise FileExistsError("simulated authorization is already reserved or consumed")
        connection.execute(
            "INSERT INTO simulated_permits VALUES(?,?,?,?,?)",
            (authorization_id, "ATTEMPT_RESERVED", request_sha256, str(reserve_usd), utc_now()),
        )
        connection.execute("COMMIT")
    except BaseException:
        if connection.in_transaction:
            connection.execute("ROLLBACK")
        raise
    finally:
        connection.close()


def simulate_mark_unknown(ledger: Path, authorization_id: str) -> None:
    connection = sqlite3.connect(ledger, timeout=10, isolation_level=None)
    try:
        connection.execute("BEGIN IMMEDIATE")
        cursor = connection.execute(
            "UPDATE simulated_permits SET state='UNKNOWN' "
            "WHERE authorization_id=? AND state='ATTEMPT_RESERVED'",
            (authorization_id,),
        )
        if cursor.rowcount != 1:
            raise RuntimeError("simulated permit was not in ATTEMPT_RESERVED")
        connection.execute("COMMIT")
    except BaseException:
        if connection.in_transaction:
            connection.execute("ROLLBACK")
        raise
    finally:
        connection.close()


def ledger_snapshot(ledger: Path) -> list[dict]:
    if not ledger.exists():
        return []
    connection = sqlite3.connect(ledger)
    try:
        try:
            rows = connection.execute(
                "SELECT authorization_id,state,request_sha256,reserve_usd "
                "FROM simulated_permits ORDER BY authorization_id"
            ).fetchall()
        except sqlite3.OperationalError:
            return []
        return [
            {
                "authorization_id": row[0],
                "state": row[1],
                "request_sha256": row[2],
                "reserve_usd": row[3],
            }
            for row in rows
        ]
    finally:
        connection.close()


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    raw = json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    temp.write_text(raw, encoding="utf-8")
    with temp.open("rb+") as stream:
        os.fsync(stream.fileno())
    os.replace(temp, path)


def send_once(*_args, **_kwargs) -> dict:
    """The consumed authorization is permanently disabled in this candidate."""
    raise RuntimeError("HF01_NO_REPLAY: no Provider send authorization is active")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("preflight", "send-once"))
    parser.add_argument("--base-url")
    parser.add_argument("--out", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    if args.mode == "send-once":
        # Stop before reading configuration, touching a ledger, creating an SDK
        # client, or making a network-capable object.
        print(json.dumps({
            "status": "BLOCKED",
            "reason": "HF01_NO_REPLAY: no Provider send authorization is active",
            "provider_requests": 0,
        }))
        return 3
    if not args.base_url or args.out is None:
        parser.error("preflight needs --base-url and --out")
    try:
        normalized = validate_endpoint(args.base_url)
        result = asyncio.run(local_mock_success(normalized))
        failed = asyncio.run(local_mock_connect_error(normalized))
        record = {
            "created_at": utc_now(),
            "status": "PASS",
            "model": MODEL,
            "base_host": EXPECTED_HOST,
            "base_path": urlsplit(normalized).path or "/",
            "expected_completion_url": expected_url(normalized),
            "request_contract": {
                "method": "POST",
                "thinking": {"type": "disabled"},
                "max_tokens": MAX_TOKENS,
                "tools_included": False,
                "max_retries": 0,
                "timeout_seconds": TIMEOUT_SECONDS,
            },
            "success_mock": result,
            "connect_error_mock": failed,
            "provider_requests": 0,
            "os_level_external_network_block": "UNVERIFIED_NOT_RUN",
        }
        write_json(args.out, record)
        print(json.dumps({
            "status": record["status"],
            "expected_url": record["expected_completion_url"],
            "model": MODEL,
            "provider_requests": 0,
            "evidence_path": str(args.out),
        }, ensure_ascii=False))
        return 0
    except Exception as exc:
        # Report an error category only. Never print credentials or proxy values.
        print(json.dumps({
            "status": "BLOCKED",
            "error_type": type(exc).__name__,
            "reason": str(exc)[:200],
            "provider_requests": 0,
        }, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
