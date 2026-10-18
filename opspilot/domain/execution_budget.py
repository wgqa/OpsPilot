from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from opspilot.domain.database import connect


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
