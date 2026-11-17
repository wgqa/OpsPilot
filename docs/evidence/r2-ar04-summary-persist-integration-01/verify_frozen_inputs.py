"""Read-only integrity check for the R2-AR04 offline integration evidence.

This verifier does not load credentials, contact a Provider, create grants, or
authorize live execution. It checks the accepted source version and frozen
evidence hashes only.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[3]
MANIFEST = Path(__file__).with_name("FROZEN_INPUTS.json")


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True, encoding="utf-8").strip()


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    if manifest.get("purpose") != "OFFLINE_VERSION_BINDING_ONLY_NOT_A_LIVE_AUTHORIZATION":
        raise SystemExit("MANIFEST_PURPOSE_INVALID")
    head = git("rev-parse", "HEAD")
    branch = git("branch", "--show-current")
    if branch != manifest["required_branch"]:
        raise SystemExit(f"BRANCH_MISMATCH expected={manifest['required_branch']} actual={branch}")
    ancestor = subprocess.run(
        ["git", "merge-base", "--is-ancestor", manifest["source_base_sha"], "HEAD"],
        cwd=ROOT, check=False,
    )
    if ancestor.returncode != 0:
        raise SystemExit("SOURCE_BASE_NOT_ANCESTOR")
    for path, expected in manifest["required_git_blobs"].items():
        head_blob = git("rev-parse", f"HEAD:{path}")
        index_blob = git("rev-parse", f":{path}")
        worktree_blob = git("hash-object", path)
        if head_blob != expected or index_blob != expected or worktree_blob != expected:
            raise SystemExit(
                f"GIT_BLOB_MISMATCH path={path} expected={expected} "
                f"head={head_blob} index={index_blob} worktree={worktree_blob}"
            )
        print(f"GIT_BLOB_OK {path} {expected}")
    for relative, expected in manifest["required_file_sha256"].items():
        path = ROOT / relative
        if not path.is_file():
            raise SystemExit(f"FROZEN_FILE_MISSING path={relative}")
        actual = sha256(path)
        if actual != expected:
            raise SystemExit(f"FILE_SHA256_MISMATCH path={relative} expected={expected} actual={actual}")
        print(f"FILE_SHA256_OK {relative} {actual}")
    print(f"HEAD_OK {head}")
    print(f"BRANCH_OK {branch}")
    print("LIVE_AUTHORIZATION=NONE_PROVIDER_REQUESTS=0")
    return 0


if __name__ == "__main__":
    sys.exit(main())
