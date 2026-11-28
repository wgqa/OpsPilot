"""Offline reproduction of the configured endpoint path and live gate result."""
from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path
from urllib.parse import urlparse

import httpx
from openai import AsyncOpenAI

ROOT = Path(__file__).resolve().parents[4]
RUNNER_DIR = ROOT / "docs/evidence/abc-live-env-unblock-01"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(RUNNER_DIR))

from opspilot.config import MODEL_BASE_URL, MODEL_NAME, ROOT as CONFIG_ROOT, load_local_environment
import run_abc_eval as abc_runner


async def main() -> int:
    env_path = CONFIG_ROOT.parent.parent / ".env"
    if not env_path.is_file():
        raise RuntimeError("MAIN_REPO_ENV_NOT_FOUND")
    load_local_environment(env_path)
    base_url = os.environ[MODEL_BASE_URL]
    model = os.environ[MODEL_NAME]
    parsed = urlparse(base_url)
    seen: list[httpx.Request] = []

    async def respond(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={
            "id": "mock-route-only", "object": "chat.completion", "created": 1,
            "model": model,
            "choices": [{"index": 0, "message": {"role": "assistant", "content": "MOCK_ONLY"},
                         "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        })

    client_http = httpx.AsyncClient(transport=httpx.MockTransport(respond), trust_env=False)
    client = AsyncOpenAI(
        api_key="mock-only-not-a-provider-key", base_url=base_url,
        http_client=client_http, max_retries=0,
    )
    try:
        await client.chat.completions.create(
            model=model, messages=[{"role": "user", "content": "MOCK_ONLY"}], max_tokens=1,
        )
    finally:
        await client.close()

    if len(seen) != 1:
        raise AssertionError("EXPECTED_ONE_MOCKTRANSPORT_INVOCATION")
    request = seen[0]
    expected_payload = json.dumps({
        "model": model, "messages": [{"role": "user", "content": "MOCK_ONLY"}], "max_tokens": 1,
    }).encode("utf-8")
    guarded_request = httpx.Request(
        "POST", str(request.url), headers={"content-type": "application/json"}, content=expected_payload,
    )
    guarded_transport = abc_runner.BudgetedAsyncTransport(
        inner=httpx.MockTransport(lambda _request: (_ for _ in ()).throw(
            AssertionError("INNER_TRANSPORT_MUST_NOT_RUN"))),
        ledger=object(), case_id="Q02-B", mode="MOCK",
        trace_path=Path("D:/never-written/ar04-live-admission-path-test.jsonl.gz"),
    )
    try:
        guarded_transport._validate_request(guarded_request, expected_payload)
    except abc_runner.RunnerStop as error:
        reason = str(error)
    else:
        raise AssertionError("EXPECTED_EXISTING_PATH_GUARD_TO_REJECT_CONFIGURED_URL")

    if reason != "PROVIDER_ENDPOINT_OR_METHOD_MISMATCH":
        raise AssertionError(f"UNEXPECTED_GUARD_RESULT:{reason}")
    print({
        "main_repo_env_loaded": True,
        "configured_url_secret_free": {"scheme": parsed.scheme, "host": parsed.hostname, "path": parsed.path},
        "mocktransport_invocations": len(seen),
        "request_path": request.url.path,
        "runner_accepts_only_root_chat_path": True,
        "guard_rejection": reason,
        "budget_reservation_reached": False,
        "inner_transport_invocations": 0,
        "provider_requests_sent": 0,
    })
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
