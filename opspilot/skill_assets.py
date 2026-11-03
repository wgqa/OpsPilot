from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from opspilot.config import ROOT


SKILL_DIRECTORY = ROOT / "skills" / "auth-incident-triage"
SKILL_NAME = "auth-incident-triage"
SCOPE_SKILL_DIRECTORY = ROOT / "skills" / "auth-scope-triage"
SCOPE_SKILL_NAME = "auth-scope-triage"
SCOPE_PROBLEM_TYPE = "auth_403_scope"
PROTOCOL_UPGRADE_SKILL_DIRECTORY = ROOT / "skills" / "protocol-upgrade-impact-analysis"
PROTOCOL_UPGRADE_SKILL_NAME = "protocol-upgrade-impact-analysis"
PROTOCOL_UPGRADE_PROBLEM_TYPE = "protocol_upgrade_impact"
SEMVER = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")


class SkillIntegrityError(RuntimeError):
    pass


def load_applicable_skill(problem_type: str | None) -> dict[str, str] | None:
    """Read the small manifest first; open the Skill body only for a matching issue."""
    if problem_type is None:
        return None
    if problem_type == SCOPE_PROBLEM_TYPE:
        directory, expected_name, title = SCOPE_SKILL_DIRECTORY, SCOPE_SKILL_NAME, "auth scope triage"
    elif problem_type == PROTOCOL_UPGRADE_PROBLEM_TYPE:
        directory, expected_name, title = (
            PROTOCOL_UPGRADE_SKILL_DIRECTORY, PROTOCOL_UPGRADE_SKILL_NAME,
            "protocol upgrade impact analysis",
        )
    else:
        directory, expected_name, title = SKILL_DIRECTORY, SKILL_NAME, "auth incident"
    manifest_path = directory / "manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise SkillIntegrityError(f"The {title} Skill manifest is unavailable or invalid.") from error
    if not isinstance(manifest, dict) or manifest.get("name") != expected_name:
        raise SkillIntegrityError(f"The {title} Skill manifest name is invalid.")
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
    skill_path = (directory / "SKILL.md").resolve()
    if skill_path.parent != directory.resolve():
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
        "name": expected_name,
        "version": version,
        "digest": actual,
        "description": str(manifest.get("description", ""))[:240],
        "content": content[:4000],
    }


def skill_asset_is_current(problem_type: str, supplied: dict[str, str]) -> bool:
    """Recheck that persisted method guidance still matches its bundled asset."""
    if not isinstance(supplied, dict):
        return False
    try:
        current = load_applicable_skill(problem_type)
    except SkillIntegrityError:
        return False
    return current is not None and all(
        supplied.get(key) == current.get(key)
        for key in ("name", "version", "digest", "description", "content")
    )
