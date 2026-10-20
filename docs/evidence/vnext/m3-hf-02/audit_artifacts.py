"""Local artifact safety/integrity checks; never prints credential values."""
from __future__ import annotations
import hashlib
import json
import re
import subprocess
from pathlib import Path

ROOT = Path.cwd()
BASE = Path(__file__).resolve().parent
LEARNING = ROOT / "docs/learning/M3-REVIEW"
artifacts = sorted(p for base in (BASE, LEARNING) for p in base.rglob("*") if p.is_file()
                   and "__pycache__" not in p.parts and p.name not in {"AUDIT.json", "EVIDENCE_INDEX.json"})
password_path = ROOT / ".runtime/m3-hf-02/journey-01/test-passwords.json"
secret_values = list(json.loads(password_path.read_text(encoding="utf-8")).values())
for name in (".env", ".env.local"):
    path = ROOT / name
    if path.exists():
        for line in path.read_text(encoding="utf-8-sig").splitlines():
            key, sep, value = line.partition("=")
            if sep and re.search(r"(?:API_KEY|TOKEN|SECRET|PASSWORD)", key, re.I):
                raw = value.strip().strip("\"'")
                if len(raw) >= 8:
                    secret_values.append(raw)
matches = []
text_errors = []
json_errors = []
for p in artifacts + [ROOT / "opspilot/domain/chat.py", ROOT / "tests/test_m3_hf02_lineage.py"]:
    data = p.read_bytes()
    if any(value.encode("utf-8") in data for value in secret_values):
        matches.append(p.relative_to(ROOT).as_posix())
    if p.suffix.lower() in {".md", ".py", ".json", ".jsonl", ".log", ".txt"}:
        try:
            content = data.decode("utf-8-sig")
        except UnicodeDecodeError:
            text_errors.append(p.relative_to(ROOT).as_posix())
            continue
        try:
            if p.suffix == ".json":
                json.loads(content)
            if p.suffix == ".jsonl":
                for line in content.splitlines():
                    if line.strip():
                        json.loads(line)
        except ValueError:
            json_errors.append(p.relative_to(ROOT).as_posix())
        if p.suffix == ".py":
            compile(content, str(p), "exec")

diff_paths = subprocess.check_output(["git", "diff", "c2f71e9", "--name-only", "--", "opspilot", "tests"], text=True).splitlines()
assert sorted(diff_paths) == ["opspilot/domain/chat.py", "tests/test_m3_hf02_lineage.py"]
source_whitespace = subprocess.run(["git", "diff", "--check", "c2f71e9", "--", "opspilot", "tests"], capture_output=True, text=True)
assert source_whitespace.returncode == 0, source_whitespace.stdout
protected = ["AGENTS.md", "PROJECT_NORTH_STAR.md", "开发目录/"]
staged = subprocess.check_output(["git", "diff", "--cached", "--name-only"], text=True).splitlines()
assert not any(path == protected[0] or path == protected[1] or path.startswith(protected[2]) for path in staged)
for old in ("docs/evidence/vnext/m3-closeout-01", "docs/evidence/d6"):
    assert not subprocess.check_output(["git", "diff", "c2f71e9", "--name-only", "--", old], text=True).strip()
assert not matches, "Known secret value found; paths only: " + repr(matches)
assert not text_errors and not json_errors, "Artifact encoding/JSON error: " + repr(text_errors + json_errors)
assert len(list(LEARNING.glob("*.md"))) == 5
interview = (LEARNING / "INTERVIEW_QA.md").read_text(encoding="utf-8")
assert len(re.findall(r"^### \d+\.", interview, re.M)) == 20
lock_paths = [p for p in (ROOT / "uv.lock", ROOT / "pyproject.toml", ROOT / "frontend/package-lock.json", ROOT / "frontend/package.json") if p.exists()]
def portable_bytes(path):
    raw = path.read_bytes()
    return raw.replace(b"\r\n", b"\n") if path.suffix.lower() in {".md", ".py", ".json", ".jsonl", ".log", ".txt", ".exit-code"} else raw


index = {"self_hash_excluded": True,
         "sha256_scope": "Portable Git text bytes (CRLF normalized to LF); PNG bytes unchanged. Original worktree hash retained separately. No content redaction or failure rewriting.",
         "files": [{"path": p.relative_to(ROOT).as_posix(), "bytes": len(portable_bytes(p)),
                    "sha256": hashlib.sha256(portable_bytes(p)).hexdigest(),
                    "worktree_original_sha256": hashlib.sha256(p.read_bytes()).hexdigest()} for p in artifacts]}
(BASE / "EVIDENCE_INDEX.json").write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")
audit = {"known_secret_values_scanned_without_export": len(secret_values), "matched_files": matches,
         "utf8_errors": text_errors, "json_errors": json_errors, "production_and_test_diff": diff_paths,
         "protected_user_files_staged": False, "old_reports_modified": False, "learning_files": 5, "interview_qa": 20,
         "source_and_test_whitespace_check_exit_code": source_whitespace.returncode,
         "raw_log_whitespace_preserved": "Original RED pytest logs contain indented blank traceback lines; not rewritten for git diff --check.",
         "dependency_files": [{"path": p.relative_to(ROOT).as_posix(), "sha256": hashlib.sha256(p.read_bytes()).hexdigest()} for p in lock_paths],
         "no_full_raw_prompt_claim_scope": "Observer and export whitelist reviewed; digest/roles/limited fragments only. Complete request bytes never exported.",
         "artifact_count_without_self_generated_index": len(artifacts)}
(BASE / "AUDIT.json").write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps({"artifacts": len(artifacts), "known_secret_matches": len(matches), "json_errors": len(json_errors), "production_files": diff_paths}, ensure_ascii=False))
