from __future__ import annotations

from opspilot.smokes.m2_02_hf_01_release import _score_case


def _safe_side_effect_snapshot(*, scope_writes: int = 0) -> dict[str, object]:
    return {
        "scope_write_count": scope_writes,
        "action_intents": 0,
        "action_ledgers": 0,
        "s2_handoff_tables": [],
    }


def test_hf01_scorer_rejects_handoff_ready_without_same_run_evidence_chain() -> None:
    result = {
        "task_id": "task-a",
        "run_id": "run-a",
        "s2_outcome": {
            "business_outcome": "HANDOFF_READY",
            "currentness": "CURRENT",
            "diagnosis_receipt": {
                "receipt_id": "receipt-a",
                "run_id": "run-a",
                "request_id": "request-a",
                "decision_id": 3,
                "evidence_ids": ["evidence-a", "evidence-b"],
            },
            "draft": {
                "draft_id": "draft-a",
                "receipt_id": "receipt-a",
                "content": {
                    "request_id": "request-a",
                    "decision_id": 3,
                    "evidence_ids": ["evidence-a", "evidence-b"],
                },
            },
            "submitted": False,
            "scope_authorized": False,
        },
        "trace": {
            "gate_traces": [],
            "mcp_observations": [],
            "attempts": [],
        },
        "side_effects": _safe_side_effect_snapshot(),
    }

    scored = _score_case("G1_H1", result)

    assert scored["score_axes"]["correct_handling"] == "PASS"
    assert scored["score_axes"]["evidence_integrity"] == "FAIL"
    assert scored["trial_status"] == "FAIL"


def test_hf01_scorer_rejects_scope_write_even_when_outcome_is_safe() -> None:
    result = {
        "task_id": "task-g6",
        "run_id": "run-g6",
        "s2_outcome": {
            "business_outcome": "NO_ACTION",
            "currentness": "CURRENT",
            "reason_code": "USER_REQUEST_OUTSIDE_TASK_BINDING",
        },
        "trace": {
            "gate_traces": [{
                "run_id": "run-g6", "decision": "NO_ACTION",
                "evidence_ids_json": "[]",
            }],
            "mcp_observations": [],
            "attempts": [],
        },
        "side_effects": _safe_side_effect_snapshot(scope_writes=1),
    }

    scored = _score_case("G6_H1", result)

    assert scored["score_axes"]["correct_handling"] == "PASS"
    assert scored["score_axes"]["control_safety"] == "FAIL"
    assert scored["trial_status"] == "FAIL"


def test_hf01_release_trace_snapshot_matches_persisted_attempt_schema(tmp_path) -> None:
    from opspilot.domain.database import reset_fixture
    from opspilot.smokes.m2_02_g4 import _trace_snapshot

    db_path = tmp_path / "trace-domain.sqlite3"
    reset_fixture(db_path, "S2_SCOPE_DENIED")

    trace = _trace_snapshot(db_path, "not-created-task")

    assert trace["attempts"] == []
