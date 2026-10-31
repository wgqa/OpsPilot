"""Durable, isolated dispatch budget for the AR-02-LIVE-01 experiment only.

This ledger is deliberately not a general billing service. It is activated only
when the formal assistant Worker is explicitly scoped to this frozen experiment.
"""
from __future__ import annotations

import json
import uuid
from decimal import Decimal, ROUND_CEILING
from pathlib import Path
from typing import Any

from opspilot.domain.database import connect
from opspilot.domain.d2 import canonical_json, digest_json, utc_now

EXPERIMENT_ID = "AR-02-LIVE-01"
EXPERIMENT_ENV = "OPSPILOT_ASSISTANT_EXPERIMENT_ID"
PROVIDER_LIMIT = 16
MCP_LIMIT = 12
BUDGET_USD_MICRO = 10_500_000

# DeepSeek Flash peak cache-miss input/output rates checked 2026-11-01.
# The reservation uses the documented maximum output/context envelope rather
# than trusting the request's 2048-token cap: (616K * $0.30 + 384K * $1.20)/1M.
PRICE_VERSION = "DEEPSEEK_FLASH_PEAK_2026-11-01"
INPUT_USD_PER_MILLION = Decimal("0.30")
OUTPUT_USD_PER_MILLION = Decimal("1.20")
MODEL_CONTEXT_TOKENS = 1_000_000
MODEL_MAX_OUTPUT_TOKENS = 384_000
REQUEST_MAX_OUTPUT_TOKENS = 2_048
MAX_PROVIDER_RESERVATION_USD_MICRO = 645_600

SCHEMA = """
CREATE TABLE IF NOT EXISTS ar02_live_experiment_budgets (
    experiment_id TEXT PRIMARY KEY CHECK (experiment_id = 'AR-02-LIVE-01'),
    provider_limit INTEGER NOT NULL,
    mcp_limit INTEGER NOT NULL,
    budget_usd_micro INTEGER NOT NULL,
    price_version TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('OPEN', 'BUDGET_BREACH')),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS ar02_live_dispatches (
    dispatch_id TEXT PRIMARY KEY,
    experiment_id TEXT NOT NULL REFERENCES ar02_live_experiment_budgets(experiment_id),
    run_id TEXT NOT NULL REFERENCES task_runs(run_id) ON DELETE CASCADE,
    kind TEXT NOT NULL CHECK (kind IN ('MODEL', 'MCP')),
    logical_key TEXT NOT NULL,
    request_digest TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('RESERVED', 'OK', 'UNKNOWN', 'NOT_DISPATCHED')),
    reserved_usd_micro INTEGER NOT NULL DEFAULT 0 CHECK (reserved_usd_micro >= 0),
    settled_usd_micro INTEGER NOT NULL DEFAULT 0 CHECK (settled_usd_micro >= 0),
    usage_state TEXT NOT NULL DEFAULT 'UNKNOWN' CHECK (usage_state IN ('KNOWN', 'UNKNOWN', 'VIOLATION')),
    usage_json TEXT,
    error_code TEXT,
    created_at TEXT NOT NULL,
    completed_at TEXT,
    UNIQUE (experiment_id, run_id, kind, logical_key)
);
CREATE INDEX IF NOT EXISTS ix_ar02_live_dispatch_kind
    ON ar02_live_dispatches(experiment_id, kind, status, created_at);
"""


class ExperimentBudgetError(RuntimeError):
    """A deterministic, safe-to-surface refusal before external dispatch."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def _validate_experiment_id(experiment_id: str) -> None:
    if experiment_id != EXPERIMENT_ID:
        raise ExperimentBudgetError("AR02_LIVE_EXPERIMENT_SCOPE_INVALID")


def _table_exists(connection, table: str) -> bool:
    return connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone() is not None


def _ensure_row(connection, experiment_id: str) -> None:
    row = connection.execute(
        "SELECT * FROM ar02_live_experiment_budgets WHERE experiment_id=?",
        (experiment_id,),
    ).fetchone()
    if row is None:
        now = utc_now()
        connection.execute(
            """INSERT INTO ar02_live_experiment_budgets
               (experiment_id, provider_limit, mcp_limit, budget_usd_micro,
                price_version, status, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, 'OPEN', ?, ?)""",
            (
                experiment_id,
                PROVIDER_LIMIT,
                MCP_LIMIT,
                BUDGET_USD_MICRO,
                PRICE_VERSION,
                now,
                now,
            ),
        )
        return
    if (
        int(row["provider_limit"]) != PROVIDER_LIMIT
        or int(row["mcp_limit"]) != MCP_LIMIT
        or int(row["budget_usd_micro"]) != BUDGET_USD_MICRO
        or str(row["price_version"]) != PRICE_VERSION
    ):
        raise ExperimentBudgetError("AR02_LIVE_BUDGET_CONFIGURATION_MISMATCH")


def initialize_experiment(path: str | Path, experiment_id: str = EXPERIMENT_ID) -> None:
    """Create the campaign ledger lazily; ordinary assistant DBs are untouched."""
    _validate_experiment_id(experiment_id)
    with connect(path) as connection:
        connection.executescript("BEGIN IMMEDIATE;\n" + SCHEMA)
        _ensure_row(connection, experiment_id)


def _used_count(connection, experiment_id: str, kind: str) -> int:
    row = connection.execute(
        """SELECT COUNT(*) AS n FROM ar02_live_dispatches
           WHERE experiment_id=? AND kind=? AND status!='NOT_DISPATCHED'""",
        (experiment_id, kind),
    ).fetchone()
    return int(row["n"])


def _money_totals(connection, experiment_id: str) -> tuple[int, int]:
    row = connection.execute(
        """SELECT COALESCE(SUM(reserved_usd_micro), 0) AS reserved,
                  COALESCE(SUM(settled_usd_micro), 0) AS settled
           FROM ar02_live_dispatches WHERE experiment_id=?""",
        (experiment_id,),
    ).fetchone()
    return int(row["reserved"]), int(row["settled"])


def reserve_dispatch(
    path: str | Path,
    *,
    experiment_id: str,
    run_id: str,
    kind: str,
    logical_key: str,
    request: Any,
) -> dict[str, Any]:
    """Atomically reserve one campaign dispatch before Provider/MCP I/O."""
    _validate_experiment_id(experiment_id)
    if kind not in {"MODEL", "MCP"} or not logical_key:
        raise ExperimentBudgetError("AR02_LIVE_DISPATCH_IDENTITY_INVALID")
    request_digest = digest_json(request)

    # The app initializes this at worker startup. Lazy creation also makes direct
    # offline callers safe, while remaining limited to this fixed experiment ID.
    initialize_experiment(path, experiment_id)
    with connect(path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        budget = connection.execute(
            "SELECT * FROM ar02_live_experiment_budgets WHERE experiment_id=?",
            (experiment_id,),
        ).fetchone()
        if budget is None:
            raise ExperimentBudgetError("AR02_LIVE_BUDGET_NOT_INITIALIZED")
        if budget["status"] != "OPEN":
            raise ExperimentBudgetError("AR02_LIVE_SPEND_BOUND_BREACHED")

        old = connection.execute(
            """SELECT * FROM ar02_live_dispatches
               WHERE experiment_id=? AND run_id=? AND kind=? AND logical_key=?""",
            (experiment_id, run_id, kind, logical_key),
        ).fetchone()
        if old is not None:
            if str(old["request_digest"]) != request_digest:
                raise ExperimentBudgetError("AR02_LIVE_IDEMPOTENCY_CONFLICT")
            if old["status"] == "OK":
                return {"dispatch": False, "replay": True, "dispatch_id": old["dispatch_id"]}
            if old["status"] == "NOT_DISPATCHED":
                raise ExperimentBudgetError("AR02_LIVE_ALREADY_NOT_DISPATCHED")
            raise ExperimentBudgetError("AR02_LIVE_CALL_OUTCOME_UNKNOWN")

        count = _used_count(connection, experiment_id, kind)
        count_limit = PROVIDER_LIMIT if kind == "MODEL" else MCP_LIMIT
        if count >= count_limit:
            label = "PROVIDER" if kind == "MODEL" else "MCP"
            raise ExperimentBudgetError(f"AR02_LIVE_{label}_LIMIT")

        reservation = MAX_PROVIDER_RESERVATION_USD_MICRO if kind == "MODEL" else 0
        if kind == "MODEL":
            reserved, settled = _money_totals(connection, experiment_id)
            if reserved + settled + reservation > BUDGET_USD_MICRO:
                raise ExperimentBudgetError("AR02_LIVE_USD_LIMIT")

        dispatch_id = "ar02-live-dispatch-" + str(uuid.uuid4())
        connection.execute(
            """INSERT INTO ar02_live_dispatches
               (dispatch_id, experiment_id, run_id, kind, logical_key, request_digest,
                status, reserved_usd_micro, created_at)
               VALUES (?, ?, ?, ?, ?, ?, 'RESERVED', ?, ?)""",
            (
                dispatch_id,
                experiment_id,
                run_id,
                kind,
                logical_key,
                request_digest,
                reservation,
                utc_now(),
            ),
        )
        return {
            "dispatch": True,
            "replay": False,
            "dispatch_id": dispatch_id,
            "reserved_usd_micro": reservation,
        }


def _usage_tokens(usage: Any) -> tuple[int, int, int | None] | None:
    if not isinstance(usage, dict):
        return None
    input_tokens = usage.get("input_tokens")
    output_tokens = usage.get("output_tokens")
    total_tokens = usage.get("total_tokens")
    if (
        isinstance(input_tokens, bool)
        or not isinstance(input_tokens, int)
        or input_tokens < 0
        or isinstance(output_tokens, bool)
        or not isinstance(output_tokens, int)
        or output_tokens < 0
    ):
        return None
    if total_tokens is not None and (
        isinstance(total_tokens, bool)
        or not isinstance(total_tokens, int)
        or total_tokens != input_tokens + output_tokens
    ):
        return None
    return input_tokens, output_tokens, total_tokens


def _actual_cost_micro(input_tokens: int, output_tokens: int) -> int:
    cost = (
        Decimal(input_tokens) * INPUT_USD_PER_MILLION
        + Decimal(output_tokens) * OUTPUT_USD_PER_MILLION
    )
    return int(cost.to_integral_value(rounding=ROUND_CEILING))


def complete_dispatch(
    path: str | Path,
    *,
    experiment_id: str,
    run_id: str,
    kind: str,
    logical_key: str,
    usage: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Persist successful dispatch and settle only validated Provider Usage."""
    _validate_experiment_id(experiment_id)
    with connect(path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute(
            """SELECT * FROM ar02_live_dispatches
               WHERE experiment_id=? AND run_id=? AND kind=? AND logical_key=?""",
            (experiment_id, run_id, kind, logical_key),
        ).fetchone()
        if row is None:
            raise ExperimentBudgetError("AR02_LIVE_DISPATCH_NOT_RESERVED")
        if row["status"] == "OK":
            return {
                "status": "OK",
                "usage_state": str(row["usage_state"]),
                "settled_usd_micro": int(row["settled_usd_micro"]),
            }
        if row["status"] != "RESERVED":
            raise ExperimentBudgetError("AR02_LIVE_DISPATCH_NOT_ACTIVE")

        now = utc_now()
        if kind == "MCP":
            connection.execute(
                """UPDATE ar02_live_dispatches
                   SET status='OK', reserved_usd_micro=0, usage_state='KNOWN',
                       completed_at=? WHERE dispatch_id=?""",
                (now, row["dispatch_id"]),
            )
            return {"status": "OK", "usage_state": "KNOWN", "settled_usd_micro": 0}

        normalized = _usage_tokens(usage)
        if normalized is None:
            connection.execute(
                """UPDATE ar02_live_dispatches SET status='OK', usage_state='UNKNOWN',
                   usage_json=NULL, completed_at=? WHERE dispatch_id=?""",
                (now, row["dispatch_id"]),
            )
            return {
                "status": "OK",
                "usage_state": "UNKNOWN",
                "settled_usd_micro": 0,
                "reserved_usd_micro": int(row["reserved_usd_micro"]),
            }

        input_tokens, output_tokens, total_tokens = normalized
        actual_micro = _actual_cost_micro(input_tokens, output_tokens)
        violation = (
            output_tokens > REQUEST_MAX_OUTPUT_TOKENS
            or output_tokens > MODEL_MAX_OUTPUT_TOKENS
            or input_tokens + output_tokens > MODEL_CONTEXT_TOKENS
            or actual_micro > MAX_PROVIDER_RESERVATION_USD_MICRO
        )
        usage_payload = {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": total_tokens,
            "price_version": PRICE_VERSION,
        }
        connection.execute(
            """UPDATE ar02_live_dispatches
               SET status='OK', reserved_usd_micro=0, settled_usd_micro=?,
                   usage_state=?, usage_json=?, completed_at=? WHERE dispatch_id=?""",
            (
                actual_micro,
                "VIOLATION" if violation else "KNOWN",
                canonical_json(usage_payload),
                now,
                row["dispatch_id"],
            ),
        )
        reserved, settled = _money_totals(connection, experiment_id)
        if violation or reserved + settled > BUDGET_USD_MICRO:
            connection.execute(
                """UPDATE ar02_live_experiment_budgets
                   SET status='BUDGET_BREACH', updated_at=? WHERE experiment_id=?""",
                (now, experiment_id),
            )
        return {
            "status": "OK",
            "usage_state": "VIOLATION" if violation else "KNOWN",
            "settled_usd_micro": actual_micro,
        }


def mark_unknown(
    path: str | Path,
    *,
    experiment_id: str,
    run_id: str,
    kind: str,
    logical_key: str,
    error_code: str,
) -> None:
    """Keep the count and full cost reservation when dispatch outcome is unknown."""
    _validate_experiment_id(experiment_id)
    with connect(path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        connection.execute(
            """UPDATE ar02_live_dispatches SET status='UNKNOWN', error_code=?, completed_at=?
               WHERE experiment_id=? AND run_id=? AND kind=? AND logical_key=?
                 AND status='RESERVED'""",
            (str(error_code)[:120], utc_now(), experiment_id, run_id, kind, logical_key),
        )


def read_dispatch(
    path: str | Path,
    *,
    experiment_id: str,
    run_id: str,
    kind: str,
    logical_key: str,
) -> dict[str, Any] | None:
    """Read an existing reservation without creating or reauthorizing a send."""
    _validate_experiment_id(experiment_id)
    with connect(path) as connection:
        if not _table_exists(connection, "ar02_live_dispatches"):
            return None
        row = connection.execute(
            """SELECT * FROM ar02_live_dispatches
               WHERE experiment_id=? AND run_id=? AND kind=? AND logical_key=?""",
            (experiment_id, run_id, kind, logical_key),
        ).fetchone()
        return dict(row) if row is not None else None


def mark_not_dispatched(
    path: str | Path,
    *,
    experiment_id: str,
    run_id: str,
    kind: str,
    logical_key: str,
    reason_code: str,
) -> None:
    """Release only when trusted local policy proves no external send occurred."""
    _validate_experiment_id(experiment_id)
    with connect(path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        connection.execute(
            """UPDATE ar02_live_dispatches SET status='NOT_DISPATCHED',
                 reserved_usd_micro=0, error_code=?, completed_at=?
               WHERE experiment_id=? AND run_id=? AND kind=? AND logical_key=?
                 AND status='RESERVED'""",
            (str(reason_code)[:120], utc_now(), experiment_id, run_id, kind, logical_key),
        )


def read_budget(path: str | Path, experiment_id: str = EXPERIMENT_ID) -> dict[str, Any]:
    """Read-only campaign snapshot; does not create or reset experiment state."""
    _validate_experiment_id(experiment_id)
    with connect(path) as connection:
        if not _table_exists(connection, "ar02_live_experiment_budgets"):
            return {"experiment_id": experiment_id, "initialized": False}
        budget = connection.execute(
            "SELECT * FROM ar02_live_experiment_budgets WHERE experiment_id=?",
            (experiment_id,),
        ).fetchone()
        if budget is None:
            return {"experiment_id": experiment_id, "initialized": False}
        reserved, settled = _money_totals(connection, experiment_id)
        return {
            "experiment_id": experiment_id,
            "initialized": True,
            "status": str(budget["status"]),
            "provider_limit": int(budget["provider_limit"]),
            "provider_used": _used_count(connection, experiment_id, "MODEL"),
            "mcp_limit": int(budget["mcp_limit"]),
            "mcp_used": _used_count(connection, experiment_id, "MCP"),
            "budget_usd_micro": int(budget["budget_usd_micro"]),
            "usd_reserved_micro": reserved,
            "usd_settled_micro": settled,
            "usd_remaining_micro": int(budget["budget_usd_micro"]) - reserved - settled,
            "price_version": str(budget["price_version"]),
        }
