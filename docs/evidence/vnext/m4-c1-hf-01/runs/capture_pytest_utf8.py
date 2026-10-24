from __future__ import annotations

import subprocess
import sys
import os
from pathlib import Path


def main() -> int:
    if len(sys.argv) < 3:
        raise SystemExit("usage: capture_pytest_utf8.py LOG_PATH PYTEST_ARGS...")
    log_path = Path(sys.argv[1])
    command = [sys.executable, "-m", "pytest", *sys.argv[2:]]
    environment = {**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"}
    completed = subprocess.run(
        command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        env=environment, check=False,
    )
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_bytes(completed.stdout)
    sys.stdout.write(f"PYTEST_EXIT_CODE={completed.returncode}\n")
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
