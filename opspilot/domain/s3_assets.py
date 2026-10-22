"""Small S3 lexical retrieval and finite Skill catalog, sharing D5 provenance.

Assets can teach methods, never authorize actions or supply live business facts.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import datetime, timezone

from opspilot.config import ROOT

DIRECTORY = ROOT / "knowledge" / "async-callback"
SKILLS = ("order-lifecycle-triage", "callback-delivery-triage")


def load_knowledge():
    # A trusted local smoke may select an isolated asset copy; never a tool argument.
    directory = DIRECTORY
    override = os.environ.get("OPSPILOT_S3_KNOWLEDGE_DIRECTORY")
    if override:
        from pathlib import Path
        directory = Path(override).resolve()
        if not directory.is_relative_to((ROOT / ".runtime/m4-02").resolve()):
            raise ValueError("S3 test Knowledge directory must stay within its runtime workspace")
    try:
        manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    result = []
    for doc in manifest.get("documents", []):
        try:
            filename = doc["file"]
            if not re.fullmatch(r"[a-z0-9-]+\.md", filename):
                continue
            body = (directory / filename).read_bytes()
            if (doc.get("active") is not True or hashlib.sha256(body).hexdigest() != doc["digest"]
                or datetime.fromisoformat(doc["valid_from"]) > datetime.now(timezone.utc)
                or datetime.fromisoformat(doc["expires_at"]) <= datetime.now(timezone.utc)):
                continue
            result.append({**doc, "content": body.decode("utf-8")[:2400], "applicable":"true"})
        except (OSError, ValueError, KeyError, TypeError):
            continue
    return result


def search_knowledge(query: str, *, limit: int = 1):
    if not query.strip() or len(query) > 300 or limit != 1:
        raise ValueError("Knowledge query must be bounded and non-empty")
    terms = set(re.findall(r"[a-z0-9]+|[\u4e00-\u9fff]", query.lower()))
    ranked = []
    for doc in load_knowledge():
        text = f"{doc['title']} {' '.join(doc['keywords'])} {doc['content']}".lower()
        score = sum(1 for term in terms if term in text)
        if score:
            ranked.append((score, doc))
    ranked.sort(key=lambda item: (-item[0], item[1]["document_id"]))
    return [{**doc, "retrieval_score":score, "query":query} for score, doc in ranked[:limit]]


def skill_catalog():
    return [{"name":"order-lifecycle-triage","description":"Distinguish HTTP success from completed order lifecycle; callback may not yet be due."},
            {"name":"callback-delivery-triage","description":"Correlate callback event transport, acknowledgement and receiver processing; no resend."}]


def load_s3_skill(name: str):
    if name not in SKILLS:
        raise ValueError("Skill is outside the reviewed S3 catalog")
    directory = ROOT / "skills" / name
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    raw = (directory / "SKILL.md").read_bytes()
    if (manifest["name"] != name or manifest["problem_type"] != "async_callback"
        or not re.fullmatch(r"(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)",str(manifest.get("version","")))
        or manifest.get("skill_file") != "SKILL.md" or manifest.get("digest_algorithm") != "sha256"
        or hashlib.sha256(raw).hexdigest() != manifest["digest"]):
        raise ValueError("S3 Skill integrity mismatch")
    return {**manifest, "content":raw.decode("utf-8")[:2400]}


def refresh_asset_refs(draft):
    """Checkpoint contains references only. Reload current text before every call."""
    knowledge, skill, excluded = [], None, []
    current_docs = {doc["document_id"]:doc for doc in load_knowledge()}
    for ref in draft.get("s3_knowledge_refs", []):
        doc = current_docs.get(ref["document_id"])
        if doc and all(doc.get(k) == ref.get(k) for k in ("version","digest","source","valid_from")):
            knowledge.append(doc)
        else:
            excluded.append({"source_type":"KNOWLEDGE","source_id":ref["document_id"],"reason":"KNOWLEDGE_REMOVED_EXPIRED_OR_CHANGED"})
    ref = draft.get("s3_skill_ref")
    if ref:
        try:
            item = load_s3_skill(ref["name"])
            if not all(item[k] == ref[k] for k in ("version","digest")):
                raise ValueError("changed")
            skill = item
        except (OSError, ValueError, KeyError):
            excluded.append({"source_type":"SKILL","source_id":ref["name"],"reason":"SKILL_REMOVED_OR_CHANGED"})
    return knowledge, skill, excluded
