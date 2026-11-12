"""Recall an actual AUTO_LEARNED project background in a fresh Session."""
import json

from langchain_core.messages import AIMessage, HumanMessage

from opspilot.domain.database import connect
from opspilot.domain.semantic_memory import list_personal_memories, personal_memory_context, revoke_personal_memory
from test_c01_b2_b_personal_memory_auto_consolidation import (
    _ask, _claim, _create_session, _enable_learning, _login, _process, _running_chat, _send_six,
)


BACKGROUND = "我长期做Java后端开发，同时在用Python做Agent工程。"


class ProjectBackgroundFixture:
    async def ainvoke(self, messages):
        human = next(message for message in reversed(messages) if isinstance(message, HumanMessage))
        sources = json.loads(str(human.content).split("\n", 1)[1])["sources"]
        return AIMessage(content=json.dumps({"proposals": [{
            "action": "ADD", "memory_kind": "PROJECT_BACKGROUND", "memory_mode": "RELEVANT",
            "memory_key": "career.direction", "content": "用户长期方向为Java后端开发和Python Agent工程。",
            "source_quotes": [{"message_id": sources[0]["message_id"], "quote": BACKGROUND}],
        }]}, ensure_ascii=False))


def test_auto_learned_project_background_uses_bilingual_topic_evidence(demo_db, tmp_path):
    with _running_chat(demo_db, tmp_path) as (client, app, model):
        headers = _login(client)
        _enable_learning(demo_db)
        source_session = _create_session(client, headers)
        _send_six(client, headers, source_session, prefix="project-background", first=BACKGROUND)
        job = _claim(app, demo_db)
        assert job is not None
        result = _process(demo_db, app, job, ProjectBackgroundFixture())
        assert result["written_count"] == 1, result
        memory, = list_personal_memories(demo_db, "tenant-a", "support-a", state="ACTIVE")
        memory_id = memory["memory_id"]
        assert (memory["creation_source"], memory["memory_kind"], memory["memory_mode"]) == (
            "AUTO_LEARNED", "PROJECT_BACKGROUND", "RELEVANT",
        )

        cases = (
            ("zh-backend", "我准备面试，能不能结合SpringBoot讲讲线程池和数据库连接池各解决什么问题？", True),
            ("zh-agent", "用LangGraph怎么管理跨轮状态和中断恢复？", True),
            ("en-backend", "How would you plan my interview preparation for building JVM web services?", True),
            ("en-agent", "How can I add human approval and persistence to an AI agent built with LangGraph?", True),
            ("both-directions", "服务端研发和智能体应用这两个方向，校招项目怎样体现各自的能力？", True),
            ("unrelated-zh", "用 Python 把这份 Excel 的金额格式化一下。", False),
            ("unrelated-en", "What should I ask a travel agent before booking a trip?", False),
            ("nearby-backend", "A frontend form stores Python examples in a static JSON file. How can I style it?", False),
        )
        for case_id, query, expected in cases:
            session = _create_session(client, headers)
            assert session != source_session
            _ask(client, headers, session, query, case_id)
            request = "\n".join(str(message.content) for message in model.seen[-1])
            assert (memory_id in request) is expected, case_id
            if expected:
                assert memory["content"] in request
            print(f"{case_id}: model input recalled={expected}")

        query = cases[0][1]
        with connect(demo_db) as connection:
            selected, _, _ = personal_memory_context(connection, "tenant-b", "support-b", query)
            assert selected == []
            connection.execute("INSERT INTO trusted_operators (actor_id,tenant_id,role) VALUES ('support-a-other','tenant-a','SUPPORT')")
            selected, _, _ = personal_memory_context(connection, "tenant-a", "support-a-other", query)
            assert selected == []
            selected, excluded, _ = personal_memory_context(connection, "tenant-a", "support-a", query, limit=0)
            assert selected == []
            assert any(item["source_id"] == memory_id and item["reason"] == "PERSONAL_MEMORY_SELECTION_LIMIT" for item in excluded)
            source_id = memory["source_message_id"]
            connection.execute("UPDATE messages SET body='source changed' WHERE message_id=?", (source_id,))
            selected, excluded, _ = personal_memory_context(connection, "tenant-a", "support-a", query)
            assert selected == []
            assert any(item["source_id"] == memory_id and item["reason"] == "PERSONAL_MEMORY_SOURCE_INVALID" for item in excluded)
            connection.execute("UPDATE messages SET body=? WHERE message_id=?", (BACKGROUND, source_id))

        revoke_personal_memory(demo_db, "tenant-a", memory_id, "support-a", idempotency_key="project-background-revoke")
        _ask(client, headers, _create_session(client, headers), query, "recheck-after-revoke")
        assert memory_id not in "\n".join(str(message.content) for message in model.seen[-1])
        print("Other owner, invalid source, zero selection budget and revoked memory remained excluded")
