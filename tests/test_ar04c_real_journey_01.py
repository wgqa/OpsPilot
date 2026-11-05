"""AR-04C offline preparation through explicit HTTPX MockTransport only."""
from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
import time
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

EXPERIMENT_ID = "AR-04C-REAL-JOURNEY-01"
J2 = (
    "我们正在升级回调协议。之前类似问题的经验可能有帮助，但我不确定这个订单到底处理完成没有。"
    "请你根据当前情况查一下：HTTP 202 代表什么、接收方处理到了哪一步、是否需要处理，以及能否帮我整理一段给同事的说明？"
)
J4 = "那我现在需要立即处理吗？你刚刚引用的协议和经验，哪些是可以相信的，哪些还需要重新验证？"
ORIGIN = "http://127.0.0.1:8000"
PASSWORDS = {
    "support-a": "support-a-password",
    "approver-a": "approver-a-password",
    "support-b": "support-b-password",
    "approver-b": "approver-b-password",
}
PROTECTED = (
    "s3_orders", "s3_deliveries", "s3_receivers", "s3_diagnoses",
    "d3_approvals", "d3_action_intents", "d3_action_ledgers",
    "s3_handoff_receipts",
)


def _login(client: TestClient, actor_id: str = "support-a") -> dict[str, str]:
    response = client.post(
        "/api/auth/login", headers={"Origin": ORIGIN},
        json={"actor_id": actor_id, "password": PASSWORDS[actor_id]},
    )
    assert response.status_code == 200, response.text
    return {"Origin": ORIGIN, "X-CSRF-Token": response.json()["csrf_token"]}


def _wait_for_run(client: TestClient, run_id: str) -> dict:
    deadline = time.monotonic() + 25
    while time.monotonic() < deadline:
        response = client.get(f"/api/runs/{run_id}")
        assert response.status_code == 200, response.text
        run = response.json()
        if run["status"] in {"SUCCEEDED", "FAILED", "BLOCKED"}:
            return run
        time.sleep(0.05)
    raise AssertionError(f"Run did not finish: {run_id}")


def _protected_counts(db_path: Path) -> dict[str, int]:
    from opspilot.domain.database import connect
    with connect(db_path) as connection:
        return {
            table: int(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
            for table in PROTECTED
        }


def _prepare_memory_seed(seed_db: Path, checkpoint: Path, off_db: Path, on_db: Path) -> dict:
    from opspilot.domain.database import reset_fixture
    from opspilot.domain.s3 import persist_s3_diagnosis, prepare_s3_fixture
    from opspilot.domain.task_control import apply_pending_critical_inputs, claim_task_run, finish_task_run
    from opspilot.web.app import create_app
    from test_ar04b_memory_journey_01 import _seed_async_project_approver
    from test_m4_03_s3 import _evidence, _facts, _task

    reset_fixture(seed_db, "S1_POS")
    prepare_s3_fixture(
        seed_db, "DELIVERY_FAILED", order_id="ar04c-memory-source",
        attempt_count=3, retry_state="EXHAUSTED",
    )
    fixture = prepare_s3_fixture(
        seed_db, "DELIVERED_PENDING", order_id="ar04c-order", contract_version=2,
    )
    assert fixture["receiver_http_status"] == 202
    _seed_async_project_approver(seed_db)
    identity, source = _task(
        seed_db, "ar04c-memory-source",
        text="Prior callback delivery exhausted retries; record only a verified investigation method.",
    )
    claim_task_run(seed_db, identity, str(source["run_id"]))
    apply_pending_critical_inputs(seed_db, identity, str(source["run_id"]))
    order, delivery, receiver = _facts(seed_db, source)
    evidence_ids = [
        _evidence(seed_db, source, "get_order_status", order),
        _evidence(seed_db, source, "get_callback_delivery", delivery),
        _evidence(seed_db, source, "get_receiver_processing", receiver),
    ]
    diagnosis = persist_s3_diagnosis(
        seed_db, str(source["task_id"]), str(source["run_id"]), evidence_ids,
    )
    assert diagnosis["outcome"] == "CALLBACK_DELIVERY_FAILED"
    finish_task_run(seed_db, identity, str(source["run_id"]), "SUCCEEDED")

    # Memory creation and approval use the product APIs; source evidence above
    # is test fixture setup through the existing Domain helpers.
    app = create_app(
        db_path=seed_db, checkpoint_db_path=checkpoint, start_worker=False,
        credentials=PASSWORDS, expected_origin=ORIGIN,
        assistant_experiment_id=EXPERIMENT_ID,
    )
    with TestClient(app) as client:
        support = _login(client)
        candidate = client.post(
            f"/api/tasks/{source['task_id']}/memories/candidates",
            headers={**support, "Idempotency-Key": "ar04c-memory-candidate"}, json={},
        )
        assert candidate.status_code == 201, candidate.text
        candidate_item = candidate.json()
        approver = _login(client, "approver-a")
        confirmed = client.post(
            f"/api/memories/{candidate_item['memory_id']}/confirm",
            headers={**approver, "Idempotency-Key": "ar04c-memory-confirm"}, json={},
        )
        assert confirmed.status_code == 200, confirmed.text
        assert confirmed.json()["state"] == "ACTIVE"
        memory = {
            "memory_id": str(candidate_item["memory_id"]),
            "version": int(confirmed.json()["version"]),
            "content_digest": str(confirmed.json()["content_digest"]),
            "candidate_created_via_api": True,
            "confirmed_via_api": True,
            "confirmed_by_actor_id": "approver-a",
            "confirmed_state": str(confirmed.json()["state"]),
        }

    # Copy one quiescent, confirmed-memory baseline so OFF/ON have identical
    # fixture facts, IDs, grants and Memory version/digest.
    with sqlite3.connect(seed_db) as source_connection:
        for target in (off_db, on_db):
            with sqlite3.connect(target) as target_connection:
                source_connection.backup(target_connection)
    return {
        "source_task_id": str(source["task_id"]),
        "source_run_id": str(source["run_id"]),
        "source_evidence_ids": evidence_ids,
        "source_diagnosis_outcome": str(diagnosis["outcome"]),
        "memory": memory,
        "target_order_id": "ar04c-order",
        "target_event_id": str(fixture["transport_trace"][0]["response"]["event_id"]),
        "target_delivery_http_status": 202,
        "target_receiver_status": "QUEUED",
    }


def _tool_call(name: str, call_id: str, arguments: dict) -> dict:
    return {
        "id": call_id,
        "type": "function",
        "function": {"name": name, "arguments": json.dumps(arguments, ensure_ascii=False)},
    }


class _MockProvider:
    """Deterministic model stand-in; its actions do not prove LLM autonomy."""

    def __init__(self, db_path: Path, condition: str):
        self.db_path = db_path
        self.condition = condition
        self.records: list[dict] = []
        self.sequence = 0

    def _response_body(self, body: dict) -> dict:
        self.sequence += 1
        messages = body.get("messages", [])
        def message_value(item: dict, key: str):
            data = item.get("data", {})
            data = data if isinstance(data, dict) else {}
            return item.get(key, data.get(key))

        def message_role(item: dict) -> str:
            data = item.get("data", {})
            data = data if isinstance(data, dict) else {}
            return str(item.get("role") or item.get("type") or data.get("role") or data.get("type") or "")

        def message_content(item: dict) -> str:
            data = item.get("data", {})
            data = data if isinstance(data, dict) else {}
            value = item.get("content", data.get("content", ""))
            return str(value or "")

        last_user = max(
            (index for index, item in enumerate(messages) if message_role(item) == "user"),
            default=-1,
        )
        current_messages = messages[last_user + 1:]
        call_names: dict[str, str] = {}
        for item in messages:
            for tool_call in item.get("tool_calls", []) if isinstance(item, dict) else []:
                function = tool_call.get("function", {})
                if isinstance(function, dict):
                    call_names[str(tool_call.get("id", ""))] = str(function.get("name", ""))

        def decoded_tool_results(source: list[dict]) -> list[tuple[str, dict]]:
            results = []
            for item in source:
                if message_role(item) != "tool":
                    continue
                name = str(
                    message_value(item, "name")
                    or call_names.get(str(message_value(item, "tool_call_id") or ""), "")
                )
                try:
                    payload = json.loads(message_content(item))
                except (TypeError, json.JSONDecodeError):
                    continue
                if name and isinstance(payload, dict):
                    results.append((name, payload))
            return results

        current_results = decoded_tool_results(current_messages)
        all_results = decoded_tool_results(messages)
        tool_names = {name for name, _ in current_results}
        followup = last_user >= 0 and J4 in json.dumps(messages[last_user], ensure_ascii=False)
        memory_enabled = any(
            "CONFIRMED PROJECT MEMORY GUIDANCE" in message_content(item)
            for item in messages if message_role(item) == "system"
        )
        call = None
        answer = None
        if followup and not current_results:
            call = _tool_call(
                "get_receiver_processing", f"ar04c-{self.condition}-{self.sequence}",
                {"reason": "Recheck the bound Event's current Receiver state before advising."},
            )
        elif not followup and not current_results:
            call = _tool_call(
                "search_project_knowledge", f"ar04c-{self.condition}-{self.sequence}",
                {"query": "HTTP 202 callback receiver processing"},
            )
        elif "search_project_knowledge" in tool_names and "get_callback_delivery" not in tool_names:
            call = _tool_call(
                "get_callback_delivery", f"ar04c-{self.condition}-{self.sequence}",
                {"reason": "Check the current bound Event transport acknowledgement."},
            )
        elif "get_callback_delivery" in tool_names and "get_receiver_processing" not in tool_names:
            call = _tool_call(
                "get_receiver_processing", f"ar04c-{self.condition}-{self.sequence}",
                {"reason": "Check processing status for the same current Event."},
            )
        elif "get_receiver_processing" in tool_names:
            if followup:
                receiver = next(
                    (payload.get("facts", {}) for name, payload in reversed(current_results)
                     if name == "get_receiver_processing"),
                    {},
                )
                status = str(receiver.get("status", "UNKNOWN"))
                event_id = str(receiver.get("event_id", "unknown"))
                memory_note = (
                    "历史 Memory 仅作为方法提示，不能当作当前事实。"
                    if memory_enabled else "本轮没有向模型提供历史 Memory，不能声称引用了旧经验。"
                )
                answer = (
                    f"本次同 Event={event_id} 的最新 Receiver 观察为 {status}；"
                    f"HTTP 202/ACKNOWLEDGED 只证明传输受理。{memory_note}"
                    "协议资料版本不能证明线上部署版本。说明仍是未提交草稿，没有执行业务写入。"
                )
            else:
                knowledge = next(
                    (payload for name, payload in all_results if name == "search_project_knowledge"),
                    {},
                )
                document = next(iter(knowledge.get("documents", [])), {})
                delivery = next(
                    (payload.get("facts", {}) for name, payload in reversed(current_results)
                     if name == "get_callback_delivery"),
                    {},
                )
                receiver = next(
                    (payload.get("facts", {}) for name, payload in reversed(current_results)
                     if name == "get_receiver_processing"),
                    {},
                )
                answer = (
                    f"协议资料 {document.get('document_id', '未取得')} v{document.get('version', '未知')}"
                    f"（Digest {document.get('digest', '未知')}）说明 HTTP 202 是受理，不代表处理完成。"
                    f"当前同 Event={receiver.get('event_id', 'unknown')} 的 Delivery="
                    f"{delivery.get('status', 'UNKNOWN')} / HTTP {delivery.get('receiver_http_status', 'unknown')}，"
                    f"Receiver={receiver.get('status', 'UNKNOWN')}；不能据此确认下游已处理。"
                    "按 SLA 观察；说明是未提交草稿，没有执行业务写入。"
                )
        message = (
            {"role": "assistant", "content": None, "tool_calls": [call]}
            if call is not None else
            {"role": "assistant", "content": answer or "No further action."}
        )
        return {
            "id": f"ar04c-mock-completion-{self.condition}-{self.sequence}",
            "object": "chat.completion",
            "created": 1793836800 + self.sequence,
            "model": "deepseek-flash",
            "choices": [{
                "index": 0, "message": message,
                "finish_reason": "tool_calls" if call is not None else "stop",
            }],
            "usage": {"prompt_tokens": 120, "completion_tokens": 36, "total_tokens": 156},
        }

    async def handle(self, request: httpx.Request) -> httpx.Response:
        body = json.loads((await request.aread()).decode("utf-8"))
        from opspilot.assistant import _ar04c_claim_state_path
        state = json.loads(_ar04c_claim_state_path().read_text(encoding="utf-8"))
        assert state["status"] == "CONSUMED", "claim must be durably consumed before HTTPX transport"
        assert self.condition in state["database_ids"]
        from opspilot.domain.database import connect
        with connect(self.db_path) as connection:
            reserved = connection.execute(
            """SELECT dispatch_id,run_id,reserved_usd_micro,status FROM ar02_live_dispatches
                   WHERE experiment_id=? AND kind='MODEL' AND status='RESERVED'
                   ORDER BY created_at DESC""",
                (EXPERIMENT_ID,),
            ).fetchall()
            request_row = connection.execute(
                "SELECT request_json FROM assistant_calls WHERE run_id=? AND kind='MODEL' "
                "ORDER BY created_at DESC LIMIT 1",
                (str(reserved[0]["run_id"]),),
            ).fetchone() if reserved else None
            budget = connection.execute(
                "SELECT status,provider_limit,budget_usd_micro "
                "FROM ar02_live_experiment_budgets WHERE experiment_id=?",
                (EXPERIMENT_ID,),
            ).fetchone()
        assert len(reserved) == 1, "Provider reservation must precede MockTransport"
        assert int(reserved[0]["reserved_usd_micro"]) == 645_600
        assert request_row is not None
        recorded_request = json.loads(str(request_row["request_json"]))
        context_budget = recorded_request.get("context_budget", {})
        assert budget and budget["status"] == "OPEN" and int(budget["provider_limit"]) == 8
        response_body = self._response_body(body)
        record = {
            "url": str(request.url), "method": request.method, "body": body,
            "dispatch_id": str(reserved[0]["dispatch_id"]),
            "reservation_before_transport_usd_micro": int(reserved[0]["reserved_usd_micro"]),
            "estimated_input_tokens": context_budget.get("estimated_input_tokens"),
            "input_budget_tokens": context_budget.get("input_budget_tokens"),
            "completion_id": response_body["id"], "usage": response_body["usage"],
        }
        self.records.append(record)
        return httpx.Response(
            200, json=response_body,
            headers={"x-request-id": response_body["id"]}, request=request,
        )

    def sync_handle(self, request: httpx.Request) -> httpx.Response:
        raise AssertionError("The formal assistant must use its async Provider client")


def _run_condition(db_path: Path, checkpoint: Path, condition: str, memory: dict, monkeypatch) -> dict:
    from opspilot.assistant import create_assistant_model
    from opspilot.domain.assistant_experiment import read_budget
    from opspilot.domain.d2 import configure_ar04c_memory_budget
    from opspilot.domain.database import connect
    from opspilot.web.app import create_app
    from opspilot.web import worker as worker_module

    # A terminal Domain Run may be committed before the Assistant's MCP client
    # context has closed and before the Worker dispatch has returned. Observe
    # those existing lifecycle boundaries so TestClient is not closed while
    # the test's own request is still unwinding.
    last_expected_run_id: list[str | None] = [None]
    completed_run_ids: set[str] = set()
    completion_lock = threading.Lock()
    dispatch_finished = threading.Event()
    worker_idle = threading.Event()
    original_dispatch_run = worker_module._dispatch_run
    original_next_worker_run = worker_module.next_worker_run

    async def tracked_dispatch_run(*args, **kwargs):
        run = kwargs.get("run") if "run" in kwargs else args[4]
        run_id = str(run["run_id"])
        try:
            return await original_dispatch_run(*args, **kwargs)
        finally:
            with completion_lock:
                completed_run_ids.add(run_id)
                if run_id == last_expected_run_id[0]:
                    dispatch_finished.set()

    def tracked_next_worker_run(*args, **kwargs):
        run = original_next_worker_run(*args, **kwargs)
        if run is None:
            with completion_lock:
                if (
                    last_expected_run_id[0] is not None
                    and last_expected_run_id[0] in completed_run_ids
                ):
                    worker_idle.set()
        return run

    monkeypatch.setattr(worker_module, "_dispatch_run", tracked_dispatch_run)
    monkeypatch.setattr(worker_module, "next_worker_run", tracked_next_worker_run)

    monkeypatch.setenv("OPSPILOT_ASSISTANT_EXPERIMENT_ID", EXPERIMENT_ID)
    monkeypatch.setenv("OPSPILOT_ASSISTANT_PROVIDER_ENABLED", "1")
    monkeypatch.setenv("OPSPILOT_MODEL_API_KEY", "offline-only-placeholder")
    monkeypatch.setenv("OPSPILOT_MODEL_NAME", "deepseek-flash")
    monkeypatch.setenv("OPSPILOT_MODEL_BASE_URL", "https://api.deepseek.com")
    monkeypatch.setenv("OPSPILOT_AR04C_MEMORY_MODE", condition)
    from opspilot.assistant import _ar04c_one_shot_authorized
    assert _ar04c_one_shot_authorized(EXPERIMENT_ID) is True
    assert read_budget(db_path, EXPERIMENT_ID)["provider_used"] == 0

    # The trusted order API creates one pending formal Run while no Worker is
    # running. Configure the scoped budget before the official Worker resumes it.
    intake_app = create_app(
        db_path=db_path, checkpoint_db_path=checkpoint, start_worker=False,
        credentials=PASSWORDS, expected_origin=ORIGIN, assistant_experiment_id=EXPERIMENT_ID,
    )
    with TestClient(intake_app) as client:
        support = _login(client)
        session = client.post("/api/sessions", headers=support)
        assert session.status_code == 201, session.text
        session_id = str(session.json()["session_id"])
        accepted = client.post(
            f"/api/sessions/{session_id}/assistant/order",
            headers={**support, "Idempotency-Key": f"ar04c-{condition.lower()}-j2"},
            json={"order_id": "ar04c-order", "initial_message": J2},
        )
        assert accepted.status_code == 202, accepted.text
        j2 = accepted.json()
        assert configure_ar04c_memory_budget(db_path, str(j2["task_id"]), EXPERIMENT_ID) == {
            "MODEL": 8, "MCP": None,
        }

    provider = _MockProvider(db_path, condition)
    def model_factory():
        return create_assistant_model(
            transport_async=httpx.MockTransport(provider.handle),
            transport_sync=httpx.MockTransport(provider.sync_handle),
        )

    worker_app = create_app(
        db_path=db_path, checkpoint_db_path=checkpoint, start_worker=True,
        credentials=PASSWORDS, expected_origin=ORIGIN, assistant_experiment_id=EXPERIMENT_ID,
        assistant_model_factory=model_factory,
    )
    with TestClient(worker_app) as client:
        _login(client)
        assert _wait_for_run(client, str(j2["run_id"]))["status"] == "SUCCEEDED"
        messages = client.get(f"/api/sessions/{session_id}/messages").json()["items"]
        j2_answer = next(item["body"] for item in messages if item["role"] == "ASSISTANT")
        assert "HTTP 202" in j2_answer and "QUEUED" in j2_answer
        assert "不能据此确认下游已处理" in j2_answer and "未提交" in j2_answer
        assert "receiver-ack-contract-v2" in j2_answer and "v2.1.0" in j2_answer
        followup = client.post(
            f"/api/sessions/{session_id}/assistant/messages",
            headers={**_login(client), "Idempotency-Key": f"ar04c-{condition.lower()}-j4"},
            json={"task_id": j2["task_id"], "body": J4},
        )
        assert followup.status_code == 202, followup.text
        j4 = followup.json()
        last_expected_run_id[0] = str(j4["run_id"])
        assert _wait_for_run(client, str(j4["run_id"]))["status"] == "SUCCEEDED"
        messages = client.get(f"/api/sessions/{session_id}/messages").json()["items"]
        answers = [item for item in messages if item["role"] == "ASSISTANT"]
        assert len(answers) == 2
        j4_answer = answers[-1]["body"]
        assert "同 Event" in j4_answer and "QUEUED" in j4_answer
        assert "不能证明线上部署版本" in j4_answer
        assert "未提交" in j4_answer
        if condition == "ON":
            assert "历史 Memory 仅作为方法提示" in j4_answer
        else:
            assert "本轮没有向模型提供历史 Memory" in j4_answer
            assert "历史 Memory 仅作为方法提示" not in j4_answer

        assert dispatch_finished.wait(30), "final Assistant dispatch did not finish before TestClient shutdown"
        assert worker_idle.wait(30), "Worker did not observe an empty queue before TestClient shutdown"

    from opspilot.domain.s3 import get_s3_binding
    with connect(db_path) as connection:
        binding = get_s3_binding(connection, str(j2["task_id"]))
        calls = [dict(row) for row in connection.execute(
            """SELECT run_id,kind,status,request_json,result_json,evidence_id,observation_id
               FROM assistant_calls WHERE run_id IN (?,?) ORDER BY created_at""",
            (str(j2["run_id"]), str(j4["run_id"])),
        )]
        manifests = {
            run_id: dict(connection.execute(
                "SELECT * FROM chat_context_manifests WHERE run_id=? ORDER BY created_at DESC LIMIT 1",
                (run_id,),
            ).fetchone())
            for run_id in (str(j2["run_id"]), str(j4["run_id"]))
        }
        attempts = [dict(row) for row in connection.execute(
            "SELECT kind,status,tool_name,run_id FROM d2_attempts WHERE task_id=? ORDER BY reserved_at",
            (str(j2["task_id"]),),
        )]
        task_budget = dict(connection.execute(
            "SELECT model_limit,mcp_limit,policy_version,deadline_ms "
            "FROM task_execution_budgets WHERE task_id=?", (str(j2["task_id"]),),
        ).fetchone())
        facts = {
            "delivery": dict(connection.execute(
                "SELECT event_id,status,receiver_http_status FROM s3_deliveries WHERE order_id='ar04c-order'"
            ).fetchone()),
            "receiver": dict(connection.execute(
                "SELECT event_id,status FROM s3_receivers WHERE order_id='ar04c-order'"
            ).fetchone()),
        }
        ledger = [dict(row) for row in connection.execute(
            "SELECT run_id,kind,status,reserved_usd_micro,settled_usd_micro,usage_json "
            "FROM ar02_live_dispatches WHERE experiment_id=? ORDER BY created_at",
            (EXPERIMENT_ID,),
        )]
    protected = _protected_counts(db_path)

    assert binding["order_id"] == "ar04c-order"
    assert facts["delivery"]["receiver_http_status"] == 202
    assert facts["delivery"]["status"] == "ACKNOWLEDGED"
    assert facts["receiver"]["status"] == "QUEUED"
    assert facts["delivery"]["event_id"] == facts["receiver"]["event_id"]
    assert task_budget["policy_version"] == "AR04C_MEMORY_ON_OFF_V1"
    assert int(task_budget["model_limit"]) == 8 and int(task_budget["mcp_limit"]) == 0
    assert int(task_budget["deadline_ms"]) == 300_000
    assert len(provider.records) == 6
    assert len([item for item in ledger if item["kind"] == "MODEL"]) == 6
    assert read_budget(db_path, EXPERIMENT_ID)["provider_used"] == 6
    assert len([item for item in attempts if item["kind"] == "MCP"]) == 4
    assert {item["tool_name"] for item in attempts if item["kind"] == "MCP"} == {
        "search_project_knowledge", "get_callback_delivery", "get_receiver_processing",
    }
    for record in provider.records:
        body = record["body"]
        assert record["url"] == "https://api.deepseek.com/chat/completions"
        assert record["method"] == "POST"
        assert body["model"] == "deepseek-flash"
        assert body["thinking"] == {"type": "disabled"}
        assert body["max_tokens"] == 2048
        assert body["tool_choice"] == "auto"
        assert body["parallel_tool_calls"] is False
        assert body.get("stream", False) is False
        assert "max_completion_tokens" not in body
        names = {item["function"]["name"] for item in body["tools"]}
        assert "load_protocol_upgrade_skill" in names
    for item in calls:
        if item["kind"] == "MODEL":
            assert int(json.loads(str(item["request_json"]))["context_budget"]["estimated_input_tokens"]) <= 12_000
    mcp = [item for item in calls if item["kind"] == "MCP"]
    result_by_name = {
        json.loads(str(item["request_json"]))["name"]: json.loads(str(item["result_json"]))
        for item in mcp
    }
    docs = result_by_name["search_project_knowledge"]["documents"]
    assert docs and any(item["document_id"] == "receiver-ack-contract-v2" for item in docs)
    delivery = result_by_name["get_callback_delivery"]["facts"]
    receiver = result_by_name["get_receiver_processing"]["facts"]
    assert delivery["status"] == "ACKNOWLEDGED" and delivery["receiver_http_status"] == 202
    assert receiver["status"] == "QUEUED" and delivery["event_id"] == receiver["event_id"]

    refs = {
        run_id: json.loads(str(row["memory_refs_json"]))
        for run_id, row in manifests.items()
    }
    if condition == "ON":
        assert all([item["memory_id"] for item in value] == [memory["memory_id"]] for value in refs.values())
        texts = [json.dumps(item["body"]["messages"], ensure_ascii=False) for item in provider.records]
        assert all(memory["memory_id"] in text for text in texts)
        assert all(memory["content_digest"] in text for text in texts)
        assert all("HISTORICAL_METHOD_HINT_ONLY" in text for text in texts)
    else:
        assert all(value == [] for value in refs.values())
        for row in manifests.values():
            excluded = json.loads(str(row["excluded_sources_json"]))
            assert any(
                item.get("source_id") == memory["memory_id"]
                and item.get("reason") == "EXPERIMENT_MEMORY_CONDITION_OFF"
                for item in excluded
            )
        texts = [json.dumps(item["body"]["messages"], ensure_ascii=False) for item in provider.records]
        assert all(memory["memory_id"] not in text for text in texts)
        assert all(memory["content_digest"] not in text for text in texts)
        assert all("HISTORICAL_METHOD_HINT_ONLY" not in text for text in texts)
    assert protected["d3_approvals"] == 0
    assert protected["d3_action_intents"] == protected["d3_action_ledgers"] == 0
    assert protected["s3_handoff_receipts"] == 0
    assert protected["s3_diagnoses"] == 1
    return {
        "condition": condition, "task_id": str(j2["task_id"]), "session_id": session_id,
        "j2_message_id": str(j2["message_id"]), "j2_run_id": str(j2["run_id"]),
        "j4_message_id": str(j4["message_id"]), "j4_run_id": str(j4["run_id"]),
        "j2_answer": j2_answer, "j4_answer": j4_answer,
        "memory_refs_j2": refs[str(j2["run_id"])], "memory_refs_j4": refs[str(j4["run_id"])],
        "provider_http_mock_requests": provider.records, "provider_ledger": ledger,
        "mcp_calls": [
            {"run_id": item["run_id"], "request": json.loads(str(item["request_json"])),
             "result": json.loads(str(item["result_json"])), "evidence_id": item["evidence_id"],
             "observation_id": item["observation_id"]}
            for item in mcp
        ],
        "task_budget": task_budget, "protected_table_counts": protected,
    }


def test_ar04c_campaign_caps_are_symmetric_and_legacy_ledger_is_unchanged(tmp_path: Path):
    from opspilot.domain.assistant_experiment import (
        AR04C_CONDITION_BUDGET_USD_MICRO, AR04C_CONDITION_PROVIDER_LIMIT,
        AR04C_MAX_PROVIDER_RESERVATION_USD_MICRO, AR04C_PRICE_VERSION,
        BUDGET_USD_MICRO, EXPERIMENT_ID as LEGACY_ID, MAX_PROVIDER_RESERVATION_USD_MICRO,
        PRICE_VERSION, ExperimentBudgetError, complete_dispatch, initialize_experiment,
        read_budget, reserve_dispatch, _actual_cost_micro,
    )
    from opspilot.domain.database import reset_fixture

    on_db, off_db, old_db = (tmp_path / name for name in ("on.sqlite3", "off.sqlite3", "old.sqlite3"))
    for db_path in (on_db, off_db, old_db):
        reset_fixture(db_path, "S1_POS")
    for db_path in (on_db, off_db):
        initialize_experiment(db_path, EXPERIMENT_ID)
        budget = read_budget(db_path, EXPERIMENT_ID)
        assert budget["provider_limit"] == AR04C_CONDITION_PROVIDER_LIMIT == 8
        assert budget["mcp_limit"] is None
        assert budget["budget_usd_micro"] == AR04C_CONDITION_BUDGET_USD_MICRO == 5_250_000
    initialize_experiment(old_db, LEGACY_ID)
    old = read_budget(old_db, LEGACY_ID)
    from opspilot.domain.assistant_experiment import MCP_LIMIT
    assert old["provider_limit"] == 16 and old["mcp_limit"] == MCP_LIMIT
    assert old["budget_usd_micro"] == BUDGET_USD_MICRO == 10_500_000
    assert old["usd_reserved_micro"] == old["usd_settled_micro"] == 0
    assert PRICE_VERSION == "DEEPSEEK_FLASH_PEAK_2026-11-01"
    assert MAX_PROVIDER_RESERVATION_USD_MICRO == 645_600
    assert AR04C_PRICE_VERSION == "DEEPSEEK_FLASH_PEAK_2026-11-05"
    assert AR04C_MAX_PROVIDER_RESERVATION_USD_MICRO == 645_600
    assert AR04C_MAX_PROVIDER_RESERVATION_USD_MICRO * AR04C_CONDITION_PROVIDER_LIMIT <= AR04C_CONDITION_BUDGET_USD_MICRO
    assert AR04C_MAX_PROVIDER_RESERVATION_USD_MICRO * AR04C_CONDITION_PROVIDER_LIMIT * 2 <= BUDGET_USD_MICRO
    assert _actual_cost_micro(12_000, 2_048) == 6_058
    assert _actual_cost_micro(12_000, 2_048, EXPERIMENT_ID) == 6_058
    from opspilot.domain.s3 import prepare_s3_fixture
    from test_m4_03_s3 import _task
    for db_path in (on_db, off_db):
        prepare_s3_fixture(db_path, "DELIVERED_PENDING", order_id=f"{db_path.stem}-order")
        _identity, task = _task(db_path, f"{db_path.stem}-order")
        run_id = str(task["run_id"])
        for number in range(8):
            key = f"model-{number}"
            held = reserve_dispatch(
                db_path, experiment_id=EXPERIMENT_ID, run_id=run_id, kind="MODEL",
                logical_key=key, request={"message": "offline"},
            )
            assert held["reserved_usd_micro"] == 645_600
            complete_dispatch(
                db_path, experiment_id=EXPERIMENT_ID, run_id=run_id, kind="MODEL",
                logical_key=key,
                usage={"input_tokens": 12_000, "output_tokens": 2_048, "total_tokens": 14_048},
            )
        with pytest.raises(ExperimentBudgetError, match="AR02_LIVE_PROVIDER_LIMIT"):
            reserve_dispatch(
                db_path, experiment_id=EXPERIMENT_ID, run_id="over", kind="MODEL",
                logical_key="ninth", request={},
            )
        budget = read_budget(db_path, EXPERIMENT_ID)
        assert budget["provider_used"] == 8
        assert budget["usd_reserved_micro"] == 0
        assert budget["usd_settled_micro"] == 8 * 6_058
    assert sum(read_budget(db, EXPERIMENT_ID)["usd_settled_micro"] for db in (on_db, off_db)) <= 10_500_000


def test_ar04c_unknown_dispatch_keeps_reservation_and_stops_next_request(tmp_path: Path):
    from opspilot.domain.assistant_experiment import (
        AR04C_MAX_PROVIDER_RESERVATION_USD_MICRO, ExperimentBudgetError,
        initialize_experiment, mark_unknown, read_budget, reserve_dispatch,
    )
    from opspilot.domain.database import reset_fixture

    db_path = tmp_path / "unknown.sqlite3"
    reset_fixture(db_path, "S1_POS")
    initialize_experiment(db_path, EXPERIMENT_ID)
    from opspilot.domain.s3 import prepare_s3_fixture
    from test_m4_03_s3 import _task
    prepare_s3_fixture(db_path, "DELIVERED_PENDING", order_id="ar04c-unknown-order")
    _identity, task = _task(db_path, "ar04c-unknown-order")
    unknown_run_id = str(task["run_id"])
    reserve_dispatch(
        db_path, experiment_id=EXPERIMENT_ID, run_id=unknown_run_id, kind="MODEL",
        logical_key="unknown-call", request={},
    )
    mark_unknown(
        db_path, experiment_id=EXPERIMENT_ID, run_id=unknown_run_id, kind="MODEL",
        logical_key="unknown-call", error_code="MOCK_UNKNOWN",
    )
    budget = read_budget(db_path, EXPERIMENT_ID)
    assert budget["status"] == "BUDGET_BREACH"
    assert budget["usd_reserved_micro"] == AR04C_MAX_PROVIDER_RESERVATION_USD_MICRO
    with pytest.raises(ExperimentBudgetError, match="AR02_LIVE_SPEND_BOUND_BREACHED"):
        reserve_dispatch(
            db_path, experiment_id=EXPERIMENT_ID, run_id="new-run", kind="MODEL",
            logical_key="new-call", request={},
        )


def test_ar04c_task_policy_allows_more_than_old_mcp_limit_and_preserves_time(tmp_path: Path):
    from opspilot.domain.assistant import run_limits_for_experiment
    from opspilot.domain.database import connect, reset_fixture
    from opspilot.domain.d2 import (
        BudgetExhausted, configure_ar04c_memory_budget, finish_attempt, reserve_attempt,
        task_attempt_limits,
    )
    from opspilot.domain.assistant_experiment import initialize_experiment
    from opspilot.domain.s3 import prepare_s3_fixture
    from opspilot.domain.task_control import apply_pending_critical_inputs, claim_task_run
    from test_m4_03_s3 import _task

    db_path = tmp_path / "policy.sqlite3"
    reset_fixture(db_path, "S1_POS")
    prepare_s3_fixture(db_path, "DELIVERED_PENDING", order_id="ar04c-order", contract_version=2)
    identity, task = _task(db_path, "ar04c-order")
    initialize_experiment(db_path, EXPERIMENT_ID)
    with pytest.raises(ValueError, match="AR04C_EXPERIMENT_SCOPE_INVALID"):
        configure_ar04c_memory_budget(db_path, str(task["task_id"]), "OTHER-EXPERIMENT")
    assert configure_ar04c_memory_budget(db_path, str(task["task_id"]), EXPERIMENT_ID) == {
        "MODEL": 8, "MCP": None,
    }
    assert task_attempt_limits(db_path, str(task["task_id"])) == {"MODEL": 8, "MCP": None}
    assert run_limits_for_experiment(EXPERIMENT_ID) == (8, None)
    with connect(db_path) as connection:
        row = connection.execute(
            "SELECT policy_version,model_limit,mcp_limit,deadline_ms,active_elapsed_ms "
            "FROM task_execution_budgets WHERE task_id=?", (task["task_id"],),
        ).fetchone()
        assert row["policy_version"] == "AR04C_MEMORY_ON_OFF_V1"
        assert int(row["model_limit"]) == 8 and int(row["mcp_limit"]) == 0
        assert int(row["deadline_ms"]) == 300_000 and int(row["active_elapsed_ms"]) == 0
    claim_task_run(db_path, identity, str(task["run_id"]))
    apply_pending_critical_inputs(db_path, identity, str(task["run_id"]))
    for number in range(11):
        attempt_id, used = reserve_attempt(
            db_path, str(task["task_id"]), "MCP", None, call_id=f"repeat-{number}",
            tool_call_id=f"tool-{number}", tool_name="get_receiver_processing",
            argument_digest="same-arguments", run_id=str(task["run_id"]),
        )
        assert used == number + 1
        finish_attempt(db_path, attempt_id, "OK", result_digest=f"result-{number}")
    assert task_attempt_limits(db_path, str(task["task_id"]))["MCP"] is None


def test_ar04c_formal_worker_mock_pair_keeps_current_queued_facts_and_memory_only_diff(tmp_path: Path, monkeypatch):
    import json
    from opspilot.assistant import (
        AR04C_AUTH_RECORD, AR04C_CLAIM, _ar04c_create_one_shot_claim,
        _ar04c_claim_state_path,
    )
    from opspilot.domain.assistant_experiment import initialize_experiment

    real_auth_record, real_claim = AR04C_AUTH_RECORD, AR04C_CLAIM
    assert not real_auth_record.exists()
    assert not real_claim.exists()
    from test_ar04c_prelive_hf01 import _write_authorization
    _write_authorization(tmp_path / "paid-auth-fixture", monkeypatch)
    _ar04c_create_one_shot_claim()

    seed_db = tmp_path / "seed.sqlite3"
    off_db, on_db = tmp_path / "off.sqlite3", tmp_path / "on.sqlite3"
    memory = _prepare_memory_seed(seed_db, tmp_path / "seed-checkpoint.sqlite3", off_db, on_db)
    for db_path in (off_db, on_db):
        initialize_experiment(db_path, EXPERIMENT_ID)
    before_off, before_on = _protected_counts(off_db), _protected_counts(on_db)
    off = _run_condition(off_db, tmp_path / "off-checkpoint.sqlite3", "OFF", memory["memory"], monkeypatch)
    on = _run_condition(on_db, tmp_path / "on-checkpoint.sqlite3", "ON", memory["memory"], monkeypatch)
    assert off["j2_answer"] == on["j2_answer"]
    assert off["j4_answer"] != on["j4_answer"]
    assert off["task_budget"] == on["task_budget"]
    assert off["memory_refs_j2"] == off["memory_refs_j4"] == []
    assert [item["memory_id"] for item in on["memory_refs_j2"]] == [memory["memory"]["memory_id"]]
    assert [item["memory_id"] for item in on["memory_refs_j4"]] == [memory["memory"]["memory_id"]]
    assert off["protected_table_counts"] == before_off
    assert on["protected_table_counts"] == before_on
    assert len(off["provider_http_mock_requests"]) == len(on["provider_http_mock_requests"]) == 6
    claim_state = json.loads(_ar04c_claim_state_path().read_text(encoding="utf-8"))
    assert claim_state["status"] == "CONSUMED"
    assert set(claim_state["database_ids"]) == {"OFF", "ON"}
    from opspilot.assistant import AR04C_CLAIM, _ar04c_contract_digest
    claim = json.loads(AR04C_CLAIM.read_text(encoding="utf-8"))
    assert claim_state["execution_head_sha"] == claim["execution_head_sha"]
    assert claim_state["claim_sha256"] == hashlib.sha256(AR04C_CLAIM.read_bytes()).hexdigest()
    assert claim_state["frozen_contract_sha256"] == _ar04c_contract_digest()
    assert not real_auth_record.exists() and not real_claim.exists()
    for off_request, on_request in zip(
        off["provider_http_mock_requests"], on["provider_http_mock_requests"], strict=True,
    ):
        assert off_request["body"]["tools"] == on_request["body"]["tools"]
    assert memory["target_delivery_http_status"] == 202
    assert memory["target_receiver_status"] == "QUEUED"

    evidence = {
        "evidence_level": "OFFLINE_FORMAL_FASTAPI_WORKER_ASSISTANT_V1_HTTPX_MOCKTRANSPORT_MCP_DOMAIN",
        "experiment_id": EXPERIMENT_ID,
        "memory_source_and_confirmation": memory,
        "memory_on": on,
        "memory_off": off,
        "external_provider_http_requests": 0,
        "mocktransport_requests": 12,
        "external_business_writes": 0,
        "real_model_autonomy_or_memory_benefit_proven": False,
    }
    target = Path(__file__).resolve().parents[1] / "docs/evidence/ar-04c/real-journey-01/runs/offline-formal-pair.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")


def test_ar04c_paid_factory_fails_closed_without_authorization_and_claim(monkeypatch):
    from opspilot.assistant import AR04C_AUTH_RECORD, AR04C_CLAIM, create_assistant_model
    assert not AR04C_AUTH_RECORD.exists()
    assert not AR04C_CLAIM.exists()
    monkeypatch.setenv("OPSPILOT_ASSISTANT_PROVIDER_ENABLED", "1")
    monkeypatch.setenv("OPSPILOT_ASSISTANT_EXPERIMENT_ID", EXPERIMENT_ID)
    monkeypatch.setenv("OPSPILOT_MODEL_API_KEY", "test-only-not-a-real-key")
    monkeypatch.setenv("OPSPILOT_MODEL_NAME", "deepseek-flash")
    monkeypatch.setenv("OPSPILOT_MODEL_BASE_URL", "https://api.deepseek.com")
    monkeypatch.delenv("OPSPILOT_AR04C_REAL_JOURNEY_01_ONE_SHOT_TOKEN", raising=False)
    with pytest.raises(RuntimeError, match="AR04C_ONE_SHOT_AUTHORIZATION_REQUIRED"):
        create_assistant_model(
            transport_async=httpx.MockTransport(lambda _request: httpx.Response(500)),
            transport_sync=httpx.MockTransport(lambda _request: httpx.Response(500)),
        )


def test_ar04c_memory_mode_is_explicit_and_scoped(monkeypatch):
    from opspilot.assistant import assistant_memory_enabled_for_experiment
    monkeypatch.delenv("OPSPILOT_AR04C_MEMORY_MODE", raising=False)
    with pytest.raises(RuntimeError, match="AR04C_MEMORY_MODE_REQUIRED"):
        assistant_memory_enabled_for_experiment(EXPERIMENT_ID)
    monkeypatch.setenv("OPSPILOT_AR04C_MEMORY_MODE", "OFF")
    assert assistant_memory_enabled_for_experiment(EXPERIMENT_ID) is False
    monkeypatch.setenv("OPSPILOT_AR04C_MEMORY_MODE", "ON")
    assert assistant_memory_enabled_for_experiment(EXPERIMENT_ID) is True
    assert assistant_memory_enabled_for_experiment("ORDINARY-APP-SESSION") is True
