from __future__ import annotations

import argparse
import hashlib
import json
import os
import socket
import sys
import uuid
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
ENV_PATH = ROOT / ".env"
DB_PATH = ROOT / ".runtime" / "user-demo" / "domain.sqlite3"
MICRO_USD = 1_000_000
MAX_INPUT_TOKENS = 12_000
MAX_OUTPUT_TOKENS = 2_048
OPERATOR_ID = "local-user-demo-owner"
GRANT_SOURCE = "USER_DEMO_EXPLICIT_OWNER_CONFIRMATION"


def _runtime_paths(runtime_name: str) -> tuple[Path, Path]:
    from runtime_paths import resolve_user_demo_runtime

    try:
        runtime_dir = resolve_user_demo_runtime(runtime_name, root=ROOT)
    except ValueError as error:
        raise UserDemoRuntimeError(str(error)) from error
    return runtime_dir / "domain.sqlite3", runtime_dir / "checkpoint.sqlite3"


class UserDemoRuntimeError(RuntimeError):
    pass


def read_env(path: Path = ENV_PATH) -> dict[str, str]:
    if not path.is_file():
        raise UserDemoRuntimeError("USER_DEMO_LOCAL_ENV_MISSING")
    values: dict[str, str] = {}
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        current = line.strip()
        if not current or current.startswith("#"):
            continue
        key, separator, value = current.partition("=")
        key = key.strip()
        if not separator or not key or not key.replace("_", "").isalnum() or key[0].isdigit():
            raise UserDemoRuntimeError(f"USER_DEMO_ENV_LINE_INVALID_{line_number}")
        if key in values:
            raise UserDemoRuntimeError(f"USER_DEMO_ENV_DUPLICATE_{key}")
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        values[key] = value
    return values


def _is_placeholder(value: str) -> bool:
    normalized = value.strip().lower()
    return not normalized or normalized.startswith((
        "change_me", "replace_me", "your_", "paste_", "verify_", "example_",
    )) or normalized in {"changeme", "change me", "placeholder", "your key here"}


def _runtime_settings(values: dict[str, str]) -> dict[str, object]:
    required = (
        "OPSPILOT_MODEL_API_KEY",
        "OPSPILOT_MODEL_NAME",
        "OPSPILOT_MODEL_BASE_URL",
        "OPSPILOT_MODEL_CONFIG_VERSION",
        "OPSPILOT_MODEL_PRICE_VERSION",
        "OPSPILOT_ASSISTANT_SERVICE_IDENTITY",
        "OPSPILOT_MODEL_INPUT_RATE_MICRO_PER_MILLION",
        "OPSPILOT_MODEL_OUTPUT_RATE_MICRO_PER_MILLION",
    )
    missing = [name for name in required if not values.get(name, "").strip()]
    if missing:
        raise UserDemoRuntimeError("USER_DEMO_LIVE_CONFIG_MISSING:" + ",".join(missing))
    api_key = values["OPSPILOT_MODEL_API_KEY"].strip()
    if _is_placeholder(api_key):
        raise UserDemoRuntimeError("USER_DEMO_PROVIDER_KEY_PLACEHOLDER")
    if values["OPSPILOT_MODEL_NAME"].strip() != "deepseek-flash":
        raise UserDemoRuntimeError("RUNTIME_PROVIDER_MODEL_UNSUPPORTED")
    if values.get("OPSPILOT_ASSISTANT_EXPERIMENT_ID", "").strip():
        raise UserDemoRuntimeError("USER_DEMO_EXPERIMENT_SCOPE_FORBIDDEN")
    for name in ("OPSPILOT_MODEL_CONFIG_VERSION", "OPSPILOT_MODEL_PRICE_VERSION",
                 "OPSPILOT_ASSISTANT_SERVICE_IDENTITY"):
        if _is_placeholder(values[name]):
            raise UserDemoRuntimeError("USER_DEMO_LIVE_CONFIG_PLACEHOLDER:" + name)
    try:
        input_rate = int(values["OPSPILOT_MODEL_INPUT_RATE_MICRO_PER_MILLION"].strip())
        output_rate = int(values["OPSPILOT_MODEL_OUTPUT_RATE_MICRO_PER_MILLION"].strip())
    except ValueError as error:
        raise UserDemoRuntimeError("RUNTIME_PRICE_INVALID") from error
    if input_rate <= 0 or output_rate <= 0:
        raise UserDemoRuntimeError("RUNTIME_PRICE_INVALID")

    from opspilot.domain.assistant_runtime_grant import runtime_config_from_env

    provider_environment = {
        "OPSPILOT_MODEL_NAME": values["OPSPILOT_MODEL_NAME"].strip(),
        "OPSPILOT_MODEL_BASE_URL": values["OPSPILOT_MODEL_BASE_URL"].strip(),
        "OPSPILOT_MODEL_CONFIG_VERSION": values["OPSPILOT_MODEL_CONFIG_VERSION"].strip(),
        "OPSPILOT_MODEL_PRICE_VERSION": values["OPSPILOT_MODEL_PRICE_VERSION"].strip(),
        "OPSPILOT_ASSISTANT_SERVICE_IDENTITY": values["OPSPILOT_ASSISTANT_SERVICE_IDENTITY"].strip(),
    }
    with patch.dict(os.environ, provider_environment):
        identity = runtime_config_from_env()
    return {
        **identity,
        "input_rate_micro_per_million": input_rate,
        "output_rate_micro_per_million": output_rate,
        "api_key_present": True,
    }


def _money_to_micro(value: str) -> int:
    try:
        amount = Decimal(value.strip())
    except (InvalidOperation, AttributeError) as error:
        raise UserDemoRuntimeError("USER_DEMO_BUDGET_INVALID") from error
    if not amount.is_finite() or amount <= 0:
        raise UserDemoRuntimeError("USER_DEMO_BUDGET_INVALID")
    micro = amount * MICRO_USD
    if micro != micro.to_integral_value() or micro > 9_223_372_036_854_775_807:
        raise UserDemoRuntimeError("USER_DEMO_BUDGET_PRECISION_OR_RANGE_INVALID")
    return int(micro)


def _expiry(value: str) -> str:
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except (ValueError, AttributeError) as error:
        raise UserDemoRuntimeError("USER_DEMO_GRANT_EXPIRY_INVALID") from error
    if parsed.tzinfo is None:
        raise UserDemoRuntimeError("USER_DEMO_GRANT_EXPIRY_REQUIRES_TIMEZONE")
    parsed = parsed.astimezone(timezone.utc)
    if parsed <= datetime.now(timezone.utc):
        raise UserDemoRuntimeError("USER_DEMO_GRANT_EXPIRY_NOT_FUTURE")
    return parsed.isoformat(timespec="seconds").replace("+00:00", "Z")


def _max_request_reserve(settings: dict[str, object]) -> int:
    from opspilot.domain.assistant_runtime_grant import _cost_micro

    return _cost_micro(
        MAX_INPUT_TOKENS, MAX_OUTPUT_TOKENS,
        int(settings["input_rate_micro_per_million"]),
        int(settings["output_rate_micro_per_million"]),
    )


def _assert_empty_runtime_ledger(path: Path) -> None:
    from opspilot.domain.database import connect

    required_tables = {
        "assistant_runtime_authority", "assistant_runtime_pools",
        "assistant_runtime_default_grant", "assistant_runtime_spends",
        "assistant_runtime_campaigns",
    }
    with connect(path) as connection:
        tables = {str(row["name"]) for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
        if not required_tables.issubset(tables):
            raise UserDemoRuntimeError("USER_DEMO_RUNTIME_SCHEMA_MISSING")
        for table in sorted(required_tables):
            if connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]:
                raise UserDemoRuntimeError("USER_DEMO_RUNTIME_STATE_ALREADY_EXISTS")


def _services_are_stopped() -> bool:
    runtime_root = ROOT / ".runtime"
    if any(runtime_root.glob("user-demo-*/processes.json")) or (runtime_root / "user-demo" / "processes.json").exists():
        return False
    for port in (8000, 5173):
        with socket.socket() as client:
            client.settimeout(0.25)
            if client.connect_ex(("127.0.0.1", port)) == 0:
                return False
    return True


def _confirmation_text(amount_micro: int) -> str:
    amount = Decimal(amount_micro) / Decimal(MICRO_USD)
    return f"AUTHORIZE REAL DEEPSEEK SPENDING UP TO USD {amount:.6f}"


def provision_user_demo_grant(
    path: str | Path,
    values: dict[str, str],
    *,
    budget_usd: str,
    expires_at: str,
    confirmation: str,
) -> dict[str, object]:
    db_path = Path(path).resolve()
    if not db_path.is_file():
        raise UserDemoRuntimeError("USER_DEMO_DATABASE_MISSING")
    if not _services_are_stopped():
        raise UserDemoRuntimeError("USER_DEMO_STOP_SERVICES_BEFORE_GRANT_CHANGE")
    settings = _runtime_settings(values)
    total_limit = _money_to_micro(budget_usd)
    expiry = _expiry(expires_at)
    reserve = _max_request_reserve(settings)
    if total_limit < reserve:
        raise UserDemoRuntimeError("USER_DEMO_BUDGET_BELOW_ONE_MAX_REQUEST_RESERVE")
    if confirmation != _confirmation_text(total_limit):
        raise UserDemoRuntimeError("USER_DEMO_GRANT_CONFIRMATION_MISMATCH")
    _assert_empty_runtime_ledger(db_path)

    from opspilot.domain.assistant_runtime_grant import provision_default_grant

    valid_from = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    audit_payload = {
        "model_id": settings["model_id"], "endpoint": settings["endpoint"],
        "model_config_version": settings["model_config_version"],
        "price_version": settings["price_version"],
        "service_identity": settings["service_identity"],
        "input_rate_micro_per_million": settings["input_rate_micro_per_million"],
        "output_rate_micro_per_million": settings["output_rate_micro_per_million"],
        "max_input_tokens": MAX_INPUT_TOKENS, "max_output_tokens": MAX_OUTPUT_TOKENS,
        "total_limit_usd_micro": total_limit, "valid_from": valid_from,
        "expires_at": expiry, "owner_confirmation": confirmation,
    }
    digest = hashlib.sha256(json.dumps(
        audit_payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
    ).encode("utf-8")).hexdigest()
    return provision_default_grant(
        db_path,
        grant_source=GRANT_SOURCE,
        operator_id=OPERATOR_ID,
        service_identity=str(settings["service_identity"]),
        model_id=str(settings["model_id"]),
        endpoint=str(settings["endpoint"]),
        model_config_version=str(settings["model_config_version"]),
        price_version=str(settings["price_version"]),
        input_rate_micro_per_million=int(settings["input_rate_micro_per_million"]),
        output_rate_micro_per_million=int(settings["output_rate_micro_per_million"]),
        max_input_tokens=MAX_INPUT_TOKENS,
        max_output_tokens=MAX_OUTPUT_TOKENS,
        total_limit_usd_micro=total_limit,
        valid_from=valid_from,
        expires_at=expiry,
        evidence_ref="LOCAL_CONFIRMATION:" + str(uuid.uuid4()),
        evidence_digest=digest,
        idempotency_key="USER_DEMO_INITIAL_GRANT:" + digest,
    )


def preflight(path: str | Path, values: dict[str, str]) -> dict[str, object]:
    db_path = Path(path).resolve()
    if not db_path.is_file():
        raise UserDemoRuntimeError("USER_DEMO_DATABASE_MISSING")
    settings = _runtime_settings(values)
    if not values.get("OPSPILOT_MODEL_API_KEY", "").strip():
        raise UserDemoRuntimeError("USER_DEMO_PROVIDER_KEY_MISSING")

    from opspilot.domain.assistant_runtime_grant import (
        RuntimeGrantError, _cost_micro, _current_grant, _effective_spend,
    )
    from opspilot.domain.database import connect

    with connect(db_path) as connection:
        try:
            _, pool, grant = _current_grant(connection, db_path, {
                key: str(settings[key]) for key in (
                    "model_id", "endpoint", "model_config_version", "price_version", "service_identity",
                )
            })
            if str(pool["status"]) != "ACTIVE":
                raise UserDemoRuntimeError("RUNTIME_SPEND_POOL_PAUSED")
            if int(grant["input_rate_micro_per_million"]) != int(settings["input_rate_micro_per_million"]):
                raise UserDemoRuntimeError("RUNTIME_PROVIDER_PRICE_CONFIGURATION_STALE")
            if int(grant["output_rate_micro_per_million"]) != int(settings["output_rate_micro_per_million"]):
                raise UserDemoRuntimeError("RUNTIME_PROVIDER_PRICE_CONFIGURATION_STALE")
            if int(grant["max_input_tokens"]) != MAX_INPUT_TOKENS or int(grant["max_output_tokens"]) != MAX_OUTPUT_TOKENS:
                raise UserDemoRuntimeError("RUNTIME_PROVIDER_TOKEN_BOUNDS_STALE")
            if connection.execute("SELECT COUNT(*) FROM assistant_runtime_campaigns").fetchone()[0]:
                raise UserDemoRuntimeError("USER_DEMO_EXPERIMENT_CAMPAIGN_FORBIDDEN")
            used = _effective_spend(connection)
            total = int(pool["total_limit_usd_micro"])
            remaining = max(0, total - used)
            provider_sends = int(connection.execute(
                "SELECT COUNT(*) FROM assistant_runtime_spends WHERE send_granted_at IS NOT NULL"
            ).fetchone()[0])
            unknown_requests = int(connection.execute(
                "SELECT COUNT(*) FROM assistant_runtime_spends WHERE status='UNKNOWN'"
            ).fetchone()[0])
            reserve = _cost_micro(
                MAX_INPUT_TOKENS, MAX_OUTPUT_TOKENS,
                int(settings["input_rate_micro_per_million"]),
                int(settings["output_rate_micro_per_million"]),
            )
            if remaining < reserve:
                raise UserDemoRuntimeError("RUNTIME_BUDGET_INSUFFICIENT_FOR_MAX_REQUEST")
            return {
                "status": str(pool["status"]),
                "model_id": str(grant["model_id"]),
                "endpoint": str(grant["endpoint"]),
                "total_limit_usd_micro": total,
                "committed_or_reserved_usd_micro": used,
                "remaining_usd_micro": remaining,
                "one_max_request_reserve_usd_micro": reserve,
                "provider_sends": provider_sends,
                "unknown_requests": unknown_requests,
                "grant_expires_at": str(grant["expires_at"]),
                "api_key_present": True,
            }
        except RuntimeGrantError as error:
            if error.commit_changes:
                connection.commit()
            raise


def spend_summary(path: str | Path) -> dict[str, object]:
    from opspilot.domain.assistant_runtime_grant import spend_summary as domain_spend_summary
    from opspilot.domain.database import connect

    db_path = Path(path).resolve()
    summary = domain_spend_summary(db_path)
    with connect(db_path) as connection:
        settled = connection.execute(
            "SELECT COALESCE(SUM(settled_usd_micro),0) FROM assistant_runtime_spends "
            "WHERE status IN ('RESPONSE_STORED','DELIVERED','RECONCILED','VIOLATION')"
        ).fetchone()[0]
        reserved = connection.execute(
            "SELECT COALESCE(SUM(reserved_usd_micro),0) FROM assistant_runtime_spends "
            "WHERE status IN ('RESERVED','SEND_GRANTED','UNKNOWN')"
        ).fetchone()[0]
        provider_sends = connection.execute(
            "SELECT COUNT(*) FROM assistant_runtime_spends WHERE send_granted_at IS NOT NULL"
        ).fetchone()[0]
        unknown_requests = connection.execute(
            "SELECT COUNT(*) FROM assistant_runtime_spends WHERE status='UNKNOWN'"
        ).fetchone()[0]
        grant = connection.execute(
            "SELECT status,expires_at FROM assistant_runtime_default_grant WHERE singleton=1"
        ).fetchone()
    return {
        **summary,
        "settled_usd_micro": int(settled),
        "open_reserved_usd_micro": int(reserved),
        "provider_sends": int(provider_sends),
        "unknown_requests": int(unknown_requests),
        "grant_status": str(grant["status"]) if grant else "MISSING",
        "grant_expires_at": str(grant["expires_at"]) if grant else None,
    }


def _usd(micro: int) -> str:
    amount = Decimal(micro) / Decimal(MICRO_USD)
    return f"USD {amount:.6f}"


def _configure_interactively(db_path: Path | None = None, runtime_name: str = "user-demo") -> None:
    selected_db_path = db_path if db_path is not None else DB_PATH
    values = read_env()
    settings = _runtime_settings(values)
    print("Live mode will create one persistent shared Runtime Grant for this Demo database.")
    print("No Provider request is sent by this setup command. Later Live-mode messages may incur charges.")
    print(f"Model: {settings['model_id']} | Endpoint: {settings['endpoint']}")
    print(f"Config version: {settings['model_config_version']} | Price version: {settings['price_version']}")
    print(f"Input rate: {settings['input_rate_micro_per_million']} micro-USD / million tokens")
    print(f"Output rate: {settings['output_rate_micro_per_million']} micro-USD / million tokens")
    print(f"Fixed request bounds: {MAX_INPUT_TOKENS} input / {MAX_OUTPUT_TOKENS} output tokens")
    print("Check the official current model pricing before entering rates or authorizing spend.")
    budget = input("Your total application fee-pool limit in USD (no default): ").strip()
    total = _money_to_micro(budget)
    expiry = input("Grant expiry (ISO-8601 timestamp with timezone, e.g. ...Z): ").strip()
    normalized_expiry = _expiry(expiry)
    reserve = _max_request_reserve(settings)
    if total < reserve:
        raise UserDemoRuntimeError(
            "USER_DEMO_BUDGET_BELOW_ONE_MAX_REQUEST_RESERVE:" + _usd(reserve)
        )
    expected = _confirmation_text(total)
    print(f"Configured application maximum: {_usd(total)}; conservative max-request reserve: {_usd(reserve)}")
    print(f"Grant expiry: {normalized_expiry}; key configured: yes (value hidden)")
    confirmation = input(f"To create the grant and authorize later Live-mode calls, type exactly: {expected}\n> ")
    result = provision_user_demo_grant(
        selected_db_path, values, budget_usd=budget, expires_at=normalized_expiry,
        confirmation=confirmation,
    )
    print(f"Runtime Grant created for '{runtime_name}'. No Provider request was sent.")
    print(f"Grant status: {result['status']}; shared limit: {_usd(total)}")


def _print_summary(db_path: Path | None = None, runtime_name: str = "user-demo") -> None:
    selected_db_path = db_path if db_path is not None else DB_PATH
    if not selected_db_path.is_file():
        raise UserDemoRuntimeError("USER_DEMO_DATABASE_MISSING")
    print(f"Selected runtime: {runtime_name}; Domain DB: .runtime/{runtime_name}/domain.sqlite3")
    try:
        summary = spend_summary(selected_db_path)
    except Exception as error:
        code = getattr(error, "code", "")
        if code in {"RUNTIME_GRANT_NOT_PROVISIONED", "RUNTIME_SPEND_POOL_NOT_PROVISIONED"}:
            print(f"Runtime Grant not configured for '{runtime_name}'. No fee pool exists.")
            return
        raise
    print(f"Pool status: {summary['status']}; Grant status: {summary['grant_status']}")
    print(f"Total limit: {_usd(int(summary['total_limit_usd_micro']))}")
    print(f"Usage settled from Provider Usage: {_usd(int(summary['settled_usd_micro']))}")
    print(f"Open / UNKNOWN reservations: {_usd(int(summary['open_reserved_usd_micro']))}")
    print(f"Committed or reserved: {_usd(int(summary['committed_or_reserved_usd_micro']))}")
    print(f"Available: {_usd(int(summary['remaining_usd_micro']))}")
    print(f"Provider sends granted: {summary['provider_sends']}")
    print(f"UNKNOWN requests: {summary['unknown_requests']}")
    if summary.get("pause_reason"):
        print(f"Pool paused: {summary['pause_reason']}")
    if summary.get("grant_expires_at"):
        print(f"Grant expires at: {summary['grant_expires_at']}")
    print("Amounts are application estimates from the configured rates, not the supplier invoice.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Local OpsPilot user-demo Runtime Grant controls.")
    parser.add_argument("command", choices=("preflight", "configure", "summary"))
    parser.add_argument("--runtime-name", default="user-demo")
    args = parser.parse_args(argv)
    from opspilot.domain.assistant_runtime_grant import RuntimeGrantError

    try:
        db_path, _checkpoint_path = _runtime_paths(args.runtime_name)
        if not db_path.is_file():
            raise UserDemoRuntimeError("USER_DEMO_DATABASE_MISSING")
        if args.command == "preflight":
            result = preflight(db_path, read_env())
            print(
                f"Live preflight passed for '{args.runtime_name}' at .runtime/{args.runtime_name}/domain.sqlite3: "
                f"model={result['model_id']}, pool={result['status']}, "
                f"available={_usd(int(result['remaining_usd_micro']))}, "
                f"max-request reserve={_usd(int(result['one_max_request_reserve_usd_micro']))}, "
                f"provider-sends={result['provider_sends']}, unknown={result['unknown_requests']}, "
                f"grant-expires={result['grant_expires_at']}; API key present (value hidden)."
            )
            return 0
        if args.command == "configure":
            if not _services_are_stopped():
                raise UserDemoRuntimeError("USER_DEMO_STOP_SERVICES_BEFORE_GRANT_CHANGE")
            _configure_interactively(db_path, args.runtime_name)
            return 0
        _print_summary(db_path, args.runtime_name)
        return 0
    except (UserDemoRuntimeError, RuntimeGrantError) as error:
        label = getattr(error, "code", None) or str(error)
        print(f"User-demo runtime operation stopped: {label}", file=sys.stderr)
        return 2
    except (OSError, ValueError) as error:
        # Avoid leaking local paths or environment contents through wrapper logs.
        print(f"User-demo runtime operation stopped: {type(error).__name__}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
