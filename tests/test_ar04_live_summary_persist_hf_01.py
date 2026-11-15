from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_DIR = ROOT / "docs/evidence/r2-ar04-live-summary-persist-hf01"
RECHECK_DIR = ROOT / "docs/evidence/r2-ar04-live-retention-recheck-01"
sys.path.insert(0, str(RECHECK_DIR))


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def test_frozen_live_summary_domain_replay_records_message_id_budget_sensitivity() -> None:
    replay = _load_module("ar04_summary_persist_replay", EVIDENCE_DIR / "replay_persistence.py")
    matrix = replay.run(samples=12)

    assert matrix["provider_requests"] == 0
    assert matrix["live_source_map_recoverable"] is False
    assert matrix["output_cap_tokens"] == 512
    assert matrix["result_counts"] == {"SUCCEEDED": 12, "FAILED": 0}
    token_counts = {
        count
        for sample in matrix["samples"]
        for count in sample["source_message_id_token_counts"].values()
    }
    assert len(token_counts) > 1
    for sample in matrix["samples"]:
        assert sample["completion_result"]["status"] == "SUCCEEDED"
        persisted = sample["domain_after_completion"]
        assert persisted["attempt"]["status"] == "SUCCEEDED"
        assert persisted["persisted_summary_count"] == 1
        assert persisted["persisted_summary_tokens"] <= 512
        assert persisted["derived_sequence_fields_present"] is False
        assert persisted["source_id_projection"]
        assert all(item["all_source_ids_resolve"] for item in persisted["source_id_projection"])
        assert all(item["source_sequences"] for item in persisted["source_id_projection"])
        for name, item in persisted["persisted_fact_evidence"].items():
            if name == "early_retry_value_seq3":
                expected = "PARTIAL" if sample["sample"] in {0, 8} else "PRESENT"
                assert item["status"] == expected
            else:
                assert item["status"] == "PRESENT", {name: item}


def test_runner_returns_domain_stop_without_reading_missing_answer_manifest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    from opspilot.domain import chat
    from opspilot.domain.task_control import TaskControlError

    recheck = _load_module("ar04_live_retention_recheck_runner", RECHECK_DIR / "run_recheck.py")
    code = "CONTEXT_SUMMARY_FACT_RETENTION_BUDGET_EXCEEDED"

    def fail_persistence(*args, **kwargs):
        raise TaskControlError(code, f"{code}:unresolved_items:2")

    monkeypatch.setattr(chat, "complete_chat_compression_attempt", fail_persistence)
    abc = recheck.abc_runner()
    # This test isolates the answer-manifest failure branch. The recheck wrapper's
    # checkout pin intentionally targets its frozen pre-fix source and is not part
    # of the runner behavior under test.
    monkeypatch.setattr(recheck, "checkout_evidence", lambda _abc: {})
    output = tmp_path / "structured-stop"
    result = recheck.run_cases(
        abc,
        output,
        mode="MOCK",
        config=abc._mock_config(),
        api_key="offline-only-not-a-real-key",
    )

    first = result["cases"][0]
    assert result["status"] == "STOPPED"
    assert result["stop_reason"] == code
    assert result["external_provider_requests"] == 0
    assert result["summary_requests"] == 1
    assert result["answer_requests"] == 0
    assert first["status"] == "STOPPED"
    assert first["domain_stop_reason"] == code
    assert first["error"] == code
    assert first["answer_manifest_present"] is False
    assert first["answer_calls"] == 0
    assert first["recorded_compression_attempt_states"][0]["status"] == "FAILED"
    assert first["recorded_compression_attempt_states"][0]["error_class"] == code
    assert [row["status"] for row in result["cases"]] == ["STOPPED", "NOT_STARTED", "NOT_STARTED"]
