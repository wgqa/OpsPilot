"""Shared model text normalization; no investigation routing or runtime."""
from __future__ import annotations
import os
import re
from opspilot.config import MODEL_API_KEY

def content_text(content: object) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        chunks: list[str] = []
        for item in content:
            if isinstance(item, dict) and isinstance(item.get("text"), str):
                chunks.append(str(item["text"]))
            elif isinstance(item, str):
                chunks.append(item)
        return "\n".join(chunks)
    return str(content) if content is not None else ""


def redact_text(value: str, *, limit: int = 2000) -> str:
    for secret_name in (MODEL_API_KEY,):
        secret = os.environ.get(secret_name, "")
        if secret:
            value = value.replace(secret, "[REDACTED]")
    return re.sub(r"(?i)(bearer\s+)[^\s'\",}]+|sk-[A-Za-z0-9_-]{8,}", "[REDACTED]", value)[:limit]
