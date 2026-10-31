"""HF-01 source/version regressions through the real local MCP stdio path."""
import json
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from pydantic import Field

from opspilot.domain.s3 import prepare_s3_fixture
from test_ar02_runtime import execute, setup_run


class KnowledgeAwareFixture(BaseChatModel):
    """Free fixture takes its answer and citation from the actual tool result."""

    query: str = "callback receiver protocol HTTP 202 processing"
    requested_version: int | None = None
    seen_results: list = Field(default_factory=list)

    @property
    def _llm_type(self):
        return "AR02_HF01_KNOWLEDGE_AWARE_FIXTURE"

    def bind_tools(self, tools, **kwargs):
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        results = [message for message in messages if isinstance(message, ToolMessage)]
        if not results:
            args = {"query": self.query}
            if self.requested_version is not None:
                args["contract_version"] = self.requested_version
            answer = AIMessage(
                content="",
                tool_calls=[{
                    "name": "search_project_knowledge",
                    "args": args,
                    "id": "hf01-knowledge-search",
                }],
            )
        else:
            payload = json.loads(results[-1].content)
            if isinstance(payload, dict) and set(payload) == {"result"}:
                payload = payload["result"]
            self.seen_results.append(payload)
            documents = payload.get("documents", [])
            refs = payload.get("source_refs", [])
            if documents and refs:
                doc = documents[0]
                ref = refs[0]
                answer = AIMessage(content=(
                    f"检索资料 {doc['document_id']} ({doc['version']})，"
                    f"来源 {ref['source']}，摘要：{doc['title']}。"
                ))
            else:
                answer = AIMessage(content=(
                    "本次授权资料检索没有命中文档；以下仅为一般 HTTP 语义说明，"
                    "没有引用本地协议资料。HTTP 202 表示受理，不能证明业务处理完成。"
                ))
        answer.usage_metadata = {"input_tokens": 10, "output_tokens": 8, "total_tokens": 18}
        return ChatResult(generations=[ChatGeneration(message=answer)])


def _answer(events):
    return next(event["answer"] for event in events if event["event"] == "answer_committed")


def _tool_payload(model):
    return next(
        json.loads(message.content)
        for batch in model.seen
        for message in batch
        if isinstance(message, ToolMessage) and message.tool_call_id == "fixture-call-0"
    )


def test_empty_mcp_knowledge_result_is_not_described_as_a_citation(demo_db, tmp_path):
    """Reproduces the old fixture claiming a source for a real empty MCP result."""
    from test_ar02_runtime import FixtureModel

    model = FixtureModel(mode="knowledge")
    created = setup_run(demo_db, "HTTP 202 acceptance processing 的一般含义是什么？", "hf01-empty-red")
    result, events = execute(demo_db, created, model, tmp_path / "empty-red.sqlite3")
    assert result["status"] == "SUCCEEDED", result
    knowledge = _tool_payload(model)
    assert knowledge["documents"] == []
    assert knowledge["source_refs"] == []
    assert "按本次检索" not in _answer(events)
    assert "引用见工具来源" not in _answer(events)


def test_positive_callback_query_returns_actual_document_and_citation(demo_db, tmp_path):
    created = setup_run(demo_db, "解释回调 Receiver 的 HTTP 202 语义", "hf01-hit")
    model = KnowledgeAwareFixture()
    result, events = execute(demo_db, created, model, tmp_path / "hit.sqlite3")

    assert result["status"] == "SUCCEEDED", result
    assert len(model.seen_results) == 1
    payload = model.seen_results[0]
    assert payload["documents"] and payload["source_refs"]
    doc, ref = payload["documents"][0], payload["source_refs"][0]
    for field in ("document_id", "version", "digest", "source"):
        assert doc[field] == ref[field]
    answer = _answer(events)
    assert doc["document_id"] in answer and doc["version"] in answer and ref["source"] in answer


def test_empty_query_allows_general_explanation_without_document_claim(demo_db, tmp_path):
    created = setup_run(demo_db, "给我解释一下 HTTP 202 acceptance processing", "hf01-empty")
    model = KnowledgeAwareFixture(query="unrelated quartz noise")
    result, events = execute(demo_db, created, model, tmp_path / "empty.sqlite3")

    assert result["status"] == "SUCCEEDED", result
    payload = model.seen_results[0]
    assert payload["documents"] == [] and payload["source_refs"] == []
    assert "一般 HTTP 语义" in _answer(events)
    assert "没有引用本地协议资料" in _answer(events)


def test_task_binding_old_version_request_is_not_deployment_verification(demo_db, tmp_path):
    prepare_s3_fixture(demo_db, "PROCESSING", order_id="ar02-order", contract_version=2)
    created = setup_run(
        demo_db, "请查历史 v1 回调 Receiver 协议。", "hf01-old-version", bind=True
    )
    model = KnowledgeAwareFixture(
        query="callback receiver processing", requested_version=1
    )
    result, events = execute(demo_db, created, model, tmp_path / "binding-version.sqlite3")

    assert result["status"] == "SUCCEEDED", result
    payload = model.seen_results[0]
    assert payload["user_requested_contract_version"] == 1
    assert payload["requested_contract_version"] == 1
    assert payload["configured_contract_version"] == 2
    assert payload["trusted_binding_contract_version"] == 2
    assert payload["latest_available_contract_version"] == 2
    assert payload["retrieved_contract_version"] == 1
    assert payload["applicable_contract_version"] == 2
    assert payload["version_conflict"] is True
    assert payload["deployment_version_verified"] is False
    assert payload["documents"] and all(
        doc["document_id"] != "receiver-ack-contract-v2" for doc in payload["documents"]
    )
    assert _answer(events)


def test_task_binding_default_uses_binding_version_but_not_deployment_claim(demo_db, tmp_path):
    prepare_s3_fixture(demo_db, "PROCESSING", order_id="ar02-order", contract_version=2)
    created = setup_run(demo_db, "请查适用的回调协议。", "hf01-binding-default", bind=True)
    model = KnowledgeAwareFixture(query="callback receiver protocol HTTP 202 processing")
    result, events = execute(demo_db, created, model, tmp_path / "binding-default.sqlite3")

    assert result["status"] == "SUCCEEDED", result
    payload = model.seen_results[0]
    assert payload["user_requested_contract_version"] is None
    assert payload["requested_contract_version"] is None
    assert payload["trusted_binding_contract_version"] == 2
    assert payload["configured_contract_version"] == 2
    assert payload["retrieved_contract_version"] == 2
    assert payload["applicable_contract_version"] == 2
    assert payload["deployment_version_verified"] is False
    assert _answer(events)


def test_no_task_old_version_request_keeps_preference_and_configuration_separate(demo_db, tmp_path):
    created = setup_run(demo_db, "请查询 v1 的 Receiver 协议。", "hf01-no-task-v1")
    model = KnowledgeAwareFixture(query="callback receiver processing", requested_version=1)
    result, events = execute(demo_db, created, model, tmp_path / "no-task-version.sqlite3")

    assert result["status"] == "SUCCEEDED", result
    payload = model.seen_results[0]
    assert payload["trusted_binding_contract_version"] is None
    assert payload["user_requested_contract_version"] == 1
    assert payload["requested_contract_version"] == 1
    assert payload["configured_contract_version"] == 2
    assert payload["latest_available_contract_version"] == 2
    assert payload["retrieved_contract_version"] == 1
    assert payload["applicable_contract_version"] == 2
    assert payload["deployment_version_verified"] is False
    assert _answer(events)
