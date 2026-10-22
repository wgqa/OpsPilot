from __future__ import annotations

import hashlib
import json
import os
import secrets
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from opspilot.config import MODEL_NAME, ROOT, load_local_environment
from opspilot.domain.database import connect, reset_fixture
from opspilot.smokes.m4_01 import EVIDENCE, _write_json
from opspilot.web.app import create_app


def _counts(db: Path, task_id: str) -> dict[str, int]:
    with connect(db) as connection:
        return {
            "control_revision": int(connection.execute(
                "SELECT control_revision FROM task_controls WHERE task_id = ?", (task_id,),
            ).fetchone()[0]),
            "business_runs": int(connection.execute(
                "SELECT COUNT(*) FROM task_runs WHERE task_id = ? AND kind <> 'CHAT_READONLY'", (task_id,),
            ).fetchone()[0]),
            "critical_inputs": int(connection.execute(
                "SELECT COUNT(*) FROM messages WHERE task_id = ? AND input_kind = 'CORRECT_TASK_INPUT'", (task_id,),
            ).fetchone()[0]),
            "action_intents": int(connection.execute(
                "SELECT COUNT(*) FROM d3_action_intents WHERE task_id = ?", (task_id,),
            ).fetchone()[0]),
        }


def main() -> int:
    load_local_environment()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_id = f"{stamp}-{uuid.uuid4().hex[:8]}"
    output = EVIDENCE / "runs" / f"intents-{run_id}"
    output.mkdir(parents=True, exist_ok=False)
    work = ROOT / ".runtime" / f"m4-01-intents-{run_id}"
    work.mkdir(parents=True, exist_ok=False)
    db = work / "domain.sqlite3"
    reset_fixture(db, "S1_POS")
    gold_bytes = (EVIDENCE / "GOLD.json").read_bytes()
    gold = json.loads(gold_bytes)
    origin = "http://testserver"
    password = secrets.token_urlsafe(24)
    app = create_app(db_path=db, start_worker=False, credentials={"support-a": password}, expected_origin=origin)
    cases: list[dict[str, Any]] = []
    with TestClient(app, raise_server_exceptions=False) as client:
        login = client.post("/api/auth/login", headers={"Origin": origin}, json={"actor_id": "support-a", "password": password})
        login.raise_for_status()
        headers = {"Origin": origin, "X-CSRF-Token": login.json()["csrf_token"]}
        for item in gold["cases"]:
            session = client.post("/api/sessions", headers=headers)
            session.raise_for_status()
            session_id = session.json()["session_id"]
            created = client.post(
                f"/api/sessions/{session_id}/tasks", headers={**headers, "Idempotency-Key": f"{run_id}-{item['id']}-create"},
                json={"initial_message": "订单接口目前返回 401，请调查当前绑定资源。"},
            )
            created.raise_for_status()
            task_id = created.json()["task_id"]
            source = client.post(
                f"/api/sessions/{session_id}/messages", headers={**headers, "Idempotency-Key": f"{run_id}-{item['id']}-chat"},
                json={"task_id": task_id, "input_kind": "CHAT_READONLY", "body": item["message"]},
            )
            source.raise_for_status()
            message_id = source.json()["message_id"]
            before = _counts(db, task_id)
            url = f"/api/tasks/{task_id}/investigation-updates/proposals"
            response = client.post(url, headers={**headers, "Idempotency-Key": message_id}, json={"source_message_id": message_id})
            result = response.json()
            replay = client.post(url, headers={**headers, "Idempotency-Key": message_id}, json={"source_message_id": message_id})
            after = _counts(db, task_id)
            matched = (
                response.status_code == 200 and result.get("intent") == item["gold_intent"]
                and (result.get("proposal") is not None) == item["proposal"]
                and before == after and replay.status_code == 200
                and replay.json().get("assessment_id") == result.get("assessment_id")
            )
            record = {
                "id": item["id"], "message": item["message"], "gold_intent": item["gold_intent"],
                "actual_intent": result.get("intent"), "status": "PASS" if matched else "FAIL",
                "http_status": response.status_code, "session_id": session_id, "task_id": task_id,
                "source_message_id": message_id, "before": before, "after": after,
                "assessment": result, "replay_status": replay.status_code,
                "replayed_assessment_id": replay.json().get("assessment_id"),
            }
            cases.append(record)
            _write_json(output / f"{item['id']}.json", record)
            print(json.dumps({key: record[key] for key in ("id", "gold_intent", "actual_intent", "status", "http_status")}, ensure_ascii=False), flush=True)
    result = {
        "run_id": run_id, "kind": "REAL_PROVIDER_HTTP_INTENT_MATRIX_NO_WORKER",
        "model_id": os.environ.get(MODEL_NAME), "gold_release": gold["release_id"],
        "gold_sha256": hashlib.sha256(gold_bytes).hexdigest(),
        "denominator": len(cases), "passed": sum(item["status"] == "PASS" for item in cases),
        "failed": sum(item["status"] != "PASS" for item in cases), "cases": cases,
        "provider_tokens": sum((item["assessment"].get("model_attempt") or {}).get("total_tokens") or 0 for item in cases),
        "runtime_directory": str(work.relative_to(ROOT)), "worker_started": False,
    }
    result["status"] = "PASS" if result["failed"] == 0 else "FAIL"
    _write_json(output / "RESULTS.json", result)
    print(json.dumps({"evidence_dir": str(output.relative_to(ROOT)), "passed": result["passed"], "failed": result["failed"]}, ensure_ascii=False))
    return 0 if result["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
