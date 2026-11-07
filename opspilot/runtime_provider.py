"""HTTPX boundary for normal Assistant calls backed by a Runtime Grant."""
from __future__ import annotations

import contextvars
import json
from contextlib import contextmanager

import httpx

from opspilot.domain import assistant_runtime_grant as runtime_grant


_DISPATCH = contextvars.ContextVar("opspilot_runtime_provider_dispatch", default=None)


@contextmanager
def dispatch_context(binding, dispatch, *, call_id, request_digest, worker_id):
    value = {
        "binding": binding,
        "dispatch": dispatch,
        "call_id": call_id,
        "request_digest": request_digest,
        "worker_id": worker_id,
    }
    token = _DISPATCH.set(value)
    try:
        yield
    finally:
        _DISPATCH.reset(token)


def _context_for(binding):
    value = _DISPATCH.get()
    if not isinstance(value, dict):
        raise runtime_grant.RuntimeGrantError("RUNTIME_PROVIDER_DISPATCH_CONTEXT_REQUIRED")
    if value["binding"].get("run_id") != binding.get("run_id"):
        raise runtime_grant.RuntimeGrantError("RUNTIME_PROVIDER_DISPATCH_RUN_MISMATCH")
    return value


def _usage_from_body(body: bytes):
    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    return payload.get("usage") if isinstance(payload, dict) else None


def wrap_transports(binding, async_transport, sync_transport):
    """Wrap only the current formal client pair; all grants remain DB-backed."""

    class RuntimeAsyncTransport(httpx.AsyncBaseTransport):
        def __init__(self, inner):
            self.inner = inner

        async def handle_async_request(self, request):
            context = _context_for(binding)
            body = await request.aread()
            body_digest, output_cap = runtime_grant.validate_http_request(
                str(request.url), request.method, body, binding,
            )
            permit = runtime_grant.claim_send(
                binding["db_path"], binding, call_id=context["call_id"],
                request_key=context["dispatch"]["request_key"],
                request_digest=context["request_digest"], body_digest=body_digest,
                request_url=str(request.url), method=request.method,
                requested_max_output_tokens=output_cap, worker_id=context["worker_id"],
            )
            if permit["action"] == "REPLAY":
                return httpx.Response(
                    int(permit["response_status"]), headers=permit["headers"],
                    content=permit["body"], request=request,
                )
            try:
                response = await self.inner.handle_async_request(request)
                response_body = await response.aread()
                result = runtime_grant.store_response(
                    binding["db_path"], context["dispatch"]["request_key"],
                    status_code=response.status_code, headers=dict(response.headers),
                    body=response_body, usage=_usage_from_body(response_body),
                )
                response_headers = dict(response.headers)
                await response.aclose()
            except BaseException as error:
                runtime_grant.mark_unknown(
                    binding["db_path"], context["dispatch"]["request_key"],
                    type(error).__name__,
                )
                raise
            if not result.get("replayable"):
                raise runtime_grant.RuntimeGrantError(
                    "RUNTIME_PROVIDER_USAGE_" + str(result.get("usage_state", "UNKNOWN"))
                )
            return httpx.Response(
                response.status_code, headers=response_headers,
                content=response_body, request=request,
            )

        async def aclose(self):
            await self.inner.aclose()

    class RuntimeSyncTransport(httpx.BaseTransport):
        def __init__(self, inner):
            self.inner = inner

        def handle_request(self, request):
            context = _context_for(binding)
            body = request.read()
            body_digest, output_cap = runtime_grant.validate_http_request(
                str(request.url), request.method, body, binding,
            )
            permit = runtime_grant.claim_send(
                binding["db_path"], binding, call_id=context["call_id"],
                request_key=context["dispatch"]["request_key"],
                request_digest=context["request_digest"], body_digest=body_digest,
                request_url=str(request.url), method=request.method,
                requested_max_output_tokens=output_cap, worker_id=context["worker_id"],
            )
            if permit["action"] == "REPLAY":
                return httpx.Response(
                    int(permit["response_status"]), headers=permit["headers"],
                    content=permit["body"], request=request,
                )
            try:
                response = self.inner.handle_request(request)
                response_body = response.read()
                result = runtime_grant.store_response(
                    binding["db_path"], context["dispatch"]["request_key"],
                    status_code=response.status_code, headers=dict(response.headers),
                    body=response_body, usage=_usage_from_body(response_body),
                )
                response_headers = dict(response.headers)
                response.close()
            except BaseException as error:
                runtime_grant.mark_unknown(
                    binding["db_path"], context["dispatch"]["request_key"],
                    type(error).__name__,
                )
                raise
            if not result.get("replayable"):
                raise runtime_grant.RuntimeGrantError(
                    "RUNTIME_PROVIDER_USAGE_" + str(result.get("usage_state", "UNKNOWN"))
                )
            return httpx.Response(
                response.status_code, headers=response_headers,
                content=response_body, request=request,
            )

        def close(self):
            self.inner.close()

    return RuntimeAsyncTransport(async_transport), RuntimeSyncTransport(sync_transport)
