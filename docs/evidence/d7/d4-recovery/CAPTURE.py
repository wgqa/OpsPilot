"""Observe existing D4 worker results; inject no new faults or business behavior.

Run from a clean OpsPilot source root with its venv Python. The two existing
tests choose failpoints and assert safety. This observer preserves the otherwise
captured child stdout/stderr and action/ledger IDs for offline review.
"""
import json
from pathlib import Path
import sys

# A file-path invocation otherwise puts this observer's directory on sys.path.
# Import the source tree under test from the clean working directory.
sys.path.insert(0, str(Path.cwd()))

import pytest

records = []


def observe(frame, event, value):
    if (event == "return" and frame.f_code.co_name == "_worker_event"
            and Path(frame.f_code.co_filename).name == "test_d4_recovery.py"):
        result = frame.f_locals["result"]
        records.append({
            "command": result.args,
            "exit_code": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "parsed_event": value,
        })


if __name__ == "__main__":
    sys.setprofile(observe)
    try:
        code = pytest.main([
            "-vv", "-s", "--basetemp=.runtime/pytest-d7-recovery",
            "tests/test_d4_recovery.py::test_d4_langgraph_replays_committed_repair_after_os_process_crash",
            "tests/test_d4_recovery.py::test_d4_langgraph_replays_committed_delivery_after_lost_response",
        ])
    finally:
        sys.setprofile(None)
        out = Path("docs/evidence/d7/d4-recovery/WORKERS.json")
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(records, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    raise SystemExit(code)
