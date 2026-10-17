from pathlib import Path

from opspilot.config import DEFAULT_DB_PATH, database_path


def test_empty_db_placeholder_uses_default_path(monkeypatch) -> None:
    monkeypatch.setenv("OPSPILOT_DB_PATH", "")
    assert database_path() == DEFAULT_DB_PATH.resolve()
