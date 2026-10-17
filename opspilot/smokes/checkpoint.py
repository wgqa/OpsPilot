from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path


THREAD_ID = "d1-cross-process-resume"


def emit(event: str, **fields: object) -> None:
    print(json.dumps({"event": event, **fields}, sort_keys=True))


def run_worker(mode: str, checkpoint_db: Path, owner_db: Path, actor: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "opspilot.smokes.checkpoint_worker",
            mode,
            "--checkpoint-db",
            str(checkpoint_db),
            "--owner-db",
            str(owner_db),
            "--thread-id",
            THREAD_ID,
            "--actor",
            actor,
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )


def worker_event(process: subprocess.CompletedProcess[str]) -> dict[str, object] | None:
    for line in process.stdout.splitlines():
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(record, dict) and "event" in record:
            return record
    return None


def run_smoke() -> int:
    with tempfile.TemporaryDirectory(prefix="opspilot-checkpoint-") as temporary:
        temp_path = Path(temporary)
        checkpoint_db = temp_path / "checkpoints.sqlite3"
        owner_db = temp_path / "task-owners.sqlite3"
        start = run_worker("start", checkpoint_db, owner_db, "support-a")
        start_event = worker_event(start)
        if start.returncode != 0 or not start_event or start_event.get("event") != "checkpoint_interrupt_saved":
            emit("checkpoint_process_a_failed", exit_code=start.returncode, stdout=start.stdout, stderr=start.stderr)
            return 1
        emit("checkpoint_process_a_exited", pid=start_event.get("pid"), exit_code=start.returncode, thread_id=THREAD_ID)

        denied = run_worker("resume", checkpoint_db, owner_db, "support-b")
        denied_event = worker_event(denied)
        if denied.returncode != 3 or not denied_event or denied_event.get("event") != "checkpoint_resume_denied":
            emit("checkpoint_ownership_negative_failed", exit_code=denied.returncode, stdout=denied.stdout)
            return 1
        emit("checkpoint_ownership_negative", exit_code=denied.returncode, reason="owner mismatch denied before checkpoint read")

        resume = run_worker("resume", checkpoint_db, owner_db, "support-a")
        resume_event = worker_event(resume)
        if resume.returncode != 0 or not resume_event or resume_event.get("event") != "checkpoint_resume_pass":
            emit("checkpoint_process_b_failed", exit_code=resume.returncode, stdout=resume.stdout, stderr=resume.stderr)
            return 1
        start_pid, resume_pid = start_event.get("pid"), resume_event.get("pid")
        if start_pid == resume_pid:
            emit("checkpoint_process_identity_failed", pid=start_pid)
            return 1
        emit(
            "checkpoint_process_b_resumed",
            pid=resume_pid,
            process_a_pid=start_pid,
            process_a_exit_code=start.returncode,
            process_b_exit_code=resume.returncode,
            thread_id=THREAD_ID,
            state_before=resume_event.get("state_before"),
            state_after=resume_event.get("state_after"),
            preserved_state=resume_event.get("preserved_state"),
        )
        emit("checkpoint_smoke_pass")
        return 0


if __name__ == "__main__":
    raise SystemExit(run_smoke())
