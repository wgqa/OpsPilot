"""Record this slice's offline pytest command, untouched bytes and exit status."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[5]
OUT = Path(__file__).resolve().parent / "runs" / sys.argv[1]
if OUT.exists():
    raise SystemExit("Use a new run label; existing evidence is never overwritten.")
OUT.mkdir(parents=True)
env = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8",
           OPSPILOT_MODEL_API_KEY="deterministic-no-paid-provider",
           OPSPILOT_MODEL_NAME="deterministic-no-paid-provider",
           OPSPILOT_MODEL_BASE_URL="http://127.0.0.1:9/v1",
           OPSPILOT_CONTUX_TRACE_PATH=str(OUT / "TRACE.jsonl"))
command = [sys.executable, "-m", "pytest", "-q", "-s", *sys.argv[2:],
           "--basetemp", str(OUT / "basetemp"), "-p", "no:cacheprovider",
           "--junitxml", str(OUT / "junit.xml")]
head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
changed = subprocess.check_output(["git", "diff", "--name-only"], cwd=ROOT, text=True, encoding="utf8").splitlines()
hashes = {name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in changed if (ROOT/name).is_file()}
legacy_paths = ["docs/evidence/vnext/m4-autonomy-c1/runs/rev1/behavior-red-trace.jsonl",
                "docs/evidence/vnext/m4-autonomy-c1/TRACE.jsonl"]
legacy_before = {name:(ROOT/name).read_bytes() for name in legacy_paths}
started = time.monotonic()
with (OUT / "pytest.log").open("wb") as log:
    result = subprocess.run(command, cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT)
preserved = []
for name, before in legacy_before.items():
    path = ROOT/name
    after = path.read_bytes()
    if after == before:
        continue
    normalized = lambda value:value.replace(b"\r\n",b"\n")
    archive = OUT / (path.stem + "-actual-test-output.jsonl")
    archive.write_bytes(after)
    if not normalized(after).startswith(normalized(before)):
        raise RuntimeError(f"Non-append change to frozen evidence; archived but not restored: {name}")
    appended = OUT / (path.stem + "-appended-rows.jsonl")
    appended.write_bytes(normalized(after)[len(normalized(before)):])
    path.write_bytes(before)
    preserved.append({"source":name,"before_sha256":hashlib.sha256(before).hexdigest(),
                      "observed_raw_sha256":hashlib.sha256(after).hexdigest(),
                      "raw_archive":archive.name,"appended_rows":appended.name,"restored_original_bytes":True})
record = {"command":command,"cwd":str(ROOT),"head_at_start":head,"working_file_sha256":hashes,
          "exit_code":result.returncode,"elapsed_seconds":round(time.monotonic()-started,3),
          "legacy_evidence_preserved":preserved,
          "provider_mode":"deterministic doubles; dummy credentials and non-provider loopback endpoint; no paid experiments"}
(OUT / "COMMAND.json").write_text(json.dumps(record,ensure_ascii=False,indent=2)+"\n",encoding="utf8")
print(json.dumps({"run":OUT.name,"head_at_start":head,"exit_code":result.returncode,
                  "elapsed_seconds":record["elapsed_seconds"],"command_record":str(OUT/"COMMAND.json")},ensure_ascii=False))
print((OUT / "pytest.log").read_text(encoding="utf8")[-4000:] if result.returncode else (OUT / "pytest.log").read_text(encoding="utf8")[-500:])
raise SystemExit(result.returncode)
