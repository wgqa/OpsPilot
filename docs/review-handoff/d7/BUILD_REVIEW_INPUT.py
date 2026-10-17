"""Build the finite D7 offline review attachment from a committed snapshot.

Standard library + Git only. This is delivery packaging, not Agent runtime.
Files are complete committed blobs; no worktree newline conversion or excerpts.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import zipfile


ROOT = Path(__file__).resolve().parents[3]


def git(*args: str) -> bytes:
    return subprocess.check_output(["git", *args], cwd=ROOT)


def selected(path: str) -> bool:
    if path in {"README.md", "TASKS.md", "AGENTS.md", ".gitattributes", ".gitignore",
                ".env.example", "pyproject.toml", "requirements.in", "requirements.lock.txt"}:
        return True
    if path.startswith("opspilot/") and path.endswith(".py"):
        return True
    if path.startswith("tests/") and path.endswith(".py"):
        return True
    if path.startswith("skills/auth-incident-triage/"):
        return True
    if path.startswith("docs/baseline/"):
        return True
    if path == "docs/handoff/Luna-D7-implementation-brief.md":
        return True
    if path in {f"docs/reviews/R{i}.md" for i in range(1, 6)}:
        return True
    if path.startswith("docs/review-handoff/d7/") and (
            path.endswith(".md") or path.endswith("BUILD_REVIEW_INPUT.py")):
        return True
    if path.startswith("docs/evidence/d7/"):
        return True
    if path in {f"docs/evidence/d{i}/REPORT.md" for i in range(1, 7)}:
        return True
    if path in {"docs/evidence/d1/pytest-clean.txt", "docs/evidence/d1/mcp-smoke.txt",
                "docs/evidence/d1/tool-call-smoke.txt", "docs/evidence/d1/checkpoint-smoke.txt",
                "docs/evidence/d1/s1-smoke.txt", "docs/evidence/d3/TRACE.json",
                "docs/evidence/d4/pytest-full.txt", "docs/evidence/d6/CASES.json",
                "docs/evidence/d6/CASES.md", "docs/evidence/d6/RESULTS.json",
                "docs/evidence/d6/pytest-full.txt"}:
        return True
    if path.startswith(tuple(f"docs/evidence/d6/e{i:02d}/" for i in range(1, 4))):
        return Path(path).name in {"TRACE.json", "run.log"}
    if path.startswith("docs/evidence/d6/e10/ATTEMPT-01"):
        return True
    if path.startswith("docs/evidence/d6/e10/attempt-02/"):
        return path.endswith(("TRACE.json", "REAL-TRAJECTORIES.json", "REPORT.md", "run.log"))
    return False


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-sha", required=True)
    args = parser.parse_args()
    sha = git("rev-parse", args.source_sha + "^{commit}").decode().strip()
    paths = sorted(git("ls-tree", "-r", "--name-only", sha).decode("utf-8").splitlines())
    chosen = [p for p in paths if selected(p)]
    destination = ROOT / "docs/review-handoff/d7/REVIEW_INPUT"
    destination.mkdir(parents=True, exist_ok=True)
    archive = destination / "opspilot-d7-review.zip"
    if archive.exists():
        raise SystemExit("Refusing to overwrite an existing review package")
    entries = []
    content = {}
    for path in chosen:
        if Path(path).name == ".env" or Path(path).suffix in {".sqlite3", ".db", ".sqlite"}:
            raise SystemExit("Forbidden runtime/secrets path")
        data = git("show", sha + ":" + path)
        content[path] = data
        entries.append({"path": path, "source_sha": sha, "source_path": path,
                        "excerpt": False, "representation": "complete committed blob",
                        "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)})
    frozen_sha = "151a1cea2ea23fa7413abbbd89d5ed6fd173da9c"
    frozen_source = "docs/evidence/d6/CASES.json"
    frozen_path = "HISTORICAL_INPUT/CASES-frozen-151a1ce.json"
    frozen_data = git("show", frozen_sha + ":" + frozen_source)
    content[frozen_path] = frozen_data
    entries.append({"path": frozen_path, "source_sha": frozen_sha, "source_path": frozen_source,
                    "excerpt": False, "representation": "complete historical committed blob",
                    "sha256": hashlib.sha256(frozen_data).hexdigest(), "bytes": len(frozen_data)})
    manifest = {
        "schema_version": "opspilot-d7-offline-review-v1", "source_snapshot_sha": sha,
        "implementation_sha": "a2517fdbe2b66e4490867cc388aadc32ec5b5197",
        "files": entries, "excerpt_count": 0,
        "runtime_python_complete": True, "tests_complete": True,
        "scope": "Complete runtime Python, tests and Skill; selected contracts/docs/evidence, not a Git mirror",
        "excluded": [".env / real API keys", ".runtime / SQLite DBs", ".git and full history",
                     "wheels and external model service", "unselected historical logs and planning documents",
                     "outer REVIEW_INPUT archive/PACKAGE.json to avoid recursive self-reference"],
        "manifest_note": "MANIFEST.json is generated metadata; it is not a source excerpt and excludes its own hash",
        "d6_history": "9 PASS + E10 PARTIAL; 4/5 real smoke; 64/64 pytest; 40 model / 33 MCP / 102725 tokens",
        "review_status": "NOT_STARTED",
    }
    with zipfile.ZipFile(archive, "x", compression=zipfile.ZIP_DEFLATED) as z:
        for path, data in content.items():
            z.writestr(path, data)
        z.writestr("MANIFEST.json", json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8") + b"\n")
    with zipfile.ZipFile(archive) as z:
        assert z.testzip() is None
        assert all(hashlib.sha256(z.read(e["path"])).hexdigest() == e["sha256"] for e in entries)
    package = {"source_snapshot_sha": sha, "implementation_sha": manifest["implementation_sha"],
               "archive": archive.name, "archive_sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
               "file_count": len(entries), "archive_bytes": archive.stat().st_size,
               "uncompressed_bytes": sum(e["bytes"] for e in entries),
               "runtime_python_files": sum(p.startswith("opspilot/") and p.endswith(".py") for p in chosen),
               "test_python_files": sum(p.startswith("tests/") and p.endswith(".py") for p in chosen),
               "all_member_hashes_verified": True, "third_party_review": "NOT_STARTED"}
    (destination / "PACKAGE.json").write_text(json.dumps(package, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(package, ensure_ascii=False))


if __name__ == "__main__":
    main()
