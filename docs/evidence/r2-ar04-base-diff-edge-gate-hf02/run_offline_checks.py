"""Run this audit against isolated checkouts with the locked local Python."""

import argparse
import hashlib
from importlib import metadata
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[3]
BASE = "1cba32753f22e0a610aa7654ab5dc6cddd94ccf2"
HEAD = "ecbd7d3ebfebc3cb4ea1f75cbf4cfae6e7786011"
F01 = (
    "tests/test_ar04c_f01_context_currentness.py"
    "::test_zero_tool_followup_can_explain_valid_historical_snapshot"
)
EDGE = "tests/test_ar04_summary_fact_retention_edges_hf_02.py"
LOCK = "requirements.lock.txt"
TOKEN_CACHE_KEY = "9b5ad71b2ce5302211f9c61530b329a4922fc6a4"
TOKEN_CACHE_SHA256 = "223921b76ee99bde995b7ff738513eef100fb51d18c93597a113bcffe865b2a7"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run_checks(mode, log):
    def record(line):
        print(line, flush=True)
        print(line, file=log, flush=True)

    def run(args, cwd, env):
        record(f"cwd: {cwd}\ncommand: {subprocess.list2cmdline(args)}")
        completed = subprocess.run(args, cwd=cwd, env=env, stdout=subprocess.PIPE,
                                   stderr=subprocess.STDOUT, encoding="utf-8", errors="replace")
        if completed.stdout:
            record(completed.stdout.rstrip("\n"))
        record(f"exit: {completed.returncode}\n")
        return completed.returncode

    def checkout(revision, destination):
        destination.mkdir()
        # A separate index applies Git's checkout filters and leaves the current
        # worktree and its index untouched.
        git_env = {**os.environ, "GIT_INDEX_FILE": str(destination.with_suffix(".index"))}
        for args in (["read-tree", revision], ["checkout-index", "--all", f"--prefix={destination.as_posix()}/"]):
            if run(["git", *args], ROOT, git_env):
                raise RuntimeError(f"Checkout failed for {revision}")
        if (destination / ".env").exists() or digest(destination / LOCK) != digest(ROOT / LOCK):
            raise RuntimeError("Unexpected checkout configuration")

    locked = dict(line.split("==", 1) for line in (ROOT / LOCK).read_text().splitlines() if "==" in line)
    mismatched = [name for name, version in locked.items() if metadata.version(name) != version]
    if mismatched:
        raise RuntimeError(f"Installed packages differ from lock: {mismatched}")
    cache_dir = Path(os.environ.get("TIKTOKEN_CACHE_DIR") or os.environ.get("DATA_GYM_CACHE_DIR")
                     or Path(tempfile.gettempdir()) / "data-gym-cache")
    cached_encoding = cache_dir / TOKEN_CACHE_KEY
    if not cached_encoding.is_file() or digest(cached_encoding) != TOKEN_CACHE_SHA256:
        raise RuntimeError("The verified cl100k_base encoding must be available in the local cache")

    scratch = Path(tempfile.mkdtemp(prefix="opspilot-hf02-"))
    guard = scratch / "offline"
    guard.mkdir()
    (guard / "sitecustomize.py").write_text(
        """import ipaddress
import sys

def check_socket(event, args):
    if event not in ('socket.connect', 'socket.getaddrinfo'):
        return
    host = args[1][0] if event == 'socket.connect' else args[0]
    if host in (None, 'localhost'):
        return
    try:
        if ipaddress.ip_address(host).is_loopback:
            return
    except ValueError:
        pass
    raise OSError('HF02: non-loopback sockets are disabled')

sys.addaudithook(check_socket)
""", encoding="utf-8",
    )
    env = {key: os.environ[key] for key in ("PATH", "SystemRoot", "WINDIR", "COMSPEC", "PATHEXT")
           if key in os.environ}
    env.update(PYTHONPATH=str(guard), PYTHONNOUSERSITE="1", PYTHONUTF8="1", PYTHONHASHSEED="0",
               PYTHONDONTWRITEBYTECODE="1", PYTEST_DISABLE_PLUGIN_AUTOLOAD="1",
               TIKTOKEN_CACHE_DIR=str(cache_dir.resolve()), TEMP=str(scratch), TMP=str(scratch))
    record(f"mode: {mode}\npython: {sys.executable}\nversion: {sys.version}\nSQLite: {sqlite3.sqlite_version}")
    record(f"lock: {len(locked)} matches; sha256={digest(ROOT / LOCK)}")
    record(f"cl100k_base cache sha256: {TOKEN_CACHE_SHA256}\nscratch: {scratch}")
    record("Fresh process and basetemp per pytest invocation. No inherited OpsPilot or Provider config.")
    guard_probe = (
        "import sys; "
        "assert 'sitecustomize' in sys.modules; "
        "sys.audit('socket.connect', None, ('127.0.0.1', 0));\n"
        "try:\n sys.audit('socket.connect', None, ('192.0.2.1', 0))\n"
        "except OSError as error:\n print(error)\n"
        "else:\n raise AssertionError('offline socket guard missing')"
    )
    if run([sys.executable, "-B", "-c", guard_probe], scratch, env):
        raise RuntimeError("Offline guard preflight failed")

    if mode in {"f01", "edge-compare"}:
        snapshots = {"head": scratch / "head", "base": scratch / "base"}
        checkout(HEAD, snapshots["head"])
        checkout(BASE, snapshots["base"])
    else:
        # The frozen artifact hash test checks raw bytes, including the
        # original line endings in the existing task worktree.
        if (ROOT / ".env").exists():
            raise RuntimeError("Run regression in the isolated task worktree without a local .env")
        snapshots = {"head": ROOT}
    if mode == "f01":
        groups = [(label, "f01", [F01]) for label in ("base", "head", "head", "base")]
    elif mode == "edge-compare":
        for destination in snapshots.values():
            shutil.copyfile(ROOT / EDGE, destination / EDGE)
        groups = [(label, "tail", [EDGE, "-rP", "-k", "tail_facts_with_headroom"]) for label in ("base", "head")]
    else:
        for relative in (EDGE, "opspilot/domain/chat.py"):
            record(f"candidate source: {relative} sha256={digest(ROOT / relative)}")
        groups = [
            ("head", "edge", [EDGE, "-rP"]),
            ("head", "retention", ["tests/test_ar04_summary_fact_retention_hf_01.py"]),
            ("head", "related", [
                "tests/test_m302_context.py", "tests/test_ar04a_context_journey_01.py",
                "tests/test_ar04c_f01_context_currentness.py", "tests/test_product_01_runtime_grant_01.py",
                "tests/test_product_01_runtime_grant_01_hf01.py", "tests/test_m1_chat.py",
                "tests/test_ar02_assistant.py",
            ]),
            ("head", "gates", [
                "tests/test_r2_ar04_compaction_c06_hf_01.py",
                "tests/test_ar04b_memory_journey_01.py::test_ar04b_revocation_before_provider_boundary_blocks_stale_memory_and_keeps_valid_path",
            ]),
        ]

    statuses = {}
    for index, (snapshot, group, tests) in enumerate(groups, start=1):
        label = f"{index}-{snapshot}-{group}"
        record(f"group: {label}")
        statuses[label] = run([
            sys.executable, "-B", "-m", "pytest", "-vv", "-p", "no:cacheprovider",
            "--tb=short", "--color=no", f"--basetemp={scratch / label}", *tests,
        ], snapshots[snapshot], env)
    record(f"pytest exit codes: {statuses}")
    return int(any(statuses.values()))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("f01", "edge-compare", "regression"))
    parser.add_argument("log", type=Path)
    args = parser.parse_args()
    with args.log.open("x", encoding="utf-8", newline="\n") as log_file:
        sys.exit(run_checks(args.mode, log_file))
