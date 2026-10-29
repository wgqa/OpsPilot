from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from opspilot.domain.database import connect


def attempt_policy_in_transaction(connection, task_id):
    """Trusted fixed policies; legacy rows are never implicitly upgraded."""
    from opspilot.domain.d2 import ScopeDenied

    row = connection.execute(
        "SELECT * FROM task_execution_budgets WHERE task_id=?", (task_id,),
    ).fetchone()
    if row is None:
        binding = connection.execute("SELECT service_id FROM task_bindings WHERE task_id=?",(task_id,)).fetchone()
        if binding and binding["service_id"] == "orders-async-demo":
            raise ScopeDenied("TASK_ATTEMPT_POLICY_MISSING")
        return {"version":"LEGACY_V1", "MODEL":8, "MCP":6, "AUX":None}
    version = row["policy_version"]
    pair = (row["model_limit"], row["mcp_limit"])
    if any(type(n) is not int for n in pair):
        raise ScopeDenied("TASK_ATTEMPT_POLICY_INVALID")
    if version == "CONTUX_S3_V1":
        binding = connection.execute(
            "SELECT service_id,tenant_id FROM task_bindings WHERE task_id=?", (task_id,),
        ).fetchone()
        if (binding is None or binding["service_id"] != "orders-async-demo"
                or binding["tenant_id"] != row["tenant_id"] or pair != (24,18)
                or type(row["aux_provider_limit"]) is not int or row["aux_provider_limit"] != 8):
            raise ScopeDenied("TASK_ATTEMPT_POLICY_INVALID")
        return {"version":version, "MODEL":24, "MCP":18, "AUX":8}
    if version != "LEGACY_V1" or pair not in {(8,6),(12,8),(16,10)} or row["aux_provider_limit"] is not None:
        raise ScopeDenied("TASK_ATTEMPT_POLICY_INVALID")
    return {"version":version, "MODEL":pair[0], "MCP":pair[1], "AUX":None}


def auxiliary_attempt_counts_in_transaction(connection, task_id):
    """Count all durable reservations, including failed and unknown outcomes."""
    return {
        "CLASSIFIER": int(connection.execute(
            """SELECT COUNT(*) FROM investigation_update_attempts a
               JOIN investigation_update_assessments s ON s.assessment_id=a.assessment_id
               WHERE s.task_id=?""", (task_id,),
        ).fetchone()[0]),
        "CHAT": int(connection.execute("SELECT COUNT(*) FROM chat_attempts a WHERE task_id=? AND NOT EXISTS (SELECT 1 FROM assistant_runs r WHERE r.run_id=a.run_id)",(task_id,)).fetchone()[0]) + int(connection.execute("SELECT COUNT(*) FROM assistant_calls a JOIN task_runs r ON r.run_id=a.run_id WHERE r.task_id=? AND a.kind='MODEL'",(task_id,)).fetchone()[0]),
        "COMPRESSION": int(connection.execute("SELECT COUNT(*) FROM context_compression_attempts WHERE task_id=?",(task_id,)).fetchone()[0]),
    }


def auxiliary_budget_in_transaction(connection, task_id):
    if task_id is None:
        return {"limit":None, "used":0, "remaining":None, "reason_code":None}
    policy = attempt_policy_in_transaction(connection, task_id)
    counts = auxiliary_attempt_counts_in_transaction(connection, task_id)
    used = sum(counts.values())
    cap = policy["AUX"]
    return {"limit":cap, "used":used, "by_kind":counts,
            "remaining":max(0,cap-used) if cap is not None else None,
            "reason_code":"TASK_AUX_PROVIDER_LIMIT" if cap is not None and used >= cap else None}


def investigation_budget_in_transaction(connection, task_id, run_id=None):
    """Project two-level remaining capacity from existing immutable Attempt rows.

    Reservation callers hold BEGIN IMMEDIATE while using this and inserting.
    No allocation counter is reset or granted by a checkpoint or caller limit.
    """
    from opspilot.domain.d2 import ScopeDenied

    policy = attempt_policy_in_transaction(connection, task_id)
    task_used = {"MODEL":0,"MCP":0}
    task_used.update({r["kind"]:int(r["n"]) for r in connection.execute(
        "SELECT kind,COUNT(*) AS n FROM d2_attempts WHERE task_id=? GROUP BY kind",(task_id,))})
    run_used = {"MODEL":0,"MCP":0}
    run_limits = None
    if run_id is not None:
        run = connection.execute(
            "SELECT task_id,tenant_id,kind FROM task_runs WHERE run_id=?",(run_id,),
        ).fetchone()
        from opspilot.domain.assistant import selected as assistant_selected
        if run is None or run["task_id"] != task_id or (run["kind"] == "CHAT_READONLY" and not assistant_selected(connection,run_id)):
            raise ScopeDenied("TASK_ATTEMPT_RUN_INVALID")
        run_used.update({r["kind"]:int(r["n"]) for r in connection.execute(
            "SELECT kind,COUNT(*) AS n FROM d2_attempts WHERE task_id=? AND run_id=? GROUP BY kind",(task_id,run_id))})
        if policy["version"] == "CONTUX_S3_V1":
            followup = connection.execute(
                "SELECT 1 FROM c1_readonly_followup_runs WHERE run_id=? AND task_id=? AND tenant_id=?",
                (run_id,task_id,run["tenant_id"]),
            ).fetchone()
            run_limits = {"MODEL":4,"MCP":3} if followup else {"MODEL":8,"MCP":6}
    elif policy["version"] == "CONTUX_S3_V1":
        raise ScopeDenied("TASK_ATTEMPT_RUN_REQUIRED")
    task_limits = {kind:policy[kind] for kind in ("MODEL","MCP")}
    remaining, reasons = {}, {}
    for kind in task_limits:
        remaining[kind] = max(0,task_limits[kind]-task_used[kind])
        reasons[kind] = f"TASK_{kind}_LIMIT" if not remaining[kind] else None
        if run_limits:
            run_remaining = max(0,run_limits[kind]-run_used[kind])
            remaining[kind] = min(remaining[kind],run_remaining)
            if not run_remaining and reasons[kind] is None:
                reasons[kind] = f"RUN_{kind}_LIMIT"
    clock = connection.execute("SELECT active_elapsed_ms,deadline_ms FROM task_execution_budgets WHERE task_id=?",(task_id,)).fetchone()
    if policy["version"] == "CONTUX_S3_V1" and clock and clock["active_elapsed_ms"] >= clock["deadline_ms"]:
        remaining = {"MODEL":0,"MCP":0}
        reasons = {"MODEL":"ACTIVE_TIME_LIMIT","MCP":"ACTIVE_TIME_LIMIT"}
    return {"policy_version":policy["version"], "task_limits":task_limits,"run_limits":run_limits,
            "task_used":task_used,"run_used":run_used,"remaining_attempts":remaining,"limit_reasons":reasons}


def investigation_budget_snapshot(path, task_id, run_id):
    with connect(path) as connection:
        return {**investigation_budget_in_transaction(connection,task_id,run_id),
                "auxiliary":auxiliary_budget_in_transaction(connection,task_id)}


def _utc_from_ms(value: int) -> str:
    return datetime.fromtimestamp(value / 1000, tz=timezone.utc).isoformat(timespec="milliseconds")


def _ms_from_utc(value: str | None) -> int | None:
    if value is None:
        return None
    return int(datetime.fromisoformat(value).timestamp() * 1000)


def _ensure_budget(connection, tenant_id: str, task_id: str, deadline_ms: int, now_ms: int) -> None:
    connection.execute(
        """INSERT OR IGNORE INTO task_execution_budgets
           (task_id, tenant_id, active_elapsed_ms, active_started_at, heartbeat_at,
            deadline_ms, deadline_reached_at, updated_at)
           VALUES (?, ?, 0, NULL, NULL, ?, NULL, ?)""",
        (task_id, tenant_id, deadline_ms, _utc_from_ms(now_ms)),
    )


def begin_execution_interval(
    path: str | Path,
    task_id: str,
    *,
    now_ms: int | None = None,
    default_deadline_ms: int = 300_000,
) -> int:
    """Start an active investigation interval and return its remaining deadline."""
    now = now_ms if now_ms is not None else int(datetime.now(timezone.utc).timestamp() * 1000)
    with connect(path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        binding = connection.execute(
            "SELECT tenant_id FROM task_bindings WHERE task_id = ?", (task_id,)
        ).fetchone()
        if binding is None:
            raise ValueError("Task does not exist.")
        tenant_id = str(binding["tenant_id"])
        _ensure_budget(connection, tenant_id, task_id, default_deadline_ms, now)
        row = connection.execute(
            "SELECT active_elapsed_ms, active_started_at, heartbeat_at, deadline_ms FROM task_execution_budgets WHERE task_id = ?",
            (task_id,),
        ).fetchone()
        if row["active_started_at"] is not None:
            raise RuntimeError("Task already has an active investigation interval.")
        remaining = max(0, int(row["deadline_ms"]) - int(row["active_elapsed_ms"]))
        started = _utc_from_ms(now) if remaining > 0 else None
        connection.execute(
            """UPDATE task_execution_budgets SET active_started_at = ?, heartbeat_at = ?,
                      deadline_reached_at = CASE WHEN ? = 0 THEN COALESCE(deadline_reached_at, ?) ELSE deadline_reached_at END,
                      updated_at = ? WHERE task_id = ?""",
            (started, started, remaining, _utc_from_ms(now), _utc_from_ms(now), task_id),
        )
    return remaining


def heartbeat_execution_interval(
    path: str | Path,
    task_id: str,
    *,
    now_ms: int | None = None,
    max_gap_ms: int = 5_000,
) -> int:
    now = now_ms if now_ms is not None else int(datetime.now(timezone.utc).timestamp() * 1000)
    with connect(path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute(
            "SELECT * FROM task_execution_budgets WHERE task_id = ?", (task_id,)
        ).fetchone()
        if row is None or row["active_started_at"] is None:
            return 0
        heartbeat = _ms_from_utc(str(row["heartbeat_at"])) or now
        delta = min(max(0, now - heartbeat), max_gap_ms)
        elapsed = int(row["active_elapsed_ms"]) + delta
        deadline = int(row["deadline_ms"])
        reached_at = row["deadline_reached_at"]
        if elapsed >= deadline and reached_at is None:
            reached_at = _utc_from_ms(now)
        connection.execute(
            """UPDATE task_execution_budgets SET active_elapsed_ms = ?, heartbeat_at = ?,
                      deadline_reached_at = ?, updated_at = ? WHERE task_id = ?""",
            (elapsed, _utc_from_ms(now), reached_at, _utc_from_ms(now), task_id),
        )
        return max(0, deadline - elapsed)


def end_execution_interval(
    path: str | Path,
    task_id: str,
    *,
    now_ms: int | None = None,
    max_gap_ms: int = 5_000,
) -> dict[str, int | bool]:
    now = now_ms if now_ms is not None else int(datetime.now(timezone.utc).timestamp() * 1000)
    with connect(path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute(
            "SELECT * FROM task_execution_budgets WHERE task_id = ?", (task_id,)
        ).fetchone()
        if row is None:
            return {"active_elapsed_ms": 0, "deadline_ms": 0, "expired": False}
        elapsed = int(row["active_elapsed_ms"])
        if row["active_started_at"] is not None:
            heartbeat = _ms_from_utc(str(row["heartbeat_at"])) or now
            elapsed += min(max(0, now - heartbeat), max_gap_ms)
        deadline = int(row["deadline_ms"])
        reached = _utc_from_ms(now) if elapsed >= deadline and row["deadline_reached_at"] is None else row["deadline_reached_at"]
        connection.execute(
            """UPDATE task_execution_budgets SET active_elapsed_ms = ?, active_started_at = NULL,
                      heartbeat_at = NULL, deadline_reached_at = ?, updated_at = ? WHERE task_id = ?""",
            (elapsed, reached, _utc_from_ms(now), task_id),
        )
    return {"active_elapsed_ms": elapsed, "deadline_ms": deadline, "expired": elapsed >= deadline}


def recover_abandoned_execution_intervals(
    path: str | Path,
    *,
    now_ms: int | None = None,
    max_gap_ms: int = 5_000,
) -> list[str]:
    """Close stale active intervals at the last persisted heartbeat after exclusive worker lock."""
    now = now_ms if now_ms is not None else int(datetime.now(timezone.utc).timestamp() * 1000)
    recovered: list[str] = []
    with connect(path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        rows = connection.execute(
            "SELECT * FROM task_execution_budgets WHERE active_started_at IS NOT NULL"
        ).fetchall()
        for row in rows:
            heartbeat = _ms_from_utc(str(row["heartbeat_at"])) or now
            elapsed = int(row["active_elapsed_ms"]) + min(max(0, now - heartbeat), max_gap_ms)
            deadline = int(row["deadline_ms"])
            reached = row["deadline_reached_at"]
            if elapsed >= deadline and reached is None:
                reached = _utc_from_ms(now)
            connection.execute(
                """UPDATE task_execution_budgets SET active_elapsed_ms = ?, active_started_at = NULL,
                          heartbeat_at = NULL, deadline_reached_at = ?, updated_at = ? WHERE task_id = ?""",
                (elapsed, reached, _utc_from_ms(now), row["task_id"]),
            )
            recovered.append(str(row["task_id"]))
    return recovered


def execution_budget_snapshot(path: str | Path, task_id: str) -> dict[str, int | str | None]:
    with connect(path) as connection:
        row = connection.execute(
            "SELECT * FROM task_execution_budgets WHERE task_id = ?", (task_id,)
        ).fetchone()
    if row is None:
        raise ValueError("Task execution budget does not exist.")
    return {
        "active_elapsed_ms": int(row["active_elapsed_ms"]),
        "deadline_ms": int(row["deadline_ms"]),
        "remaining_ms": max(0, int(row["deadline_ms"]) - int(row["active_elapsed_ms"])),
        "active_started_at": str(row["active_started_at"]) if row["active_started_at"] else None,
        "heartbeat_at": str(row["heartbeat_at"]) if row["heartbeat_at"] else None,
        "deadline_reached_at": str(row["deadline_reached_at"]) if row["deadline_reached_at"] else None,
    }
