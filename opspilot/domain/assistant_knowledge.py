"""Small, server-owned Demo document scopes for Sessions without a business Task.

This mapping grants only document reads. It is not a business TaskBinding,
Semantic Memory approval grant, deployment observation, or production IAM.
"""
from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path
from typing import Any

from opspilot.config import ROOT
from opspilot.domain.database import connect
from opspilot.domain.d2 import digest_json, utc_now
from opspilot.domain.s3_assets import load_knowledge, search_knowledge
from opspilot.domain.task_control import TaskControlError, TrustedIdentity, _verify_identity

REGISTRY = ROOT / "knowledge" / "assistant-access.json"
SCHEMA = """
CREATE TABLE IF NOT EXISTS assistant_session_scopes (
    session_id TEXT PRIMARY KEY REFERENCES sessions(session_id) ON DELETE CASCADE,
    project_id TEXT NOT NULL,
    selected_at TEXT NOT NULL
);
"""


class KnowledgeScopeDenied(TaskControlError):
    pass


def _registry() -> list[dict[str, Any]]:
    """Reload on every access; malformed policy cannot become a permission."""
    try:
        value = json.loads(Path(REGISTRY).read_text(encoding="utf-8"))
        if type(value.get("schema_version")) is not int or value["schema_version"] != 1:
            raise ValueError("Unsupported registry")
        projects = value["projects"]
        if not isinstance(projects, list):
            raise ValueError("Invalid project list")
        seen: set[tuple[str, str]] = set()
        for project in projects:
            key = (project["tenant_id"], project["project_id"])
            if key in seen:
                raise ValueError("Ambiguous project grant")
            seen.add(key)
            if (
                not all(isinstance(v, str) and v for v in key)
                or not re.fullmatch(r"[a-z0-9][a-z0-9-]{1,63}", project["project_id"])
                or type(project["active"]) is not bool
                or type(project["grant_version"]) is not int or project["grant_version"] < 1
                or type(project["configured_contract_version"]) is not int
                or project["configured_contract_version"] < 1
                or not isinstance(project["title"], str)
            ):
                raise ValueError("Invalid grant fields")
            for name in ("actor_ids", "roles", "document_ids"):
                entries = project[name]
                if not isinstance(entries, list) or not entries or any(not isinstance(v, str) or not v for v in entries):
                    raise ValueError("Invalid grant membership")
        return projects
    except (OSError, ValueError, TypeError, KeyError, AttributeError) as error:
        raise KnowledgeScopeDenied("KNOWLEDGE_REGISTRY_UNAVAILABLE") from error


def _session(connection: sqlite3.Connection, identity: TrustedIdentity, session_id: str) -> None:
    _verify_identity(connection, identity)
    if connection.execute(
        "SELECT 1 FROM sessions WHERE session_id=? AND tenant_id=? AND owner_id=?",
        (session_id, identity.tenant_id, identity.actor_id),
    ).fetchone() is None:
        raise KnowledgeScopeDenied("SESSION_SCOPE_DENIED")


def _allowed(identity: TrustedIdentity) -> list[dict[str, Any]]:
    return [p for p in _registry() if p["active"] and p["tenant_id"] == identity.tenant_id
            and identity.actor_id in p["actor_ids"] and identity.role in p["roles"]]


def _scope(connection: sqlite3.Connection, identity: TrustedIdentity, session_id: str) -> tuple[list[dict[str, Any]], str | None]:
    _session(connection, identity, session_id)
    projects = _allowed(identity)
    current = connection.execute(
        "SELECT project_id FROM assistant_session_scopes WHERE session_id=?", (session_id,),
    ).fetchone()
    allowed_ids = {p["project_id"] for p in projects}
    selected = str(current["project_id"]) if current and current["project_id"] in allowed_ids else None
    if selected is None and len(projects) == 1:
        selected = projects[0]["project_id"]
    return projects, selected


def _projection(projects: list[dict[str, Any]], selected: str | None) -> dict[str, Any]:
    return {
        "items": [{"project_id": p["project_id"], "title": p["title"],
                   "configured_contract_version": p["configured_contract_version"],
                   "grant_version": p["grant_version"]} for p in projects],
        "selected_project": selected,
        "selection_required": selected is None and len(projects) > 1,
        "reason_code": "KNOWLEDGE_SCOPE_SELECTION_REQUIRED" if selected is None and projects
                       else "KNOWLEDGE_SCOPE_DENIED" if not projects else None,
    }


def list_scopes(path: str | Path, identity: TrustedIdentity, session_id: str) -> dict[str, Any]:
    with connect(path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        projects, selected = _scope(connection, identity, session_id)
        if selected is not None:
            connection.execute(
                "INSERT INTO assistant_session_scopes(session_id,project_id,selected_at) VALUES (?,?,?) "
                "ON CONFLICT(session_id) DO UPDATE SET project_id=excluded.project_id,selected_at=excluded.selected_at "
                "WHERE assistant_session_scopes.project_id != excluded.project_id",
                (session_id, selected, utc_now()),
            )
        return _projection(projects, selected)


def select_scope(path: str | Path, identity: TrustedIdentity, session_id: str, project_id: str) -> dict[str, Any]:
    with connect(path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        _session(connection, identity, session_id)
        projects = _allowed(identity)
        if project_id not in {p["project_id"] for p in projects}:
            raise KnowledgeScopeDenied("KNOWLEDGE_SCOPE_DENIED")
        connection.execute(
            "INSERT INTO assistant_session_scopes(session_id,project_id,selected_at) VALUES (?,?,?) "
            "ON CONFLICT(session_id) DO UPDATE SET project_id=excluded.project_id,selected_at=excluded.selected_at",
            (session_id, project_id, utc_now()),
        )
        return _projection(projects, project_id)


def _documents(project: dict[str, Any], contract_version: int | None = None) -> list[dict[str, Any]]:
    allowed = set(project["document_ids"])
    return [d for d in load_knowledge(contract_version=contract_version) if d["document_id"] in allowed]


def search(path: str | Path, identity: TrustedIdentity, session_id: str, query: str,
           contract_version: int | None = None) -> dict[str, Any]:
    if contract_version is not None and (type(contract_version) is not int or contract_version < 1):
        raise ValueError("Requested contract version must be a positive integer preference")
    with connect(path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        projects, selected = _scope(connection, identity, session_id)
        if selected is None:
            raise KnowledgeScopeDenied("KNOWLEDGE_SCOPE_SELECTION_REQUIRED" if projects else "KNOWLEDGE_SCOPE_DENIED")
        project = next(p for p in projects if p["project_id"] == selected)
        connection.execute(
            "INSERT OR IGNORE INTO assistant_session_scopes(session_id,project_id,selected_at) VALUES (?,?,?)",
            (session_id, selected, utc_now()),
        )
        configured = project["configured_contract_version"]
        selected_version = contract_version if contract_version is not None else configured
        allowed_documents = _documents(project)
        allowed_ids = {d["document_id"] for d in allowed_documents}
        # Reuse the existing bounded Demo retriever (current catalog has six
        # documents), then apply the grant before returning any text or refs.
        documents = [d for d in search_knowledge(query, limit=8, contract_version=selected_version)
                     if d["document_id"] in allowed_ids][:3]
        documents = [{k: v for k, v in d.items() if k != "applicable"} for d in documents]
        versions = sorted({v for d in allowed_documents for v in d["contract_versions"]})
        refs = [{k: d[k] for k in ("document_id", "version", "digest", "source", "valid_from", "expires_at")}
                for d in documents]
        return {
            "project_id": selected,
            "grant_version": project["grant_version"],
            "scope_digest": digest_json(project),
            "documents": documents,
            "source_refs": refs,
            "requested_contract_version": contract_version,
            "configured_contract_version": configured,
            "retrieved_contract_version": selected_version,
            "latest_available_contract_version": max(versions) if versions else None,
            "version_conflict": contract_version is not None and contract_version != configured,
            "deployment_version_verified": False,
            "configuration_scope": "TRUSTED_DEMO_DOCUMENT_PROJECT_NOT_LIVE_DEPLOYMENT",
            "authority": "HISTORICAL_METHOD_ONLY_NOT_CURRENT_BUSINESS_EVIDENCE",
        }


def sources_current(connection: sqlite3.Connection, identity: TrustedIdentity,
                    session_id: str, result: dict[str, Any]) -> tuple[bool, str | None]:
    """Revalidate persisted tool refs; never trust old JSON as a current grant."""
    try:
        projects, selected = _scope(connection, identity, session_id)
        if not isinstance(result, dict) or result.get("project_id") != selected:
            return False, "KNOWLEDGE_SESSION_SCOPE_CHANGED"
        project = next((p for p in projects if p["project_id"] == selected), None)
        if project is None:
            return False, "KNOWLEDGE_SCOPE_DENIED"
        if (type(result.get("grant_version")) is not int or result["grant_version"] != project["grant_version"]
                or result.get("scope_digest") != digest_json(project)):
            return False, "KNOWLEDGE_GRANT_CHANGED"
        documents, refs = result.get("documents"), result.get("source_refs")
        if not isinstance(documents, list) or not isinstance(refs, list) or len(documents) != len(refs):
            return False, "KNOWLEDGE_SOURCE_INVALID"
        current = {d["document_id"]: d for d in _documents(project)}
        ref_ids = [r.get("document_id") for r in refs if isinstance(r, dict)]
        if len(ref_ids) != len(refs) or len(set(ref_ids)) != len(ref_ids):
            return False, "KNOWLEDGE_SOURCE_INVALID"
        if [d.get("document_id") for d in documents if isinstance(d, dict)] != ref_ids:
            return False, "KNOWLEDGE_SOURCE_INVALID"
        for doc, ref in zip(documents, refs):
            item = current.get(ref["document_id"])
            fields = ("document_id", "version", "digest", "source", "valid_from", "expires_at")
            if item is None or any(ref.get(k) != item.get(k) or doc.get(k) != item.get(k) for k in fields):
                return False, "KNOWLEDGE_REMOVED_EXPIRED_OR_CHANGED"
            if doc.get("content") != item["content"]:
                return False, "KNOWLEDGE_SOURCE_CONTENT_MISMATCH"
        return True, None
    except (KnowledgeScopeDenied, TaskControlError, ValueError, TypeError, KeyError):
        return False, "KNOWLEDGE_SCOPE_OR_SOURCE_INVALID"
