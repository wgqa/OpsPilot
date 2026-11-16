"""Record non-secret endpoint shape and presence flags; never inspect key values."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from urllib.parse import urlsplit

_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from opspilot.config import ROOT, load_local_environment


def main() -> int:
    env_path = ROOT.parent.parent / ".env"
    if not env_path.is_file():
        raise RuntimeError("MAIN_REPO_ENV_NOT_FOUND")
    load_local_environment(env_path)
    raw_endpoint = os.environ.get("OPSPILOT_MODEL_BASE_URL", "")
    parsed = urlsplit(raw_endpoint)
    result = {
        "evidence_level": "LOCAL_ENV_PRESENCE_AND_URL_SHAPE_ONLY",
        "main_repo_env_found": True,
        "main_repo_env_loaded": True,
        "api_key_present": bool(os.environ.get("OPSPILOT_MODEL_API_KEY", "").strip()),
        "model_name_present": bool(os.environ.get("OPSPILOT_MODEL_NAME", "").strip()),
        "endpoint_shape": {
            "scheme": parsed.scheme,
            "host": parsed.hostname,
            "port": parsed.port,
            "path": parsed.path,
            "query_present": bool(parsed.query),
            "fragment_present": bool(parsed.fragment),
        },
        "provider_requests_sent": 0,
        "provider_cost_usd": "0.00",
    }
    out = Path(__file__).with_name("CONFIGURATION_SHAPE.json")
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
