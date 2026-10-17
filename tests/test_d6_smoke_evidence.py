from __future__ import annotations

import json
from pathlib import Path

import opspilot.smokes.d3 as d3_smoke
from opspilot.config import MODEL_API_KEY, MODEL_NAME
from opspilot.smokes.d5 import _work_dir_for_checkpoint


def test_d5_smoke_workspace_isolated_by_checkpoint_name(tmp_path: Path) -> None:
    first = _work_dir_for_checkpoint(tmp_path / "d6-e10.sqlite3")
    second = _work_dir_for_checkpoint(tmp_path / "d6-e10-retry.sqlite3")

    assert first != second
    assert first == tmp_path / "d6-e10-d5-smoke-work"


def test_d3_smoke_preserves_failed_start_process_without_crashing(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv(MODEL_API_KEY, "d6-test-key")
    monkeypatch.setenv(MODEL_NAME, "d6-test-model")
    monkeypatch.setattr(
        d3_smoke,
        "_run_child",
        lambda command: {
            "command": command,
            "return_code": 1,
            "events": [{"event": "d3_start_failed", "error": "provider timeout"}],
            "stdout_unparsed": "",
            "stderr": "provider timeout (redacted)",
            "pid": 2468,
        },
    )

    evidence_dir = tmp_path / "d3-evidence"
    result = d3_smoke.run_smoke(
        tmp_path / "domain.sqlite3",
        tmp_path / "checkpoint.sqlite3",
        evidence_dir,
    )

    trace = json.loads((evidence_dir / "TRACE.json").read_text(encoding="utf-8"))
    assert result == 1
    assert trace["result"] == "FAIL"
    assert trace["processes"]["start"]["return_code"] == 1
    assert trace["processes"]["start"]["stderr"] == "provider timeout (redacted)"
    assert trace["checks"]["gate_ready_and_plan_hash"] is False
    assert trace["checks"]["model_and_mcp_trajectory_present"] is False
