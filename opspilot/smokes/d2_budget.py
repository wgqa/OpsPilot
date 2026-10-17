from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from opspilot.domain.d2 import create_task_binding
from opspilot.domain.database import reset_fixture


def emit(event: str, **fields: object) -> None:
    print(json.dumps({"event": event, **fields}, sort_keys=True))


def _run(mode: str, db_path: Path, task_id: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "opspilot.smokes.d2_budget_worker",
            mode,
            "--db",
            str(db_path),
            "--task-id",
            task_id,
            "--limit",
            "1",
        ],
        cwd=Path(__file__).resolve().parents[2],
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )


def run_smoke(db_path: Path) -> int:
    reset_fixture(db_path, "S1_POS")
    binding = create_task_binding(db_path, "support-a", "orders-demo", "integration-a")
    first = _run("reserve", db_path, str(binding["task_id"]))
    second = _run("read-and-reject", db_path, str(binding["task_id"]))
    try:
        first_event = json.loads(first.stdout.splitlines()[-1])
        second_event = json.loads(second.stdout.splitlines()[-1])
    except (IndexError, json.JSONDecodeError):
        emit("d2_budget_restart_failed", process_a_exit=first.returncode, process_a_stdout=first.stdout, process_b_exit=second.returncode, process_b_stdout=second.stdout)
        return 1
    passed = (
        first.returncode == 0
        and second.returncode == 0
        and first_event.get("event") == "d2_budget_attempt_reserved"
        and second_event.get("event") == "d2_budget_persisted_after_restart"
        and first_event.get("pid") != second_event.get("pid")
        and second_event.get("mcp_used") == 1
        and second_event.get("next_attempt_denied") is True
    )
    emit(
        "d2_budget_restart_result",
        passed=passed,
        task_id=binding["task_id"],
        process_a=first_event,
        process_b=second_event,
    )
    return 0 if passed else 1


def main() -> int:
    import argparse
    import tempfile

    parser = argparse.ArgumentParser()
    parser.add_argument("--db")
    args = parser.parse_args()
    if args.db:
        return run_smoke(Path(args.db).resolve())
    with tempfile.TemporaryDirectory(prefix="opspilot-d2-budget-") as temporary:
        return run_smoke(Path(temporary) / "domain.sqlite3")


if __name__ == "__main__":
    raise SystemExit(main())
