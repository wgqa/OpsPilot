from __future__ import annotations

import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit

from opspilot.domain.database import connect
from opspilot.domain.task_control import TaskControlError, TrustedIdentity, trusted_identity


COOKIE_NAME = "opspilot_session"


@dataclass(frozen=True)
class AuthContext:
    identity: TrustedIdentity
    token_digest: str
    csrf_digest: str
    expires_at: str


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def normalize_origin(value: str) -> str | None:
    try:
        parsed = urlsplit(value)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.path not in {"", "/"}:
            return None
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            return None
        host = parsed.hostname
        if host is None:
            return None
        port = parsed.port
        authority = host.lower() if port is None else f"{host.lower()}:{port}"
        return f"{parsed.scheme.lower()}://{authority}"
    except ValueError:
        return None


def check_origin(origin: str | None, expected_origin: str) -> None:
    if origin is None or normalize_origin(origin) != normalize_origin(expected_origin):
        raise TaskControlError("ORIGIN_REJECTED")


def issue_session(
    path: str | Path,
    *,
    actor_id: str,
    password: str,
    configured_password: str,
    ttl_seconds: int = 3600,
) -> tuple[str, str, AuthContext]:
    if not configured_password or not hmac.compare_digest(password, configured_password):
        raise TaskControlError("INVALID_CREDENTIALS")
    identity = trusted_identity(path, actor_id)
    token = secrets.token_urlsafe(32)
    csrf_token = secrets.token_urlsafe(32)
    token_digest, csrf_digest = _digest(token), _digest(csrf_token)
    now = datetime.now(timezone.utc)
    created_at = now.isoformat(timespec="milliseconds")
    expires_at = (now + timedelta(seconds=max(60, min(ttl_seconds, 86_400)))).isoformat(timespec="milliseconds")
    with connect(path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        # Re-resolve the actor inside the same write transaction before recording
        # a server-side session; request-supplied role/tenant never enter this row.
        row = connection.execute(
            "SELECT tenant_id, role FROM trusted_operators WHERE actor_id = ?", (actor_id,)
        ).fetchone()
        if row is None or (str(row["tenant_id"]), str(row["role"])) != (identity.tenant_id, identity.role):
            raise TaskControlError("TRUSTED_IDENTITY_MISMATCH")
        connection.execute(
            """INSERT INTO web_auth_sessions
               (token_digest, actor_id, tenant_id, role, csrf_digest, created_at, expires_at, revoked_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, NULL)""",
            (token_digest, identity.actor_id, identity.tenant_id, identity.role, csrf_digest, created_at, expires_at),
        )
    return token, csrf_token, AuthContext(identity, token_digest, csrf_digest, expires_at)


def authenticate_session(path: str | Path, token: str | None) -> AuthContext:
    if not token:
        raise TaskControlError("AUTHENTICATION_REQUIRED")
    digest = _digest(token)
    now = datetime.now(timezone.utc).isoformat(timespec="milliseconds")
    with connect(path) as connection:
        row = connection.execute(
            """SELECT s.actor_id, s.tenant_id, s.role, s.csrf_digest, s.expires_at
               FROM web_auth_sessions AS s JOIN trusted_operators AS o
                 ON o.actor_id = s.actor_id AND o.tenant_id = s.tenant_id AND o.role = s.role
               WHERE s.token_digest = ? AND s.revoked_at IS NULL AND s.expires_at > ?""",
            (digest, now),
        ).fetchone()
    if row is None:
        raise TaskControlError("AUTHENTICATION_REQUIRED")
    identity = TrustedIdentity(str(row["actor_id"]), str(row["tenant_id"]), str(row["role"]))
    return AuthContext(identity, digest, str(row["csrf_digest"]), str(row["expires_at"]))


def verify_csrf(context: AuthContext, csrf_token: str | None) -> None:
    if not csrf_token or not hmac.compare_digest(_digest(csrf_token), context.csrf_digest):
        raise TaskControlError("CSRF_REJECTED")


def revoke_session(path: str | Path, context: AuthContext) -> None:
    now = datetime.now(timezone.utc).isoformat(timespec="milliseconds")
    with connect(path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        connection.execute(
            "UPDATE web_auth_sessions SET revoked_at = ? WHERE token_digest = ? AND revoked_at IS NULL",
            (now, context.token_digest),
        )
