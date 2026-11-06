from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from opspilot.domain.assistant import read_session_professional_outcomes
from opspilot.domain.database import connect, reset_fixture
from opspilot.web.app import create_app
from opspilot.web.worker import SingleInstanceWorker, _dispatch_run
from test_product_01_final_bridge_01 import _BridgeAssistantModel
from test_ar05_s2_assistant_handoff_01 import QUESTION, _S2InvestigatorFixture
from test_m1_web_api import ORIGIN, PASSWORDS, _login, _session

ROOT = Path(__file__).resolve().parents[1]


def _dispatch(db_path: Path, checkpoint_path: Path, run_id: str, assistant_factory=None) -> None:
    from opspilot.domain.task_control import next_worker_run

    worker = SingleInstanceWorker(db_path)
    worker.acquire()
    worker.register()
    try:
        selected = next_worker_run(db_path)
        assert selected is not None and str(selected["run_id"]) == run_id
        asyncio.run(_dispatch_run(
            db_path, checkpoint_path, worker.owner_id, "executor-a", selected,
            worker_epoch=worker.epoch, assistant_model_factory=assistant_factory or (lambda: None),
        ))
    finally:
        worker.release()


def _create_s2_result(client: TestClient, db_path: Path, checkpoint: Path, headers: dict[str, str], session_id: str, key: str) -> str:
    response = client.post(
        f"/api/sessions/{session_id}/tasks",
        headers={**headers, "Idempotency-Key": key},
        json={"initial_message": QUESTION},
    )
    assert response.status_code == 202, response.text
    task = response.json()
    _dispatch(db_path, checkpoint, str(task["run_id"]))
    return str(task["task_id"])


def test_professional_outcome_projection_reports_exact_scoped_omissions(
    demo_db: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    import opspilot.investigator as investigator

    reset_fixture(demo_db, "S2_SCOPE_DENIED")
    monkeypatch.setattr(investigator, "ChatOpenAI", _S2InvestigatorFixture)
    monkeypatch.setenv("OPSPILOT_MODEL_API_KEY", "offline-placeholder")
    monkeypatch.setenv("OPSPILOT_MODEL_NAME", "offline-deterministic-model")
    checkpoint = tmp_path / "closeout-checkpoint.sqlite3"
    app = create_app(
        db_path=demo_db, checkpoint_db_path=checkpoint, start_worker=False,
        credentials=PASSWORDS, expected_origin=ORIGIN,
        assistant_model_factory=lambda: _BridgeAssistantModel(mode="proposal"),
    )

    with TestClient(app, raise_server_exceptions=False) as client:
        headers = _login(client)[1]
        session_id = _session(client, headers)
        chat = client.post(
            f"/api/sessions/{session_id}/assistant/messages",
            headers={**headers, "Idempotency-Key": "closeout-result-reader"},
            json={"body": "请说明本会话已经完成的专业调查。", "task_id": None},
        )
        assert chat.status_code == 202, chat.text
        reader_run_id = str(chat.json()["run_id"])
        _dispatch(demo_db, checkpoint, reader_run_id, lambda: _BridgeAssistantModel(mode="proposal"))

        projected = read_session_professional_outcomes(demo_db, reader_run_id)
        assert projected["items"] == []
        assert projected["omitted_count"] == 0

        task_ids: list[str] = []
        projections = {}
        for index in range(1, 7):
            task_id = _create_s2_result(
                client, demo_db, checkpoint, headers, session_id, f"closeout-s2-{index}",
            )
            task_ids.append(task_id)
            if index == 6:
                # Add a real, valid but older source. It changes the omitted total
                # without changing the four most recently returned result bodies.
                with connect(demo_db) as db:
                    db.execute(
                        "UPDATE session_task_links SET linked_at='2000-01-01T00:00:00+00:00' WHERE session_id=? AND task_id=?",
                        (session_id, task_id),
                    )
            projected = read_session_professional_outcomes(demo_db, reader_run_id)
            assert len(projected["items"]) == min(index, 4)
            assert projected["omitted_count"] == max(0, index - 4)
            assert all(item["professional_type"] == "S2_SCOPE_HANDOFF" for item in projected["items"])
            projections[index] = projected

        assert projections[4]["omitted_count"] == 0
        assert projections[5]["omitted_count"] == 1
        assert projections[6]["omitted_count"] == 2
        assert projections[5]["snapshot_digest"] != projections[6]["snapshot_digest"]
        assert [item["task_id"] for item in projections[6]["items"]] == [
            item["task_id"] for item in read_session_professional_outcomes(demo_db, reader_run_id)["items"]
        ]

        # A terminal Task is excluded from both returned results and the count.
        with connect(demo_db) as db:
            db.execute(
                "UPDATE task_controls SET terminal_state='ABORTED' WHERE task_id=?",
                (task_ids[0],),
            )
        terminal = read_session_professional_outcomes(demo_db, reader_run_id)
        assert len(terminal["items"]) == 4
        assert terminal["omitted_count"] == 1

        # A valid result in another Session does not affect this Session's count.
        other_session = _session(client, headers)
        _create_s2_result(client, demo_db, checkpoint, headers, other_session, "closeout-other-session")
        after_unrelated = read_session_professional_outcomes(demo_db, reader_run_id)
        assert len(after_unrelated["items"]) == len(terminal["items"])
        assert after_unrelated["omitted_count"] == terminal["omitted_count"]

        # A same-tenant Task whose trusted owner differs is not counted even if a
        # deliberately inconsistent fixture link places it in this Session.
        with connect(demo_db) as db:
            db.execute(
                "INSERT INTO trusted_operators (actor_id, tenant_id, role) VALUES ('support-c', 'tenant-a', 'SUPPORT')",
            )
        wrong_owner_task = _create_s2_result(
            client, demo_db, checkpoint, headers, session_id, "closeout-wrong-owner",
        )
        with connect(demo_db) as db:
            db.execute("UPDATE task_bindings SET actor_id='support-c' WHERE task_id=?", (wrong_owner_task,))
        after_wrong_owner = read_session_professional_outcomes(demo_db, reader_run_id)
        assert [item["task_id"] for item in after_wrong_owner["items"]] == [
            item["task_id"] for item in terminal["items"]
        ]
        assert after_wrong_owner["omitted_count"] == terminal["omitted_count"]

        # A bound Task with no plan or diagnosis is not a readable professional result.
        ordinary = client.post(
            f"/api/sessions/{session_id}/tasks",
            headers={**headers, "Idempotency-Key": "closeout-no-result"},
            json={"initial_message": "只创建调查，不运行它。"},
        )
        assert ordinary.status_code == 202, ordinary.text
        without_result = read_session_professional_outcomes(demo_db, reader_run_id)
        assert len(without_result["items"]) == 4
        assert without_result["omitted_count"] == 1


def test_normal_cli_reset_entry_initializes_an_isolated_demo_database(tmp_path: Path) -> None:
    database = tmp_path / "fresh-demo.sqlite3"
    environment = {
        key: value for key, value in os.environ.items()
        if key not in {
            "OPSPILOT_MODEL_API_KEY", "OPENAI_API_KEY",
            "OPSPILOT_ASSISTANT_PROVIDER_ENABLED",
        }
    }
    result = subprocess.run(
        [sys.executable, "-m", "opspilot.cli", "reset", "--scenario", "S1_POS", "--db", str(database)],
        cwd=ROOT, env=environment, text=True, capture_output=True, timeout=15,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["event"] == "fixture_reset"
    assert database.is_file()
    with connect(database) as db:
        row = db.execute(
            "SELECT credential_ref, config_version FROM integrations WHERE tenant_id='tenant-a' AND integration_id='integration-a'"
        ).fetchone()
    assert row is not None and row["credential_ref"] == "cred-v1"
