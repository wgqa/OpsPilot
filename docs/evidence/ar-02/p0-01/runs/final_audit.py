"""Offline artifact audit; does not construct a model or call business services."""
from pathlib import Path
import hashlib
import json
import os
import re
import subprocess

root = Path(__file__).resolve().parents[1]
repo = root.parents[3]
excluded_logs = {"closeout-export.log", "final-audit.log"}
files = sorted(
    f for f in (root / "runs").rglob("*")
    if f.is_file() and f.name not in excluded_logs
)
index = {
    "kind": "INDEX_OF_ACTUAL_RUN_ARTIFACTS_NOT_SYNTHETIC_CALLS",
    "files": [
        {
            "path": f.relative_to(root).as_posix(),
            "sha256_lf": hashlib.sha256(
                f.read_bytes().replace(b"\r\n", b"\n")
            ).hexdigest(),
        }
        for f in files
    ],
}
(root / "TRACE_INDEX.json").write_text(
    json.dumps(index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
)
key_pattern = re.compile(rb"(?<![A-Za-z0-9_-])sk-[A-Za-z0-9_-]{16,}")
environment_values = [
    v.encode() for k, v in os.environ.items()
    if ("API_KEY" in k or k.endswith("_TOKEN")) and len(v) > 15
]
records = 0
for f in root.rglob("*"):
    if not f.is_file():
        continue
    data = f.read_bytes()
    assert not key_pattern.search(data), f"Possible key pattern: {f.name}"
    assert not any(v in data for v in environment_values), f"Environment secret: {f.name}"
    if f.suffix == ".json":
        json.loads(data.decode("utf-8-sig"))
        records += 1
    if f.suffix == ".jsonl":
        for line in data.decode("utf-8-sig").splitlines():
            if line.strip():
                json.loads(line)
                records += 1
historical = "docs/evidence/vnext/m4-autonomy-c1/runs/rev1/behavior-red-trace.jsonl"
assert (repo / historical).read_bytes() == subprocess.check_output(
    ["git", "show", "HEAD:" + historical], cwd=repo
)
assert not subprocess.check_output(
    ["git", "diff", "HEAD", "--", "opspilot", "frontend/src", "frontend/test", "tests"],
    cwd=repo,
)
results = json.loads((root / "RESULTS.json").read_text(encoding="utf-8-sig"))
assert results["real_provider_requests"] == 0
assert results["formal_event_correction"]["driver_exit_code"] == 0
print(json.dumps({
    "index_files": len(files), "parsed_records": records,
    "secret_matches": 0, "source_unchanged_since_implementation": True,
    "historical_exact_blob_preserved": True,
    "provider_requests_from_recorded_results": 0,
    "note": "Offline consistency audit, not a re-execution of product tests",
}))
