from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from opspilot.config import ROOT


KNOWLEDGE_DIRECTORY = ROOT / "knowledge" / "api-scope"
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class KnowledgeIntegrityError(RuntimeError):
    pass


def load_scope_knowledge(service_id: str, *, include_legacy: bool = False) -> list[dict[str, str]]:
    """Load only digest-verified versioned scope documents applicable to this service."""
    try:
        manifest = json.loads((KNOWLEDGE_DIRECTORY / "manifest.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise KnowledgeIntegrityError("The API Scope Knowledge manifest is unavailable or invalid.") from error
    if not isinstance(manifest, dict) or manifest.get("schema_version") != 1 or not isinstance(manifest.get("documents"), list):
        raise KnowledgeIntegrityError("The API Scope Knowledge manifest schema is invalid.")
    selected: list[dict[str, str]] = []
    for raw in manifest["documents"]:
        if not isinstance(raw, dict) or raw.get("service_id") != service_id:
            continue
        if not raw.get("applicable") and not include_legacy:
            continue
        filename = raw.get("file")
        digest = raw.get("digest")
        if (
            not isinstance(filename, str) or Path(filename).name != filename
            or raw.get("digest_algorithm") != "sha256" or not isinstance(digest, str)
            or not _SHA256.fullmatch(digest)
        ):
            raise KnowledgeIntegrityError("An API Scope Knowledge entry is malformed.")
        path = (KNOWLEDGE_DIRECTORY / filename).resolve()
        if path.parent != KNOWLEDGE_DIRECTORY.resolve():
            raise KnowledgeIntegrityError("An API Scope Knowledge path escapes its asset directory.")
        try:
            body = path.read_bytes()
        except OSError as error:
            raise KnowledgeIntegrityError("An API Scope Knowledge document is unavailable.") from error
        actual = hashlib.sha256(body).hexdigest()
        if actual != digest:
            raise KnowledgeIntegrityError("An API Scope Knowledge document digest does not match its manifest.")
        try:
            content = body.decode("utf-8")
        except UnicodeDecodeError as error:
            raise KnowledgeIntegrityError("An API Scope Knowledge document is not UTF-8.") from error
        selected.append({
            "document_id": str(raw["document_id"]), "version": str(raw["version"]),
            "digest": actual, "source": str(raw["source"]), "valid_from": str(raw["valid_from"]),
            "applicable": str(bool(raw["applicable"])).lower(), "content": content[:4000],
        })
    return selected
