from __future__ import annotations

import json
import sys
import time
from pathlib import Path


def main(argv: list[str]) -> int:
    if len(argv) != 10:
        return 2
    db, task_id, draft_id, digest, revision, operation_id, go, ready, result_path = argv[1:]
    Path(ready).write_text("ready", encoding="utf-8")
    deadline = time.monotonic() + 20
    while not Path(go).exists() and time.monotonic() < deadline:
        time.sleep(0.005)
    if not Path(go).exists():
        Path(result_path).write_text(json.dumps({"ok": False, "code": "RACE_BARRIER_TIMEOUT"}), encoding="utf-8")
        return 3
    from opspilot.domain.s2_handoff import submit_s2_handoff
    from opspilot.domain.task_control import trusted_identity

    try:
        result = submit_s2_handoff(
            db,
            trusted_identity(db, "support-a"),
            task_id=task_id,
            operation_id=operation_id,
            draft_id=draft_id,
            draft_digest=digest,
            expected_control_revision=int(revision),
            handoff_kind="SCOPE_REVIEW",
        )
        Path(result_path).write_text(json.dumps({"ok": True, **result}), encoding="utf-8")
    except Exception as error:  # Child output is evidence consumed by the parent test.
        Path(result_path).write_text(json.dumps({"ok": False, "code": getattr(error, "code", type(error).__name__)}), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
