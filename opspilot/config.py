from __future__ import annotations

import os
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB_PATH = ROOT / ".runtime" / "opspilot.sqlite3"
DEFAULT_CHECKPOINT_DB_PATH = ROOT / ".runtime" / "opspilot-checkpoints.sqlite3"
MODEL_API_KEY = "OPSPILOT_MODEL_API_KEY"
MODEL_BASE_URL = "OPSPILOT_MODEL_BASE_URL"
MODEL_NAME = "OPSPILOT_MODEL_NAME"


def load_local_environment(path: Path | None = None) -> None:
    """Load simple KEY=VALUE lines without overriding process-level secrets."""
    env_path = path or ROOT / ".env"
    if not env_path.is_file():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        key, separator, value = stripped.partition("=")
        if not separator or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key.strip()):
            raise ValueError("Invalid .env entry; expected KEY=VALUE.")
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        os.environ.setdefault(key.strip(), value)


def database_path(value: str | None = None) -> Path:
    path = Path(value or os.environ.get("OPSPILOT_DB_PATH") or DEFAULT_DB_PATH)
    if not path.is_absolute():
        path = ROOT / path
    return path.resolve()
