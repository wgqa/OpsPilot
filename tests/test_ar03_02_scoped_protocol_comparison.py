"""Tests for Session-Authorized Protocol Knowledge Version Comparison (AR-03-02).

Validates:
1. Legal v1/v2 protocol comparison within an authorized project session.
2. Real business documents (callback-retry v1/v2, order-lifecycle v1/v2).
3. Cross-tenant, cross-project, and foreign-session isolation (fails closed).
4. Unpermitted document rejection (documents not in project document_ids).
5. Historical version comparison (not rejected simply because it's not the configured version).
6. Scope change, deactivation, and grant version change revocation detection.
7. Safe wrapper returns structured error diagnostics rather than unhandled crashes.
8. Server-side resolution prevents arbitrary caller file paths or forged digests.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import shutil
import pytest

from opspilot.config import ROOT
from opspilot.domain import assistant_knowledge as knowledge
from opspilot.domain.database import connect
from opspilot.domain.protocol_comparison import (
    DEFAULT_CATALOG_DIRS,
    DocumentNotFoundError,
    DocumentIntegrityError,
    InvalidReferenceError,
)
from opspilot.domain.scoped_protocol_comparison import (
    DocumentNotAuthorizedError,
    ScopedComparisonError,
    ScopedProtocolComparisonResult,
    compare_scoped_protocols,
    compare_scoped_protocols_safe,
    scoped_comparison_is_current,
)
from opspilot.domain.task_control import (
    TaskControlError,
    TrustedIdentity,
    create_session,
    trusted_identity,
)


@pytest.fixture
def scoped_env(demo_db: Path, monkeypatch, tmp_path: Path):
    """Set up an isolated SQLite database, assistant access registry, and active session."""
    registry = tmp_path / "assistant-access.json"
    shutil.copyfile(knowledge.REGISTRY, registry)
    monkeypatch.setattr(knowledge, "REGISTRY", registry)

    with connect(demo_db) as connection:
        connection.executescript(knowledge.SCHEMA)

    identity = trusted_identity(demo_db, "support-a")
    session_id = create_session(demo_db, identity)["session_id"]
    return demo_db, identity, session_id, registry


def test_scoped_comparison_callback_retry_real_business_documents(scoped_env):
    """AR03-02-02: Complete offline comparison of real callback-retry-contract v1 vs v2."""
    db, identity, session_id, _ = scoped_env

    result = compare_scoped_protocols(
        db,
        identity,
        session_id,
        base_document_id="callback-retry-contract",
        target_document_id="callback-retry-contract-v2",
    )

    # 1. Provenance and authorization metadata
    assert isinstance(result, ScopedProtocolComparisonResult)
    assert result.session_id == session_id
    assert result.project_id == "orders-callback"
    assert result.tenant_id == "tenant-a"
    assert result.actor_id == "support-a"
    assert result.grant_version == 1

    # 2. Epistemic boundary constraints
    assert result.deployment_version_verified is False
    assert any("LIVE_DEPLOYMENT_VERSION_UNVERIFIED" in aspect for aspect in result.unconfirmed_aspects)

    # 3. Structural difference details
    assert result.identical is False
    assert result.diff_count == 1
    evidence = result.diff_evidence[0]
    assert evidence["diff_type"] == "SECTION_MODIFIED"
    assert "TEMPORARY_UNAVAILABLE" in evidence["base_excerpt"]
    assert "attempt_count reaches max_attempts" in evidence["target_excerpt"]

    # 4. Verified digests
    assert evidence["base_excerpt_digest"] == hashlib.sha256(evidence["base_excerpt"].encode("utf-8")).hexdigest()
    assert evidence["target_excerpt_digest"] == hashlib.sha256(evidence["target_excerpt"].encode("utf-8")).hexdigest()

    # 5. Output format is consumable by future agent tools
    as_dict = result.to_dict()
    assert as_dict["authority"] == "SESSION_AUTHORIZED_INVESTIGATION_EVIDENCE_NOT_ACTION_AUTHORIZATION"
    assert as_dict["project_id"] == "orders-callback"
    assert as_dict["base_ref"]["document_id"] == "callback-retry-contract"
    assert as_dict["target_ref"]["document_id"] == "callback-retry-contract-v2"

    # 6. Current validity check
    is_valid, reason = scoped_comparison_is_current(db, identity, session_id, result)
    assert is_valid is True
    assert reason is None


def test_scoped_comparison_order_lifecycle_real_business_documents(scoped_env):
    """AR03-02-02: Compare real order-lifecycle-contract v1 vs v2."""
    db, identity, session_id, _ = scoped_env

    result = compare_scoped_protocols(
        db,
        identity,
        session_id,
        base_document_id="order-lifecycle-contract",
        target_document_id="order-lifecycle-contract-v2",
    )

    assert result.identical is False
    assert result.diff_count == 1
    assert "order-lifecycle-contract" in result.base_ref["document_id"]
    assert "order-lifecycle-contract-v2" in result.target_ref["document_id"]
    assert result.base_ref["version"] == "1.0.0"
    assert result.target_ref["version"] == "2.0.0"
    assert result.deployment_version_verified is False

    is_valid, reason = scoped_comparison_is_current(db, identity, session_id, result)
    assert is_valid is True
    assert reason is None


def test_unauthorized_document_rejected(scoped_env):
    """AR03-02-03: Documents not in project['document_ids'] are rejected."""
    db, identity, session_id, _ = scoped_env

    # api-scope-current exists in api-scope catalog, but is not in orders-callback project
    with pytest.raises(DocumentNotAuthorizedError) as exc_info:
        compare_scoped_protocols(
            db,
            identity,
            session_id,
            base_document_id="callback-retry-contract",
            target_document_id="api-scope-current",
        )
    assert "DOCUMENT_NOT_AUTHORIZED" in str(exc_info.value)
    assert exc_info.value.reason_code == "DOCUMENT_NOT_AUTHORIZED"

    # Safe wrapper returns structured error
    safe_res = compare_scoped_protocols_safe(
        db,
        identity,
        session_id,
        base_document_id="callback-retry-contract",
        target_document_id="api-scope-current",
    )
    assert safe_res["success"] is False
    assert safe_res["result"] is None
    assert safe_res["error"]["reason_code"] == "DOCUMENT_NOT_AUTHORIZED"


def test_cross_tenant_access_denied(scoped_env):
    """AR03-02-03: Caller from tenant-b cannot access tenant-a project or session."""
    db, _, session_id, _ = scoped_env
    other_tenant_identity = trusted_identity(db, "support-b")
    other_session_id = create_session(db, other_tenant_identity)["session_id"]

    # support-b attempting to use support-b's session on orders-callback (which is tenant-a)
    with pytest.raises(knowledge.KnowledgeScopeDenied):
        compare_scoped_protocols(
            db,
            other_tenant_identity,
            other_session_id,
            base_document_id="callback-retry-contract",
            target_document_id="callback-retry-contract-v2",
        )

    # support-b attempting to hijack support-a's session
    with pytest.raises(knowledge.KnowledgeScopeDenied, match="SESSION_SCOPE_DENIED"):
        compare_scoped_protocols(
            db,
            other_tenant_identity,
            session_id,
            base_document_id="callback-retry-contract",
            target_document_id="callback-retry-contract-v2",
        )


def test_selection_required_when_multiple_projects_unselected(scoped_env):
    """AR03-02-01: When multiple projects match and none is selected, selection is required."""
    db, identity, session_id, registry = scoped_env

    policy = json.loads(registry.read_text(encoding="utf-8"))
    second_project = deepcopy(policy["projects"][0])
    second_project.update(
        project_id="orders-archive",
        title="历史归档合同",
        configured_contract_version=1,
    )
    policy["projects"].append(second_project)
    registry.write_text(json.dumps(policy), encoding="utf-8")

    # Multiple projects available, none selected yet
    with pytest.raises(knowledge.KnowledgeScopeDenied, match="SELECTION_REQUIRED"):
        compare_scoped_protocols(
            db,
            identity,
            session_id,
            base_document_id="callback-retry-contract",
            target_document_id="callback-retry-contract-v2",
        )

    # After explicit selection, comparison succeeds
    knowledge.select_scope(db, identity, session_id, "orders-callback")
    res = compare_scoped_protocols(
        db,
        identity,
        session_id,
        base_document_id="callback-retry-contract",
        target_document_id="callback-retry-contract-v2",
    )
    assert res.project_id == "orders-callback"


def test_scope_switch_invalidates_previous_result(scoped_env):
    """AR03-02-03: Switching selected project invalidates prior scoped comparison results."""
    db, identity, session_id, registry = scoped_env

    policy = json.loads(registry.read_text(encoding="utf-8"))
    second_project = deepcopy(policy["projects"][0])
    second_project.update(
        project_id="orders-archive",
        title="历史归档合同",
        configured_contract_version=1,
    )
    policy["projects"].append(second_project)
    registry.write_text(json.dumps(policy), encoding="utf-8")

    knowledge.select_scope(db, identity, session_id, "orders-callback")
    res = compare_scoped_protocols(
        db,
        identity,
        session_id,
        base_document_id="callback-retry-contract",
        target_document_id="callback-retry-contract-v2",
    )
    assert scoped_comparison_is_current(db, identity, session_id, res) == (True, None)

    # Switch project scope
    knowledge.select_scope(db, identity, session_id, "orders-archive")
    is_valid, reason = scoped_comparison_is_current(db, identity, session_id, res)
    assert is_valid is False
    assert reason == "KNOWLEDGE_SESSION_SCOPE_CHANGED"


def test_project_deactivation_revokes_authorization(scoped_env):
    """AR03-02-03: Deactivating project prevents new comparisons and revokes prior results."""
    db, identity, session_id, registry = scoped_env

    res = compare_scoped_protocols(
        db,
        identity,
        session_id,
        base_document_id="callback-retry-contract",
        target_document_id="callback-retry-contract-v2",
    )
    assert scoped_comparison_is_current(db, identity, session_id, res)[0] is True

    # Deactivate project
    policy = json.loads(registry.read_text(encoding="utf-8"))
    policy["projects"][0]["active"] = False
    registry.write_text(json.dumps(policy), encoding="utf-8")

    # New calls fail closed
    with pytest.raises(knowledge.KnowledgeScopeDenied):
        compare_scoped_protocols(
            db,
            identity,
            session_id,
            base_document_id="callback-retry-contract",
            target_document_id="callback-retry-contract-v2",
        )

    # Old result is no longer valid
    is_valid, reason = scoped_comparison_is_current(db, identity, session_id, res)
    assert is_valid is False
    assert reason == "KNOWLEDGE_SCOPE_DENIED"


def test_grant_version_bump_invalidates_old_result(scoped_env):
    """AR03-02-03: Updating grant_version invalidates previous results."""
    db, identity, session_id, registry = scoped_env

    res = compare_scoped_protocols(
        db,
        identity,
        session_id,
        base_document_id="callback-retry-contract",
        target_document_id="callback-retry-contract-v2",
    )

    policy = json.loads(registry.read_text(encoding="utf-8"))
    policy["projects"][0]["grant_version"] = 2
    registry.write_text(json.dumps(policy), encoding="utf-8")

    is_valid, reason = scoped_comparison_is_current(db, identity, session_id, res)
    assert is_valid is False
    assert reason == "KNOWLEDGE_GRANT_CHANGED"


def test_document_removal_from_grant_revokes_result(scoped_env):
    """AR03-02-03: If a document is removed from document_ids, previous results become invalid."""
    db, identity, session_id, registry = scoped_env

    res = compare_scoped_protocols(
        db,
        identity,
        session_id,
        base_document_id="callback-retry-contract",
        target_document_id="callback-retry-contract-v2",
    )

    policy = json.loads(registry.read_text(encoding="utf-8"))
    policy["projects"][0]["document_ids"] = ["callback-retry-contract-v2"]  # removed v1
    registry.write_text(json.dumps(policy), encoding="utf-8")

    is_valid, reason = scoped_comparison_is_current(db, identity, session_id, res)
    assert is_valid is False
    assert reason == "DOCUMENT_AUTHORIZATION_REVOKED"


def test_historical_version_comparison_permitted(scoped_env):
    """AR03-02-03: Comparing historical version (v1) when project configured version is v2 is allowed."""
    db, identity, session_id, registry = scoped_env

    policy = json.loads(registry.read_text(encoding="utf-8"))
    assert policy["projects"][0]["configured_contract_version"] == 2

    # Comparing v1 (contract_version 1) vs v2 (contract_version 2) is permitted
    res = compare_scoped_protocols(
        db,
        identity,
        session_id,
        base_document_id="callback-retry-contract",
        target_document_id="callback-retry-contract-v2",
    )
    assert res.diff_count == 1
    assert res.base_ref["version"] == "1.0.0"
    assert res.target_ref["version"] == "2.0.0"


def test_invalid_input_parameters_fail_closed(scoped_env):
    """Invalid reference inputs fail closed."""
    db, identity, session_id, _ = scoped_env

    with pytest.raises(InvalidReferenceError):
        compare_scoped_protocols(db, identity, session_id, base_document_id="", target_document_id="callback-retry-contract")

    with pytest.raises(InvalidReferenceError):
        compare_scoped_protocols(db, identity, session_id, base_document_id="callback-retry-contract", target_document_id="   ")

    safe_res = compare_scoped_protocols_safe(db, identity, session_id, base_document_id="", target_document_id="callback-retry-contract")
    assert safe_res["success"] is False
    assert safe_res["error"]["reason_code"] == "MISSING_OR_INVALID_REFERENCE"


def test_nonexistent_document_fails_closed(scoped_env, registry=None):
    """If a document is in project['document_ids'] but cannot be found in catalogs, it fails closed."""
    db, identity, session_id, registry = scoped_env

    policy = json.loads(registry.read_text(encoding="utf-8"))
    policy["projects"][0]["document_ids"].append("phantom-contract-doc")
    registry.write_text(json.dumps(policy), encoding="utf-8")

    with pytest.raises(DocumentNotFoundError):
        compare_scoped_protocols(
            db,
            identity,
            session_id,
            base_document_id="callback-retry-contract",
            target_document_id="phantom-contract-doc",
        )


def test_disk_file_tampering_invalidates_scoped_comparison(scoped_env, tmp_path):
    """If a catalog file on disk is modified, revalidation fails closed."""
    db, identity, session_id, _ = scoped_env

    # Create isolated copy of async-callback catalog
    cat_dir = tmp_path / "tampered-catalog"
    shutil.copytree(ROOT / "knowledge" / "async-callback", cat_dir)

    res = compare_scoped_protocols(
        db,
        identity,
        session_id,
        base_document_id="callback-retry-contract",
        target_document_id="callback-retry-contract-v2",
        catalog_dirs=[cat_dir],
    )
    assert scoped_comparison_is_current(db, identity, session_id, res, catalog_dirs=[cat_dir]) == (True, None)

    # Tamper with base file on disk
    (cat_dir / "callback-retry-contract.md").write_text("TAMPERED CONTENT", encoding="utf-8")

    is_valid, reason = scoped_comparison_is_current(db, identity, session_id, res, catalog_dirs=[cat_dir])
    assert is_valid is False
    assert reason == "DOCUMENT_INTEGRITY_OR_EXPIRED"


def test_safe_wrapper_returns_structured_error_on_various_failures(scoped_env):
    """Verify safe wrapper handles authorization, reference, and document errors cleanly."""
    db, identity, session_id, _ = scoped_env

    # 1. Unauthorized document
    res_unauth = compare_scoped_protocols_safe(
        db, identity, session_id,
        base_document_id="callback-retry-contract",
        target_document_id="api-scope-current",
    )
    assert res_unauth["success"] is False
    assert res_unauth["error"]["reason_code"] == "DOCUMENT_NOT_AUTHORIZED"

    # 2. Cross-tenant
    other_tenant_identity = trusted_identity(db, "support-b")
    res_tenant = compare_scoped_protocols_safe(
        db, other_tenant_identity, session_id,
        base_document_id="callback-retry-contract",
        target_document_id="callback-retry-contract-v2",
    )
    assert res_tenant["success"] is False
    assert "SESSION_SCOPE_DENIED" in res_tenant["error"]["reason_code"]

    # 3. Success case produces structured result
    res_ok = compare_scoped_protocols_safe(
        db, identity, session_id,
        base_document_id="callback-retry-contract",
        target_document_id="callback-retry-contract-v2",
    )
    assert res_ok["success"] is True
    assert res_ok["error"] is None
    assert res_ok["result"]["project_id"] == "orders-callback"
    assert res_ok["result"]["diff_count"] == 1


def test_same_document_id_with_explicit_versions(scoped_env, tmp_path):
    """When a single document_id has multiple versions, explicit version selection resolves them."""
    db, identity, session_id, registry = scoped_env

    cat_dir = tmp_path / "multi-version-cat"
    cat_dir.mkdir(parents=True, exist_ok=True)

    doc_v1 = "# Spec\nLine 1\n"
    doc_v2 = "# Spec\nLine 1 modified\n"
    b_bytes = doc_v1.encode("utf-8")
    t_bytes = doc_v2.encode("utf-8")
    (cat_dir / "spec-v1.md").write_bytes(b_bytes)
    (cat_dir / "spec-v2.md").write_bytes(t_bytes)

    manifest = {
        "schema_version": 1,
        "documents": [
            {
                "document_id": "unified-spec",
                "file": "spec-v1.md",
                "version": "1.0.0",
                "digest": hashlib.sha256(b_bytes).hexdigest(),
                "source": "local:unified/v1",
                "valid_from": "2026-01-01T00:00:00+00:00",
                "active": True,
            },
            {
                "document_id": "unified-spec",
                "file": "spec-v2.md",
                "version": "2.0.0",
                "digest": hashlib.sha256(t_bytes).hexdigest(),
                "source": "local:unified/v2",
                "valid_from": "2026-01-01T00:00:00+00:00",
                "active": True,
            },
        ],
    }
    (cat_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    # Authorize unified-spec in project
    policy = json.loads(registry.read_text(encoding="utf-8"))
    policy["projects"][0]["document_ids"].append("unified-spec")
    registry.write_text(json.dumps(policy), encoding="utf-8")

    res = compare_scoped_protocols(
        db,
        identity,
        session_id,
        base_document_id="unified-spec",
        target_document_id="unified-spec",
        base_version="1.0.0",
        target_version="2.0.0",
        catalog_dirs=[cat_dir],
    )
    assert res.base_ref["version"] == "1.0.0"
    assert res.target_ref["version"] == "2.0.0"
    assert res.identical is False
    assert res.diff_count == 1

