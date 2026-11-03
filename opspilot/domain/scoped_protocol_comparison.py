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
import hashlib
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


MAX_PROTOCOL_EXCERPTS = 3
MAX_PROTOCOL_EXCERPT_CHARS = 1600


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
_TOPIC_GENERIC_WORDS = {
    "a", "an", "and", "about", "compare", "comparison", "document", "documents",
    "docs", "find", "for", "in", "list", "of", "please", "protocol", "protocols",
    "related", "search", "show", "the", "to", "version", "versions", "with",
    "behavior", "behaviour",
}
_TOPIC_GENERIC_CJK = {"协议", "文档", "资料", "版本", "查询", "检索", "比较", "相关"}


def _normalize_topic_word(value: str) -> str:
    """Apply a small, deterministic normalization without a growing synonym table."""
    word = value.casefold()
    if len(word) > 4 and word.endswith("ies"):
        return word[:-3] + "y"
    if len(word) > 5 and word.endswith("ing"):
        return word[:-3]
    if len(word) > 4 and word.endswith("ed"):
        return word[:-2]
    if len(word) > 3 and word.endswith("s") and not word.endswith("ss"):
        return word[:-1]
    return word


def _topic_terms(topic: str) -> tuple[str, ...]:
    """Normalize English words and Chinese character bigrams for metadata retrieval.

    This is bounded catalog-metadata matching, not content search. Generic query
    wording is discarded; the few existing bilingual domain terms stay stable
    while ordinary descriptor words no longer have to exist in document text.
    """
    normalized = topic.casefold().strip()
    terms = {
        _normalize_topic_word(word)
        for word in re.findall(r"[a-z0-9]+", normalized)
        if _normalize_topic_word(word) not in _TOPIC_GENERIC_WORDS
    }
    for run in re.findall(r"[\u3400-\u9fff]+", normalized):
        if len(run) == 1:
            if run not in _TOPIC_GENERIC_CJK:
                terms.add(run)
            continue
        for index in range(len(run) - 1):
            term = run[index:index + 2]
            if term not in _TOPIC_GENERIC_CJK:
                terms.add(term)
    for source, target in _TOPIC_ALIASES:
        if source in normalized:
            terms.add(target)
    return tuple(sorted(term for term in terms if term))


def _topic_relevance(topic_terms: tuple[str, ...], entry: dict[str, Any]) -> int:
    if not topic_terms:
        return 0
    searchable = " ".join((
        str(entry.get("document_id", "")),
        str(entry.get("title", "")),
        str(entry.get("file", "")),
        *(str(keyword) for keyword in entry.get("keywords", []) if keyword is not None),
    ))
    return len(set(topic_terms).intersection(_topic_terms(searchable)))


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
    relevance_scores: dict[str, int] = {}

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

            relevance = _topic_relevance(topic_terms, entry) if topic_terms else 0
            if topic_terms and relevance == 0:
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
                relevance_scores[doc_id] = relevance

    doc_list = list(discovered_docs.values())
    doc_list.sort(key=lambda d: (-relevance_scores.get(d["document_id"], 0), d["document_id"]))

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


def _protocol_excerpt_rows(
    content: str, query: str, *, start_line: int, start_column: int,
) -> tuple[list[dict[str, Any]], dict[str, int] | None]:
    """Select a few exact, bounded source lines and return a continuation cursor."""
    lines = content.splitlines() or [content]
    if type(start_line) is not int or type(start_column) is not int:
        raise InvalidReferenceError("INVALID_PROTOCOL_EXCERPT_CURSOR")
    if start_line < 1 or start_line > len(lines) or start_column < 1:
        raise InvalidReferenceError("INVALID_PROTOCOL_EXCERPT_CURSOR")
    if start_column > len(lines[start_line - 1]) + 1:
        raise InvalidReferenceError("INVALID_PROTOCOL_EXCERPT_CURSOR")
    terms = _topic_terms(query)
    headings: dict[int, str] = {}
    current_heading = "Root"
    for number, line in enumerate(lines, start=1):
        if line.lstrip().startswith("#"):
            current_heading = line.lstrip(" #\t")[:160] or "Untitled section"
        headings[number] = current_heading

    ranked: list[tuple[int, int]] = []
    for index, line in enumerate(lines[start_line - 1:], start=start_line - 1):
        line_terms = set(_topic_terms(line))
        score = len(line_terms.intersection(terms)) if terms else 0
        if score:
            ranked.append((score, index))
    if ranked:
        selected = [index for _, index in sorted(ranked, key=lambda pair: (-pair[0], pair[1]))[:MAX_PROTOCOL_EXCERPTS]]
    else:
        selected = list(range(start_line - 1, min(start_line - 1 + MAX_PROTOCOL_EXCERPTS, len(lines))))

    rows: list[dict[str, Any]] = []
    remaining = MAX_PROTOCOL_EXCERPT_CHARS
    next_cursor: dict[str, int] | None = None
    last_complete_line = start_line - 1
    for index in sorted(set(selected)):
        if remaining <= 0:
            break
        source_line = lines[index]
        column_offset = start_column - 1 if index == start_line - 1 else 0
        text = source_line[column_offset:]
        truncated = False
        if len(text) > remaining:
            offsets = [text.casefold().find(term.casefold()) for term in terms]
            offsets = [offset for offset in offsets if offset >= 0]
            if offsets:
                local_start = max(0, min(offsets) - min(160, remaining // 4))
                column_offset += local_start
                text = source_line[column_offset:column_offset + remaining]
            else:
                text = text[:remaining]
            truncated = True
        if not text:
            last_complete_line = max(last_complete_line, index + 1)
            continue
        column_start = column_offset + 1
        rows.append({
            "section": headings[index + 1],
            "line_start": index + 1,
            "line_end": index + 1,
            "column_start": column_start,
            "column_end": column_start + len(text) - 1,
            "text": text,
            "excerpt_digest": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            "truncated": truncated,
        })
        remaining -= len(text)
        if truncated:
            next_cursor = {"line": index + 1, "column": column_start + len(text)}
            break
        last_complete_line = index + 1
    if next_cursor is None and last_complete_line < len(lines):
        next_cursor = {"line": last_complete_line + 1, "column": 1}
    return rows, next_cursor


def read_scoped_protocol_excerpt(
    db: sqlite3.Connection | str | Path,
    identity: TrustedIdentity,
    session_id: str,
    *,
    document_id: str,
    version: str,
    query: str,
    start_line: int = 1,
    start_column: int = 1,
    catalog_dirs: Sequence[Path | str] | None = None,
) -> dict[str, Any]:
    """Read bounded original text from a document currently authorized for this Session.

    The caller supplies only a discovered document identity and a bounded topic.
    File paths and digests are resolved from the trusted catalog after the
    current Session grant is checked. The result is static method evidence,
    never a runtime deployment or business fact.
    """
    if not isinstance(document_id, str) or not document_id.strip() or len(document_id) > 120:
        raise InvalidReferenceError("INVALID_DOCUMENT_ID")
    if not isinstance(version, str) or not version.strip() or len(version) > 40:
        raise InvalidReferenceError("INVALID_DOCUMENT_VERSION")
    if not isinstance(query, str) or not query.strip() or len(query) > 200:
        raise InvalidReferenceError("INVALID_PROTOCOL_EXCERPT_QUERY")

    project = get_session_project(db, identity, session_id)
    if document_id not in set(project.get("document_ids", [])):
        raise DocumentNotAuthorizedError("DOCUMENT_NOT_AUTHORIZED")

    catalogs = _ensure_catalog_dirs(catalog_dirs)
    ref = _resolve_catalog_ref(document_id, version, catalogs)
    if ref.version != version:
        raise DocumentNotFoundError("DOCUMENT_VERSION_NOT_FOUND")
    resolved = resolve_document(ref, catalog_dirs=catalogs)
    excerpts, next_cursor = _protocol_excerpt_rows(
        resolved.content, query.strip(), start_line=start_line, start_column=start_column,
    )
    return {
        "session_id": session_id,
        "project_id": project["project_id"],
        "tenant_id": identity.tenant_id,
        "actor_id": identity.actor_id,
        "grant_version": project["grant_version"],
        "scope_digest": digest_json(project),
        "document_ref": {
            "document_id": resolved.document_id,
            "title": resolved.title,
            "version": resolved.version,
            "source": resolved.source,
            "digest": resolved.digest,
            "valid_from": resolved.valid_from,
            "expires_at": resolved.expires_at,
        },
        "query": query.strip(),
        "start_line": start_line,
        "start_column": start_column,
        "excerpts": excerpts,
        "next_cursor": next_cursor,
        "source_refs": [{
            "document_id": resolved.document_id,
            "version": resolved.version,
            "source": resolved.source,
            "digest": resolved.digest,
            "line_start": excerpt["line_start"],
            "line_end": excerpt["line_end"],
            "column_start": excerpt["column_start"],
            "column_end": excerpt["column_end"],
            "excerpt_digest": excerpt["excerpt_digest"],
        } for excerpt in excerpts],
        "authority": "SESSION_AUTHORIZED_ORIGINAL_TEXT_NOT_RUNTIME_EVIDENCE",
        "deployment_version_verified": False,
    }


def scoped_protocol_excerpt_is_current(
    db: sqlite3.Connection | str | Path,
    identity: TrustedIdentity,
    session_id: str,
    excerpt_result: dict[str, Any],
    *,
    catalog_dirs: Sequence[Path | str] | None = None,
) -> tuple[bool, str | None]:
    """Recheck current grant, catalog digest, excerpt text and source locations."""
    try:
        if not isinstance(excerpt_result, dict):
            return False, "PROTOCOL_EXCERPT_RESULT_MALFORMED"
        if excerpt_result.get("session_id") != session_id:
            return False, "CROSS_SESSION_PROTOCOL_EXCERPT_REJECTED"
        if excerpt_result.get("tenant_id") != identity.tenant_id:
            return False, "CROSS_TENANT_PROTOCOL_EXCERPT_REJECTED"
        if excerpt_result.get("actor_id") != identity.actor_id:
            return False, "PROTOCOL_EXCERPT_ACTOR_MISMATCH"
        ref = excerpt_result.get("document_ref")
        if not isinstance(ref, dict):
            return False, "PROTOCOL_EXCERPT_RESULT_MALFORMED"
        current = read_scoped_protocol_excerpt(
            db, identity, session_id,
            document_id=ref.get("document_id"),
            version=ref.get("version"),
            query=excerpt_result.get("query"),
            start_line=excerpt_result.get("start_line"),
            start_column=excerpt_result.get("start_column"),
            catalog_dirs=catalog_dirs,
        )
        supplied = {key: value for key, value in excerpt_result.items() if key != "success"}
        if canonical_json(supplied) != canonical_json(current):
            return False, "PROTOCOL_EXCERPT_RESULT_CHANGED_OR_TAMPERED"
        return True, None
    except (KnowledgeScopeDenied, TaskControlError, ProtocolComparisonError, ValueError, TypeError, KeyError, AttributeError):
        return False, "PROTOCOL_EXCERPT_SCOPE_OR_SOURCE_INVALID"


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
