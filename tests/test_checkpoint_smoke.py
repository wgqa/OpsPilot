from opspilot.smokes.checkpoint import run_smoke


def test_sqlite_checkpoint_survives_distinct_agent_processes() -> None:
    assert run_smoke() == 0
