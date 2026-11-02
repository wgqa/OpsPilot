"""Session-authorized Protocol Version Comparison Domain Bridge (AR-03-02).

Bridges caller identity and session project authorization grants to
the protocol version comparison calculation, ensuring:
1. Strict session scope and tenant isolation.
2. Documents must be explicitly permitted under the session's active project grant.
3. Cryptographic digest and canonical source resolution from trusted catalog manifests,
   preventing caller/model tampering with file paths or digests.
4. Epistemic boundaries: static comparison results are investigation evidence only
   and cannot prove runtime cluster deployment state or authorize business actions.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
from pathlib import Path
import re
import sqlite3
from typing import Any, Sequence

from opspilot.domain.assistant_knowledge import (
    KnowledgeScopeDenied,
    get_session_project,
)
from opspilot.domain.d2 import canonical_json, digest_json, utc_now
from opspilot.domain.database import connect
from opspilot.domain.protocol_comparison import (
    DEFAULT_CATALOG_DIRS,
    DocumentNotFoundError,
    DocumentIntegrityError,
    DocumentExpiredError,
    DocumentRef,
    InvalidReferenceError,
    ProtocolComparisonError,
    ProtocolComparisonResult,
    _ensure_catalog_dirs,
    compare_protocol_versions,
    resolve_document,
)
from opspilot.domain.task_control import TaskControlError, TrustedIdentity


class ScopedComparisonError(ProtocolComparisonError):
    """Base exception for scoped protocol comparison errors."""

    def __init__(self, message: str, reason_code: str | None = None):
        super().__init__(message, reason_code=reason_code or "SCOPED_COMPARISON_ERROR")


class DocumentNotAuthorizedError(ScopedComparisonError):
    """Document is not authorized under the session's active project grant."""

    def __init__(self, message: str):
        super().__init__(message, reason_code="DOCUMENT_NOT_AUTHORIZED")


@dataclass(frozen=True)
class ScopedProtocolComparisonResult:
    """Session-authorized protocol comparison result with provenance metadata."""

    session_id: str
    project_id: str
    tenant_id: str
    actor_id: str
    grant_version: int
    scope_digest: str
    base_document_id: str
    target_document_id: str
    comparison: ProtocolComparisonResult

    @property
    def base_ref(self) -> dict[str, Any]:
        return self.comparison.base_ref

    @property
    def target_ref(self) -> dict[str, Any]:
        return self.comparison.target_ref

    @property
    def identical(self) -> bool:
        return self.comparison.identical

    @property
    def summary(self) -> str:
        return self.comparison.summary

    @property
    def diff_count(self) -> int:
        return self.comparison.diff_count

    @property
    def differences(self) -> list[dict[str, Any]]:
        return self.comparison.differences

    @property
    def diff_evidence(self) -> list[dict[str, Any]]:
        return self.comparison.diff_evidence

    @property
    def unconfirmed_aspects(self) -> list[str]:
        return self.comparison.unconfirmed_aspects

    @property
    def deployment_version_verified(self) -> bool:
        return False

    @property
    def comparison_digest(self) -> str:
        return self.comparison.comparison_digest

    @property
    def compared_at(self) -> str:
        return self.comparison.compared_at

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "project_id": self.project_id,
            "tenant_id": self.tenant_id,
            "actor_id": self.actor_id,
            "grant_version": self.grant_version,
            "scope_digest": self.scope_digest,
            "base_document_id": self.base_document_id,
            "target_document_id": self.target_document_id,
            "authority": "SESSION_AUTHORIZED_INVESTIGATION_EVIDENCE_NOT_ACTION_AUTHORIZATION",
            "deployment_version_verified": False,
            "base_ref": self.comparison.base_ref,
            "target_ref": self.comparison.target_ref,
            "identical": self.comparison.identical,
            "summary": self.comparison.summary,
            "diff_count": self.comparison.diff_count,
            "differences": self.comparison.differences,
            "diff_evidence": self.comparison.diff_evidence,
            "unconfirmed_aspects": self.comparison.unconfirmed_aspects,
            "comparison_digest": self.comparison.comparison_digest,
            "compared_at": self.comparison.compared_at,
        }


def _matches_version(entry: dict[str, Any], requested_version: str | None) -> bool:
    if requested_version is None:
        return True
    req_str = str(requested_version).strip()
    ent_ver = str(entry.get("version", "")).strip()
    if ent_ver == req_str:
        return True
    if ent_ver.startswith(f"{req_str}.") or req_str.startswith(f"{ent_ver}."):
        return True
    contract_vers = entry.get("contract_versions")
    if isinstance(contract_vers, list):
        if req_str in [str(v) for v in contract_vers]:
            return True
    return False


def _resolve_catalog_ref(
    document_id: str,
    version: str | None,
    catalog_dirs: list[Path],
) -> DocumentRef:
    """Find a document entry in trusted catalogs and construct a verified DocumentRef.

    Populates digest and source directly from trusted catalog manifests, preventing
    untrusted inputs from forging digests or paths.
    """
    matching_entries: list[tuple[dict[str, Any], Path]] = []

    for catalog_dir in catalog_dirs:
        manifest_path = catalog_dir / "manifest.json"
        if not manifest_path.is_file():
            continue
        try:
            manifest_content = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(manifest_content, dict) or not isinstance(manifest_content.get("documents"), list):
            continue
        for entry in manifest_content["documents"]:
            if not isinstance(entry, dict):
                continue
            if entry.get("document_id") == document_id:
                if _matches_version(entry, version):
                    matching_entries.append((entry, catalog_dir))

    if not matching_entries:
        ver_str = f" v'{version}'" if version else ""
        raise DocumentNotFoundError(
            f"DOCUMENT_NOT_FOUND: Document '{document_id}'{ver_str} not found in trusted catalogs"
        )

    # If version was not specified and multiple versions exist, sort by version string
    if len(matching_entries) > 1 and version is None:
        matching_entries.sort(key=lambda t: t[0].get("version", ""), reverse=True)

    entry, _ = matching_entries[0]

    return DocumentRef(
        document_id=entry["document_id"],
        version=entry["version"],
        digest=entry["digest"],
        source=entry["source"],
        valid_from=entry.get("valid_from"),
        expires_at=entry.get("expires_at"),
        title=entry.get("title", entry["document_id"]),
    )


def compare_scoped_protocols(
    db: sqlite3.Connection | str | Path,
    identity: TrustedIdentity,
    session_id: str,
    base_document_id: str,
    target_document_id: str,
    *,
    base_version: str | None = None,
    target_version: str | None = None,
    catalog_dirs: Sequence[Path | str] | None = None,
    as_of: datetime | str | None = None,
    allow_inapplicable: bool = True,
) -> ScopedProtocolComparisonResult:
    """Execute session-authorized protocol comparison between two specification documents.

    Validates:
    1. Caller identity and session ownership in SQLite.
    2. Active project selection and authorization under assistant-access registry.
    3. Both base and target documents must be present in project['document_ids'].
    4. Cryptographic integrity and source matching via trusted catalogs.
    5. Structural difference calculation and localized sliding excerpts.

    Raises:
        KnowledgeScopeDenied: if session or project scope is invalid or selection required.
        DocumentNotAuthorizedError: if either document is not granted to the session's project.
        ProtocolComparisonError: if document cannot be found, resolved, or verified.
    """
    if not isinstance(base_document_id, str) or not base_document_id.strip():
        raise InvalidReferenceError("Base document ID must be a non-empty string")
    if not isinstance(target_document_id, str) or not target_document_id.strip():
        raise InvalidReferenceError("Target document ID must be a non-empty string")

    # 1. Authorize session and retrieve active project definition
    project = get_session_project(db, identity, session_id)

    # 2. Document authorization gate
    allowed_doc_ids = set(project.get("document_ids", []))
    if base_document_id not in allowed_doc_ids:
        raise DocumentNotAuthorizedError(
            f"DOCUMENT_NOT_AUTHORIZED: Base document '{base_document_id}' is not permitted "
            f"under project '{project['project_id']}'"
        )
    if target_document_id not in allowed_doc_ids:
        raise DocumentNotAuthorizedError(
            f"DOCUMENT_NOT_AUTHORIZED: Target document '{target_document_id}' is not permitted "
            f"under project '{project['project_id']}'"
        )

    # 3. Resolve trusted DocumentRefs directly from catalogs (no caller-supplied digests)
    resolved_catalogs = _ensure_catalog_dirs(catalog_dirs)
    base_ref = _resolve_catalog_ref(base_document_id, base_version, resolved_catalogs)
    target_ref = _resolve_catalog_ref(target_document_id, target_version, resolved_catalogs)

    # 4. Invoke verified comparison
    comparison_res = compare_protocol_versions(
        base_ref,
        target_ref,
        catalog_dirs=resolved_catalogs,
        as_of=as_of,
        allow_inapplicable=allow_inapplicable,
    )

    # 5. Assemble and return scoped result
    return ScopedProtocolComparisonResult(
        session_id=session_id,
        project_id=project["project_id"],
        tenant_id=project["tenant_id"],
        actor_id=identity.actor_id,
        grant_version=project["grant_version"],
        scope_digest=digest_json(project),
        base_document_id=base_document_id,
        target_document_id=target_document_id,
        comparison=comparison_res,
    )


def compare_scoped_protocols_safe(
    db: sqlite3.Connection | str | Path,
    identity: TrustedIdentity,
    session_id: str,
    base_document_id: str,
    target_document_id: str,
    *,
    base_version: str | None = None,
    target_version: str | None = None,
    catalog_dirs: Sequence[Path | str] | None = None,
    as_of: datetime | str | None = None,
    allow_inapplicable: bool = True,
) -> dict[str, Any]:
    """Safe wrapper returning error dictionary on failure instead of raising."""
    try:
        res = compare_scoped_protocols(
            db,
            identity,
            session_id,
            base_document_id,
            target_document_id,
            base_version=base_version,
            target_version=target_version,
            catalog_dirs=catalog_dirs,
            as_of=as_of,
            allow_inapplicable=allow_inapplicable,
        )
        return {
            "success": True,
            "error": None,
            "result": res.to_dict(),
        }
    except ProtocolComparisonError as err:
        return {
            "success": False,
            "error": {
                "reason_code": getattr(err, "reason_code", "PROTOCOL_COMPARISON_ERROR"),
                "message": str(err),
            },
            "result": None,
        }
    except (KnowledgeScopeDenied, TaskControlError) as err:
        return {
            "success": False,
            "error": {
                "reason_code": str(err),
                "message": f"Authorization error: {err}",
            },
            "result": None,
        }


def scoped_comparison_is_current(
    db: sqlite3.Connection | str | Path,
    identity: TrustedIdentity,
    session_id: str,
    comparison_result: dict[str, Any] | ScopedProtocolComparisonResult,
    *,
    catalog_dirs: Sequence[Path | str] | None = None,
) -> tuple[bool, str | None]:
    """Revalidate that a previously executed scoped comparison remains valid under current state.

    Never trusts old comparison JSON as an enduring grant. Rechecks:
    1. Session ownership and tenant matching in SQLite.
    2. Selected project is still active, granted, and matching result's project_id.
    3. Project grant_version and scope_digest match current registry.
    4. Both base and target documents remain in authorized document_ids.
    5. Underlying catalog files and digests have not been tampered with or revoked.
    """
    try:
        data = comparison_result.to_dict() if isinstance(comparison_result, ScopedProtocolComparisonResult) else comparison_result
        if not isinstance(data, dict):
            return False, "COMPARISON_RESULT_MALFORMED"

        # 1. Session, Tenant, and Actor isolation checks
        if "session_id" not in data or data.get("session_id") != session_id:
            return False, "CROSS_SESSION_COMPARISON_REJECTED"

        if "tenant_id" not in data or data.get("tenant_id") != identity.tenant_id:
            return False, "CROSS_TENANT_COMPARISON_REJECTED"

        if "actor_id" not in data or data.get("actor_id") != identity.actor_id:
            return False, "ACTOR_MISMATCH"

        # 2. Check session and active project in SQLite
        try:
            project = get_session_project(db, identity, session_id)
        except KnowledgeScopeDenied as err:
            return False, str(err)

        if data.get("project_id") != project["project_id"]:
            return False, "KNOWLEDGE_SESSION_SCOPE_CHANGED"

        # 2. Check document authorization still active in project
        allowed_docs = set(project.get("document_ids", []))
        base_ref = data.get("base_ref", {})
        target_ref = data.get("target_ref", {})
        base_id = base_ref.get("document_id")
        target_id = target_ref.get("document_id")

        if base_id not in allowed_docs or target_id not in allowed_docs:
            return False, "DOCUMENT_AUTHORIZATION_REVOKED"

        # 3. Check grant version and scope digest
        if data.get("grant_version") != project["grant_version"] or data.get("scope_digest") != digest_json(project):
            return False, "KNOWLEDGE_GRANT_CHANGED"

        # Preserve the original content digest check, then recompute the full
        # public comparison. The digest intentionally remains compatible with
        # the comparison engine; it is not a digest of every presentation field.
        res_data = {
            "base_digest": base_ref.get("digest"),
            "target_digest": target_ref.get("digest"),
            "identical": data.get("identical"),
            "diff_count": data.get("diff_count"),
        }
        if not data.get("identical"):
            res_data["differences"] = data.get("differences", [])
        if data.get("comparison_digest") != digest_json(res_data):
            return False, "COMPARISON_DIGEST_MISMATCH"

        # Rebuild all user-visible fields from the current trusted catalog. This
        # also detects edits to summary, diff excerpts, uncertainty notices and
        # other fields not covered by the legacy comparison_digest.
        try:
            current = compare_scoped_protocols(
                db,
                identity,
                session_id,
                base_document_id=base_id,
                target_document_id=target_id,
                base_version=str(base_ref.get("version")),
                target_version=str(target_ref.get("version")),
                catalog_dirs=catalog_dirs,
            ).to_dict()
        except (DocumentIntegrityError, DocumentNotFoundError, DocumentExpiredError):
            return False, "DOCUMENT_INTEGRITY_OR_EXPIRED"
        except ProtocolComparisonError:
            return False, "COMPARISON_SOURCE_INVALID"

        supplied = {key: value for key, value in data.items()
                    if key not in {"compared_at", "success"}}
        recomputed = {key: value for key, value in current.items()
                      if key not in {"compared_at", "success"}}
        if canonical_json(supplied) != canonical_json(recomputed):
            return False, "COMPARISON_RESULT_CHANGED_OR_TAMPERED"

        return True, None
    except (KnowledgeScopeDenied, TaskControlError, ProtocolComparisonError, ValueError, TypeError, KeyError, AttributeError):
        return False, "KNOWLEDGE_SCOPE_OR_SOURCE_INVALID"


def _infer_family(document_id: str) -> str:
    """Infer protocol family grouping key from document_id."""
    stem = re.sub(r"-v\d+.*$", "", document_id)
    stem = re.sub(r"-(contract|spec|protocol)$", "", stem)
    return stem or document_id


_TOPIC_ALIASES = (
    ("回调", "callback"),
    ("重试", "retry"),
    ("失败", "failure"),
    ("策略", "policy"),
)


def _topic_terms(topic: str) -> tuple[str, ...]:
    """Normalize short English/Chinese topic expressions into metadata terms.

    English words are matched independently across the authorized entry's
    metadata, so a phrase such as "callback retry" need not appear verbatim in
    one field. The small bilingual aliases cover the callback terminology
    already used by the catalog; this is not document-content search.
    """
    normalized = topic.casefold().strip()
    terms = set(re.findall(r"[a-z0-9]+", normalized))
    for source, target in _TOPIC_ALIASES:
        if source in normalized:
            terms.add(target)
    if terms:
        return tuple(sorted(terms))
    compact = re.sub(r"\s+", "", normalized)
    return (compact,) if compact else ()


def list_scoped_protocols(
    db: sqlite3.Connection | str | Path,
    identity: TrustedIdentity,
    session_id: str,
    *,
    topic: str | None = None,
    catalog_dirs: Sequence[Path | str] | None = None,
) -> dict[str, Any]:
    """List and discover authorized protocol documents and versions under the authenticated session.

    Enforces:
    1. Caller identity and session ownership in SQLite.
    2. Active project selection and authorization under assistant-access registry.
    3. Strict isolation: only documents in project['document_ids'] can be discovered.
    4. Optional topic filtering over document_id, title, file, and keywords.
    5. Grouping into protocol families with versions for easy Agent discovery.
    6. Epistemic boundary: discovery results do not prove cluster deployment state.
    """
    project = get_session_project(db, identity, session_id)
    allowed_doc_ids = set(project.get("document_ids", []))

    resolved_catalogs = _ensure_catalog_dirs(catalog_dirs)
    topic_str = topic.strip() if (isinstance(topic, str) and topic.strip()) else None
    topic_terms = _topic_terms(topic_str) if topic_str else ()

    discovered_docs: dict[str, dict[str, Any]] = {}

    for catalog_dir in resolved_catalogs:
        manifest_path = catalog_dir / "manifest.json"
        if not manifest_path.is_file():
            continue
        try:
            manifest_content = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(manifest_content, dict) or not isinstance(manifest_content.get("documents"), list):
            continue

        for entry in manifest_content["documents"]:
            if not isinstance(entry, dict):
                continue
            doc_id = entry.get("document_id")
            if not doc_id or doc_id not in allowed_doc_ids:
                continue

            if topic_terms:
                keywords = [str(kw) for kw in entry.get("keywords", [])]
                searchable = " ".join((
                    str(doc_id),
                    str(entry.get("title", "")),
                    str(entry.get("file", "")),
                    *keywords,
                )).casefold()
                if not all(term in searchable for term in topic_terms):
                    continue

            if doc_id not in discovered_docs:
                ref = DocumentRef(
                    document_id=str(doc_id),
                    version=str(entry.get("version", "1.0.0")),
                    digest=str(entry.get("digest", "")),
                    source=str(entry.get("source", "")),
                    valid_from=entry.get("valid_from"),
                    expires_at=entry.get("expires_at"),
                    title=entry.get("title", doc_id),
                )
                resolved = resolve_document(ref, catalog_dirs=[catalog_dir])
                discovered_docs[doc_id] = {
                    "document_id": resolved.document_id,
                    "title": resolved.title,
                    "version": resolved.version,
                    "contract_versions": entry.get("contract_versions", []),
                    "source": resolved.source,
                    "digest": resolved.digest,
                    "valid_from": resolved.valid_from,
                    "expires_at": resolved.expires_at,
                    "keywords": entry.get("keywords", []),
                }

    doc_list = list(discovered_docs.values())
    doc_list.sort(key=lambda d: d["document_id"])

    families_map: dict[str, list[dict[str, Any]]] = {}
    for doc in doc_list:
        family = _infer_family(doc["document_id"])
        families_map.setdefault(family, []).append(doc)

    protocols = []
    for family_name, f_docs in sorted(families_map.items()):
        protocols.append({
            "family": family_name,
            "document_ids": [d["document_id"] for d in f_docs],
            "versions": [d["version"] for d in f_docs],
            "documents": f_docs,
        })

    return {
        "session_id": session_id,
        "project_id": project["project_id"],
        "tenant_id": project["tenant_id"],
        "actor_id": identity.actor_id,
        "grant_version": project["grant_version"],
        "scope_digest": digest_json(project),
        "topic": topic,
        "protocol_documents": doc_list,
        "protocols": protocols,
        "document_count": len(doc_list),
        "deployment_version_verified": False,
        "authority": "SESSION_AUTHORIZED_DISCOVERY_NOT_ACTION_AUTHORIZATION",
    }


def scoped_discovery_is_current(
    db: sqlite3.Connection | str | Path,
    identity: TrustedIdentity,
    session_id: str,
    discovery_result: dict[str, Any],
    *,
    catalog_dirs: Sequence[Path | str] | None = None,
) -> tuple[bool, str | None]:
    """Revalidate that previously executed protocol discovery remains valid under current state.

    Never trusts old discovery JSON as an enduring grant. Rechecks:
    1. Session ownership and tenant matching in SQLite.
    2. Selected project is still active, granted, and matching result's project_id.
    3. Project grant_version and scope_digest match current registry.
    4. All discovered documents remain in authorized document_ids.
    5. Underlying catalog files and digests have not been tampered with or revoked.
    """
    try:
        if not isinstance(discovery_result, dict):
            return False, "DISCOVERY_RESULT_MALFORMED"

        if "session_id" not in discovery_result or discovery_result.get("session_id") != session_id:
            return False, "CROSS_SESSION_DISCOVERY_REJECTED"

        if "tenant_id" not in discovery_result or discovery_result.get("tenant_id") != identity.tenant_id:
            return False, "CROSS_TENANT_DISCOVERY_REJECTED"

        if "actor_id" not in discovery_result or discovery_result.get("actor_id") != identity.actor_id:
            return False, "ACTOR_MISMATCH"

        try:
            project = get_session_project(db, identity, session_id)
        except KnowledgeScopeDenied as err:
            return False, str(err)

        if discovery_result.get("project_id") != project["project_id"]:
            return False, "KNOWLEDGE_SESSION_SCOPE_CHANGED"

        if discovery_result.get("grant_version") != project["grant_version"] or discovery_result.get("scope_digest") != digest_json(project):
            return False, "KNOWLEDGE_GRANT_CHANGED"

        allowed_docs = set(project.get("document_ids", []))
        docs = discovery_result.get("protocol_documents", [])
        if not isinstance(docs, list):
            return False, "DISCOVERY_RESULT_MALFORMED"

        for doc in docs:
            if not isinstance(doc, dict):
                return False, "DISCOVERY_RESULT_MALFORMED"
            doc_id = doc.get("document_id")
            if not doc_id or doc_id not in allowed_docs:
                return False, "DOCUMENT_AUTHORIZATION_REVOKED"

        try:
            resolved_catalogs = _ensure_catalog_dirs(catalog_dirs)
            for doc in docs:
                ref = DocumentRef(
                    document_id=doc["document_id"],
                    version=str(doc.get("version", "1.0.0")),
                    digest=str(doc.get("digest", "")),
                    source=str(doc.get("source", "")),
                    valid_from=doc.get("valid_from"),
                    expires_at=doc.get("expires_at"),
                    title=doc.get("title", doc["document_id"]),
                )
                resolved = resolve_document(ref, catalog_dirs=resolved_catalogs)
                if resolved.digest != doc.get("digest"):
                    return False, "DOCUMENT_INTEGRITY_OR_EXPIRED"
        except (DocumentIntegrityError, DocumentNotFoundError):
            return False, "DOCUMENT_INTEGRITY_OR_EXPIRED"

        # Recreate the complete discovery projection and compare every exposed
        # field. Checking each document digest alone would still allow a caller
        # to alter protocol groups, labels, versions or topic metadata.
        current = list_scoped_protocols(
            db, identity, session_id,
            topic=discovery_result.get("topic"),
            catalog_dirs=catalog_dirs,
        )
        supplied = {key: value for key, value in discovery_result.items() if key != "success"}
        if canonical_json(supplied) != canonical_json(current):
            return False, "DISCOVERY_RESULT_CHANGED_OR_TAMPERED"
        return True, None
    except (KnowledgeScopeDenied, TaskControlError, ProtocolComparisonError, ValueError, TypeError, KeyError, AttributeError):
        return False, "KNOWLEDGE_SCOPE_OR_SOURCE_INVALID"
