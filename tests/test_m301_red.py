from __future__ import annotations

import sys
from pathlib import Path

from fastapi.testclient import TestClient

from opspilot.domain.episodic_memory import create_memory_candidate
from opspilot.investigator import _prompt_messages


TESTS_DIR = Path(__file__).resolve().parent
if str(TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(TESTS_DIR))

from test_d5_context import _seed_verified_source  # noqa: E402
from test_m2_02_s2_diagnosis import _capture_s2_probe  # noqa: E402


def test_m301_red_s1_memory_is_derived_from_case_not_fixed_template(demo_db: Path) -> None:
    source_task_id = _seed_verified_source(demo_db, "unused")

    candidate = create_memory_candidate(demo_db, source_task_id, "support-a")

    assert candidate.get("schema_version") == "opspilot-case-memory-v1"
    assert candidate.get("source_outcome") == "REPAIRED_VERIFIED"
    assert candidate.get("experience", {}).get("case_specific_facts")
    assert candidate["summary"] != (
        "历史案例提示：先核对主体状态、认证策略、集成配置和真实业务 Probe。"
        "只用当前任务的 MCP Evidence 交给确定性门禁判断；历史经验不代表当前事实、根因或授权。"
    )


def test_m301_red_s2_diagnosis_receipt_can_create_diagnosed_experience(
    demo_db: Path, live_api: str,
) -> None:
    source_task_id, run_id, _probe, evidence_ids = _capture_s2_probe(
        demo_db, live_api, "S2_SCOPE_DENIED", "m301-red-s2-source",
    )
    from opspilot.domain.s2_diagnosis import create_diagnosis_receipt

    receipt = create_diagnosis_receipt(
        demo_db, task_id=source_task_id, run_id=run_id, evidence_ids=evidence_ids,
    )
    assert receipt["outcome"] == "DIAGNOSED"

    candidate = create_memory_candidate(demo_db, source_task_id, "support-a")

    assert candidate.get("source_outcome") == "DIAGNOSED"
    assert candidate.get("source_refs")
    assert candidate.get("source_report_ref") is None
    assert candidate.get("source_verification_id") is None


def test_m301_red_s2_investigator_context_can_select_active_case_memory(
    demo_db: Path, live_api: str, monkeypatch,
) -> None:
    task_id, run_id, _probe, _evidence_ids = _capture_s2_probe(
        demo_db, live_api, "S2_SCOPE_DENIED", "m301-context-s2",
    )
    source_task_id = "source-task-a"
    memory = {
        "memory_id": "m301-case-memory-s2",
        "version": 2,
        "digest": "f" * 64,
        "content_digest": "f" * 64,
        "schema_version": "opspilot-case-memory-v1",
        "summary": "历史 S2 案例：应只使用本次 Run 的 Probe request_id 查询当前 Authz facts。",
        "source_task_id": source_task_id,
        "source_outcome": "SCOPE_ESCALATED",
        "source_refs": [{"kind": "HANDOFF_RECEIPT", "id": "source-receipt"}],
    }
    import opspilot.investigator as investigator

    def applicable(_path, candidate_task_id, problem_type, **_kwargs):
        assert candidate_task_id == task_id
        assert problem_type == "auth_403_scope"
        return [memory], []

    monkeypatch.setattr(investigator, "select_applicable_memories", applicable)
    metadata: dict[str, object] = {}
    messages = _prompt_messages(
        demo_db, task_id, {"evidence_ids": []}, context_metadata=metadata,
        run_id=run_id, s2_mode=True,
    )

    assert "m301-case-memory-s2" in "\n".join(str(item.content) for item in messages)
    assert metadata["selected_memories"][0]["memory_id"] == "m301-case-memory-s2"


def test_m301_red_web_exposes_candidate_creation_for_task_owner(demo_db: Path) -> None:
    source_task_id = _seed_verified_source(demo_db, "unused")
    from opspilot.web.app import create_app

    passwords = {
        "support-a": "support-test-password",
        "approver-a": "approver-test-password",
        "support-b": "support-b-test-password",
        "approver-b": "approver-b-test-password",
    }
    app = create_app(
        db_path=demo_db, start_worker=False, credentials=passwords,
        expected_origin="http://testserver",
    )
    with TestClient(app, raise_server_exceptions=False) as client:
        login = client.post(
            "/api/auth/login", headers={"Origin": "http://testserver"},
            json={"actor_id": "support-a", "password": passwords["support-a"]},
        )
        assert login.status_code == 200
        response = client.post(
            f"/api/tasks/{source_task_id}/memories/candidates",
            headers={
                "Origin": "http://testserver",
                "X-CSRF-Token": login.json()["csrf_token"],
                "Idempotency-Key": "m301-red-candidate-01",
            },
            json={},
        )
        assert response.status_code == 201, response.text
