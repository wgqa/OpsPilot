"""One deployment-wide, opt-in Runtime Grant and durable Assistant spend pool.

This is deliberately a small local-domain boundary, not an HTTP/admin service.
Schema creation never provisions authority, a Grant, or money. Only explicit
trusted local operations below can do that.
"""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from opspilot.domain.database import connect
from opspilot.domain.d2 import canonical_json, digest_json, utc_now


SCHEMA = """
CREATE TABLE IF NOT EXISTS assistant_runtime_authority (
  singleton INTEGER PRIMARY KEY CHECK(singleton=1),
  authority_id TEXT NOT NULL UNIQUE,
  database_file_identity TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS assistant_runtime_pools (
  pool_id TEXT PRIMARY KEY CHECK(pool_id='DEFAULT'),
  authority_id TEXT NOT NULL,
  total_limit_usd_micro INTEGER NOT NULL CHECK(total_limit_usd_micro > 0),
  status TEXT NOT NULL CHECK(status IN ('ACTIVE','PAUSED')),
  pause_reason TEXT,
  version INTEGER NOT NULL CHECK(version >= 1),
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS assistant_runtime_default_grant (
  singleton INTEGER PRIMARY KEY CHECK(singleton=1),
  grant_id TEXT NOT NULL UNIQUE,
  version INTEGER NOT NULL CHECK(version >= 1),
  authority_id TEXT NOT NULL,
  pool_id TEXT NOT NULL CHECK(pool_id='DEFAULT'),
  status TEXT NOT NULL CHECK(status IN ('ACTIVE','REVOKED')),
  grant_source TEXT NOT NULL,
  operator_id TEXT NOT NULL,
  service_identity TEXT NOT NULL,
  model_id TEXT NOT NULL,
  endpoint TEXT NOT NULL,
  model_config_version TEXT NOT NULL,
  price_version TEXT NOT NULL,
  input_rate_micro_per_million INTEGER NOT NULL CHECK(input_rate_micro_per_million >= 0),
  output_rate_micro_per_million INTEGER NOT NULL CHECK(output_rate_micro_per_million >= 0),
  max_input_tokens INTEGER NOT NULL CHECK(max_input_tokens > 0),
  max_output_tokens INTEGER NOT NULL CHECK(max_output_tokens > 0),
  valid_from TEXT NOT NULL,
  expires_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS assistant_runtime_grant_history (
  grant_id TEXT NOT NULL,
  version INTEGER NOT NULL,
  snapshot_json TEXT NOT NULL,
  created_at TEXT NOT NULL,
  PRIMARY KEY(grant_id,version)
);
CREATE TABLE IF NOT EXISTS assistant_runtime_run_bindings (
  run_id TEXT PRIMARY KEY,
  session_id TEXT NOT NULL,
  task_id TEXT,
  source_message_id TEXT NOT NULL,
  grant_id TEXT NOT NULL,
  grant_version INTEGER NOT NULL,
  authority_id TEXT NOT NULL,
  database_file_identity TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS assistant_runtime_spends (
  dispatch_id TEXT PRIMARY KEY,
  pool_id TEXT NOT NULL CHECK(pool_id='DEFAULT'),
  authority_id TEXT NOT NULL,
  request_key TEXT NOT NULL UNIQUE,
  assistant_call_id TEXT NOT NULL UNIQUE,
  run_id TEXT NOT NULL,
  session_id TEXT NOT NULL,
  source_message_id TEXT NOT NULL,
  logical_key TEXT NOT NULL,
  request_digest TEXT NOT NULL,
  http_body_digest TEXT,
  http_url TEXT,
  http_method TEXT,
  worker_id TEXT,
  grant_id TEXT NOT NULL,
  grant_version INTEGER NOT NULL,
  price_version TEXT NOT NULL,
  input_rate_micro_per_million INTEGER NOT NULL,
  output_rate_micro_per_million INTEGER NOT NULL,
  max_input_tokens INTEGER NOT NULL,
  max_output_tokens INTEGER NOT NULL,
  requested_max_output_tokens INTEGER,
  reserved_usd_micro INTEGER NOT NULL CHECK(reserved_usd_micro >= 0),
  settled_usd_micro INTEGER,
  status TEXT NOT NULL CHECK(status IN ('RESERVED','SEND_GRANTED','UNKNOWN','RESPONSE_STORED','DELIVERED','VIOLATION','NOT_DISPATCHED','RECONCILED')),
  response_status INTEGER,
  response_headers_json TEXT,
  response_body BLOB,
  usage_json TEXT,
  completion_id TEXT,
  error_code TEXT,
  created_at TEXT NOT NULL,
  send_granted_at TEXT,
  completed_at TEXT,
  updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_assistant_runtime_spends_pool_status
  ON assistant_runtime_spends(pool_id,status);
CREATE UNIQUE INDEX IF NOT EXISTS ux_assistant_runtime_one_send_per_pool
  ON assistant_runtime_spends(pool_id) WHERE status='SEND_GRANTED';
CREATE TABLE IF NOT EXISTS assistant_runtime_audit (
  audit_id TEXT PRIMARY KEY,
  authority_id TEXT NOT NULL,
  grant_id TEXT,
  action TEXT NOT NULL,
  operator_id TEXT NOT NULL,
  source TEXT NOT NULL,
  evidence_ref TEXT NOT NULL,
  evidence_digest TEXT NOT NULL,
  idempotency_key TEXT NOT NULL UNIQUE,
  request_digest TEXT NOT NULL,
  details_json TEXT NOT NULL,
  created_at TEXT NOT NULL
);
"""


class RuntimeGrantError(RuntimeError):
    def __init__(self, code: str, *, commit_changes: bool = False):
        super().__init__(code)
        self.code = code
        self.commit_changes = commit_changes


POOL_ID = "DEFAULT"
MAX_PRODUCT_INPUT_TOKENS = 12_000
MAX_PRODUCT_OUTPUT_TOKENS = 2_048


def _file_identity(path: str | Path) -> str:
    value = str(path)
    if value == ":memory:":
        raise RuntimeGrantError("RUNTIME_DB_IDENTITY_UNAVAILABLE")
    try:
        info = Path(path).resolve(strict=True).stat()
    except OSError as error:
        raise RuntimeGrantError("RUNTIME_DB_IDENTITY_UNAVAILABLE") from error
    # st_ino is the filesystem file ID on supported local filesystems. Together
    # with the volume/device ID it detects a copied/replaced database file.
    if not info.st_ino:
        raise RuntimeGrantError("RUNTIME_DB_FILE_ID_UNAVAILABLE")
    return hashlib.sha256(f"{info.st_dev}:{info.st_ino}".encode("ascii")).hexdigest()


def _endpoint(value: object) -> str:
    if not isinstance(value, str):
        raise RuntimeGrantError("RUNTIME_PROVIDER_ENDPOINT_INVALID")
    parsed = urlparse(value.strip())
    if (
        parsed.scheme != "https" or parsed.hostname != "api.deepseek.com"
        or parsed.port not in (None, 443) or parsed.username is not None
        or parsed.password is not None or parsed.query or parsed.fragment
        or parsed.path not in ("", "/", "/v1")
    ):
        raise RuntimeGrantError("RUNTIME_PROVIDER_ENDPOINT_INVALID")
    return value.strip().rstrip("/")


def runtime_config_from_env() -> dict[str, str]:
    """Read non-secret deployment identity/config used to bind the Grant."""
    from opspilot.config import MODEL_BASE_URL, MODEL_NAME

    values = {
        "model_id": os.environ.get(MODEL_NAME, "").strip(),
        "endpoint": os.environ.get(MODEL_BASE_URL, "").strip(),
        "model_config_version": os.environ.get("OPSPILOT_MODEL_CONFIG_VERSION", "").strip(),
        "price_version": os.environ.get("OPSPILOT_MODEL_PRICE_VERSION", "").strip(),
        "service_identity": os.environ.get("OPSPILOT_ASSISTANT_SERVICE_IDENTITY", "").strip(),
    }
    if any(not value for value in values.values()):
        raise RuntimeGrantError("RUNTIME_DEPLOYMENT_CONFIG_INCOMPLETE")
    values["endpoint"] = _endpoint(values["endpoint"])
    return values


def _valid_iso(value: object, code: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise RuntimeGrantError(code)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise RuntimeGrantError(code) from error
    if parsed.tzinfo is None:
        raise RuntimeGrantError(code)
    return parsed.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _validate_evidence(operator_id, source, evidence_ref, evidence_digest, idempotency_key):
    values = (operator_id, source, evidence_ref, evidence_digest, idempotency_key)
    if any(not isinstance(value, str) or not value.strip() for value in values):
        raise RuntimeGrantError("RUNTIME_GRANT_AUDIT_EVIDENCE_REQUIRED")
    digest = evidence_digest.strip().lower()
    if len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
        raise RuntimeGrantError("RUNTIME_GRANT_AUDIT_EVIDENCE_DIGEST_INVALID")


def _grant_snapshot(row, *, pool_limit=None):
    data = dict(row)
    data.pop("singleton", None)
    data.pop("updated_at", None)
    if pool_limit is not None:
        data["total_limit_usd_micro"] = int(pool_limit)
    return data


def _write_history(connection, row, pool_limit):
    snapshot = _grant_snapshot(row, pool_limit=pool_limit)
    connection.execute(
        "INSERT OR IGNORE INTO assistant_runtime_grant_history(grant_id,version,snapshot_json,created_at) VALUES (?,?,?,?)",
        (row["grant_id"], int(row["version"]), canonical_json(snapshot), utc_now()),
    )


def _audit(connection, *, authority_id, grant_id, action, operator_id, source,
           evidence_ref, evidence_digest, idempotency_key, request, details):
    request_digest = digest_json(request)
    old = connection.execute(
        "SELECT * FROM assistant_runtime_audit WHERE idempotency_key=?", (idempotency_key,)
    ).fetchone()
    if old:
        if not _audit_replay_matches(
            old, action=action, operator_id=operator_id, source=source,
            evidence_ref=evidence_ref, evidence_digest=evidence_digest,
            request_digest=request_digest,
        ):
            raise RuntimeGrantError("RUNTIME_AUDIT_IDEMPOTENCY_CONFLICT")
        return False
    connection.execute(
        """INSERT INTO assistant_runtime_audit
           (audit_id,authority_id,grant_id,action,operator_id,source,evidence_ref,evidence_digest,
            idempotency_key,request_digest,details_json,created_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
        ("runtime-audit-" + str(uuid.uuid4()), authority_id, grant_id, action,
         operator_id.strip(), source.strip(), evidence_ref.strip(), evidence_digest.strip().lower(),
         idempotency_key.strip(), request_digest, canonical_json(details), utc_now()),
    )
    return True


def _audit_replay_matches(old, *, action, operator_id, source, evidence_ref,
                          evidence_digest, request_digest) -> bool:
    return (
        old["action"] == action
        and old["request_digest"] == request_digest
        and old["operator_id"] == operator_id.strip()
        and old["source"] == source.strip()
        and old["evidence_ref"] == evidence_ref.strip()
        and old["evidence_digest"] == evidence_digest.strip().lower()
    )


def _authority(connection, path):
    row = connection.execute("SELECT * FROM assistant_runtime_authority WHERE singleton=1").fetchone()
    if row is None:
        raise RuntimeGrantError("RUNTIME_GRANT_NOT_PROVISIONED")
    if _file_identity(path) != row["database_file_identity"]:
        raise RuntimeGrantError("RUNTIME_DB_IDENTITY_MISMATCH")
    return dict(row)


def _pool(connection):
    row = connection.execute("SELECT * FROM assistant_runtime_pools WHERE pool_id=?", (POOL_ID,)).fetchone()
    if row is None:
        raise RuntimeGrantError("RUNTIME_SPEND_POOL_NOT_PROVISIONED")
    if row["status"] != "ACTIVE":
        raise RuntimeGrantError("RUNTIME_SPEND_POOL_PAUSED:" + str(row["pause_reason"] or "UNKNOWN"))
    return dict(row)


def _usage_values(usage):
    if not isinstance(usage, dict):
        return None
    input_tokens = usage.get("prompt_tokens", usage.get("input_tokens"))
    output_tokens = usage.get("completion_tokens", usage.get("output_tokens"))
    total_tokens = usage.get("total_tokens")
    if type(input_tokens) is not int or type(output_tokens) is not int or type(total_tokens) is not int:
        return None
    if input_tokens < 0 or output_tokens < 0 or total_tokens != input_tokens + output_tokens:
        return None
    return {"input_tokens": input_tokens, "output_tokens": output_tokens, "total_tokens": total_tokens}


def _cost_micro(input_tokens, output_tokens, input_rate, output_rate):
    numerator = input_tokens * input_rate + output_tokens * output_rate
    return (numerator + 999_999) // 1_000_000


def _effective_spend(connection):
    rows = connection.execute(
        "SELECT status,reserved_usd_micro,settled_usd_micro FROM assistant_runtime_spends WHERE pool_id=?",
        (POOL_ID,),
    ).fetchall()
    total = 0
    for row in rows:
        status = str(row["status"])
        if status in {"RESERVED", "SEND_GRANTED", "UNKNOWN"}:
            total += int(row["reserved_usd_micro"])
        elif status in {"RESPONSE_STORED", "DELIVERED", "RECONCILED", "VIOLATION"}:
            if row["settled_usd_micro"] is None or int(row["settled_usd_micro"]) < 0:
                _pause(connection, "SPEND_LEDGER_INTEGRITY_ERROR")
                raise RuntimeGrantError("RUNTIME_LEDGER_INTEGRITY_ERROR", commit_changes=True)
            total += int(row["settled_usd_micro"])
        elif status not in {"NOT_DISPATCHED"}:
            _pause(connection, "SPEND_LEDGER_INTEGRITY_ERROR")
            raise RuntimeGrantError("RUNTIME_LEDGER_INTEGRITY_ERROR", commit_changes=True)
    pool = connection.execute(
        "SELECT total_limit_usd_micro FROM assistant_runtime_pools WHERE pool_id=?",
        (POOL_ID,),
    ).fetchone()
    if pool is not None and total > int(pool["total_limit_usd_micro"]):
        _pause(connection, "SPEND_LEDGER_EXCEEDS_AUTHORIZED_LIMIT")
        raise RuntimeGrantError("RUNTIME_LEDGER_INTEGRITY_ERROR", commit_changes=True)
    return total


def _pause(connection, reason):
    connection.execute(
        "UPDATE assistant_runtime_pools SET status='PAUSED',pause_reason=?,version=version+1,updated_at=? WHERE pool_id=?",
        (reason, utc_now(), POOL_ID),
    )


def _current_grant(connection, path, config, *, check_active=True):
    authority = _authority(connection, path)
    pool = _pool(connection)
    row = connection.execute("SELECT * FROM assistant_runtime_default_grant WHERE singleton=1").fetchone()
    if row is None:
        raise RuntimeGrantError("RUNTIME_GRANT_NOT_PROVISIONED")
    grant = dict(row)
    if grant["authority_id"] != authority["authority_id"] or pool["authority_id"] != authority["authority_id"]:
        _pause(connection, "AUTHORITY_REFERENCE_MISMATCH")
        raise RuntimeGrantError("RUNTIME_DB_IDENTITY_MISMATCH", commit_changes=True)
    if check_active:
        if grant["status"] != "ACTIVE":
            raise RuntimeGrantError("RUNTIME_GRANT_REVOKED")
        now = _valid_iso(utc_now(), "RUNTIME_CLOCK_INVALID")
        if now < grant["valid_from"] or now >= grant["expires_at"]:
            raise RuntimeGrantError("RUNTIME_GRANT_EXPIRED_OR_NOT_YET_VALID")
        expected = {
            "model_id": grant["model_id"], "endpoint": grant["endpoint"],
            "model_config_version": grant["model_config_version"],
            "price_version": grant["price_version"], "service_identity": grant["service_identity"],
        }
        normalized = dict(config or {})
        if normalized.get("endpoint"):
            normalized["endpoint"] = _endpoint(normalized["endpoint"])
        if any(normalized.get(key) != value for key, value in expected.items()):
            _pause(connection, "PROVIDER_CONFIGURATION_OR_PRICE_VERSION_STALE")
            raise RuntimeGrantError("RUNTIME_PROVIDER_CONFIGURATION_STALE", commit_changes=True)
    return authority, pool, grant


def provision_default_grant(
    path: str | Path, *, grant_source: str, operator_id: str, service_identity: str,
    model_id: str, endpoint: str, model_config_version: str, price_version: str,
    input_rate_micro_per_million: int, output_rate_micro_per_million: int,
    max_input_tokens: int, max_output_tokens: int, total_limit_usd_micro: int,
    valid_from: str, expires_at: str, evidence_ref: str, evidence_digest: str,
    idempotency_key: str,
) -> dict[str, object]:
    """Explicit local provisioning. Database initialization never calls this."""
    _validate_evidence(operator_id, grant_source, evidence_ref, evidence_digest, idempotency_key)
    if any(not isinstance(x, str) or not x.strip() for x in (service_identity, model_id, model_config_version, price_version)):
        raise RuntimeGrantError("RUNTIME_GRANT_CONFIGURATION_REQUIRED")
    if model_id.strip() != "deepseek-flash":
        raise RuntimeGrantError("RUNTIME_PROVIDER_MODEL_UNSUPPORTED")
    endpoint = _endpoint(endpoint)
    for value, code in (
        (input_rate_micro_per_million, "RUNTIME_PRICE_INVALID"),
        (output_rate_micro_per_million, "RUNTIME_PRICE_INVALID"),
        (max_input_tokens, "RUNTIME_TOKEN_BOUND_INVALID"),
        (max_output_tokens, "RUNTIME_TOKEN_BOUND_INVALID"),
        (total_limit_usd_micro, "RUNTIME_BUDGET_INVALID"),
    ):
        if type(value) is not int or value < 0:
            raise RuntimeGrantError(code)
    if input_rate_micro_per_million <= 0 or output_rate_micro_per_million <= 0:
        raise RuntimeGrantError("RUNTIME_PRICE_INVALID")
    if not 0 < max_input_tokens <= MAX_PRODUCT_INPUT_TOKENS or not 0 < max_output_tokens <= MAX_PRODUCT_OUTPUT_TOKENS:
        raise RuntimeGrantError("RUNTIME_TOKEN_BOUND_INVALID")
    if total_limit_usd_micro <= 0:
        raise RuntimeGrantError("RUNTIME_BUDGET_INVALID")
    valid_from = _valid_iso(valid_from, "RUNTIME_GRANT_TIME_INVALID")
    expires_at = _valid_iso(expires_at, "RUNTIME_GRANT_TIME_INVALID")
    if valid_from >= expires_at:
        raise RuntimeGrantError("RUNTIME_GRANT_TIME_INVALID")
    file_id = _file_identity(path)
    grant_id = "assistant-runtime-default-" + str(uuid.uuid4())
    with connect(path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        existing_audit = connection.execute(
            "SELECT * FROM assistant_runtime_audit WHERE idempotency_key=?", (idempotency_key.strip(),)
        ).fetchone()
        request = {
            "grant_source": grant_source.strip(), "operator_id": operator_id.strip(),
            "service_identity": service_identity.strip(), "model_id": model_id.strip(),
            "endpoint": endpoint, "model_config_version": model_config_version.strip(),
            "price_version": price_version.strip(), "input_rate_micro_per_million": input_rate_micro_per_million,
            "output_rate_micro_per_million": output_rate_micro_per_million,
            "max_input_tokens": max_input_tokens, "max_output_tokens": max_output_tokens,
            "total_limit_usd_micro": total_limit_usd_micro, "valid_from": valid_from, "expires_at": expires_at,
        }
        if existing_audit:
            if not _audit_replay_matches(
                existing_audit, action="PROVISION", operator_id=operator_id,
                source=grant_source, evidence_ref=evidence_ref,
                evidence_digest=evidence_digest, request_digest=digest_json(request),
            ):
                raise RuntimeGrantError("RUNTIME_AUDIT_IDEMPOTENCY_CONFLICT")
            row = connection.execute("SELECT * FROM assistant_runtime_default_grant WHERE singleton=1").fetchone()
            return dict(row) if row else {"status": "PROVISIONED_RECORD_REMOVED"}
        if connection.execute("SELECT 1 FROM assistant_runtime_authority WHERE singleton=1").fetchone():
            raise RuntimeGrantError("RUNTIME_DEFAULT_GRANT_ALREADY_PROVISIONED")
        authority_id = "assistant-runtime-authority-" + str(uuid.uuid4())
        now = utc_now()
        connection.execute(
            "INSERT INTO assistant_runtime_authority(singleton,authority_id,database_file_identity,created_at) VALUES (1,?,?,?)",
            (authority_id, file_id, now),
        )
        connection.execute(
            "INSERT INTO assistant_runtime_pools(pool_id,authority_id,total_limit_usd_micro,status,pause_reason,version,created_at,updated_at) VALUES (?, ?, ?, 'ACTIVE', NULL, 1, ?, ?)",
            (POOL_ID, authority_id, total_limit_usd_micro, now, now),
        )
        connection.execute(
            """INSERT INTO assistant_runtime_default_grant
            (singleton,grant_id,version,authority_id,pool_id,status,grant_source,operator_id,service_identity,
             model_id,endpoint,model_config_version,price_version,input_rate_micro_per_million,
             output_rate_micro_per_million,max_input_tokens,max_output_tokens,valid_from,expires_at,updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (1, grant_id, 1, authority_id, POOL_ID, "ACTIVE", grant_source.strip(), operator_id.strip(), service_identity.strip(),
             model_id.strip(), endpoint, model_config_version.strip(), price_version.strip(),
             input_rate_micro_per_million, output_rate_micro_per_million, max_input_tokens, max_output_tokens,
             valid_from, expires_at, now),
        )
        row = connection.execute("SELECT * FROM assistant_runtime_default_grant WHERE singleton=1").fetchone()
        _write_history(connection, row, total_limit_usd_micro)
        _audit(connection, authority_id=authority_id, grant_id=grant_id, action="PROVISION",
               operator_id=operator_id, source=grant_source, evidence_ref=evidence_ref,
               evidence_digest=evidence_digest, idempotency_key=idempotency_key, request=request,
               details={"grant_version": 1, "pool_id": POOL_ID, "total_limit_usd_micro": total_limit_usd_micro})
        return dict(row)


def revise_default_grant(
    path: str | Path, *, expected_version: int, changes: dict[str, object], operator_id: str,
    source: str, evidence_ref: str, evidence_digest: str, idempotency_key: str,
) -> dict[str, object]:
    """Audited local revision. Pool spending history and identity are never reset."""
    _validate_evidence(operator_id, source, evidence_ref, evidence_digest, idempotency_key)
    allowed = {
        "status", "grant_source", "service_identity", "model_id", "endpoint", "model_config_version",
        "price_version", "input_rate_micro_per_million", "output_rate_micro_per_million",
        "max_input_tokens", "max_output_tokens", "valid_from", "expires_at", "total_limit_usd_micro",
    }
    if not isinstance(changes, dict) or not changes or set(changes) - allowed:
        raise RuntimeGrantError("RUNTIME_GRANT_REVISION_INVALID")
    if "endpoint" in changes:
        changes = {**changes, "endpoint": _endpoint(changes["endpoint"])}
    for key in ("grant_source", "service_identity", "model_id", "model_config_version", "price_version"):
        if key in changes and isinstance(changes[key], str):
            changes = {**changes, key: changes[key].strip()}
    request = {"expected_version": expected_version, "changes": changes}
    with connect(path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        authority = _authority(connection, path)
        old = connection.execute("SELECT * FROM assistant_runtime_default_grant WHERE singleton=1").fetchone()
        pool = connection.execute("SELECT * FROM assistant_runtime_pools WHERE pool_id=?", (POOL_ID,)).fetchone()
        if old is None or pool is None:
            raise RuntimeGrantError("RUNTIME_GRANT_NOT_PROVISIONED")
        if connection.execute("SELECT 1 FROM assistant_runtime_audit WHERE idempotency_key=?", (idempotency_key.strip(),)).fetchone():
            audit = connection.execute("SELECT * FROM assistant_runtime_audit WHERE idempotency_key=?", (idempotency_key.strip(),)).fetchone()
            if not _audit_replay_matches(
                audit, action="REVISE", operator_id=operator_id, source=source,
                evidence_ref=evidence_ref, evidence_digest=evidence_digest,
                request_digest=digest_json(request),
            ):
                raise RuntimeGrantError("RUNTIME_AUDIT_IDEMPOTENCY_CONFLICT")
            return dict(connection.execute("SELECT * FROM assistant_runtime_default_grant WHERE singleton=1").fetchone())
        if int(old["version"]) != expected_version:
            raise RuntimeGrantError("RUNTIME_GRANT_VERSION_CONFLICT")
        current = dict(old)
        next_values = {key: value for key, value in changes.items() if key != "total_limit_usd_micro"}
        if "status" in next_values and next_values["status"] not in {"ACTIVE", "REVOKED"}:
            raise RuntimeGrantError("RUNTIME_GRANT_REVISION_INVALID")
        for key in ("grant_source", "service_identity", "model_id", "model_config_version", "price_version"):
            if key in next_values and (not isinstance(next_values[key], str) or not next_values[key].strip()):
                raise RuntimeGrantError("RUNTIME_GRANT_REVISION_INVALID")
        if "model_id" in next_values and next_values["model_id"].strip() != "deepseek-flash":
            raise RuntimeGrantError("RUNTIME_PROVIDER_MODEL_UNSUPPORTED")
        for key in ("input_rate_micro_per_million", "output_rate_micro_per_million", "max_input_tokens", "max_output_tokens"):
            if key in next_values and (type(next_values[key]) is not int or next_values[key] < 0):
                raise RuntimeGrantError("RUNTIME_GRANT_REVISION_INVALID")
        for key in ("input_rate_micro_per_million", "output_rate_micro_per_million"):
            if key in next_values and next_values[key] <= 0:
                raise RuntimeGrantError("RUNTIME_PRICE_INVALID")
        next_values["version"] = expected_version + 1
        next_values["updated_at"] = utc_now()
        if "valid_from" in next_values:
            next_values["valid_from"] = _valid_iso(next_values["valid_from"], "RUNTIME_GRANT_TIME_INVALID")
        if "expires_at" in next_values:
            next_values["expires_at"] = _valid_iso(next_values["expires_at"], "RUNTIME_GRANT_TIME_INVALID")
        merged = {**current, **next_values}
        if merged["valid_from"] >= merged["expires_at"]:
            raise RuntimeGrantError("RUNTIME_GRANT_TIME_INVALID")
        if not 0 < int(merged["max_input_tokens"]) <= MAX_PRODUCT_INPUT_TOKENS or not 0 < int(merged["max_output_tokens"]) <= MAX_PRODUCT_OUTPUT_TOKENS:
            raise RuntimeGrantError("RUNTIME_TOKEN_BOUND_INVALID")
        requested_limit = changes.get("total_limit_usd_micro", pool["total_limit_usd_micro"])
        if type(requested_limit) is not int:
            raise RuntimeGrantError("RUNTIME_BUDGET_INVALID")
        total_limit = requested_limit
        try:
            effective = _effective_spend(connection)
        except RuntimeGrantError as error:
            if error.commit_changes:
                connection.commit()
            raise
        if total_limit <= 0 or total_limit < effective:
            raise RuntimeGrantError("RUNTIME_BUDGET_BELOW_COMMITTED_OR_RESERVED")
        if "total_limit_usd_micro" in changes:
            connection.execute(
                "UPDATE assistant_runtime_pools SET total_limit_usd_micro=?,version=version+1,updated_at=? WHERE pool_id=?",
                (total_limit, utc_now(), POOL_ID),
            )
        assignments = ",".join(f"{key}=?" for key in next_values)
        connection.execute(
            f"UPDATE assistant_runtime_default_grant SET {assignments} WHERE singleton=1",
            tuple(next_values.values()),
        )
        row = connection.execute("SELECT * FROM assistant_runtime_default_grant WHERE singleton=1").fetchone()
        _write_history(connection, row, total_limit)
        _audit(connection, authority_id=authority["authority_id"], grant_id=old["grant_id"], action="REVISE",
               operator_id=operator_id, source=source, evidence_ref=evidence_ref,
               evidence_digest=evidence_digest, idempotency_key=idempotency_key, request=request,
               details={"from_version": expected_version, "to_version": expected_version + 1,
                        "changed_fields": sorted(changes), "pool_limit_usd_micro": total_limit})
        return dict(row)


def _binding_from_history(connection, run_row, binding_row):
    history = connection.execute(
        "SELECT snapshot_json FROM assistant_runtime_grant_history WHERE grant_id=? AND version=?",
        (binding_row["grant_id"], binding_row["grant_version"]),
    ).fetchone()
    if history is None:
        raise RuntimeGrantError("RUNTIME_RUN_GRANT_HISTORY_MISSING")
    try:
        snapshot = json.loads(history["snapshot_json"])
    except (TypeError, json.JSONDecodeError) as error:
        raise RuntimeGrantError("RUNTIME_RUN_GRANT_HISTORY_INVALID") from error
    return {
        **snapshot,
        "run_id": run_row["run_id"], "session_id": run_row["session_id"],
        "task_id": run_row["task_id"], "source_message_id": run_row["source_message_id"],
        "grant_version": int(binding_row["grant_version"]),
        "authority_id": binding_row["authority_id"],
        "database_file_identity": binding_row["database_file_identity"],
        "db_path": str(Path(connection.execute("PRAGMA database_list").fetchone()[2]).resolve()),
    }


def bind_run(path: str | Path, run_id: str, config: dict[str, str]) -> dict[str, object]:
    """Persist the single authorized default Grant/version on an ASSISTANT_V1 Run."""
    with connect(path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        authority = _authority(connection, path)
        run = connection.execute(
            """SELECT r.run_id,r.session_id,r.task_id,r.source_message_id,a.core
               FROM task_runs r JOIN assistant_runs a ON a.run_id=r.run_id WHERE r.run_id=?""",
            (run_id,),
        ).fetchone()
        if run is None or run["core"] != "ASSISTANT_V1" or not run["source_message_id"]:
            raise RuntimeGrantError("RUNTIME_ASSISTANT_RUN_REQUIRED")
        bound = connection.execute("SELECT * FROM assistant_runtime_run_bindings WHERE run_id=?", (run_id,)).fetchone()
        file_id = authority["database_file_identity"]
        if bound:
            if (bound["session_id"] != run["session_id"] or bound["task_id"] != run["task_id"]
                or bound["source_message_id"] != run["source_message_id"]
                or bound["authority_id"] != authority["authority_id"] or bound["database_file_identity"] != file_id):
                raise RuntimeGrantError("RUNTIME_RUN_BINDING_MISMATCH")
            return _binding_from_history(connection, run, bound)
        try:
            _, _, grant = _current_grant(connection, path, config)
        except RuntimeGrantError as error:
            if error.commit_changes:
                connection.commit()
            raise
        connection.execute(
            """INSERT INTO assistant_runtime_run_bindings
               (run_id,session_id,task_id,source_message_id,grant_id,grant_version,authority_id,database_file_identity,created_at)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (run_id, run["session_id"], run["task_id"], run["source_message_id"], grant["grant_id"],
             grant["version"], authority["authority_id"], file_id, utc_now()),
        )
        bound = connection.execute("SELECT * FROM assistant_runtime_run_bindings WHERE run_id=?", (run_id,)).fetchone()
        return _binding_from_history(connection, run, bound)


def _validate_run_binding_in_transaction(connection, path, run_id, binding):
    if not isinstance(binding, dict) or binding.get("run_id") != run_id:
        raise RuntimeGrantError("RUNTIME_RUN_BINDING_MISSING")
    authority = _authority(connection, path)
    row = connection.execute(
        "SELECT * FROM assistant_runtime_run_bindings WHERE run_id=?", (run_id,)
    ).fetchone()
    run = connection.execute(
        "SELECT session_id,task_id,source_message_id FROM task_runs WHERE run_id=?", (run_id,)
    ).fetchone()
    if row is None or run is None:
        raise RuntimeGrantError("RUNTIME_RUN_BINDING_MISSING")
    expected = _binding_from_history(connection, dict(run) | {"run_id": run_id}, row)
    for key in ("grant_id", "grant_version", "authority_id", "database_file_identity", "session_id", "source_message_id", "task_id"):
        if binding.get(key) != expected.get(key):
            raise RuntimeGrantError("RUNTIME_RUN_BINDING_MISMATCH")
    if authority["authority_id"] != binding.get("authority_id"):
        raise RuntimeGrantError("RUNTIME_DB_IDENTITY_MISMATCH")
    return expected


def validate_run_binding(path: str | Path, run_id: str, binding: dict[str, object], config: dict[str, str]) -> dict[str, object]:
    """Verify the in-process reference against the persisted run and DB identity."""
    with connect(path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        expected = _validate_run_binding_in_transaction(connection, path, run_id, binding)
        # Existing Run recovery may use a stored response after revocation, but
        # its client remains pinned to the Run's historical model and endpoint.
        if config:
            normalized = dict(config)
            if normalized.get("endpoint"):
                normalized["endpoint"] = _endpoint(normalized["endpoint"])
            for key in ("model_id", "endpoint", "model_config_version", "price_version", "service_identity"):
                if normalized.get(key) != expected.get(key):
                    raise RuntimeGrantError("RUNTIME_PROVIDER_CONFIGURATION_STALE")
        return expected


def _stable_request_key(binding, logical_key):
    identity = {
        "session_id": binding["session_id"], "source_message_id": binding["source_message_id"],
        "kind": "MODEL", "logical_key": logical_key,
    }
    return "runtime-call-" + digest_json(identity)


def reserve_dispatch(path, binding, *, call_id: str, logical_key: str, request_digest: str, worker_id: str):
    """Persist the worst-case fee reservation before entering the Provider transport."""
    with connect(path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        expected = _validate_run_binding_in_transaction(
            connection, path, str(binding.get("run_id", "")), binding,
        )
        call = connection.execute(
            "SELECT * FROM assistant_calls WHERE call_id=? AND run_id=? AND kind='MODEL'",
            (call_id, expected["run_id"]),
        ).fetchone()
        if call is None or call["logical_key"] != logical_key or call["request_digest"] != request_digest:
            raise RuntimeGrantError("RUNTIME_ASSISTANT_CALL_BINDING_INVALID")
        request_key = _stable_request_key(expected, logical_key)
        existing = connection.execute("SELECT * FROM assistant_runtime_spends WHERE request_key=?", (request_key,)).fetchone()
        if existing:
            if existing["request_digest"] != request_digest:
                raise RuntimeGrantError("RUNTIME_LOGICAL_REQUEST_DIGEST_CONFLICT")
            if existing["status"] in {"RESPONSE_STORED", "DELIVERED"}:
                return {**dict(existing), "request_key": request_key, "replay": True}
            if existing["assistant_call_id"] != call_id:
                raise RuntimeGrantError("RUNTIME_LOGICAL_REQUEST_ALREADY_CLAIMED")
            if existing["status"] != "RESERVED":
                raise RuntimeGrantError("RUNTIME_EXTERNAL_RESULT_UNKNOWN")
            return {**dict(existing), "request_key": request_key, "replay": False}
        try:
            authority, pool, grant = _current_grant(connection, path, runtime_config_from_env())
        except RuntimeGrantError as error:
            if error.commit_changes:
                connection.commit()
            raise
        if grant["grant_id"] != expected["grant_id"] or int(grant["version"]) != int(expected["version"]):
            raise RuntimeGrantError("RUNTIME_GRANT_VERSION_STALE")
        reserve = _cost_micro(
            int(grant["max_input_tokens"]), int(grant["max_output_tokens"]),
            int(grant["input_rate_micro_per_million"]), int(grant["output_rate_micro_per_million"]),
        )
        try:
            effective = _effective_spend(connection)
        except RuntimeGrantError as error:
            if error.commit_changes:
                connection.commit()
            raise
        if effective + reserve > int(pool["total_limit_usd_micro"]):
            raise RuntimeGrantError("RUNTIME_BUDGET_EXHAUSTED")
        now = utc_now()
        dispatch_id = "runtime-dispatch-" + str(uuid.uuid4())
        connection.execute(
            """INSERT INTO assistant_runtime_spends
            (dispatch_id,pool_id,authority_id,request_key,assistant_call_id,run_id,session_id,source_message_id,
             logical_key,request_digest,worker_id,grant_id,grant_version,price_version,input_rate_micro_per_million,
             output_rate_micro_per_million,max_input_tokens,max_output_tokens,reserved_usd_micro,status,created_at,updated_at)
             VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,'RESERVED',?,?)""",
            (dispatch_id, POOL_ID, authority["authority_id"], request_key, call_id, expected["run_id"],
             expected["session_id"], expected["source_message_id"], logical_key, request_digest, worker_id,
             grant["grant_id"], grant["version"], grant["price_version"], grant["input_rate_micro_per_million"],
             grant["output_rate_micro_per_million"], grant["max_input_tokens"], grant["max_output_tokens"],
             reserve, now, now),
        )
        row = dict(connection.execute("SELECT * FROM assistant_runtime_spends WHERE dispatch_id=?", (dispatch_id,)).fetchone())
        row["request_key"] = request_key
        row["replay"] = False
        return row


def validate_http_request(request_url: str, method: str, body: bytes, binding: dict[str, object]) -> tuple[str, int]:
    """Validate final HTTPX serialization without storing Authorization or secrets."""
    try:
        parsed = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RuntimeGrantError("RUNTIME_PROVIDER_REQUEST_INVALID") from error
    if not isinstance(parsed, dict) or method.upper() != "POST":
        raise RuntimeGrantError("RUNTIME_PROVIDER_REQUEST_INVALID")
    messages = parsed.get("messages")
    tools = parsed.get("tools", [])
    if not isinstance(messages, list) or not isinstance(tools, list):
        raise RuntimeGrantError("RUNTIME_PROVIDER_REQUEST_INVALID")
    base = str(binding["endpoint"]).rstrip("/")
    url = request_url.rstrip("/")
    if url != base + "/chat/completions":
        raise RuntimeGrantError("RUNTIME_PROVIDER_REQUEST_ENDPOINT_MISMATCH")
    if parsed.get("model") != binding["model_id"] or "max_completion_tokens" in parsed:
        raise RuntimeGrantError("RUNTIME_PROVIDER_REQUEST_MODEL_MISMATCH")
    max_tokens = parsed.get("max_tokens")
    if type(max_tokens) is not int or max_tokens <= 0 or max_tokens > int(binding["max_output_tokens"]):
        raise RuntimeGrantError("RUNTIME_PROVIDER_REQUEST_OUTPUT_BOUND_INVALID")
    if parsed.get("thinking") != {"type": "disabled"}:
        raise RuntimeGrantError("RUNTIME_PROVIDER_REQUEST_MODE_MISMATCH")
    if parsed.get("stream", False) is not False:
        raise RuntimeGrantError("RUNTIME_PROVIDER_STREAMING_NOT_ALLOWED")
    if tools:
        if parsed.get("parallel_tool_calls", False) is not False:
            raise RuntimeGrantError("RUNTIME_PROVIDER_PARALLEL_TOOLS_NOT_ALLOWED")
        if parsed.get("tool_choice") not in ("auto", "none") and not isinstance(parsed.get("tool_choice"), dict):
            raise RuntimeGrantError("RUNTIME_PROVIDER_TOOL_CHOICE_INVALID")
    from opspilot.domain.context_engineering import estimate_messages_tokens, estimate_text_tokens

    input_estimate = (
        estimate_messages_tokens(messages)
        + estimate_text_tokens(canonical_json(tools))
        + 64
    )
    if input_estimate > int(binding["max_input_tokens"]):
        raise RuntimeGrantError("RUNTIME_PROVIDER_REQUEST_INPUT_BOUND_INVALID")
    return hashlib.sha256(body).hexdigest(), max_tokens


def claim_send(path, binding, *, call_id: str, request_key: str, request_digest: str, body_digest: str,
               request_url: str, method: str, requested_max_output_tokens: int, worker_id: str):
    """Atomically acquire the one-use Provider send authority or return a saved response."""
    with connect(path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        _authority(connection, path)
        expected = _validate_run_binding_in_transaction(
            connection, path, str(binding.get("run_id", "")), binding,
        )
        row = connection.execute("SELECT * FROM assistant_runtime_spends WHERE request_key=?", (request_key,)).fetchone()
        if row is None:
            raise RuntimeGrantError("RUNTIME_DISPATCH_NOT_RESERVED")
        if (
            row["run_id"] != expected["run_id"]
            or row["session_id"] != expected["session_id"]
            or row["source_message_id"] != expected["source_message_id"]
            or row["grant_id"] != expected["grant_id"]
            or int(row["grant_version"]) != int(expected["grant_version"])
        ):
            raise RuntimeGrantError("RUNTIME_CALL_BINDING_MISMATCH")
        if row["assistant_call_id"] != call_id:
            raise RuntimeGrantError("RUNTIME_CALL_ID_MISMATCH")
        if row["request_digest"] != request_digest:
            raise RuntimeGrantError("RUNTIME_LOGICAL_REQUEST_DIGEST_CONFLICT")
        if row["status"] in {"RESPONSE_STORED", "DELIVERED"}:
            if (
                row["http_body_digest"] != body_digest
                or row["http_url"] != request_url
                or row["http_method"] != method.upper()
                or int(row["requested_max_output_tokens"] or 0) != requested_max_output_tokens
                or row["response_body"] is None or not row["usage_json"]
            ):
                raise RuntimeGrantError("RUNTIME_STORED_RESPONSE_NOT_REPLAYABLE")
            return {"action": "REPLAY", "response_status": row["response_status"],
                    "headers": json.loads(row["response_headers_json"] or "{}"),
                    "body": bytes(row["response_body"]), "completion_id": row["completion_id"]}
        if row["status"] != "RESERVED":
            raise RuntimeGrantError("RUNTIME_EXTERNAL_RESULT_UNKNOWN")
        try:
            _, _, grant = _current_grant(connection, path, runtime_config_from_env())
        except RuntimeGrantError as error:
            if error.commit_changes:
                connection.commit()
            raise
        if (grant["grant_id"] != row["grant_id"] or int(grant["version"]) != int(row["grant_version"])
            or grant["grant_id"] != binding.get("grant_id")
            or int(grant["version"]) != int(binding.get("grant_version", -1))):
            raise RuntimeGrantError("RUNTIME_GRANT_VERSION_STALE")
        active = connection.execute(
            "SELECT 1 FROM assistant_runtime_spends WHERE pool_id=? AND status='SEND_GRANTED'",
            (POOL_ID,),
        ).fetchone()
        if active:
            raise RuntimeGrantError("RUNTIME_PROVIDER_CONCURRENCY_LIMIT")
        connection.execute(
            """UPDATE assistant_runtime_spends SET status='SEND_GRANTED',http_body_digest=?,http_url=?,http_method=?,
               requested_max_output_tokens=?,worker_id=?,send_granted_at=?,updated_at=?
               WHERE request_key=? AND status='RESERVED'""",
            (body_digest, request_url, method.upper(), requested_max_output_tokens, worker_id,
             utc_now(), utc_now(), request_key),
        )
        return {"action": "SEND"}


def mark_unknown(path, request_key: str, error_code: str):
    with connect(path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        connection.execute(
            """UPDATE assistant_runtime_spends SET status='UNKNOWN',error_code=?,completed_at=?,updated_at=?
               WHERE request_key=? AND status='SEND_GRANTED'""",
            (str(error_code)[:120], utc_now(), utc_now(), request_key),
        )


def release_not_dispatched(path, request_key: str, reason: str):
    """Release only a reservation which never acquired durable send authority."""
    with connect(path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        connection.execute(
            """UPDATE assistant_runtime_spends SET status='NOT_DISPATCHED',reserved_usd_micro=0,
               error_code=?,completed_at=?,updated_at=? WHERE request_key=? AND status='RESERVED'""",
            (str(reason)[:120], utc_now(), utc_now(), request_key),
        )


def close_unfinished_dispatch(path, request_key: str, reason: str):
    """Close only states whose send status can be read from the durable ledger."""
    with connect(path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute(
            "SELECT status FROM assistant_runtime_spends WHERE request_key=?", (request_key,)
        ).fetchone()
        if row is None:
            return "MISSING"
        status = str(row["status"])
        if status == "RESERVED":
            connection.execute(
                """UPDATE assistant_runtime_spends SET status='NOT_DISPATCHED',reserved_usd_micro=0,
                   error_code=?,completed_at=?,updated_at=? WHERE request_key=? AND status='RESERVED'""",
                (str(reason)[:120], utc_now(), utc_now(), request_key),
            )
            return "NOT_DISPATCHED"
        if status == "SEND_GRANTED":
            connection.execute(
                """UPDATE assistant_runtime_spends SET status='UNKNOWN',error_code=?,completed_at=?,updated_at=?
                   WHERE request_key=? AND status='SEND_GRANTED'""",
                (str(reason)[:120], utc_now(), utc_now(), request_key),
            )
            return "UNKNOWN"
        return status


def _safe_headers(headers):
    result = {}
    for name in ("content-type", "x-request-id", "request-id", "date"):
        if name in headers:
            result[name] = str(headers[name])
    return result


def store_response(path, request_key: str, *, status_code: int, headers: dict[str, str], body: bytes, usage: object):
    values = _usage_values(usage)
    with connect(path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute("SELECT * FROM assistant_runtime_spends WHERE request_key=?", (request_key,)).fetchone()
        if row is None or row["status"] != "SEND_GRANTED":
            raise RuntimeGrantError("RUNTIME_RESPONSE_WITHOUT_SEND_AUTHORITY")
        safe_headers = _safe_headers({str(k).lower(): v for k, v in headers.items()})
        completion_id = None
        try:
            response = json.loads(body.decode("utf-8"))
            if isinstance(response, dict) and isinstance(response.get("id"), str):
                completion_id = response["id"]
        except (UnicodeDecodeError, json.JSONDecodeError):
            response = None
        if values is None:
            connection.execute(
                """UPDATE assistant_runtime_spends SET status='UNKNOWN',response_status=?,response_headers_json=?,
                   response_body=?,error_code='PROVIDER_USAGE_UNKNOWN',completed_at=?,updated_at=?
                   WHERE request_key=? AND status='SEND_GRANTED'""",
                (status_code, canonical_json(safe_headers), sqlite3.Binary(body), utc_now(), utc_now(), request_key),
            )
            return {"replayable": False, "usage_state": "UNKNOWN"}
        actual = _cost_micro(
            values["input_tokens"], values["output_tokens"],
            row["input_rate_micro_per_million"], row["output_rate_micro_per_million"],
        )
        exceeds_bound = (
            values["input_tokens"] > int(row["max_input_tokens"])
            or values["output_tokens"] > int(row["requested_max_output_tokens"] or row["max_output_tokens"])
            or actual > int(row["reserved_usd_micro"])
        )
        if exceeds_bound:
            _pause(connection, "ACTUAL_USAGE_EXCEEDED_RESERVED_BOUND")
            connection.execute(
                """UPDATE assistant_runtime_spends SET status='VIOLATION',settled_usd_micro=?,usage_json=?,
                   response_status=?,response_headers_json=?,response_body=?,completion_id=?,error_code='USAGE_EXCEEDED_BOUND',
                   completed_at=?,updated_at=? WHERE request_key=? AND status='SEND_GRANTED'""",
                (actual, canonical_json(values), status_code, canonical_json(safe_headers), sqlite3.Binary(body),
                 completion_id, utc_now(), utc_now(), request_key),
            )
            return {"replayable": False, "usage_state": "VIOLATION", "actual_usd_micro": actual}
        connection.execute(
            """UPDATE assistant_runtime_spends SET status='RESPONSE_STORED',settled_usd_micro=?,usage_json=?,
               response_status=?,response_headers_json=?,response_body=?,completion_id=?,completed_at=?,updated_at=?
               WHERE request_key=? AND status='SEND_GRANTED'""",
            (actual, canonical_json(values), status_code, canonical_json(safe_headers), sqlite3.Binary(body),
             completion_id, utc_now(), utc_now(), request_key),
        )
        return {"replayable": True, "usage_state": "KNOWN", "actual_usd_micro": actual,
                "completion_id": completion_id}


def mark_delivered(path, request_key: str):
    with connect(path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        connection.execute(
            """UPDATE assistant_runtime_spends SET status='DELIVERED',updated_at=?
               WHERE request_key=? AND status='RESPONSE_STORED'""",
            (utc_now(), request_key),
        )


def recoverable_response(path, call_id: str, request_digest: str):
    with connect(path) as connection:
        row = connection.execute(
            """SELECT * FROM assistant_runtime_spends WHERE assistant_call_id=?
               AND request_digest=? AND status IN ('RESPONSE_STORED','DELIVERED')""",
            (call_id, request_digest),
        ).fetchone()
        if row is None or row["response_body"] is None or not row["usage_json"]:
            return None
        return dict(row)


def require_stored_response(path, request_key: str, *, call_id: str, request_digest: str):
    """Prove the HTTP layer committed this call's response and valid Usage."""
    with connect(path) as connection:
        row = connection.execute(
            """SELECT * FROM assistant_runtime_spends WHERE request_key=? AND assistant_call_id=?
               AND request_digest=? AND status IN ('RESPONSE_STORED','DELIVERED')""",
            (request_key, call_id, request_digest),
        ).fetchone()
        if row is None or row["response_body"] is None or row["usage_json"] is None:
            raise RuntimeGrantError("RUNTIME_PROVIDER_RESPONSE_NOT_DURABLE")
        if int(row["response_status"] or 0) < 200 or int(row["response_status"] or 0) >= 300:
            raise RuntimeGrantError("RUNTIME_PROVIDER_HTTP_RESPONSE_FAILED")
        try:
            usage = json.loads(row["usage_json"])
        except (TypeError, json.JSONDecodeError) as error:
            raise RuntimeGrantError("RUNTIME_PROVIDER_USAGE_UNKNOWN") from error
        if _usage_values(usage) is None:
            raise RuntimeGrantError("RUNTIME_PROVIDER_USAGE_UNKNOWN")
        return {"completion_id": row["completion_id"], "usage": usage,
                "response_status": int(row["response_status"])}


def recover_interrupted_sends(path: str | Path, worker_id: str):
    """A fresh exclusive Worker converts prior-process send authority to UNKNOWN."""
    with connect(path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        rows = connection.execute(
            "SELECT request_key FROM assistant_runtime_spends WHERE status='SEND_GRANTED' AND worker_id<>?",
            (worker_id,),
        ).fetchall()
        connection.execute(
            """UPDATE assistant_runtime_spends SET status='UNKNOWN',error_code='WORKER_RESTART_AFTER_SEND_GRANT',
               completed_at=?,updated_at=? WHERE status='SEND_GRANTED' AND worker_id<>?""",
            (utc_now(), utc_now(), worker_id),
        )
        return [str(row["request_key"]) for row in rows]


def reconcile_unknown(path: str | Path, request_key: str, *, outcome: str, operator_id: str,
                      evidence_ref: str, evidence_digest: str, idempotency_key: str,
                      usage: dict[str, object] | None = None) -> dict[str, object]:
    """Trusted local-only reconciliation; it never calls or resends the Provider."""
    _validate_evidence(operator_id, "LOCAL_RECONCILIATION", evidence_ref, evidence_digest, idempotency_key)
    if outcome not in {"CHARGED", "NOT_CHARGED"}:
        raise RuntimeGrantError("RUNTIME_RECONCILIATION_OUTCOME_INVALID")
    request = {"request_key": request_key, "outcome": outcome, "usage": usage}
    with connect(path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        old_audit = connection.execute("SELECT * FROM assistant_runtime_audit WHERE idempotency_key=?", (idempotency_key.strip(),)).fetchone()
        if old_audit:
            if not _audit_replay_matches(
                old_audit, action="RECONCILE_UNKNOWN", operator_id=operator_id,
                source="LOCAL_RECONCILIATION", evidence_ref=evidence_ref,
                evidence_digest=evidence_digest, request_digest=digest_json(request),
            ):
                raise RuntimeGrantError("RUNTIME_AUDIT_IDEMPOTENCY_CONFLICT")
            row = connection.execute("SELECT * FROM assistant_runtime_spends WHERE request_key=?", (request_key,)).fetchone()
            return dict(row) if row else {"status": "MISSING"}
        authority = _authority(connection, path)
        row = connection.execute("SELECT * FROM assistant_runtime_spends WHERE request_key=?", (request_key,)).fetchone()
        if row is None or row["status"] != "UNKNOWN":
            raise RuntimeGrantError("RUNTIME_DISPATCH_NOT_RECONCILABLE")
        settled = 0
        normalized = None
        if outcome == "CHARGED":
            normalized = _usage_values(usage)
            if normalized is None:
                raise RuntimeGrantError("RUNTIME_USAGE_INVALID")
            settled = _cost_micro(normalized["input_tokens"], normalized["output_tokens"],
                                  row["input_rate_micro_per_million"], row["output_rate_micro_per_million"])
            if (normalized["input_tokens"] > row["max_input_tokens"]
                or normalized["output_tokens"] > row["requested_max_output_tokens"]
                or settled > row["reserved_usd_micro"]):
                _pause(connection, "RECONCILED_USAGE_EXCEEDED_RESERVED_BOUND")
                connection.execute(
                    "UPDATE assistant_runtime_spends SET status='VIOLATION',settled_usd_micro=?,usage_json=?,error_code='RECONCILED_USAGE_EXCEEDED_BOUND',completed_at=?,updated_at=? WHERE request_key=?",
                    (settled, canonical_json(normalized), utc_now(), utc_now(), request_key),
                )
                _audit(connection, authority_id=authority["authority_id"], grant_id=row["grant_id"],
                       action="RECONCILE_UNKNOWN", operator_id=operator_id, source="LOCAL_RECONCILIATION",
                       evidence_ref=evidence_ref, evidence_digest=evidence_digest, idempotency_key=idempotency_key,
                       request=request, details={"outcome": outcome, "settled_usd_micro": settled,
                                                 "request_key": request_key, "pool_paused": True})
                return dict(connection.execute("SELECT * FROM assistant_runtime_spends WHERE request_key=?", (request_key,)).fetchone())
        connection.execute(
            "UPDATE assistant_runtime_spends SET status='RECONCILED',settled_usd_micro=?,usage_json=?,completed_at=?,updated_at=? WHERE request_key=? AND status='UNKNOWN'",
            (settled, canonical_json(normalized) if normalized else None, utc_now(), utc_now(), request_key),
        )
        _audit(connection, authority_id=authority["authority_id"], grant_id=row["grant_id"],
               action="RECONCILE_UNKNOWN", operator_id=operator_id, source="LOCAL_RECONCILIATION",
               evidence_ref=evidence_ref, evidence_digest=evidence_digest, idempotency_key=idempotency_key,
               request=request, details={"outcome": outcome, "settled_usd_micro": settled,
                                         "request_key": request_key})
        return dict(connection.execute("SELECT * FROM assistant_runtime_spends WHERE request_key=?", (request_key,)).fetchone())


def spend_summary(path: str | Path) -> dict[str, object]:
    with connect(path) as connection:
        authority = _authority(connection, path)
        pool = connection.execute("SELECT * FROM assistant_runtime_pools WHERE pool_id=?", (POOL_ID,)).fetchone()
        if pool is None:
            raise RuntimeGrantError("RUNTIME_SPEND_POOL_NOT_PROVISIONED")
        try:
            effective = _effective_spend(connection)
        except RuntimeGrantError as error:
            if error.commit_changes:
                connection.commit()
            raise
        return {"authority_id": authority["authority_id"], "pool_id": POOL_ID,
                "status": pool["status"], "pause_reason": pool["pause_reason"],
                "total_limit_usd_micro": int(pool["total_limit_usd_micro"]),
                "committed_or_reserved_usd_micro": effective,
                "remaining_usd_micro": max(0, int(pool["total_limit_usd_micro"]) - effective)}
