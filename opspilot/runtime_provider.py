"""HTTPX boundary for normal Assistant calls backed by a Runtime Grant."""
from __future__ import annotations

import contextvars
import json
from contextlib import contextmanager

import httpx

from opspilot.domain import assistant_runtime_grant as runtime_grant


_DISPATCH = contextvars.ContextVar("opspilot_runtime_provider_dispatch", default=None)


@contextmanager
def dispatch_context(binding, dispatch, *, call_id, request_digest, worker_id, worker_epoch):
    value = {
        "binding": binding,
        "dispatch": dispatch,
        "call_id": call_id,
        "request_digest": request_digest,
        "worker_id": worker_id,
        "worker_epoch": worker_epoch,
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


def _decoded_body_headers(headers):
    """Drop wire-body framing after HTTPX has decoded a response body."""
    encoded_representation_headers = {
        "content-encoding", "content-length", "transfer-encoding",
    }
    return {
        str(name): str(value)
        for name, value in headers.items()
        if str(name).lower() not in encoded_representation_headers
    }


class _SSEUsageCapture:
    """Validate a complete Chat Completions SSE response and retain trusted usage."""

    def __init__(self):
        self._line = bytearray()
        self._data: list[str] = []
        self.usage = None
        self.done = False
        self.finish_reason = None

    def feed(self, chunk: bytes) -> None:
        if self.done:
            return
        self._line.extend(chunk)
        while True:
            boundary = self._line.find(b"\n")
            if boundary < 0:
                break
            line = bytes(self._line[:boundary]).rstrip(b"\r")
            del self._line[:boundary + 1]
            self._consume_line(line)

    def _consume_line(self, line: bytes) -> None:
        if not line:
            self._consume_event()
            return
        if line.startswith(b"data:"):
            value = line[5:]
            if value.startswith(b" "):
                value = value[1:]
            try:
                self._data.append(value.decode("utf-8"))
            except UnicodeDecodeError as error:
                raise runtime_grant.RuntimeGrantError("RUNTIME_PROVIDER_STREAM_INVALID_UTF8") from error

    def _consume_event(self) -> None:
        if not self._data:
            return
        payload_text = "\n".join(self._data)
        self._data.clear()
        if payload_text == "[DONE]":
            self.done = True
            return
        try:
            payload = json.loads(payload_text)
        except json.JSONDecodeError as error:
            raise runtime_grant.RuntimeGrantError("RUNTIME_PROVIDER_STREAM_INVALID_EVENT") from error
        if not isinstance(payload, dict):
            raise runtime_grant.RuntimeGrantError("RUNTIME_PROVIDER_STREAM_INVALID_EVENT")
        if isinstance(payload.get("usage"), dict):
            self.usage = payload["usage"]
        choices = payload.get("choices")
        if choices is not None and not isinstance(choices, list):
            raise runtime_grant.RuntimeGrantError("RUNTIME_PROVIDER_STREAM_INVALID_EVENT")
        for choice in choices or []:
            if not isinstance(choice, dict):
                raise runtime_grant.RuntimeGrantError("RUNTIME_PROVIDER_STREAM_INVALID_EVENT")
            reason = choice.get("finish_reason")
            if isinstance(reason, str) and reason:
                self.finish_reason = reason

    def complete(self):
        if self._line:
            self._consume_line(bytes(self._line).rstrip(b"\r"))
            self._line.clear()
        self._consume_event()
        if not self.done or self.finish_reason is None:
            raise runtime_grant.RuntimeGrantError("RUNTIME_PROVIDER_STREAM_INCOMPLETE")
        return self.usage


class _CapturedAsyncByteStream(httpx.AsyncByteStream):
    def __init__(self, *, decoded_response, binding, request_key, status_code, headers, request):
        self.decoded_response = decoded_response
        self.binding = binding
        self.request_key = request_key
        self.status_code = status_code
        self.headers = headers
        self.request = request
        self.capture = _SSEUsageCapture()
        self.body = bytearray()
        self.completed = False
        self.closed = False

    def _persist_complete_response(self):
        usage = self.capture.complete()
        result = runtime_grant.store_response(
            self.binding["db_path"], self.request_key, status_code=self.status_code,
            headers=self.headers, body=bytes(self.body), usage=usage,
        )
        if not result.get("replayable"):
            raise runtime_grant.RuntimeGrantError(
                "RUNTIME_PROVIDER_USAGE_" + str(result.get("usage_state", "UNKNOWN"))
            )
        self.completed = True

    async def __aiter__(self):
        try:
            async for chunk in self.decoded_response.aiter_bytes():
                self.body.extend(chunk)
                self.capture.feed(chunk)
                if self.capture.done and not self.completed:
                    # The OpenAI SDK may stop pulling bytes immediately after
                    # [DONE], so persist at the protocol terminator rather than
                    # waiting for an additional iterator read.
                    self._persist_complete_response()
                yield chunk
            if not self.completed:
                self._persist_complete_response()
        except BaseException as error:
            if not self.completed:
                runtime_grant.mark_unknown(
                    self.binding["db_path"], self.request_key, type(error).__name__,
                )
            raise
        finally:
            await self._close_decoded_response()

    async def _close_decoded_response(self):
        if self.closed:
            return
        self.closed = True
        await self.decoded_response.aclose()

    async def aclose(self):
        if not self.completed:
            runtime_grant.mark_unknown(
                self.binding["db_path"], self.request_key, "ProviderStreamClosedEarly",
            )
        await self._close_decoded_response()


def wrap_transports(binding, async_transport, sync_transport):
    """Wrap only the current formal client pair; all grants remain DB-backed."""

    class RuntimeAsyncTransport(httpx.AsyncBaseTransport):
        def __init__(self, inner):
            self.inner = inner

        async def handle_async_request(self, request):
            context = _context_for(binding)
            body = await request.aread()
            try:
                request_payload = json.loads(body.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                request_payload = {}
            streaming = isinstance(request_payload, dict) and request_payload.get("stream") is True
            body_digest, output_cap = runtime_grant.validate_http_request(
                str(request.url), request.method, body, binding,
            )
            permit = runtime_grant.claim_send(
                binding["db_path"], binding, call_id=context["call_id"],
                request_key=context["dispatch"]["request_key"],
                request_digest=context["request_digest"], body_digest=body_digest,
                request_url=str(request.url), method=request.method,
                requested_max_output_tokens=output_cap, worker_id=context["worker_id"],
                worker_epoch=context["worker_epoch"],
            )
            if permit["action"] == "REPLAY":
                return httpx.Response(
                    int(permit["response_status"]), headers=permit["headers"],
                    content=permit["body"], request=request,
                )
            if streaming:
                # Usage is part of the last SSE event; ask the Provider for an
                # uncompressed wire body so the same bytes can be validated,
                # persisted, and replayed locally without a second send.
                request.headers["accept-encoding"] = "identity"
            try:
                response = await self.inner.handle_async_request(request)
                if streaming:
                    decoded_response = httpx.Response(
                        response.status_code, headers=dict(response.headers),
                        stream=response.stream, request=request,
                    )
                    response.headers = httpx.Headers(_decoded_body_headers(response.headers))
                    response.stream = _CapturedAsyncByteStream(
                        decoded_response=decoded_response, binding=binding,
                        request_key=context["dispatch"]["request_key"],
                        status_code=response.status_code, headers=dict(decoded_response.headers),
                        request=request,
                    )
                    return response
                try:
                    response_body = await response.aread()
                finally:
                    await response.aclose()
                result = runtime_grant.store_response(
                    binding["db_path"], context["dispatch"]["request_key"],
                    status_code=response.status_code, headers=dict(response.headers),
                    body=response_body, usage=_usage_from_body(response_body),
                )
                # `aread()` returns decoded bytes. Carrying the original
                # content-encoding/length into a new Response makes HTTPX try
                # to decode the already-decoded body again (and can surface
                # as an SDK connection error after a real HTTP 200).
                response_headers = _decoded_body_headers(response.headers)
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
            try:
                request_payload = json.loads(body.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                request_payload = {}
            if isinstance(request_payload, dict) and request_payload.get("stream") is True:
                raise runtime_grant.RuntimeGrantError("RUNTIME_PROVIDER_ASYNC_STREAM_REQUIRED")
            body_digest, output_cap = runtime_grant.validate_http_request(
                str(request.url), request.method, body, binding,
            )
            permit = runtime_grant.claim_send(
                binding["db_path"], binding, call_id=context["call_id"],
                request_key=context["dispatch"]["request_key"],
                request_digest=context["request_digest"], body_digest=body_digest,
                request_url=str(request.url), method=request.method,
                requested_max_output_tokens=output_cap, worker_id=context["worker_id"],
                worker_epoch=context["worker_epoch"],
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
                response_headers = _decoded_body_headers(response.headers)
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
