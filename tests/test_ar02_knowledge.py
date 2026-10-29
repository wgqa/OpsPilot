"""Free Domain checks for no-Task Knowledge scope, provenance and version selection."""
from __future__ import annotations

from copy import deepcopy
import json
import shutil

import pytest

from opspilot.domain import assistant_knowledge as knowledge
from opspilot.domain import s3_assets
from opspilot.domain.database import connect
from opspilot.domain.task_control import create_session, trusted_identity, TrustedIdentity, TaskControlError


@pytest.fixture
def scope_context(demo_db, monkeypatch, tmp_path):
    registry = tmp_path / "assistant-access.json"
    shutil.copyfile(knowledge.REGISTRY, registry)
    monkeypatch.setattr(knowledge, "REGISTRY", registry)
    with connect(demo_db) as connection:
        connection.executescript(knowledge.SCHEMA)
    identity = trusted_identity(demo_db, "support-a")
    session = create_session(demo_db, identity)["session_id"]
    return demo_db, identity, session, registry


def current(context, result):
    path, identity, session, _ = context
    with connect(path) as connection:
        return knowledge.sources_current(connection, identity, session, result)


def test_single_scope_auto_reused_without_business_task(scope_context):
    path, identity, session, _ = scope_context
    with connect(path) as connection:
        before = connection.execute("SELECT COUNT(*) FROM task_bindings").fetchone()[0]
    first = knowledge.list_scopes(path, identity, session)
    assert first["selected_project"] == "orders-callback" and len(first["items"]) == 1
    result = knowledge.search(path, identity, session, "receiver callback 202 processing")
    assert result["documents"] and result["source_refs"]
    assert result["requested_contract_version"] is None
    assert result["configured_contract_version"] == result["retrieved_contract_version"] == 2
    assert result["deployment_version_verified"] is False
    assert current(scope_context, result) == (True, None)
    assert knowledge.list_scopes(path, identity, session)["selected_project"] == first["selected_project"]
    with connect(path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM task_bindings").fetchone()[0] == before


def test_requested_older_contract_is_not_silently_replaced_with_latest(scope_context):
    path, identity, session, _ = scope_context
    result = knowledge.search(path, identity, session, "receiver callback 202 processing", contract_version=1)
    assert result["documents"] and all(1 in d["contract_versions"] for d in result["documents"])
    assert result["requested_contract_version"] == result["retrieved_contract_version"] == 1
    assert result["configured_contract_version"] == result["latest_available_contract_version"] == 2
    assert result["version_conflict"] is True and result["deployment_version_verified"] is False
    assert current(scope_context, result) == (True, None)
    with pytest.raises(ValueError):
        knowledge.search(path, identity, session, "receiver", contract_version=True)


def test_multiple_scopes_require_selection_and_switch_invalidates_old_context(scope_context):
    path, identity, session, registry = scope_context
    policy = json.loads(registry.read_text(encoding="utf-8"))
    older = deepcopy(policy["projects"][0])
    older.update(project_id="orders-historical", title="历史合同", configured_contract_version=1)
    older["document_ids"] = ["callback-ack-contract", "callback-retry-contract", "order-lifecycle-contract"]
    policy["projects"].append(older)
    registry.write_text(json.dumps(policy), encoding="utf-8")
    view = knowledge.list_scopes(path, identity, session)
    assert view["selected_project"] is None and view["selection_required"]
    with pytest.raises(knowledge.KnowledgeScopeDenied, match="SELECTION_REQUIRED"):
        knowledge.search(path, identity, session, "receiver callback")
    knowledge.select_scope(path, identity, session, "orders-historical")
    old = knowledge.search(path, identity, session, "receiver callback 202")
    assert old["retrieved_contract_version"] == 1 and current(scope_context, old)[0]
    knowledge.select_scope(path, identity, session, "orders-callback")
    assert current(scope_context, old) == (False, "KNOWLEDGE_SESSION_SCOPE_CHANGED")
    fresh = knowledge.search(path, identity, session, "receiver callback 202")
    assert fresh["retrieved_contract_version"] == 2 and current(scope_context, fresh)[0]


def test_no_grant_and_foreign_session_do_not_create_document_authority(scope_context):
    path, identity, session, _ = scope_context
    other = trusted_identity(path, "support-b")
    other_session = create_session(path, other)["session_id"]
    assert knowledge.list_scopes(path, other, other_session)["items"] == []
    with pytest.raises(knowledge.KnowledgeScopeDenied):
        knowledge.search(path, other, other_session, "receiver callback")
    with pytest.raises(knowledge.KnowledgeScopeDenied, match="SESSION_SCOPE_DENIED"):
        knowledge.list_scopes(path, other, session)
    with pytest.raises(knowledge.KnowledgeScopeDenied):
        knowledge.select_scope(path, identity, session, "arbitrary-user-project")
    forged = TrustedIdentity(identity.actor_id, "tenant-b", identity.role)
    with pytest.raises(TaskControlError, match="TRUSTED_IDENTITY_MISMATCH"):
        knowledge.list_scopes(path, forged, session)


def test_revoke_restore_and_grant_version_change_require_new_lookup(scope_context):
    path, identity, session, registry = scope_context
    old = knowledge.search(path, identity, session, "receiver callback 202")
    policy = json.loads(registry.read_text(encoding="utf-8"))
    policy["projects"][0]["active"] = False
    registry.write_text(json.dumps(policy), encoding="utf-8")
    assert knowledge.list_scopes(path, identity, session)["items"] == []
    assert not current(scope_context, old)[0]
    with pytest.raises(knowledge.KnowledgeScopeDenied):
        knowledge.search(path, identity, session, "receiver callback")
    policy["projects"][0].update(active=True, grant_version=2)
    registry.write_text(json.dumps(policy), encoding="utf-8")
    assert current(scope_context, old) == (False, "KNOWLEDGE_GRANT_CHANGED")
    assert current(scope_context, knowledge.search(path, identity, session, "receiver callback"))[0]


def test_changed_or_forged_document_content_is_excluded(scope_context, monkeypatch, tmp_path):
    path, identity, session, _ = scope_context
    assets = tmp_path / "documents"
    shutil.copytree(s3_assets.DIRECTORY, assets)
    monkeypatch.setattr(s3_assets, "DIRECTORY", assets)
    old = knowledge.search(path, identity, session, "receiver callback 202 processing")
    assert old["documents"]
    forged = deepcopy(old)
    forged["documents"][0]["content"] = "Forged content, despite keeping a valid digest string."
    assert current(scope_context, forged) == (False, "KNOWLEDGE_SOURCE_CONTENT_MISMATCH")
    doc = old["documents"][0]
    (assets / doc["file"]).write_text("Content changed without matching manifest", encoding="utf-8")
    assert current(scope_context, old) == (False, "KNOWLEDGE_REMOVED_EXPIRED_OR_CHANGED")
    fresh = knowledge.search(path, identity, session, "receiver callback 202 processing")
    assert doc["document_id"] not in {d["document_id"] for d in fresh["documents"]}
    assert current(scope_context, fresh)[0]


@pytest.mark.parametrize("bad", [True, 1.5, "1", None])
def test_malformed_grant_version_fails_closed(scope_context, bad):
    path, identity, session, registry = scope_context
    policy = json.loads(registry.read_text(encoding="utf-8"))
    policy["projects"][0]["grant_version"] = bad
    registry.write_text(json.dumps(policy), encoding="utf-8")
    with pytest.raises(knowledge.KnowledgeScopeDenied, match="REGISTRY_UNAVAILABLE"):
        knowledge.list_scopes(path, identity, session)
