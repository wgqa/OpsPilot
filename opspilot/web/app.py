from __future__ import annotations

import asyncio
import json
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncIterator

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, StreamingResponse
from opspilot.domain.database import connect, initialize
from opspilot.domain.events import list_session_events, project_outbox, reconcile_legacy_action_events
from opspilot.domain.task_control import (
    TaskControlError,
    TrustedIdentity,
    abort_task,
    admit_task_message,
    create_session,
    create_task_with_initial_run,
    trusted_identity,
)
from opspilot.web.auth import (
    COOKIE_NAME,
    AuthContext,
    authenticate_session,
    check_origin,
    issue_session,
    revoke_session,
    verify_csrf,
)
from opspilot.web.schemas import AbortTaskRequest, CreateTaskRequest, LoginRequest, MessageRequest


_STATUS_BY_CODE = {
    "AUTHENTICATION_REQUIRED": 401,
    "INVALID_CREDENTIALS": 401,
    "ORIGIN_REJECTED": 403,
    "CSRF_REJECTED": 403,
    "TASK_OWNER_REQUIRED": 403,
    "TASK_RUN_SCOPE_DENIED": 404,
    "SESSION_SCOPE_DENIED": 404,
    "SESSION_TASK_LINK_REQUIRED": 404,
    "TASK_SCOPE_DENIED": 404,
    "TASK_RUN_NOT_FOUND": 404,
    "RESOURCE_NOT_FOUND": 404,
    "IDEMPOTENCY_CONFLICT": 409,
    "IDEMPOTENCY_STATE_AMBIGUOUS": 409,
    "IDEMPOTENCY_KEY_REQUIRED": 422,
    "TASK_RUN_BUSY": 409,
    "TASK_RUN_NOT_QUEUED": 409,
    "TASK_RUN_NOT_RESUMABLE": 409,
    "TASK_RUN_NOT_ACTIVE": 409,
    "TASK_ABORTED": 409,
    "TASK_ALREADY_TERMINAL": 409,
    "TASK_CONTROL_STALE": 409,
    "TASK_INPUT_PENDING": 409,
    "TASK_REQUIRED_FOR_BUSINESS_RUN": 409,
    "CORRECTION_REQUIRES_TASK": 422,
    "INVALID_REQUEST": 422,
}


def _public_run(row: Any) -> dict[str, Any]:
    return {
        "run_id": str(row["run_id"]),
        "task_id": str(row["task_id"]) if row["task_id"] is not None else None,
        "session_id": str(row["session_id"]),
        "source_message_id": str(row["source_message_id"]) if row["source_message_id"] else None,
        "kind": str(row["kind"]),
        "status": str(row["status"]),
        "waiting_reason": str(row["blocked_reason"]) if row["blocked_reason"] else None,
        "created_at": str(row["created_at"]),
        "started_at": str(row["started_at"]) if row["started_at"] else None,
        "ended_at": str(row["ended_at"]) if row["ended_at"] else None,
        "answer_status": "NOT_IMPLEMENTED" if row["kind"] == "CHAT_READONLY" else None,
    }


def create_app(
    *,
    db_path: str | Path | None = None,
    checkpoint_db_path: str | Path | None = None,
    start_worker: bool = True,
    credentials: dict[str, str] | None = None,
    expected_origin: str | None = None,
    heartbeat_seconds: float = 10.0,
) -> FastAPI:
    from opspilot.config import DEFAULT_CHECKPOINT_DB_PATH, database_path, load_local_environment

    load_local_environment()
    resolved_db = database_path(str(db_path) if db_path is not None else None)
    checkpoint_path = Path(checkpoint_db_path or os.environ.get("OPSPILOT_CHECKPOINT_DB_PATH") or DEFAULT_CHECKPOINT_DB_PATH)
    if not checkpoint_path.is_absolute():
        checkpoint_path = Path(__file__).resolve().parents[2] / checkpoint_path
    checkpoint_path = checkpoint_path.resolve()
    origin = expected_origin or os.environ.get("OPSPILOT_WEB_ORIGIN", "http://127.0.0.1:8000")
    passwords = credentials or {
        "support-a": os.environ.get("OPSPILOT_WEB_SUPPORT_PASSWORD", ""),
        "approver-a": os.environ.get("OPSPILOT_WEB_APPROVER_PASSWORD", ""),
        "support-b": os.environ.get("OPSPILOT_WEB_SUPPORT_B_PASSWORD", ""),
        "approver-b": os.environ.get("OPSPILOT_WEB_APPROVER_B_PASSWORD", ""),
    }
    ttl_seconds = int(os.environ.get("OPSPILOT_WEB_SESSION_TTL_SECONDS", "3600"))
    deadline_ms = int(os.environ.get("OPSPILOT_INVESTIGATION_DEADLINE_MS", "300000"))
    executor_id = os.environ.get("OPSPILOT_EXECUTOR_ID", "executor-a")

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        initialize(resolved_db)
        reconcile_legacy_action_events(str(resolved_db))
        project_outbox(str(resolved_db))
        worker = None
        worker_task: asyncio.Task[None] | None = None
        if start_worker:
            from opspilot.web.worker import SingleInstanceWorker, run_worker

            worker = SingleInstanceWorker(resolved_db)
            worker.acquire()
            worker.register()
            await worker.recover_after_exclusive_start()
            worker_task = asyncio.create_task(
                run_worker(
                    resolved_db,
                    checkpoint_path,
                    worker_id=worker.owner_id,
                    executor_id=executor_id,
                ),
                name="opspilot-domain-run-worker",
            )
            app.state.worker_id = worker.owner_id
        try:
            yield
        finally:
            if worker_task is not None:
                worker_task.cancel()
                try:
                    await worker_task
                except asyncio.CancelledError:
                    pass
            if worker is not None:
                worker.release()

    app = FastAPI(title="OpsPilot Local API", version="1.0", lifespan=lifespan)
    app.state.db_path = resolved_db
    app.state.expected_origin = origin
    app.state.heartbeat_seconds = max(0.05, heartbeat_seconds)
    app.state.cookie_secure = origin.lower().startswith("https://")

    async def current_user(request: Request) -> AuthContext:
        return authenticate_session(resolved_db, request.cookies.get(COOKIE_NAME))

    async def write_user(request: Request) -> AuthContext:
        context = await current_user(request)
        check_origin(request.headers.get("origin"), origin)
        verify_csrf(context, request.headers.get("x-csrf-token"))
        return context

    @app.exception_handler(TaskControlError)
    async def task_control_error(_request: Request, error: TaskControlError) -> JSONResponse:
        return JSONResponse({"code": error.code}, status_code=_STATUS_BY_CODE.get(error.code, 400))

    @app.exception_handler(RequestValidationError)
    async def validation_error(_request: Request, _error: RequestValidationError) -> JSONResponse:
        return JSONResponse({"code": "INVALID_REQUEST"}, status_code=422)

    @app.exception_handler(HTTPException)
    async def http_error(_request: Request, error: HTTPException) -> JSONResponse:
        code = str(error.detail) if isinstance(error.detail, str) else "HTTP_ERROR"
        return JSONResponse({"code": code}, status_code=error.status_code)

    @app.exception_handler(Exception)
    async def internal_error(_request: Request, _error: Exception) -> JSONResponse:
        return JSONResponse({"code": "INTERNAL_ERROR"}, status_code=500)

    def require_idempotency_key(value: str | None) -> str:
        if value is None or not value.strip() or len(value) > 200:
            raise TaskControlError("IDEMPOTENCY_KEY_REQUIRED")
        return value.strip()

    def require_session_owner(identity: TrustedIdentity, session_id: str) -> None:
        with connect(resolved_db) as connection:
            row = connection.execute(
                "SELECT 1 FROM sessions WHERE session_id = ? AND tenant_id = ? AND owner_id = ?",
                (session_id, identity.tenant_id, identity.actor_id),
            ).fetchone()
        if row is None:
            raise TaskControlError("SESSION_SCOPE_DENIED")

    def require_task_reader(identity: TrustedIdentity, task_id: str) -> dict[str, Any]:
        with connect(resolved_db) as connection:
            row = connection.execute(
                """SELECT b.task_id, b.thread_id, b.tenant_id, b.actor_id, b.service_id,
                          b.integration_id, b.principal_id, b.ticket_id, b.status,
                          c.terminal_state, c.control_revision, c.pending_critical_message_seq,
                          c.applied_critical_message_seq
                   FROM task_bindings AS b JOIN task_controls AS c
                     ON c.task_id = b.task_id AND c.tenant_id = b.tenant_id
                   WHERE b.task_id = ? AND b.tenant_id = ?""",
                (task_id, identity.tenant_id),
            ).fetchone()
            if row is None:
                raise TaskControlError("TASK_SCOPE_DENIED")
            if identity.role == "SUPPORT" and str(row["actor_id"]) == identity.actor_id:
                return {key: row[key] for key in row.keys()}
            if identity.role == "APPROVER":
                allowed = connection.execute(
                    """SELECT 1 FROM d3_plans AS p JOIN d3_plan_authorizations AS a
                         ON a.tenant_id = p.tenant_id AND a.task_id = p.task_id AND a.plan_hash = p.plan_hash
                       WHERE p.task_id = ? AND p.tenant_id = ? AND a.eligibility = 'ACTIVE'
                         AND ? = 'WAITING_APPROVAL' LIMIT 1""",
                    (task_id, identity.tenant_id, row["status"]),
                ).fetchone()
                if allowed is not None:
                    return {key: row[key] for key in row.keys()}
        raise TaskControlError("TASK_SCOPE_DENIED")

    @app.get("/api/health")
    async def health() -> dict[str, Any]:
        return {"status": "ok", "mode": "local-single-instance", "worker": bool(start_worker)}

    @app.post("/api/auth/login")
    async def login(request: Request, body: LoginRequest, response: Response) -> dict[str, Any]:
        check_origin(request.headers.get("origin"), origin)
        configured_password = passwords.get(body.actor_id, "")
        token, csrf_token, context = issue_session(
            resolved_db, actor_id=body.actor_id, password=body.password,
            configured_password=configured_password, ttl_seconds=ttl_seconds,
        )
        response.set_cookie(
            COOKIE_NAME, token, max_age=max(60, min(ttl_seconds, 86_400)), httponly=True,
            secure=app.state.cookie_secure, samesite="strict", path="/api",
        )
        return {"actor_id": context.identity.actor_id, "tenant_id": context.identity.tenant_id,
                "role": context.identity.role, "csrf_token": csrf_token, "expires_at": context.expires_at}

    @app.get("/api/auth/me")
    async def me(context: AuthContext = Depends(current_user)) -> dict[str, Any]:
        return {"actor_id": context.identity.actor_id, "tenant_id": context.identity.tenant_id,
                "role": context.identity.role, "expires_at": context.expires_at}

    @app.post("/api/auth/logout")
    async def logout(response: Response, context: AuthContext = Depends(write_user)) -> dict[str, str]:
        revoke_session(resolved_db, context)
        response.delete_cookie(COOKIE_NAME, path="/api", httponly=True,
                               secure=app.state.cookie_secure, samesite="strict")
        return {"status": "logged_out"}

    @app.post("/api/sessions", status_code=201)
    async def post_session(context: AuthContext = Depends(write_user)) -> dict[str, Any]:
        return create_session(resolved_db, context.identity)

    @app.get("/api/sessions")
    async def get_sessions(
        limit: int = Query(default=50, ge=1, le=100), offset: int = Query(default=0, ge=0),
        context: AuthContext = Depends(current_user),
    ) -> dict[str, Any]:
        with connect(resolved_db) as connection:
            rows = connection.execute(
                """SELECT s.session_id, s.created_at, s.updated_at,
                          (SELECT COUNT(*) FROM session_task_links l WHERE l.session_id = s.session_id) AS task_count
                   FROM sessions s WHERE s.tenant_id = ? AND s.owner_id = ?
                   ORDER BY s.updated_at DESC, s.session_id ASC LIMIT ? OFFSET ?""",
                (context.identity.tenant_id, context.identity.actor_id, limit, offset),
            ).fetchall()
        return {"items": [{key: row[key] for key in row.keys()} for row in rows],
                "limit": limit, "offset": offset}

    @app.get("/api/sessions/{session_id}")
    async def get_session(session_id: str, context: AuthContext = Depends(current_user)) -> dict[str, Any]:
        require_session_owner(context.identity, session_id)
        with connect(resolved_db) as connection:
            row = connection.execute(
                "SELECT session_id, created_at, updated_at FROM sessions WHERE session_id = ?",
                (session_id,),
            ).fetchone()
            links = connection.execute(
                "SELECT task_id, linked_at, is_primary FROM session_task_links WHERE session_id = ? ORDER BY linked_at, task_id",
                (session_id,),
            ).fetchall()
        return {**{key: row[key] for key in row.keys()},
                "tasks": [{key: link[key] for key in link.keys()} for link in links]}

    @app.post("/api/sessions/{session_id}/tasks", status_code=202)
    async def post_task(
        session_id: str,
        body: CreateTaskRequest,
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
        context: AuthContext = Depends(write_user),
    ) -> dict[str, Any]:
        key = require_idempotency_key(idempotency_key)
        if context.identity.role != "SUPPORT":
            raise TaskControlError("TASK_OWNER_REQUIRED")
        result = create_task_with_initial_run(
            resolved_db, context.identity, session_id=session_id,
            service_id=os.environ.get("OPSPILOT_DEMO_SERVICE_ID", "orders-demo"),
            integration_id=os.environ.get("OPSPILOT_DEMO_INTEGRATION_ID", "integration-a"),
            ticket_id=os.environ.get("OPSPILOT_DEMO_TICKET_ID", "INC-A-001"),
            initial_message=body.initial_message, idempotency_key=key,
            deadline_ms=deadline_ms,
        )
        replayed = bool(result.pop("replayed", False))
        return JSONResponse({**result, "replayed": replayed}, status_code=200 if replayed else 202)

    @app.get("/api/tasks/{task_id}")
    async def get_task(task_id: str, context: AuthContext = Depends(current_user)) -> dict[str, Any]:
        item = require_task_reader(context.identity, task_id)
        with connect(resolved_db) as connection:
            plan = connection.execute(
                """SELECT plan_hash, plan_version, created_by, created_at FROM d3_plans
                   WHERE task_id = ? ORDER BY plan_version DESC LIMIT 1""",
                (task_id,),
            ).fetchone()
        output = {key: item[key] for key in item.keys()}
        output["pending_plan"] = ({key: plan[key] for key in plan.keys()} if plan else None)
        return output

    @app.get("/api/tasks/{task_id}/runs")
    async def get_task_runs(
        task_id: str, context: AuthContext = Depends(current_user)
    ) -> dict[str, Any]:
        require_task_reader(context.identity, task_id)
        with connect(resolved_db) as connection:
            rows = connection.execute(
                "SELECT * FROM task_runs WHERE task_id = ? AND tenant_id = ? ORDER BY created_at, run_id",
                (task_id, context.identity.tenant_id),
            ).fetchall()
        return {"items": [_public_run(row) for row in rows]}

    @app.get("/api/runs/{run_id}")
    async def get_run(run_id: str, context: AuthContext = Depends(current_user)) -> dict[str, Any]:
        with connect(resolved_db) as connection:
            row = connection.execute(
                "SELECT * FROM task_runs WHERE run_id = ? AND tenant_id = ?",
                (run_id, context.identity.tenant_id),
            ).fetchone()
        if row is None:
            raise TaskControlError("TASK_RUN_SCOPE_DENIED")
        if row["task_id"] is not None:
            require_task_reader(context.identity, str(row["task_id"]))
        else:
            require_session_owner(context.identity, str(row["session_id"]))
        return _public_run(row)

    @app.post("/api/sessions/{session_id}/messages", status_code=202)
    async def post_message(
        session_id: str,
        body: MessageRequest,
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
        context: AuthContext = Depends(write_user),
    ) -> dict[str, Any]:
        result = admit_task_message(
            resolved_db, context.identity, session_id=session_id, task_id=body.task_id,
            input_kind=body.input_kind, body=body.body,
            idempotency_key=require_idempotency_key(idempotency_key),
        )
        return {**result, "answer_status": "NOT_IMPLEMENTED" if body.input_kind == "CHAT_READONLY" else None}

    @app.get("/api/sessions/{session_id}/messages")
    async def get_messages(
        session_id: str,
        after_seq: int = Query(default=0, ge=0), limit: int = Query(default=100, ge=1, le=500),
        context: AuthContext = Depends(current_user),
    ) -> dict[str, Any]:
        require_session_owner(context.identity, session_id)
        with connect(resolved_db) as connection:
            rows = connection.execute(
                """SELECT message_id, task_id, sequence, role, input_kind, body, created_at,
                          application_state, applied_run_id
                   FROM messages WHERE session_id = ? AND tenant_id = ? AND sequence > ?
                   ORDER BY sequence LIMIT ?""",
                (session_id, context.identity.tenant_id, after_seq, limit),
            ).fetchall()
        return {"items": [{key: row[key] for key in row.keys()} for row in rows]}

    @app.post("/api/tasks/{task_id}/abort", status_code=202)
    async def post_abort(
        task_id: str,
        body: AbortTaskRequest,
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
        context: AuthContext = Depends(write_user),
    ) -> dict[str, Any]:
        return abort_task(
            resolved_db, context.identity, task_id=task_id, reason=body.reason,
            idempotency_key=require_idempotency_key(idempotency_key),
        )

    def event_cursor(after: int, last_event_id: str | None) -> int:
        if last_event_id is not None:
            try:
                parsed = int(last_event_id)
            except ValueError as error:
                raise TaskControlError("INVALID_EVENT_CURSOR") from error
            if parsed < 0:
                raise TaskControlError("INVALID_EVENT_CURSOR")
            return parsed  # Last-Event-ID explicitly wins over `after`.
        return after

    @app.get("/api/sessions/{session_id}/events/history")
    async def event_history(
        session_id: str,
        after: int = Query(default=0, ge=0), limit: int = Query(default=100, ge=1, le=500),
        last_event_id: str | None = Header(default=None, alias="Last-Event-ID"),
        context: AuthContext = Depends(current_user),
    ) -> dict[str, Any]:
        cursor = event_cursor(after, last_event_id)
        project_outbox(str(resolved_db))
        events = list_session_events(str(resolved_db), session_id, context.identity,
                                     after_seq=cursor, limit=limit)
        return {"items": events, "after": cursor, "cursor_source": "Last-Event-ID" if last_event_id is not None else "after"}

    @app.get("/api/sessions/{session_id}/events")
    async def event_stream(
        request: Request,
        session_id: str,
        after: int = Query(default=0, ge=0),
        last_event_id: str | None = Header(default=None, alias="Last-Event-ID"),
        context: AuthContext = Depends(current_user),
    ) -> StreamingResponse:
        cursor = event_cursor(after, last_event_id)
        require_session_owner(context.identity, session_id)
        heartbeat = app.state.heartbeat_seconds

        async def stream() -> AsyncIterator[str]:
            nonlocal cursor
            last_heartbeat = time.monotonic()
            while not await request.is_disconnected():
                try:
                    authenticate_session(resolved_db, request.cookies.get(COOKIE_NAME))
                except TaskControlError:
                    break
                project_outbox(str(resolved_db))
                events = list_session_events(str(resolved_db), session_id, context.identity,
                                             after_seq=cursor, limit=100)
                if events:
                    for event in events:
                        cursor = int(event["event_seq"])
                        data = json.dumps(event["payload"], ensure_ascii=False, sort_keys=True)
                        yield f"id: {cursor}\nevent: {event['event_kind']}\ndata: {data}\n\n"
                    last_heartbeat = time.monotonic()
                    continue
                if time.monotonic() - last_heartbeat >= heartbeat:
                    yield ": heartbeat\n\n"
                    last_heartbeat = time.monotonic()
                await asyncio.sleep(min(heartbeat, 0.25))

        return StreamingResponse(
            stream(), media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no",
                     "X-Content-Type-Options": "nosniff"},
        )

    return app
