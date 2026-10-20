# HF-01 Start Manifest

- Expected baseline: `22823acc519789c14e2cefe8e0f4c16a05fb4b72`
- Actual starting HEAD: `22823acc519789c14e2cefe8e0f4c16a05fb4b72`
- Branch: `main`
- `origin/main`: `22823acc519789c14e2cefe8e0f4c16a05fb4b72`
- Working tree: pre-existing local modifications/untracked artifacts recorded in `runs/freeze-check-01/initial-status.txt`; preserved.
- Python: 3.14.0 (`.venv`)
- Node: v24.16.0; npm 11.13.0
- Runtime lock files: `requirements.lock.txt`, `frontend/package-lock.json`; hashes recorded in `FROZEN_SHA256SUMS.txt`.
- Model ID: `deepseek-flash`; base host: `https://api.deepseek.com`; API key presence checked without recording its value.
- Investigator MCP: child stdio server `python -m opspilot.mcp_server --db <isolated-db> --binding-id <task_id>`; read-only and task-bound. No secret/credential is recorded here.
- Scope: evidence under `docs/evidence/vnext/m3-01-hf-01/`; code/tests only if a deterministic RED proves a frozen safety breach.
- Existing user files and untracked directories were not staged or modified.
