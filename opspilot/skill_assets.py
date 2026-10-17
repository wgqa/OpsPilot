from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from opspilot.config import ROOT


SKILL_DIRECTORY = ROOT / "skills" / "auth-incident-triage"
SKILL_NAME = "auth-incident-triage"
SEMVER = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")


class SkillIntegrityError(RuntimeError):
    pass


def load_applicable_skill(problem_type: str | None) -> dict[str, str] | None:
    """Read the small manifest first; open the Skill body only for a matching issue."""
    if problem_type is None:
        return None
    manifest_path = SKILL_DIRECTORY / "manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise SkillIntegrityError("The auth incident Skill manifest is unavailable or invalid.") from error
    if not isinstance(manifest, dict) or manifest.get("name") != SKILL_NAME:
        raise SkillIntegrityError("The auth incident Skill manifest name is invalid.")
    if manifest.get("problem_type") != problem_type:
        return None
    version = manifest.get("version")
    if not isinstance(version, str) or not SEMVER.fullmatch(version):
        raise SkillIntegrityError("The auth incident Skill version is not semantic versioning.")
    if manifest.get("skill_file") != "SKILL.md" or manifest.get("digest_algorithm") != "sha256":
        raise SkillIntegrityError("The auth incident Skill manifest file contract is invalid.")
    expected = manifest.get("digest")
    if not isinstance(expected, str) or not re.fullmatch(r"[0-9a-f]{64}", expected):
        raise SkillIntegrityError("The auth incident Skill digest is invalid.")
    skill_path = (SKILL_DIRECTORY / "SKILL.md").resolve()
    if skill_path.parent != SKILL_DIRECTORY.resolve():
        raise SkillIntegrityError("The auth incident Skill path escapes its asset directory.")
    try:
        content_bytes = skill_path.read_bytes()
    except OSError as error:
        raise SkillIntegrityError("The auth incident Skill body is unavailable.") from error
    actual = hashlib.sha256(content_bytes).hexdigest()
    if actual != expected:
        raise SkillIntegrityError("The auth incident Skill body does not match its manifest digest.")
    try:
        content = content_bytes.decode("utf-8")
    except UnicodeDecodeError as error:
        raise SkillIntegrityError("The auth incident Skill body is not UTF-8.") from error
    return {
        "name": SKILL_NAME,
        "version": version,
        "digest": actual,
        "description": str(manifest.get("description", ""))[:240],
        "content": content[:4000],
    }
