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
_S3_RETRIEVAL_ANCHORS = {
    "order", "orders", "订单", "callback", "webhook", "回调", "delivery", "投递",
    "receiver", "接收", "queue", "队列", "retry", "重试", "event", "事件",
    "ack", "acknowledgement", "processed", "处理",
}


def load_knowledge(*, contract_version: int | None = None):
    # A trusted local smoke may select an isolated asset copy; never a tool argument.
    directory = DIRECTORY
    override = os.environ.get("OPSPILOT_S3_KNOWLEDGE_DIRECTORY")
    if override:
        from pathlib import Path
        directory = Path(override).resolve()
        if not directory.is_relative_to((ROOT / ".runtime").resolve()):
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
            supported_versions = doc.get("contract_versions", [1])
            if (not isinstance(supported_versions, list)
                or any(type(value) is not int or value < 1 for value in supported_versions)
                or (contract_version is not None and contract_version not in supported_versions)):
                continue
            result.append({**doc, "content": body.decode("utf-8")[:2400], "applicable":"true"})
        except (OSError, ValueError, KeyError, TypeError):
            continue
    return result


def _tokens(text: str) -> list[str]:
    tokens: list[str] = []
    for value in re.findall(r"[a-z0-9]+|[\u4e00-\u9fff]+", text.lower()):
        if value[0].isascii():
            tokens.append(value)
        else:
            tokens.extend(value)
            tokens.extend(value[index:index + 2] for index in range(len(value) - 1))
    return tokens


def _lexical_score(query: str, text: str) -> tuple[float, list[str]]:
    terms = set(_tokens(query))
    document = text.lower()
    matched = sorted(term for term in terms if term in document)
    return float(len(matched)), matched


def _bm25_lite_score(query: str, text: str, *, average_length: float) -> tuple[float, list[str]]:
    query_terms = _tokens(query)
    document_terms = _tokens(text)
    if not query_terms or not document_terms:
        return 0.0, []
    frequencies: dict[str, int] = {}
    for term in document_terms:
        frequencies[term] = frequencies.get(term, 0) + 1
    unique_query = sorted(set(query_terms))
    matched = [term for term in unique_query if frequencies.get(term, 0)]
    length = len(document_terms)
    k1, b = 1.2, 0.75
    score = sum(
        (frequency * (k1 + 1)) / (frequency + k1 * (1 - b + b * length / max(average_length, 1.0)))
        for term in query_terms
        if (frequency := frequencies.get(term, 0))
    )
    return score, matched


def search_knowledge(
    query: str, *, limit: int = 1, contract_version: int | None = None, method: str = "bm25-lite-v1",
):
    if not query.strip() or len(query) > 300 or isinstance(limit, bool) or not 1 <= limit <= 8:
        raise ValueError("Knowledge query must be bounded; at most eight ranked documents are available")
    if method not in {"lexical-v1", "bm25-lite-v1"}:
        raise ValueError("Unsupported local Knowledge ranking method")
    documents = load_knowledge(contract_version=contract_version)
    rows = []
    average_length = (
        sum(len(_tokens(f"{d['title']} {' '.join(d['keywords'])} {d['content']}")) for d in documents)
        / max(len(documents), 1)
    )
    for doc in documents:
        text = f"{doc['title']} {' '.join(doc['keywords'])} {doc['content']}"
        if method == "lexical-v1":
            score, matched = _lexical_score(query, text)
        else:
            score, matched = _bm25_lite_score(query, text, average_length=average_length)
        # Generic words such as "version" must not turn an unrelated API/Auth
        # query into callback Knowledge. Require an S3 subject anchor in both
        # the user's query and the candidate's actual matched terms.
        if score > 0 and any(term in _S3_RETRIEVAL_ANCHORS for term in _tokens(query)) \
                and any(term in _S3_RETRIEVAL_ANCHORS for term in matched):
            rows.append((score, doc, matched))
    rows.sort(key=lambda item: (-item[0], item[1]["document_id"]))
    return [{**doc, "retrieval_score": score, "retrieval_method": method,
             "matched_terms": matched, "query": query,
             "bound_contract_version": contract_version} for score, doc, matched in rows[:limit]]


def skill_catalog():
    return [{"name":"order-lifecycle-triage","description":"Use when order lifecycle is not yet established or HTTP 200 may be confused with completion; verify order first."},
            {"name":"callback-delivery-triage","description":"Use after a completed order: correlate delivery event, retry/failure details, acknowledgement and receiver queue; never resend."}]


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


def refresh_asset_refs(draft, *, contract_version: int | None = None):
    """Checkpoint contains references only. Reload current text before every call."""
    knowledge, skill, excluded = [], None, []
    current_docs = {doc["document_id"]:doc for doc in load_knowledge(contract_version=contract_version)}
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
